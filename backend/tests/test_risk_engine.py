from datetime import date
from app.services.risk_engine import RiskEngine

def test_risk_engine_low_risk():
    engine = RiskEngine()
    validation_data = {"passed_count": 5, "failed_count": 0, "signals": []}
    tamper_data = {"tamper_risk": 0.08, "signals": []}
    face_data = {"similarity": 0.92, "status": "MATCH", "signals": []}
    
    result = engine.calculate(
        mrz_data={"is_valid": True},
        validation_data=validation_data,
        tamper_data=tamper_data,
        face_data=face_data,
        watchlist_match=None
    )

    assert result["risk_level"] == "LOW"
    assert result["risk_score"] < 25.0
    assert "CLEAR FOR ENTRY" in result["recommendation"]
    assert len(result["breakdown"]) == 5

def test_risk_engine_critical_tampering_and_watchlist():
    engine = RiskEngine()
    validation_data = {
        "passed_count": 1,
        "failed_count": 3,
        "signals": [
            {"module": "MRZ", "signal": "MRZ Checksum Mismatch", "severity": "HIGH", "score_impact": 40.0, "explanation": "Corrupted check digit."},
            {"module": "VALIDATION", "signal": "Document Expired", "severity": "CRITICAL", "score_impact": 45.0, "explanation": "Document expired."}
        ]
    }
    tamper_data = {
        "tamper_risk": 0.95,
        "signals": [
            {"type": "photo_boundary_anomaly", "confidence": 0.95, "explanation": "Photo splicing detected."}
        ]
    }
    face_data = {
        "similarity": 0.15,
        "status": "REVIEW_REQUIRED",
        "signals": [
            {"module": "FACE", "signal": "Biometric Face Mismatch", "severity": "HIGH", "score_impact": 25.0, "explanation": "Face mismatch."}
        ]
    }
    watchlist_match = {
        "matched": True,
        "entry": {"watchlist_id": "WL-001", "category": "Demo Flag", "severity": "CRITICAL"},
        "explanation": "Simulated match."
    }

    result = engine.calculate(
        mrz_data={"is_valid": False},
        validation_data=validation_data,
        tamper_data=tamper_data,
        face_data=face_data,
        watchlist_match=watchlist_match
    )

    assert result["risk_level"] == "CRITICAL"
    assert result["risk_score"] >= 75.0
    assert "SUPERVISOR ESCALATION" in result["recommendation"]


def test_risk_engine_isolated_critical_signal_floors_to_high():
    """
    An expired document (or any CRITICAL rule violation) is a definitive, legal
    fact -- not a probabilistic risk that an unrelated clean face match or low
    tamper score should be able to dilute into a LOW/MEDIUM weighted average.
    Regression guard for exactly that: otherwise-clean signals plus one
    isolated CRITICAL validation signal must still floor to at least HIGH.
    """
    engine = RiskEngine()
    validation_data = {
        "passed_count": 4,
        "failed_count": 1,
        "signals": [
            {"module": "VALIDATION", "signal": "Document Expired", "severity": "CRITICAL",
             "score_impact": 28.0, "explanation": "Travel document validity expired."}
        ]
    }
    tamper_data = {"tamper_risk": 0.07, "signals": []}
    face_data = {"similarity": 0.91, "status": "MATCH", "signals": []}

    result = engine.calculate(
        mrz_data={"is_valid": True},
        validation_data=validation_data,
        tamper_data=tamper_data,
        face_data=face_data,
        watchlist_match=None
    )

    assert result["critical_floor_applied"] is True
    assert result["risk_level"] in ("HIGH", "CRITICAL")
    assert result["risk_score"] > 49.0


