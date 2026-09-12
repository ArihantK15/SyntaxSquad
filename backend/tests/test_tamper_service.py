import cv2
import numpy as np
from app.services.tamper_service import TamperDetectionService
from app.ml.tamper_model import TamperForensics


def _canvas_with_real_qr_code(payload: str = "https://example.com/test-payload-1234567890") -> np.ndarray:
    """A genuine, decodable QR code (via OpenCV's own encoder) pasted onto a
    blank canvas -- not a synthetic noise stand-in, so detection/exclusion
    logic is exercised against the real thing."""
    qr = cv2.QRCodeEncoder_create().encode(payload)
    qr_big = cv2.resize(qr, (150, 150), interpolation=cv2.INTER_NEAREST)
    canvas = np.full((400, 400, 3), 255, dtype=np.uint8)
    canvas[100:250, 100:250] = cv2.cvtColor(qr_big, cv2.COLOR_GRAY2BGR)
    return canvas


def test_genuine_qr_code_is_not_flagged_as_a_splicing_anomaly():
    """
    Reproduces a real false positive found by running an actual e-Aadhaar
    screenshot through the live app: `detect_splicing_boundaries` looks for
    bounded rectangular regions of unusually high internal variance to catch
    pasted photo/text patches. A QR code -- present by design on real
    government ID formats like Aadhaar -- IS exactly that shape (a small,
    high-contrast block of dense black/white noise), so a genuine,
    untampered card's own QR code was flagged as a "High-frequency boundary
    discontinuity" with 95% confidence.
    """
    canvas = _canvas_with_real_qr_code()
    anomalies = TamperForensics.detect_splicing_boundaries(canvas)
    assert anomalies == []


def test_qr_exclusion_does_not_blind_detection_of_a_real_splice_elsewhere():
    """The QR-code exclusion must be scoped to the QR's own region -- an
    actual pasted patch elsewhere on the same document must still be
    caught."""
    canvas = _canvas_with_real_qr_code()
    rng = np.random.default_rng(42)
    noise_patch = rng.integers(0, 255, size=(60, 80, 3), dtype=np.uint8)
    canvas[300:360, 20:100] = noise_patch

    anomalies = TamperForensics.detect_splicing_boundaries(canvas)
    assert len(anomalies) == 1
    x, y, cw, ch = anomalies[0]["region"]
    assert x < 100 or y >= 300  # matches the noise patch, not the QR region


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
