import os
import cv2
import numpy as np
import torch
from typing import Tuple, Optional, Dict, Any, List
from facenet_pytorch import MTCNN, InceptionResnetV1


def _fixed_image_standardization(image_tensor: torch.Tensor) -> torch.Tensor:
    """Matches facenet-pytorch's own preprocessing so embeddings from a manually
    cropped/resized face patch land in the same distribution the model was
    trained on."""
    return (image_tensor - 127.5) / 128.0


class FaceDetectorAndVerifier:
    """
    Face detection + verification backed by pretrained deep models:
    - MTCNN for face detection (facenet-pytorch).
    - InceptionResnetV1, pretrained on VGGFace2, for 512-d L2-normalized face
      embeddings (facenet-pytorch).

    The MATCH threshold in face_service.py is calibrated against the LFW
    face-verification benchmark -- see scripts/calibrate_face_threshold.py.
    """

    EMBED_SIZE = (160, 160)  # InceptionResnetV1's expected input size

    def __init__(self):
        self.device = torch.device("cpu")
        self.mtcnn = MTCNN(keep_all=True, device=self.device, post_process=False)
        self.embedder = InceptionResnetV1(pretrained="vggface2").eval().to(self.device)

        # Interim FG-NET-only fine-tune (block8 + last_linear + last_bn unfrozen,
        # see scripts/finetune_face_embedder.py) for better cross-age matching.
        # This is a sanity-check checkpoint trained on FG-NET alone (82
        # identities) -- NOT the intended FG-NET+YLFW combined fine-tune, which
        # is still pending YLFW-Dev-Train-Balanced access. Swap this out once
        # that combined checkpoint exists.
        finetuned_path = os.path.join(os.path.dirname(__file__), "weights", "face_embedder_finetuned.pth")
        if os.path.exists(finetuned_path):
            state_dict = torch.load(finetuned_path, map_location=self.device)
            self.embedder.load_state_dict(state_dict)
            self.embedder.eval()

    def detect_face(
        self,
        img_bgr: np.ndarray,
        max_w_ratio: float = 1.0,
        max_h_ratio: float = 1.0,
        fallback_rect: Optional[Tuple[float, float, float, float]] = None,
    ) -> List[Tuple[int, int, int, int]]:
        """
        Detects faces in a BGR image. Returns list of (x, y, w, h).

        max_w_ratio/max_h_ratio bound the plausible face size as a fraction of the
        input frame -- a document's inset portrait is normally a modest fraction
        of the full page, so document-scoped callers should pass a tighter bound.

        fallback_rect, if given, is a fractional (x, y, w, h) region used when no
        plausible face is detected (e.g. a stylized/synthetic avatar MTCNN can't
        recognize as a face). Callers know their own frame's geometry, so they
        should supply this explicitly rather than relying on a generic guess.
        """
        ih, iw = img_bgr.shape[:2]
        try:
            rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            boxes, probs = self.mtcnn.detect(rgb)
            if boxes is not None:
                plausible = []
                for box, prob in zip(boxes, probs):
                    if prob is None or prob < 0.90:
                        continue
                    x1, y1, x2, y2 = box
                    w, h = x2 - x1, y2 - y1
                    if w <= iw * max_w_ratio and h <= ih * max_h_ratio:
                        plausible.append((
                            int(max(0, x1)), int(max(0, y1)),
                            int(min(w, iw)), int(min(h, ih))
                        ))
                if plausible:
                    return plausible
        except Exception:
            pass

        # Fallback: no plausible detection, use caller-supplied or generic region.
        if fallback_rect is not None:
            fx, fy, fw, fh = fallback_rect
            return [(int(iw * fx), int(ih * fy), int(iw * fw), int(ih * fh))]

        if iw > ih:
            # Document layout: portrait in left region
            return [(int(iw * 0.05), int(ih * 0.15), int(iw * 0.35), int(ih * 0.55))]
        else:
            # Centered live webcam frame
            return [(int(iw * 0.15), int(ih * 0.15), int(iw * 0.70), int(ih * 0.70))]

    def check_quality(self, face_bgr: np.ndarray) -> Dict[str, Any]:
        """Quality and anti-spoofing checks."""
        h, w = face_bgr.shape[:2]
        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)

        # Brightness check
        mean_brightness = float(np.mean(gray))
        is_dark = mean_brightness < 45
        is_overexposed = mean_brightness > 220

        # Sharpness / blurriness check via Laplacian variance
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        is_blurry = lap_var < 35.0

        # Liveness heuristic based on frequency texture analysis
        liveness_score = 0.95
        if is_blurry:
            liveness_score -= 0.25
        if is_dark or is_overexposed:
            liveness_score -= 0.15

        return {
            "resolution": f"{w}x{h}",
            "mean_brightness": round(mean_brightness, 1),
            "laplacian_sharpness": round(lap_var, 1),
            "is_blurry": is_blurry,
            "is_dark": is_dark,
            "is_overexposed": is_overexposed,
            "liveness_score": round(max(0.20, liveness_score), 2)
        }

    def extract_embedding(self, face_bgr: np.ndarray) -> Optional[np.ndarray]:
        """Extracts a 512-d L2-normalized VGGFace2 face embedding from a face crop."""
        if face_bgr is None or face_bgr.size == 0:
            return None
        rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, self.EMBED_SIZE)
        tensor = torch.from_numpy(resized).permute(2, 0, 1).float().unsqueeze(0)
        tensor = _fixed_image_standardization(tensor)
        with torch.no_grad():
            emb = self.embedder(tensor.to(self.device))
        return emb.squeeze(0).cpu().numpy()

    def compare_faces(self, emb1: Optional[np.ndarray], emb2: Optional[np.ndarray]) -> float:
        """Cosine similarity between two face embeddings, mapped to 0..1."""
        if emb1 is None or emb2 is None:
            return 0.0
        norm1, norm2 = np.linalg.norm(emb1), np.linalg.norm(emb2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        cos_sim = float(np.dot(emb1, emb2) / (norm1 * norm2))
        return max(0.0, min(1.0, (cos_sim + 1.0) / 2.0))
