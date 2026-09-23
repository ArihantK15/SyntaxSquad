import cv2
import numpy as np
from PIL import Image
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


def _canvas_with_wide_thin_header_banner() -> np.ndarray:
    """
    A single continuous, thin, textured horizontal strip -- e.g. a printed
    decorative banner/rule carrying a logo mark and wordmark, the kind of
    element real ID-card header layouts (Aadhaar's government emblem +
    'आधार' wordmark row, in particular) actually have. Real, not synthetic
    noise standing in for something else: same shape class (extreme
    width:height ratio) as what was actually flagged -- 95% confidence --
    on a genuine, unaltered Aadhaar card (case BM-2026-41713, region
    361x19px, ~19:1 aspect ratio) after the QR-code-shaped false positive
    above was already excluded.
    """
    rng = np.random.default_rng(7)
    canvas = np.full((300, 512, 3), 255, dtype=np.uint8)
    canvas[10:29, 20:470] = rng.integers(50, 200, size=(19, 450, 3), dtype=np.uint8)
    return canvas


def test_wide_thin_header_banner_is_not_flagged_as_a_splicing_anomaly():
    """
    Reproduces a real false positive found by running an actual, genuine
    e-Aadhaar card (never a synthetic specimen) through the live app: the
    QR-code exclusion above only scopes out QR-shaped (roughly square)
    regions. A different genuine design element -- a wide, thin banner
    row containing the government emblem and the 'आधार' wordmark -- is
    NOT QR-shaped (its bounding box is ~19:1 wide:tall, nothing like a
    QR code's near-1:1 box), so it sailed straight past that exclusion
    and was flagged as a "High-frequency boundary discontinuity" at 95%
    confidence, pushing the case to 83% overall tamper risk / HIGH.

    A real pasted/spliced patch (a photo replacement, a stamp, an altered
    text block) is essentially never this extremely elongated -- this is
    the geometric signature of a printed banner/rule, not a forgery.
    """
    canvas = _canvas_with_wide_thin_header_banner()
    anomalies = TamperForensics.detect_splicing_boundaries(canvas)
    assert anomalies == []


def test_extreme_aspect_ratio_guard_does_not_blind_detection_of_a_real_splice_elsewhere():
    """The wide-thin-banner exclusion must be scoped to genuinely elongated
    shapes -- an actual pasted patch of ordinary (non-extreme) proportions
    elsewhere on the same document must still be caught."""
    canvas = _canvas_with_wide_thin_header_banner()
    rng = np.random.default_rng(42)
    noise_patch = rng.integers(0, 255, size=(60, 80, 3), dtype=np.uint8)
    canvas[150:210, 200:280] = noise_patch

    anomalies = TamperForensics.detect_splicing_boundaries(canvas)
    assert len(anomalies) == 1
    x, y, cw, ch = anomalies[0]["region"]
    assert x >= 150 and y >= 100  # matches the noise patch, not the banner


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


# --- EXIF metadata signal (Signal E) -----------------------------------
#
# Unit-tested against plain exif/exif_ifd dicts via _evaluate_exif_signals,
# the same way _aggregate_tamper_score above is tested against plain
# numbers/dicts rather than real files -- this pins down each business
# rule (missing metadata, an editor signature, a suspicious date gap)
# precisely and independently of Pillow's own EXIF-writing quirks.
# Pillow can only reliably WRITE top-level IFD0 tags (e.g. Software) in a
# round-trippable way; nested Exif-sub-IFD tags like DateTimeOriginal are
# unreliable to write back out for a test fixture, so the date-gap rule is
# covered here at the dict level instead of via a real saved file.

def test_missing_exif_is_flagged_but_only_at_low_confidence():
    """
    Absence of EXIF is a real but weak/noisy tell -- innocent pipelines
    (WhatsApp/Telegram recompression, a screenshot of an already-issued
    digital ID) strip it just as thoroughly as tampering does. It must
    still surface as a signal (so a fully metadata-stripped image isn't
    silently ignored), but at low confidence so it can't dominate the
    aggregate score on its own.
    """
    signals = TamperDetectionService._evaluate_exif_signals({}, {})
    assert len(signals) == 1
    assert signals[0]["type"] == "exif_metadata_missing"
    assert signals[0]["confidence"] < 0.5


def test_genuine_camera_exif_is_not_flagged():
    """A plausible camera capture profile -- Make/Model present, no editor
    Software tag, capture and modify timestamps matching -- must not raise
    any EXIF signal."""
    exif = {271: "Google", 272: "Pixel 8", 306: "2026:01:15 10:00:00"}
    exif_ifd = {36867: "2026:01:15 10:00:00"}
    signals = TamperDetectionService._evaluate_exif_signals(exif, exif_ifd)
    assert signals == []


