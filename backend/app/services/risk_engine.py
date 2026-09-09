from typing import Dict, Any, List, Optional
from app.core.config import settings

class RiskEngine:
    """
    Central Risk Intelligence Layer.
    Aggregates multi-factor forensic signals into an explainable 0-100 risk score.
    Outputs factor breakdown, individual risk signals, risk tier, and human-in-the-loop recommendations.
    """

    def __init__(self):
        self.w_mrz = settings.WEIGHT_MRZ
        self.w_tamper = settings.WEIGHT_TAMPER
        self.w_face = settings.WEIGHT_FACE
        self.w_consistency = settings.WEIGHT_CONSISTENCY
        self.w_watchlist = settings.WEIGHT_WATCHLIST

    def calculate(
        self,
        mrz_data: Optional[Dict[str, Any]],
        validation_data: Dict[str, Any],
        tamper_data: Dict[str, Any],
        face_data: Optional[Dict[str, Any]],
        watchlist_match: Optional[Dict[str, Any]]
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
        else:
            # Face verification pending or not performed yet
            face_raw_risk = 15.0

        face_raw_risk = min(100.0, face_raw_risk)
        face_contrib = round(face_raw_risk * self.w_face, 1)

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

        # Total Aggregated Score (0 to 100)
        total_risk = round(mrz_contrib + tamper_contrib + face_contrib + consistency_contrib + watchlist_contrib, 1)
        total_risk = max(0.0, min(100.0, total_risk))

        # Deterministic hard-stop override: a CRITICAL-severity signal (e.g. an
        # expired document, a watchlist hit) is a definitive rule violation, not
        # a probabilistic risk that unrelated clean signals should be able to
        # dilute -- a clean face match doesn't make an expired passport valid
        # for travel. Floor the score so it can never classify below HIGH when
        # any such signal is present.
        critical_floor_applied = False
        if any(sig.get("severity") == "CRITICAL" for sig in all_signals) and total_risk <= settings.THRESHOLD_MEDIUM:
            total_risk = settings.THRESHOLD_MEDIUM + 0.1
            critical_floor_applied = True

        # Risk Tier Classification
        if total_risk <= settings.THRESHOLD_LOW:
            risk_level = "LOW"
            recommendation = "CLEAR FOR ENTRY — Routine processing permitted"
        elif total_risk <= settings.THRESHOLD_MEDIUM:
            risk_level = "MEDIUM"
            recommendation = "ROUTINE VERIFICATION — Officer visual confirmation recommended"
        elif total_risk <= settings.THRESHOLD_HIGH:
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
                "weight": self.w_face,
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

        return {
            "risk_score": total_risk,
            "risk_level": risk_level,
            "recommendation": recommendation,
            "critical_floor_applied": critical_floor_applied,
            "breakdown": breakdown,
            "signals": all_signals
        }

def get_risk_engine() -> RiskEngine:
    return RiskEngine()
