from datetime import date
from typing import Dict, Any, List, Optional, Tuple
from app.core.config import settings
from app.services.rules_engine import DocumentRulesEngine

# Heuristic used to discount face-match confidence when the document photo
# was very likely taken long enough ago (or the holder was a minor when it
# was taken) that ordinary facial aging -- not tampering or a genuine
# mismatch -- could plausibly account for a lower similarity score. The MRZ
# only carries DOB and expiry (no issue date), so the document's issue date
# is ESTIMATED from expiry minus the standard ICAO validity period for the
# holder's age bracket. This is a transparent business rule, not a measured
# calibration -- there is no ground-truth cross-age dataset behind these
# thresholds yet (see scripts/finetune_face_embedder.py for that effort in
# progress). Revisit these numbers once real accuracy data exists.
ADULT_PASSPORT_VALIDITY_YEARS = 10
MINOR_PASSPORT_VALIDITY_YEARS = 5
MINOR_AGE_CUTOFF_YEARS = 18

# Children's faces change disproportionately faster per year than adults'
# (well-established in cross-age face-recognition research, e.g. the FG-NET
# dataset this project is fine-tuning against) -- so a photo taken while the
# holder was a minor is weighted as if the elapsed time were longer.
MINOR_AT_ISSUE_GAP_MULTIPLIER = 1.6

AGE_GAP_MODERATE_YEARS = 4.0
AGE_GAP_HIGH_YEARS = 8.0
FACE_WEIGHT_DISCOUNT_MODERATE = 0.75  # 25% weight reduction
FACE_WEIGHT_DISCOUNT_HIGH = 0.50      # 50% weight reduction


def _years_between(earlier: date, later: date) -> float:
    return (later - earlier).days / 365.25


