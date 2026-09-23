import os
import cv2
import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from app.core.config import settings
from app.ml.face_verifier import FaceDetectorAndVerifier

class BaseFaceService(ABC):
    @abstractmethod
    def verify(self, document_image_path: str, live_image_path: str, case_id: str) -> Dict[str, Any]:
        """Compares document portrait to live face capture."""
        pass

class FaceVerificationService(BaseFaceService):
    # Calibrated against the LFW face-verification benchmark (500 genuine +
    # 500 impostor pairs) -- see scripts/calibrate_face_threshold.py. At 0.72:
    # 98.0% accuracy, 0.60% false-accept rate, 3.40% false-reject rate.
    # Returned in every result below so the UI displays this real number
    # instead of a value someone has to remember to keep in sync by hand.
    #
    # A FG-NET-only fine-tuned embedder was briefly wired in and recalibrated
    # (threshold 0.70) but reverted: it regressed same-age LFW verification
    # hard -- false-accept rate 0.60% -> 10.20%, a ~17x increase -- because it
    # was trained on only 82 cross-age identities with no same-age diversity.
    # That checkpoint is preserved for reference at
    # backend/app/ml/weights/face_embedder_finetuned.fgnet_only_SANITY_CHECK.pth.bak
    # (renamed so face_verifier.py's auto-load no longer picks it up). Do not
    # re-wire it in; wait for the intended combined FG-NET+YLFW fine-tune
    # (scripts/finetune_face_embedder.py) and recalibrate against that instead.
    MATCH_THRESHOLD = 0.72

    def __init__(self):
        self.detector = FaceDetectorAndVerifier()

    def crop_and_save(self, img_bgr: np.ndarray, bbox: tuple, out_path: str) -> str:
        x, y, w, h = bbox
        # Add slight padding
        pad_x, pad_y = int(w * 0.15), int(h * 0.15)
        ih, iw = img_bgr.shape[:2]
        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)
        x2 = min(iw, x + w + pad_x)
        y2 = min(ih, y + h + pad_y)
        crop = img_bgr[y1:y2, x1:x2]
        cv2.imwrite(out_path, crop)
        return out_path

    def verify(self, document_image_path: str, live_image_path: str, case_id: str) -> Dict[str, Any]:
        if not os.path.exists(document_image_path):
            raise FileNotFoundError(f"Document image not found: {document_image_path}")
        if not os.path.exists(live_image_path):
            raise FileNotFoundError(f"Live capture image not found: {live_image_path}")

        doc_img = cv2.imread(document_image_path)
        live_img = cv2.imread(live_image_path)

        if doc_img is None or live_img is None:
            raise ValueError("Unable to load document or live image for face verification.")

        # Detect face in document
        # In travel documents, prioritize left side of document
        dh, dw = doc_img.shape[:2]
        doc_left_roi = doc_img[:, 0:int(dw * 0.55)]
        # A passport-style inset portrait is a modest fraction of the ROI; bound the
        # detection so a false-positive on document artwork/background isn't mistaken
        # for the portrait, and give an explicit fallback region sized for this
        # specific (left-cropped) ROI rather than a generic aspect-ratio guess
        # (see FaceDetectorAndVerifier.detect_face).
        doc_faces = self.detector.detect_face(
            doc_left_roi, max_w_ratio=0.55, max_h_ratio=0.75,
            fallback_rect=(0.05, 0.12, 0.45, 0.55)
        )

        # Fallback to whole doc if not found in left side
        if not doc_faces:
            doc_faces = self.detector.detect_face(
                doc_img, max_w_ratio=0.4, max_h_ratio=0.75,
                fallback_rect=(0.05, 0.15, 0.35, 0.55)
            )

        # Detect face in live image (subject typically fills most of a selfie frame)
        live_faces = self.detector.detect_face(
            live_img, fallback_rect=(0.15, 0.15, 0.70, 0.70)
        )

        crops_dir = os.path.join(settings.UPLOAD_DIR, "crops")
        doc_crop_path = os.path.join(crops_dir, f"{case_id}_doc_face.jpg")
        live_crop_path = os.path.join(crops_dir, f"{case_id}_live_face.jpg")

        doc_face_url = None
        live_face_url = None

        if not doc_faces:
            # Fallback: extract expected passport photo rectangle
            px, py, pw, ph = int(dw * 0.05), int(dh * 0.15), int(dw * 0.35), int(dh * 0.55)
            self.crop_and_save(doc_img, (px, py, pw, ph), doc_crop_path)
            doc_face_url = f"/uploads/crops/{case_id}_doc_face.jpg"
            
            return {
                "similarity": 0.0,
                "status": "NO_FACE_DETECTED",
                "document_face_url": doc_face_url,
                "live_face_url": None,
                "quality_checks": {"issue": "Could not detect clear face in document photo"},
                "anti_spoofing_score": 0.5,
                "match_threshold": self.MATCH_THRESHOLD,
                "signals": [{
                    "module": "FACE",
                    "signal": "Document Portrait Undetected",
                    "severity": "HIGH",
                    "confidence": 0.90,
                    "explanation": "Automated face detector could not isolate a clear frontal portrait in document image.",
                    "score_impact": 20.0
                }]
            }

        if len(doc_faces) > 1:
            # Symmetric with the live-capture multiplicity check below --
            # previously only the live side flagged this; a document image
            # with more than one plausible face region (background pattern,
            # hologram, a splice with two portraits) silently used
            # doc_faces[0] (whatever order the detector happened to return)
            # with no signal at all.
            self.crop_and_save(doc_img, doc_faces[0], doc_crop_path)
            return {
                "similarity": 0.0,
                "status": "MULTIPLE_FACES",
                "document_face_url": f"/uploads/crops/{case_id}_doc_face.jpg",
                "live_face_url": None,
                "quality_checks": {"multiple_faces_detected": len(doc_faces)},
                "anti_spoofing_score": 0.4,
                "match_threshold": self.MATCH_THRESHOLD,
                "signals": [{
                    "module": "FACE",
                    "signal": "Multiple Faces in Document Image",
                    "severity": "MEDIUM",
                    "confidence": 0.85,
                    "explanation": "More than one plausible face region detected in the document image. Manual review required.",
                    "score_impact": 15.0
                }]
            }

        if not live_faces:
            # Document face was found
            self.crop_and_save(doc_img, doc_faces[0], doc_crop_path)
            return {
                "similarity": 0.0,
                "status": "NO_FACE_DETECTED",
                "document_face_url": f"/uploads/crops/{case_id}_doc_face.jpg",
                "live_face_url": None,
                "quality_checks": {"issue": "No face found in live capture"},
                "anti_spoofing_score": 0.5,
                "match_threshold": self.MATCH_THRESHOLD,
                "signals": [{
                    "module": "FACE",
                    "signal": "Live Subject Face Not Detected",
                    "severity": "HIGH",
                    "confidence": 0.90,
                    "explanation": "No face identified in the live webcam/capture frame. Re-take photo.",
                    "score_impact": 20.0
                }]
            }

        if len(live_faces) > 1:
            return {
                "similarity": 0.0,
                "status": "MULTIPLE_FACES",
                "document_face_url": None,
                "live_face_url": None,
                "quality_checks": {"multiple_faces_detected": len(live_faces)},
                "anti_spoofing_score": 0.4,
                "match_threshold": self.MATCH_THRESHOLD,
                "signals": [{
                    "module": "FACE",
                    "signal": "Multiple Faces in Live Capture",
                    "severity": "MEDIUM",
                    "confidence": 0.95,
                    "explanation": "More than one person detected in live capture frame. Individual screening required.",
                    "score_impact": 15.0
                }]
            }

        # Crop both faces
        self.crop_and_save(doc_img, doc_faces[0], doc_crop_path)
        self.crop_and_save(live_img, live_faces[0], live_crop_path)
        doc_face_url = f"/uploads/crops/{case_id}_doc_face.jpg"
        live_face_url = f"/uploads/crops/{case_id}_live_face.jpg"

        # Quality check on live face
        lx, ly, lw, lh = live_faces[0]
        live_crop_bgr = live_img[ly:ly+lh, lx:lx+lw]
        quality = self.detector.check_quality(live_crop_bgr)

        # Extract embeddings and compute similarity
        dx, dy, dw_f, dh_f = doc_faces[0]
        doc_crop_bgr = doc_img[dy:dy+dh_f, dx:dx+dw_f]
        
        emb_doc = self.detector.extract_embedding(doc_crop_bgr)
        emb_live = self.detector.extract_embedding(live_crop_bgr)
        similarity = self.detector.compare_faces(emb_doc, emb_live)

        is_match = similarity >= self.MATCH_THRESHOLD
        status = "MATCH" if is_match else "REVIEW_REQUIRED"

        signals = []
        if not is_match:
            signals.append({
                "module": "FACE",
                "signal": "Biometric Face Mismatch",
                "severity": "HIGH",
                "confidence": round(1.0 - similarity, 2),
                "explanation": f"Live face biometric similarity score ({round(similarity*100, 1)}%) is below verification threshold ({self.MATCH_THRESHOLD*100:.0f}%). Manual identity review required.",
                "score_impact": 25.0
            })
        if quality.get("is_blurry") or quality.get("is_dark"):
            signals.append({
                "module": "FACE",
                "signal": "Sub-Optimal Biometric Quality",
                "severity": "LOW",
                "confidence": 0.85,
                "explanation": "Live facial capture exhibits suboptimal lighting or motion blur.",
                "score_impact": 5.0
            })

        return {
            "similarity": round(similarity, 3),
            "status": status,
            "document_face_url": doc_face_url,
            "live_face_url": live_face_url,
            "quality_checks": quality,
            "anti_spoofing_score": quality.get("liveness_score", 0.95),
            "match_threshold": self.MATCH_THRESHOLD,
            "signals": signals,
            # The live capture's own embedding -- feeds the cross-case
            # duplicate-identity gallery (identity_gallery_service.py). Only
            # ever the LIVE embedding, never the document photo's: the
            # question that answers is "has this real, physically-present
            # person been screened before under a different claimed
            # identity," not anything about the printed document photo.
            "live_embedding": emb_live.tolist() if emb_live is not None else None
        }

def get_face_service() -> BaseFaceService:
    return FaceVerificationService()
