"""
Regression guard for FaceVerificationService.verify()'s handling of multiple
detected faces. The live-capture side explicitly detects and flags this
(status "MULTIPLE_FACES"); the document side had no equivalent check -- if
the detector found more than one plausible face region in the document
image (background pattern, hologram, a splice with two portraits), the code
silently used doc_faces[0] (whatever order the detector happened to return)
with no signal raised at all, unlike the symmetric live-face path.

Uses a lightweight PIL-generated image and a monkeypatched detector so this
doesn't need to load the real MTCNN/InceptionResnetV1 models.
"""
import os

from PIL import Image

from app.services.face_service import FaceVerificationService


class _FakeDetector:
    """Reports two plausible face boxes on the FIRST call (the document
    side's detect_face call, which happens first in verify()) and exactly
    one box on every call after that (the live-capture side) -- isolates
    testing the document-side multiplicity gap specifically, independent of
    the live-side check that already exists."""

    def __init__(self):
        self.call_count = 0

    def detect_face(self, img_bgr, max_w_ratio=1.0, max_h_ratio=1.0, fallback_rect=None):
        self.call_count += 1
        if self.call_count == 1:
            return [(5, 5, 20, 20), (40, 40, 20, 20)]
        return [(5, 5, 20, 20)]


def _make_image(path, size=(100, 100)):
    Image.new("RGB", size, "white").save(path)


def test_multiple_document_faces_are_flagged_not_silently_picked(tmp_path):
    doc_path = str(tmp_path / "doc.jpg")
    live_path = str(tmp_path / "live.jpg")
    _make_image(doc_path)
    _make_image(live_path)

    service = FaceVerificationService()
    service.detector = _FakeDetector()

    result = service.verify(doc_path, live_path, "test-case-multi-doc-face")

    assert result["status"] == "MULTIPLE_FACES"
    assert any(
        sig["module"] == "FACE" and "Multiple" in sig["signal"] and "document" in sig["explanation"].lower()
        for sig in result["signals"]
    )