def test_risk_engine_breakdown_reconciles_to_total_when_critical_floor_applies():
    """
    Reproduces a real credibility gap in the "Explainable risk breakdown"
    panel: when an isolated CRITICAL signal (e.g. a cross-case duplicate-
    identity match, which deliberately carries no weighted factor of its
    own) floors the score, the 5 weighted categories previously summed to
    far less than the displayed total with no line item accounting for the
    difference -- in a panel literally named "Explainable". The floor must
    now appear as its own breakdown entry, named after the triggering
    signal, whose contribution makes the categories sum back to the total.
    """
    engine = RiskEngine()
    validation_data = {"passed_count": 5, "failed_count": 0, "signals": []}
    tamper_data = {"tamper_risk": 0.1, "signals": []}
    face_data = {"similarity": 0.97, "status": "MATCH", "signals": []}

    result = engine.calculate(
        mrz_data={"is_valid": True},
        validation_data=validation_data,
        tamper_data=tamper_data,
        face_data=face_data,
        watchlist_match=None,
        duplicate_identity_match={"case_number": "BM-2026-F0E17", "similarity": 1.0}
    )

    assert result["critical_floor_applied"] is True
    floor_entry = next(b for b in result["breakdown"] if b["factor"] == "Critical Signal Floor")
    assert floor_entry["weight"] is None
    assert floor_entry["raw_risk"] is None
    assert any("Duplicate Identity" in s for s in floor_entry["top_signals"])

    reconciled_total = round(sum(b["weighted_contribution"] for b in result["breakdown"]), 1)
    assert reconciled_total == result["risk_score"]


def test_risk_engine_breakdown_has_no_floor_entry_when_floor_not_applied():
    """A clean/low-risk result must not grow a phantom breakdown row."""
    engine = RiskEngine()
    validation_data = {"passed_count": 5, "failed_count": 0, "signals": []}
    tamper_data = {"tamper_risk": 0.08, "signals": []}
    face_data = {"similarity": 0.92, "status": "MATCH", "signals": []}

    result = engine.calculate(
        mrz_data={"is_valid": True},
        validation_data=validation_data,
        tamper_data=tamper_data,
        face_data=face_data,
        watchlist_match=None
    )

    assert result["critical_floor_applied"] is False
    assert all(b["factor"] != "Critical Signal Floor" for b in result["breakdown"])
    reconciled_total = round(sum(b["weighted_contribution"] for b in result["breakdown"]), 1)
    assert reconciled_total == result["risk_score"]


def test_risk_engine_critical_tamper_verdict_floors_score():
    """
    A tamper_risk that crosses into the tamper service's own CRITICAL tier
    (>=0.85) represents a highly-confident forgery finding -- it must be able
    to floor the overall risk the same way an expired document does, even if
    face verification and validation are otherwise clean. Regression guard for
    the earlier gap where tamper signal severity was capped at HIGH and could
    never trigger the critical-floor override.
    """
    engine = RiskEngine()
    validation_data = {"passed_count": 5, "failed_count": 0, "signals": []}
    tamper_data = {
        "tamper_risk": 0.91,
        "risk_level": "CRITICAL",
        "signals": [
            {"type": "photo_boundary_anomaly", "confidence": 0.95,
             "explanation": "Photo splicing detected."}
        ]
    }
    face_data = {"similarity": 0.9, "status": "MATCH", "signals": []}

    result = engine.calculate(
        mrz_data={"is_valid": True},
        validation_data=validation_data,
        tamper_data=tamper_data,
        face_data=face_data,
        watchlist_match=None
    )

    assert result["critical_floor_applied"] is True
    assert result["risk_level"] in ("HIGH", "CRITICAL")


def _yymmdd(d: date) -> str:
    return d.strftime("%y%m%d")


