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
