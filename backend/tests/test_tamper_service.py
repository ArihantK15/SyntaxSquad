from app.services.tamper_service import TamperDetectionService


def test_high_confidence_cnn_alone_reaches_high_risk_tier():
    """
    Reproduces a real calibration gap: the tamper CNN was trained tonight to
    87.8% validation accuracy specifically so it can flag forgeries the
    hand-tuned heuristics miss (e.g. clean ELA, no detectable splice edges).
    But the aggregation formula capped its contribution at
    `cnn_tamper_prob * 0.4`, so even a maximally confident CNN detection
    (prob ~1.0) could never independently push tamper_risk into the HIGH
    tier (>= 0.70) -- it could only ever nudge the score toward MEDIUM,
    silently discarding the model's own confidence.
    """
    score = TamperDetectionService._aggregate_tamper_score(
        mean_ela=0.05,  # clean by the ELA heuristic
        cnn_tamper_prob=0.98,  # CNN is highly confident this is tampered
        signals=[],  # no heuristic signals fired
    )
    assert score >= 0.70


def test_low_confidence_cnn_does_not_reach_high_risk_tier():
    """A weak/uncertain CNN signal (near coin-flip) should not, by itself,
    escalate a document with no other anomalies to HIGH."""
    score = TamperDetectionService._aggregate_tamper_score(
        mean_ela=0.05,
        cnn_tamper_prob=0.55,
        signals=[],
    )
    assert score < 0.70


def test_signal_score_contribution_scales_with_its_own_confidence():
    """
    Two forensic signals at low confidence (e.g. 0.5) should contribute less
    to the aggregate score than two signals at high confidence (e.g. 0.95) --
    the old formula added a flat 0.25 per signal regardless of its own
    confidence, treating a barely-there anomaly the same as a near-certain one.
    """
    low_conf_signals = [
        {"type": "a", "confidence": 0.50},
        {"type": "b", "confidence": 0.50},
    ]
    high_conf_signals = [
        {"type": "a", "confidence": 0.95},
        {"type": "b", "confidence": 0.95},
    ]
    low_score = TamperDetectionService._aggregate_tamper_score(0.05, None, low_conf_signals)
    high_score = TamperDetectionService._aggregate_tamper_score(0.05, None, high_conf_signals)
    assert high_score > low_score