def test_risk_engine_discounts_face_weight_for_large_age_gap():
    """
    A document that was very likely issued to the holder as a minor, long
    enough ago that ordinary facial aging plausibly explains a mediocre
    (but not clearly-mismatched) similarity score, should have its face
    module weight discounted rather than penalized as if it were a same-age
    photo -- see risk_engine.estimate_face_age_gap.
    """
    engine = RiskEngine()
    today = date.today()
    # DOB ~11 years ago, expiry ~1 year ago -> estimated 5-year-validity
    # minor's passport, issued ~6 years ago while the holder was ~5 --
    # a large, minor-at-issue gap.
    mrz_data = {
        "is_valid": True,
        "birth_date": _yymmdd(today.replace(year=today.year - 11)),
        "expiry_date": _yymmdd(today.replace(year=today.year - 1)),
    }
    validation_data = {"passed_count": 5, "failed_count": 0, "signals": []}
    tamper_data = {"tamper_risk": 0.05, "signals": []}
    face_data = {"similarity": 0.60, "status": "MATCH", "signals": []}

    result = engine.calculate(
        mrz_data=mrz_data,
        validation_data=validation_data,
        tamper_data=tamper_data,
        face_data=face_data,
        watchlist_match=None
    )

    face_entry = next(b for b in result["breakdown"] if b["factor"] == "Biometric Face Verification")
    assert face_entry["weight"] < engine.w_face

    age_gap_signals = [s for s in result["signals"] if s["module"] == "FACE" and "Age-Gap" in s["signal"]]
    assert len(age_gap_signals) == 1
    assert "gap since likely document" in age_gap_signals[0]["explanation"]
    # Purely informational -- discounting the face weight already reduces
    # its contribution, so the note itself must not ALSO add risk score.
    assert age_gap_signals[0]["score_impact"] == 0.0


def test_risk_engine_does_not_discount_face_weight_for_a_genuine_mismatch():
    """
    Reproduces a real gap: the age-gap discount fired regardless of the
    face module's own verdict, so a GENUINE mismatch (REVIEW_REQUIRED) on
    an old document got its weight cut exactly like a merely-uncertain
    MATCH would -- softening the one signal that actually caught an
    impersonator, rather than a case where the system is uncertain solely
    because of aging. The aging rationale (documented on the discount
    itself) only supports discounting a borderline SIMILARITY SCORE,
    never a case where face verification already returned an affirmative
    mismatch/no-face verdict.

    Concrete before/after, same MRZ age-gap setup as
    test_risk_engine_discounts_face_weight_for_large_age_gap (effective
    gap ~9.6 years -> the 50% discount tier), with an otherwise clean,
    moderate-tamper, single-consistency-flag case chosen so the total
    composite score straddles the real HIGH/MEDIUM boundary (default
    threshold_medium=49):
      - undiscounted: 21.0 (tamper) + 25.5 (face, undiscounted 0.30 * 85)
        + 3.0 (consistency) = 49.5 -> HIGH ("SECONDARY INSPECTION")
      - buggy discount applied: 21.0 + 12.75 (0.15 * 85) + 3.0 = 36.75
        -> MEDIUM ("ROUTINE VERIFICATION") -- a real impersonation case
        silently downgraded out of secondary inspection.
    """
    engine = RiskEngine()
    today = date.today()
    mrz_data = {
        "is_valid": True,
        "birth_date": _yymmdd(today.replace(year=today.year - 11)),
        "expiry_date": _yymmdd(today.replace(year=today.year - 1)),
    }
    validation_data = {"passed_count": 4, "failed_count": 1, "signals": []}
    tamper_data = {"tamper_risk": 0.70, "signals": []}
    face_data = {"similarity": 0.15, "status": "REVIEW_REQUIRED", "signals": []}

    result = engine.calculate(
        mrz_data=mrz_data,
        validation_data=validation_data,
        tamper_data=tamper_data,
        face_data=face_data,
        watchlist_match=None
    )

    face_entry = next(b for b in result["breakdown"] if b["factor"] == "Biometric Face Verification")
    assert face_entry["weight"] == engine.w_face  # undiscounted -- this is a real mismatch, not aging uncertainty
    assert not [s for s in result["signals"] if s["module"] == "FACE" and "Age-Gap" in s["signal"]]

    assert result["risk_score"] == 49.5
    assert result["risk_level"] == "HIGH"
    assert "SECONDARY INSPECTION" in result["recommendation"]