def test_editing_software_tag_is_flagged_at_high_confidence():
    """An EXIF Software tag naming a known photo editor has no legitimate
    documentary-capture explanation -- a camera/scanner never writes
    'Adobe Photoshop' as its own Software tag."""
    exif = {305: "Adobe Photoshop 25.0 (Windows)"}
    signals = TamperDetectionService._evaluate_exif_signals(exif, {})
    assert len(signals) == 1
    assert signals[0]["type"] == "exif_editing_software"
    assert signals[0]["confidence"] >= 0.7


def test_editing_software_check_is_case_insensitive_and_substring_based():
    """Editor signatures appear as free-form version strings (e.g. 'GIMP
    2.10.34') -- the check must match on substring, not exact equality."""
    exif = {305: "gimp 2.10.34"}
    signals = TamperDetectionService._evaluate_exif_signals(exif, {})
    assert any(s["type"] == "exif_editing_software" for s in signals)


def test_modification_date_shortly_after_capture_is_not_flagged():
    """A few seconds/minutes between DateTimeOriginal and DateTime is
    normal encoder/save latency on a genuine single capture-to-storage
    write -- must not trigger the date-inconsistency signal."""
    exif = {306: "2026:01:15 10:00:04"}
    exif_ifd = {36867: "2026:01:15 10:00:00"}
    signals = TamperDetectionService._evaluate_exif_signals(exif, exif_ifd)
    assert not any(s["type"] == "exif_date_inconsistency" for s in signals)


def test_modification_date_long_after_capture_is_flagged():
    """A modification timestamp a full day after the original capture
    timestamp is the EXIF fingerprint of a post-capture re-save/edit."""
    exif = {306: "2026:01:20 10:00:00"}  # 5 days after capture
    exif_ifd = {36867: "2026:01:15 10:00:00"}
    signals = TamperDetectionService._evaluate_exif_signals(exif, exif_ifd)
    matches = [s for s in signals if s["type"] == "exif_date_inconsistency"]
    assert len(matches) == 1
    assert matches[0]["confidence"] >= 0.6


def test_malformed_exif_dates_do_not_crash_or_flag():
    """Not every device writes EXIF dates in the standard format -- an
    unparseable date must be treated as no signal, not an exception."""
    exif = {306: "not-a-date"}
    exif_ifd = {36867: "also-not-a-date"}
    signals = TamperDetectionService._evaluate_exif_signals(exif, exif_ifd)
    assert not any(s["type"] == "exif_date_inconsistency" for s in signals)


def _save_jpeg_with_exif(path, exif_dict=None):
    img = Image.new("RGB", (200, 120), color=(230, 230, 230))
    if exif_dict:
        exif = Image.Exif()
        for tag, value in exif_dict.items():
            exif[tag] = value
        img.save(path, "JPEG", exif=exif.tobytes())
    else:
        img.save(path, "JPEG")


def test_genuine_specimen_file_is_not_flagged(tmp_path):
    """End-to-end through analyze_exif_metadata (real file I/O, not just
    the pure dict logic above): a specimen carrying a plausible camera
    profile must not be flagged."""
    path = str(tmp_path / "genuine.jpg")
    _save_jpeg_with_exif(path, {271: "Google", 272: "Pixel 8", 305: "HDR+ 1.0"})
    service = TamperDetectionService()
    result = service.analyze_exif_metadata(path)
    assert result["signals"] == []


def test_stripped_exif_specimen_file_is_flagged(tmp_path):
    """A specimen saved with no EXIF block at all -- e.g. a screenshot or
    a messaging-app recompression -- must raise the missing-metadata
    signal."""
    path = str(tmp_path / "stripped.jpg")
    _save_jpeg_with_exif(path, exif_dict=None)
    service = TamperDetectionService()
    result = service.analyze_exif_metadata(path)
    assert any(s["type"] == "exif_metadata_missing" for s in result["signals"])


def test_editor_software_specimen_file_is_flagged(tmp_path):
    """A specimen whose EXIF Software tag names a photo editor must raise
    the editing-software signal."""
    path = str(tmp_path / "edited.jpg")
    _save_jpeg_with_exif(path, {305: "Adobe Photoshop 25.0 (Windows)"})
    service = TamperDetectionService()
    result = service.analyze_exif_metadata(path)
    assert any(s["type"] == "exif_editing_software" for s in result["signals"])
