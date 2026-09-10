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