def test_risk_engine_no_age_gap_discount_for_recent_adult_document():
    """Regression guard: a normal, recently-issued adult document must not
    trigger any face-weight discount or explanatory signal."""
    engine = RiskEngine()
    today = date.today()
    mrz_data = {
        "is_valid": True,
        "birth_date": _yymmdd(today.replace(year=today.year - 40)),
        "expiry_date": _yymmdd(today.replace(year=today.year + 9)),
    }
    validation_data = {"passed_count": 5, "failed_count": 0, "signals": []}
    tamper_data = {"tamper_risk": 0.05, "signals": []}
    face_data = {"similarity": 0.90, "status": "MATCH", "signals": []}

    result = engine.calculate(
        mrz_data=mrz_data,
        validation_data=validation_data,
        tamper_data=tamper_data,
        face_data=face_data,
        watchlist_match=None
    )

    face_entry = next(b for b in result["breakdown"] if b["factor"] == "Biometric Face Verification")
    assert face_entry["weight"] == engine.w_face
    assert not [s for s in result["signals"] if s["module"] == "FACE" and "Age-Gap" in s["signal"]]


def test_risk_engine_missing_mrz_dates_never_discounts_face_weight():
    """Regression guard: absent/unparseable MRZ dates (the common case in
    existing tests and for documents with no MRZ) must never trigger a
    discount -- only a genuinely computed gap may."""
    engine = RiskEngine()
    face_data = {"similarity": 0.90, "status": "MATCH", "signals": []}

    result = engine.calculate(
        mrz_data={"is_valid": True},  # no birth_date/expiry_date at all
        validation_data={"passed_count": 5, "failed_count": 0, "signals": []},
        tamper_data={"tamper_risk": 0.05, "signals": []},
        face_data=face_data,
        watchlist_match=None
    )
    face_entry = next(b for b in result["breakdown"] if b["factor"] == "Biometric Face Verification")
    assert face_entry["weight"] == engine.w_face


def test_risk_engine_duplicate_identity_match_floors_to_critical_via_existing_mechanism():
    """
    A cross-case duplicate-identity gallery hit (see identity_gallery_service.py)
    is modeled as a CRITICAL-severity signal under a new "IDENTITY" module --
    deliberately reusing the SAME hard-stop floor mechanism a watchlist hit or
    an expired document already uses, rather than adding a new weighted
    factor (which would need a PolicySettings schema migration). It must
    floor an otherwise entirely clean screening to at least HIGH.
    """
    engine = RiskEngine()
    validation_data = {"passed_count": 5, "failed_count": 0, "signals": []}
    tamper_data = {"tamper_risk": 0.05, "signals": []}
    face_data = {"similarity": 0.95, "status": "MATCH", "signals": []}
    duplicate_identity_match = {
        "case_id": "prior-case-uuid",
        "case_number": "BM-2026-PRIOR",
        "full_name": "SUNIL MEHTA",
        "similarity": 0.97
    }

    result = engine.calculate(
        mrz_data={"is_valid": True},
        validation_data=validation_data,
        tamper_data=tamper_data,
        face_data=face_data,
        watchlist_match=None,
        duplicate_identity_match=duplicate_identity_match
    )

    identity_signals = [s for s in result["signals"] if s["module"] == "IDENTITY"]
    assert len(identity_signals) == 1
    assert identity_signals[0]["severity"] == "CRITICAL"
    assert "BM-2026-PRIOR" in identity_signals[0]["signal"]
    assert result["critical_floor_applied"] is True
    assert result["risk_level"] in ("HIGH", "CRITICAL")


def test_risk_engine_no_duplicate_identity_match_emits_no_identity_signal():
    engine = RiskEngine()
    validation_data = {"passed_count": 5, "failed_count": 0, "signals": []}
    tamper_data = {"tamper_risk": 0.05, "signals": []}
    face_data = {"similarity": 0.95, "status": "MATCH", "signals": []}

    result = engine.calculate(
        mrz_data={"is_valid": True},
        validation_data=validation_data,
        tamper_data=tamper_data,
        face_data=face_data,
        watchlist_match=None,
        duplicate_identity_match=None
    )

    assert not any(s["module"] == "IDENTITY" for s in result["signals"])
    assert result["risk_level"] == "LOW"
