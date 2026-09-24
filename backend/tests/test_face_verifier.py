"""
Regression guard for the face-similarity signal (MTCNN + InceptionResnetV1,
pretrained on VGGFace2, via facenet-pytorch).

An earlier implementation used an untrained neural embedding net, which produced
near-constant similarity (~0.85-1.0) regardless of input -- including for pairs of
random noise images -- making biometric face verification a silent no-op that
always reported MATCH. These tests are a fast, offline smoke check that the
model is wired correctly and behaves sanely; the real accuracy number (98.0% on
the LFW benchmark) comes from scripts/calibrate_face_threshold.py, which is not
run as part of this suite since it downloads ~475MB of benchmark data.
"""
import os
import tempfile

import cv2
import numpy as np

from app.ml.face_verifier import FaceDetectorAndVerifier
from app.utils.synthetic_generator import SyntheticDocumentGenerator
from app.core.demo_faces import PERSON_A

_det = FaceDetectorAndVerifier()  # model load is expensive; share across tests


def test_embedding_shape_and_normalization():
    img = np.random.default_rng(0).integers(0, 255, (160, 160, 3), dtype=np.uint8)
    emb = _det.extract_embedding(img)
    assert emb is not None
    assert emb.shape == (512,)
    assert abs(np.linalg.norm(emb) - 1.0) < 1e-4


def test_embedding_is_deterministic():
    img = np.random.default_rng(1).integers(0, 255, (160, 160, 3), dtype=np.uint8)
    emb_a = _det.extract_embedding(img)
    emb_b = _det.extract_embedding(img)
    assert _det.compare_faces(emb_a, emb_b) > 0.999


def test_compare_faces_handles_missing_embedding():
    img = np.random.default_rng(2).integers(0, 255, (160, 160, 3), dtype=np.uint8)
    emb = _det.extract_embedding(img)
    assert _det.compare_faces(None, emb) == 0.0
    assert _det.compare_faces(emb, None) == 0.0
    assert _det.compare_faces(None, None) == 0.0


def test_extract_embedding_handles_empty_crop():
    assert _det.extract_embedding(np.zeros((0, 0, 3), dtype=np.uint8)) is None


def test_detect_face_falls_back_when_no_face_found():
    """A blank frame has no detectable face; detect_face must use the caller's
    fallback_rect rather than crashing or returning nothing."""
    blank = np.full((200, 300, 3), 128, dtype=np.uint8)
    boxes = _det.detect_face(blank, fallback_rect=(0.1, 0.1, 0.5, 0.5))
    assert len(boxes) == 1
    x, y, w, h = boxes[0]
    assert (x, y, w, h) == (30, 20, 150, 100)


def test_hand_drawn_avatar_is_not_detected_as_a_face():
    """
    Documents real/expected behavior of the generator's hand-drawn avatar
    fallback (used when no face_photo_path is given): a properly trained
    face detector correctly does NOT recognize it as a face. This is exactly
    why generate_specimen_doc() (demo.py) and the auto-simulated live
    capture (screening.py) must always pass a real face_photo_path -- if
    they didn't, MTCNN's raw detection returns None here, and only the
    caller's generic fallback_rect keeps detect_face() from returning
    nothing, silently turning the "detected face" into an arbitrary crop of
    non-face artwork.
    """
    with tempfile.TemporaryDirectory() as tmp:
        doc_path = os.path.join(tmp, "avatar_doc.jpg")
        SyntheticDocumentGenerator.generate_document(
            out_path=doc_path, mode="genuine", surname="TEST", given_names="USER"
        )
        img = cv2.imread(doc_path)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        boxes, probs = _det.mtcnn.detect(rgb)
        assert boxes is None


def _apply_synthetic_moire(gray_u8: np.ndarray, freq_cycles: float = 14.0, amplitude: float = 28.0, angle_deg: float = 20.0) -> np.ndarray:
    """
    Same construction as scripts/check_frequency_liveness_signal.py's own
    apply_synthetic_moire (see that script's own disclosure of what this
    proxy is and is not validated against) -- duplicated here in miniature
    rather than imported, so this fast/offline pytest suite doesn't depend
    on the scripts/ directory being importable, mirroring how test_ocr.py
    etc. don't import from scripts/ either.
    """
    h, w = gray_u8.shape
    yy, xx = np.indices((h, w), dtype=np.float64)
    theta = np.deg2rad(angle_deg)
    xr = xx * np.cos(theta) + yy * np.sin(theta)
    grating = amplitude * np.sin(2 * np.pi * freq_cycles * xr / w)
    return np.clip(gray_u8.astype(np.float64) + grating, 0, 255).astype(np.uint8)


def _apply_synthetic_halftone(gray_u8: np.ndarray, cell_size: float = 7.0, amplitude: float = 45.0, angle_deg: float = 45.0) -> np.ndarray:
    h, w = gray_u8.shape
    yy, xx = np.indices((h, w), dtype=np.float64)
    theta = np.deg2rad(angle_deg)
    xr = xx * np.cos(theta) - yy * np.sin(theta)
    yr = xx * np.sin(theta) + yy * np.cos(theta)
    dot_pattern = np.cos(2 * np.pi * xr / cell_size) * np.cos(2 * np.pi * yr / cell_size)
    return np.clip(gray_u8.astype(np.float64) + amplitude * dot_pattern, 0, 255).astype(np.uint8)