def estimate_face_age_gap(mrz_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Estimates how long ago the document's photo was likely captured, using
    only MRZ DOB + expiry (no issue date is machine-readable). Returns None
    when there isn't enough valid MRZ date data to estimate anything --
    callers must not penalize face-match confidence on missing/unparseable
    dates, only on a genuine, computed large gap.
    """
    if not mrz_data:
        return None
    dob_date = DocumentRulesEngine.parse_yymmdd(mrz_data.get("birth_date", ""))
    expiry_date = DocumentRulesEngine.parse_yymmdd(mrz_data.get("expiry_date", ""))
    if not dob_date or not expiry_date:
        return None

    age_at_expiry_years = _years_between(dob_date, expiry_date)
    validity_years = (
        MINOR_PASSPORT_VALIDITY_YEARS if age_at_expiry_years < MINOR_AGE_CUTOFF_YEARS
        else ADULT_PASSPORT_VALIDITY_YEARS
    )
    try:
        estimated_issue_date = expiry_date.replace(year=expiry_date.year - validity_years)
    except ValueError:
        # Feb 29 on a non-leap estimated issue year.
        estimated_issue_date = expiry_date.replace(year=expiry_date.year - validity_years, day=28)

    photo_age_years = max(0.0, _years_between(estimated_issue_date, date.today()))
    age_at_issue_years = _years_between(dob_date, estimated_issue_date)
    was_minor_at_issue = age_at_issue_years < MINOR_AGE_CUTOFF_YEARS

    effective_gap_years = photo_age_years * (
        MINOR_AT_ISSUE_GAP_MULTIPLIER if was_minor_at_issue else 1.0
    )

    return {
        "photo_age_years": round(photo_age_years, 1),
        "effective_gap_years": round(effective_gap_years, 1),
        "was_minor_at_issue": was_minor_at_issue,
        "estimated_issue_date": estimated_issue_date,
    }


def face_weight_discount_for_gap(effective_gap_years: float) -> Tuple[float, Optional[str]]:
    """Returns (multiplier, tier_label). tier_label is None when no discount applies."""
    if effective_gap_years >= AGE_GAP_HIGH_YEARS:
        return FACE_WEIGHT_DISCOUNT_HIGH, "HIGH"
    if effective_gap_years >= AGE_GAP_MODERATE_YEARS:
        return FACE_WEIGHT_DISCOUNT_MODERATE, "MODERATE"
    return 1.0, None


class RiskEngine:
    """
    Central Risk Intelligence Layer.
    Aggregates multi-factor forensic signals into an explainable 0-100 risk score.
    Outputs factor breakdown, individual risk signals, risk tier, and human-in-the-loop recommendations.
    """

    def __init__(self, policy=None):
        """
        `policy` is an optional PolicySettings row (see policy_service.py) --
        the live, officer-editable weights/thresholds from the Settings page.
        Falls back to the static app.core.config defaults when omitted (e.g.
        existing tests that construct RiskEngine() directly).
        """
        self.w_mrz = policy.weight_mrz if policy else settings.WEIGHT_MRZ
        self.w_tamper = policy.weight_tamper if policy else settings.WEIGHT_TAMPER
        self.w_face = policy.weight_face if policy else settings.WEIGHT_FACE
        self.w_consistency = policy.weight_consistency if policy else settings.WEIGHT_CONSISTENCY
        self.w_watchlist = policy.weight_watchlist if policy else settings.WEIGHT_WATCHLIST
        self.threshold_low = policy.threshold_low if policy else settings.THRESHOLD_LOW
        self.threshold_medium = policy.threshold_medium if policy else settings.THRESHOLD_MEDIUM
        self.threshold_high = policy.threshold_high if policy else settings.THRESHOLD_HIGH

    def calculate(
        self,
        mrz_data: Optional[Dict[str, Any]],
        validation_data: Dict[str, Any],
        tamper_data: Dict[str, Any],
        face_data: Optional[Dict[str, Any]],
        watchlist_match: Optional[Dict[str, Any]],
        duplicate_identity_match: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        all_signals: List[Dict[str, Any]] = []

        # --- 1. MRZ & Validation Factor (25%) ---
        mrz_raw_risk = 0.0
        mrz_signals_list = []
        if validation_data and validation_data.get("signals"):
            for sig in validation_data["signals"]:
                all_signals.append(sig)
                mrz_signals_list.append(sig["signal"])
                mrz_raw_risk += sig.get("score_impact", 15.0)

        mrz_raw_risk = min(100.0, mrz_raw_risk)
        mrz_contrib = round(mrz_raw_risk * self.w_mrz, 1)

        # --- 2. Tamper Analysis Factor (30%) ---
        tamper_raw_risk = 0.0
        tamper_signals_list = []
        if tamper_data:
            tamper_score = tamper_data.get("tamper_risk", 0.1) * 100.0
            tamper_raw_risk = min(100.0, tamper_score)
            # Tie signal severity to the tamper service's own document-level
            # verdict (already calibrated: tamper_risk >= 0.85 -> CRITICAL) so a
            # highly-confident forgery finding can trigger the same hard-stop
            # floor as an expired document or watchlist hit, rather than being
            # capped at HIGH and diluted by unrelated clean signals.
            tamper_overall_level = tamper_data.get("risk_level", "LOW")
            for sig in tamper_data.get("signals", []):
                confidence = sig.get("confidence", 0.8)
                if tamper_overall_level == "CRITICAL":
                    severity = "CRITICAL"
                elif confidence > 0.85:
                    severity = "HIGH"
                else:
                    severity = "MEDIUM"
                signal_entry = {
                    "module": "TAMPER",
                    "signal": f"Forensic Anomaly ({sig['type'].replace('_', ' ').title()})",
                    "severity": severity,
                    "confidence": confidence,
                    "explanation": sig.get("explanation", "Potential image texture or compression anomaly detected."),
                    "score_impact": round(confidence * 18.0, 1)
                }
                all_signals.append(signal_entry)
                tamper_signals_list.append(signal_entry["signal"])

        tamper_contrib = round(tamper_raw_risk * self.w_tamper, 1)

        # --- 3. Face Verification Factor (30%) ---
        face_raw_risk = 0.0
        face_signals_list = []
        face_weight = self.w_face
        if face_data:
            similarity = face_data.get("similarity", 1.0)
            status = face_data.get("status", "MATCH")

            if status == "MATCH":
                face_raw_risk = max(0.0, (1.0 - similarity) * 40.0)
            elif status == "REVIEW_REQUIRED":
                face_raw_risk = max(60.0, (1.0 - similarity) * 100.0)
            elif status in ["NO_FACE_DETECTED", "MULTIPLE_FACES"]:
                face_raw_risk = 85.0

            for sig in face_data.get("signals", []):
                all_signals.append(sig)
                face_signals_list.append(sig["signal"])

            # Discount the face module's weight when the MRZ DOB (combined
            # with expiry, since issue date isn't machine-readable) implies
            # the document photo is likely old enough -- or was taken young
            # enough -- that ordinary facial aging plausibly explains a
            # lower similarity score, distinct from tampering or a genuine
            # identity mismatch. Only ever discounts risk (never amplifies
            # it) and only fires on a REAL computed gap, never on missing
            # MRZ data -- see estimate_face_age_gap's None-on-insufficient-
            # data contract.
            #
            # Restricted to status == "MATCH": the aging rationale only
            # supports softening a borderline SIMILARITY SCORE. It must
            # never fire on REVIEW_REQUIRED/NO_FACE_DETECTED/MULTIPLE_FACES
            # -- those are the module's own affirmative mismatch/no-face
            # verdicts, not aging uncertainty, and discounting them would
            # soften the exact signal that caught a genuine impersonation
            # on an old-but-unaltered document.
            age_gap = estimate_face_age_gap(mrz_data) if status == "MATCH" else None
            if age_gap:
                discount, tier = face_weight_discount_for_gap(age_gap["effective_gap_years"])
                if tier:
                    face_weight = round(self.w_face * discount, 4)
                    minor_note = " (holder was a minor when the document was likely issued)" if age_gap["was_minor_at_issue"] else ""
                    all_signals.append({
                        "module": "FACE",
                        "signal": f"Age-Gap-Adjusted Face Confidence ({tier})",
                        "severity": "LOW",
                        "confidence": 0.7,
                        "explanation": (
                            f"Face similarity lower-confidence due to an estimated "
                            f"{age_gap['photo_age_years']:.0f}-year gap since likely document "
                            f"photo capture{minor_note}. Face verification's weight in the "
                            f"composite risk score was reduced from {self.w_face:.2f} to "
                            f"{face_weight:.2f} to avoid over-penalizing a plausible aging "
                            f"effect rather than tampering or a genuine mismatch. Estimated "
                            f"issue date is not authoritative -- derived from MRZ expiry minus "
                            f"standard ICAO validity, since issue date isn't MRZ-readable."
                        ),
                        "score_impact": 0.0
                    })
        else:
            # Face verification pending or not performed yet
            face_raw_risk = 15.0

        face_raw_risk = min(100.0, face_raw_risk)
        face_contrib = round(face_raw_risk * face_weight, 1)

        # --- 4. Consistency Checks (10%) ---
        consistency_raw_risk = 0.0
        consistency_signals_list = []
        if validation_data.get("failed_count", 0) > 0:
            consistency_raw_risk = min(100.0, validation_data["failed_count"] * 30.0)
            consistency_signals_list.append(f"{validation_data['failed_count']} Rule Discrepancies")
        consistency_contrib = round(consistency_raw_risk * self.w_consistency, 1)

        # --- 5. Watchlist Demo Signal (5%) ---
        watchlist_raw_risk = 0.0
        watchlist_signals_list = []
        if watchlist_match:
            watchlist_raw_risk = 100.0
            entry = watchlist_match["entry"]
            signal_entry = {
                "module": "WATCHLIST",
                "signal": f"Demo Watchlist Hit: {entry['category']}",
                "severity": entry.get("severity", "CRITICAL"),
                "confidence": 0.99,
                "explanation": f"[SIMULATED DATA] {watchlist_match['explanation']} Requires officer identity review.",
                "score_impact": 25.0
            }
            all_signals.append(signal_entry)
            watchlist_signals_list.append(signal_entry["signal"])
        watchlist_contrib = round(watchlist_raw_risk * self.w_watchlist, 1)

        # --- 6. Cross-Case Duplicate Identity Check (CRITICAL flag only, no weight) ---
        #
        # A gallery hit (see identity_gallery_service.py) means this
        # screening's live face closely matches a PREVIOUS case filed under
        # a different name/document -- a real, named identity-fraud signal,
        # not a probabilistic risk. Modeled purely as a CRITICAL-severity
        # signal that rides the SAME hard-stop floor an expired document or
        # watchlist hit already uses, deliberately without its own weighted
        # factor: adding one would need a new PolicySettings column, and
        # this app has no migration tooling (Base.metadata.create_all only
        # creates missing tables, it won't alter an existing populated
        # one). The floor mechanism alone is sufficient to guarantee at
        # least HIGH regardless of how clean every other factor is.
        if duplicate_identity_match:
            matched_case_number = duplicate_identity_match["case_number"]
            similarity = duplicate_identity_match.get("similarity", 0.0)
            all_signals.append({
                "module": "IDENTITY",
                "signal": f"Possible Duplicate Identity: matches Case {matched_case_number}",
                "severity": "CRITICAL",
                "confidence": round(similarity, 2),
                "explanation": (
                    f"This individual's live facial biometric closely matches a PREVIOUS "
                    f"screening (Case {matched_case_number}), filed under a different name "
                    f"or document number. Similarity: {round(similarity * 100, 1)}%. "
                    f"Requires officer identity review."
                ),
                "score_impact": 30.0
            })

        # Total Aggregated Score (0 to 100)
        total_risk = round(mrz_contrib + tamper_contrib + face_contrib + consistency_contrib + watchlist_contrib, 1)
        total_risk = max(0.0, min(100.0, total_risk))
        pre_floor_total = total_risk

        # Deterministic hard-stop override: a CRITICAL-severity signal (e.g. an
        # expired document, a watchlist hit) is a definitive rule violation, not
        # a probabilistic risk that unrelated clean signals should be able to
        # dilute -- a clean face match doesn't make an expired passport valid
        # for travel. Floor the score so it can never classify below HIGH when
        # any such signal is present.
        critical_floor_applied = False
        if any(sig.get("severity") == "CRITICAL" for sig in all_signals) and total_risk <= self.threshold_medium:
            total_risk = self.threshold_medium + 0.1
            critical_floor_applied = True

        # Risk Tier Classification
        if total_risk <= self.threshold_low:
            risk_level = "LOW"
            recommendation = "CLEAR FOR ENTRY — Routine processing permitted"
        elif total_risk <= self.threshold_medium:
            risk_level = "MEDIUM"
            recommendation = "ROUTINE VERIFICATION — Officer visual confirmation recommended"
        elif total_risk <= self.threshold_high:
            risk_level = "HIGH"
            recommendation = "SECONDARY INSPECTION — Multiple document risk indicators detected"
        else:
            risk_level = "CRITICAL"
            recommendation = "SUPERVISOR ESCALATION — Significant anomalies requiring physical document review"

        breakdown = [
            {
                "factor": "MRZ & Document Validation",
                "weight": self.w_mrz,
                "raw_risk": round(mrz_raw_risk, 1),
                "weighted_contribution": mrz_contrib,
                "top_signals": mrz_signals_list[:2]
            },
            {
                "factor": "Forensic Tamper AI",
                "weight": self.w_tamper,
                "raw_risk": round(tamper_raw_risk, 1),
                "weighted_contribution": tamper_contrib,
                "top_signals": tamper_signals_list[:2]
            },
            {
                "factor": "Biometric Face Verification",
                "weight": face_weight,
                "raw_risk": round(face_raw_risk, 1),
                "weighted_contribution": face_contrib,
                "top_signals": face_signals_list[:2]
            },
            {
                "factor": "Data Consistency Crosscheck",
                "weight": self.w_consistency,
                "raw_risk": round(consistency_raw_risk, 1),
                "weighted_contribution": consistency_contrib,
                "top_signals": consistency_signals_list
            },
            {
                "factor": "Simulated Watchlist Adapter",
                "weight": self.w_watchlist,
                "raw_risk": round(watchlist_raw_risk, 1),
                "weighted_contribution": watchlist_contrib,
                "top_signals": watchlist_signals_list
            }
        ]

        # Makes the hard-stop override (above) visible as its own line, not
        # just an invisible jump between the weighted categories' sum and the
        # displayed total -- previously a CRITICAL signal with no weighted
        # factor of its own (duplicate-identity match) could supply most of
        # the score while the breakdown categories summed to far less than
        # the total, in a panel literally named "Explainable risk breakdown".
        # No weight/raw_risk of its own (see RiskFactorBreakdown's schema
        # comment): this is a flat point adjustment, not a proportional
        # category.
        if critical_floor_applied:
            critical_signal_names = [s["signal"] for s in all_signals if s.get("severity") == "CRITICAL"]
            breakdown.append({
                "factor": "Critical Signal Floor",
                "weight": None,
                "raw_risk": None,
                "weighted_contribution": round(total_risk - pre_floor_total, 1),
                "top_signals": critical_signal_names[:2]
            })

        return {
            "risk_score": total_risk,
            "risk_level": risk_level,
            "recommendation": recommendation,
            "critical_floor_applied": critical_floor_applied,
            "breakdown": breakdown,
            "signals": all_signals
        }

def get_risk_engine(policy=None) -> RiskEngine:
    return RiskEngine(policy=policy)