def _person_a_face_crop_bgr() -> np.ndarray:
    """A real (if AI-generated) face photo, not random noise -- the frequency
    heuristic's whole premise is that a real face crop's spectrum behaves
    differently from an injected periodic pattern's, so a meaningful test
    of it needs real face-like texture, not synthetic noise."""
    img = cv2.imread(PERSON_A)
    assert img is not None
    return img


def test_frequency_artifacts_not_detected_on_a_clean_real_face_crop():
    """
    Fast, deterministic smoke check on a single real face crop -- the
    statistical false-positive-rate claim (see
    FaceDetectorAndVerifier.FREQ_ARTIFACT_CONCENTRATION_THRESHOLD's own
    comment: 5.4% on n=800 real LFW crops) comes from
    scripts/check_frequency_liveness_signal.py, not from this test, which
    only confirms the ordinary/expected case behaves as expected.
    """
    result = FaceDetectorAndVerifier.analyze_frequency_artifacts(_person_a_face_crop_bgr())
    assert result["frequency_artifact_detected"] is False


def test_frequency_artifacts_detected_on_synthetic_moire_overlay():
    """The synthetic-proxy validation this heuristic was actually calibrated
    against (scripts/check_frequency_liveness_signal.py) -- this is the fast
    offline version of that same check on a single fixed image, not a
    substitute for it."""
    img = _person_a_face_crop_bgr()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    moire_gray = _apply_synthetic_moire(gray)
    moire_bgr = cv2.cvtColor(moire_gray, cv2.COLOR_GRAY2BGR)

    result = FaceDetectorAndVerifier.analyze_frequency_artifacts(moire_bgr)
    assert result["frequency_artifact_detected"] is True
    assert result["moire_energy_concentration"] > FaceDetectorAndVerifier.FREQ_ARTIFACT_CONCENTRATION_THRESHOLD


def test_frequency_artifacts_detected_on_synthetic_halftone_overlay():
    """
    Fixed, hand-picked cell_size/amplitude for this single deterministic
    image (unlike the randomized-per-sample sweep
    scripts/check_frequency_liveness_signal.py runs across hundreds of real
    LFW crops) -- halftone recall there was only 41.9% overall, i.e. not
    every configuration triggers detection even on a real attack; this
    picks one of the configurations that reliably does on THIS image, to
    demonstrate the mechanism works at all. The 41.9% recall figure is the
    honest overall claim, not this test.
    """
    img = _person_a_face_crop_bgr()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    halftone_gray = _apply_synthetic_halftone(gray)
    halftone_bgr = cv2.cvtColor(halftone_gray, cv2.COLOR_GRAY2BGR)

    result = FaceDetectorAndVerifier.analyze_frequency_artifacts(halftone_bgr)
    assert result["frequency_artifact_detected"] is True
    assert result["moire_energy_concentration"] > FaceDetectorAndVerifier.FREQ_ARTIFACT_CONCENTRATION_THRESHOLD


def test_frequency_artifacts_handles_an_all_zero_crop_without_crashing():
    """
    An all-zero crop is the true zero-energy degenerate case: 0 times the
    Hann window is still 0 everywhere, so its FFT magnitude is 0 in the
    band too -- must return a clean not-detected result rather than
    dividing by zero (total_energy <= 0 short-circuit).

    NOT the same as a uniform mid-gray crop: multiplying a nonzero constant
    by the Hann window produces the WINDOW's own frequency content (a real,
    nonzero spectrum, not a degenerate one) -- a genuinely blank live
    capture would in practice already be caught by check_quality's
    is_blurry check (zero Laplacian variance) well before this signal is
    reached.
    """
    zeros = np.zeros((160, 160, 3), dtype=np.uint8)
    result = FaceDetectorAndVerifier.analyze_frequency_artifacts(zeros)
    assert result["frequency_artifact_detected"] is False
    assert result["moire_energy_concentration"] == 0.0


def test_check_quality_surfaces_frequency_fields_and_discounts_liveness_score():
    """check_quality (the method face_service.py actually calls) must wire
    analyze_frequency_artifacts's output through -- both as its own fields
    and as a discount on the coarse liveness_score heuristic -- not just
    compute it and drop it."""
    img = _person_a_face_crop_bgr()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    moire_bgr = cv2.cvtColor(_apply_synthetic_moire(gray), cv2.COLOR_GRAY2BGR)

    clean_quality = _det.check_quality(img)
    moire_quality = _det.check_quality(moire_bgr)

    assert clean_quality["frequency_artifact_detected"] is False
    assert moire_quality["frequency_artifact_detected"] is True
    assert moire_quality["liveness_score"] < clean_quality["liveness_score"]


def test_specimen_with_embedded_real_photo_is_detected_as_a_face():
    """The fix: passing a real face_photo_path makes the portrait region an
    actual detectable, embeddable face."""
    with tempfile.TemporaryDirectory() as tmp:
        doc_path = os.path.join(tmp, "real_face_doc.jpg")
        SyntheticDocumentGenerator.generate_document(
            out_path=doc_path, mode="genuine", surname="TEST", given_names="USER",
            face_photo_path=PERSON_A
        )
        img = cv2.imread(doc_path)
        doc_left_roi = img[:, 0:int(img.shape[1] * 0.55)]
        rgb = cv2.cvtColor(doc_left_roi, cv2.COLOR_BGR2RGB)
        boxes, probs = _det.mtcnn.detect(rgb)
        assert boxes is not None
        assert len(boxes) >= 1
