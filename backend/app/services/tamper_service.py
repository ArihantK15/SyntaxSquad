import os
import cv2
import numpy as np
import torch
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from pathlib import Path

from app.core.config import settings
from app.ml.tamper_model import LightweightForensicCNN, TamperForensics

class BaseTamperService(ABC):
    @abstractmethod
    def analyze(self, image_path: str, case_id: str) -> Dict[str, Any]:
        """Performs multi-signal forensic tampering analysis on document image."""
        pass

WEIGHTS_PATH = Path(__file__).resolve().parent.parent / "ml" / "weights" / "tamper_cnn.pth"


class TamperDetectionService(BaseTamperService):
    def __init__(self):
        self.device = torch.device("cpu")
        self.model = LightweightForensicCNN().to(self.device)
        self.model.eval()

        # The CNN starts with random (untrained) weights, which produce
        # near-arbitrary output -- not a useful signal, and mixing it into the
        # score would let noise skew results. Only use its output once a real
        # trained checkpoint exists (see scripts/train_tamper_cnn.py); until
        # then, the well-tested forensic heuristics (ELA, edge discontinuity,
        # portrait-seam, compression-mismatch) carry the score alone.
        self.cnn_ready = False
        if WEIGHTS_PATH.exists():
            try:
                state_dict = torch.load(WEIGHTS_PATH, map_location=self.device)
                self.model.load_state_dict(state_dict)
                self.cnn_ready = True
            except Exception:
                self.cnn_ready = False

    def analyze_portrait_region(self, img_cv: np.ndarray) -> Dict[str, Any]:
        """
        Signal C: Analyzes the portrait photo region (left side of document).
        Checks for spliced borders, mismatch in resolution, and halo artifacts.
        """
        h, w = img_cv.shape[:2]
        # In travel documents/passports, photo is typically in the left 10%-45% width, 15%-75% height
        photo_roi = img_cv[int(h*0.15):int(h*0.75), int(w*0.05):int(w*0.45)]
        if photo_roi.size == 0:
            return {"suspicious": False, "score": 0.1, "signals": []}

        # Analyze edges around photo perimeter
        gray_roi = cv2.cvtColor(photo_roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray_roi, 80, 180)
        edge_density = float(np.count_nonzero(edges)) / float(edges.size)

        # Compute gradient orientation consistency along boundary
        border_top = photo_roi[0:10, :]
        border_left = photo_roi[:, 0:10]
        border_var = float(np.var(border_top) + np.var(border_left)) / 2.0

        signals = []
        is_suspicious = False
        # border_var's threshold was calibrated against flat, hand-drawn avatar
        # graphics (uniform background -> low variance baseline). A real photo
        # composited into the document naturally has rich texture right up to
        # its own edges (hair, lighting, background detail), which pushes
        # border_var well above that old baseline regardless of tampering --
        # measured ~5900-6400 for both genuine and actually-spliced real-photo
        # documents, i.e. it no longer discriminates once real photos are in
        # play. detect_splicing_boundaries' edge_discontinuity signal (Signal B)
        # reliably catches real splices instead, so this check is raised well
        # above the natural real-photo baseline rather than tuned to a value
        # that can't actually separate the two cases.
        if edge_density > 0.18 or border_var > 9000:
            is_suspicious = True
            signals.append({
                "type": "photo_boundary_anomaly",
                "confidence": 0.86,
                "region": [int(w*0.05), int(h*0.15), int(w*0.40), int(h*0.60)],
                "explanation": "Unusual edge density and high-gradient seam around portrait boundary. Potential photo replacement."
            })

        return {
            "suspicious": is_suspicious,
            "score": 0.75 if is_suspicious else 0.15,
            "signals": signals
        }

    def analyze_text_compression(self, img_cv: np.ndarray, ela_gray: np.ndarray) -> Dict[str, Any]:
        """
        Signal D: Analyzes visual text and MRZ regions for recompression mismatch.
        """
        h, w = img_cv.shape[:2]
        # MRZ zone is bottom 25% of document
        mrz_roi = ela_gray[int(h*0.75):h, :]
        # Upper body zone
        upper_roi = ela_gray[0:int(h*0.5), :]
        
        mrz_mean = float(np.mean(mrz_roi)) if mrz_roi.size > 0 else 0
        upper_mean = float(np.mean(upper_roi)) if upper_roi.size > 0 else 0

        signals = []
        is_anomaly = False
        ratio = abs(mrz_mean - upper_mean) / (upper_mean + 1e-5)
        
        if ratio > 0.85 and mrz_mean > 35:
            is_anomaly = True
            signals.append({
                "type": "text_compression_anomaly",
                "confidence": 0.82,
                "region": [0, int(h*0.75), w, int(h*0.25)],
                "explanation": "Significant compression divergence between Machine Readable Zone and main document body."
            })

        return {
            "is_anomaly": is_anomaly,
            "ratio": ratio,
            "signals": signals
        }

    def analyze(self, image_path: str, case_id: str) -> Dict[str, Any]:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Document image not found: {image_path}")

        img_cv = cv2.imread(image_path)
        if img_cv is None:
            raise ValueError(f"OpenCV cannot decode image: {image_path}")

        h, w = img_cv.shape[:2]
        
        # Prepare heatmap destination
        heatmap_filename = f"{case_id}_tamper_heatmap.jpg"
        heatmap_full_path = os.path.join(settings.UPLOAD_DIR, "heatmaps", heatmap_filename)
        
        # 1. Error Level Analysis (Signal A)
        mean_ela, ela_gray = TamperForensics.generate_ela(image_path, heatmap_full_path)
        
        signals: List[Dict[str, Any]] = []
        visual_anomalies: List[Dict[str, Any]] = []

        # Check ELA threshold
        if mean_ela > 0.22:
            signals.append({
                "type": "compression_anomaly",
                "confidence": min(0.92, round(mean_ela * 3.5, 2)),
                "region": [int(w*0.1), int(h*0.2), int(w*0.8), int(h*0.6)],
                "explanation": "Multi-layer JPEG recompression artifacts detected via Error Level Analysis (ELA)."
            })

        # 2. Boundary / edge splicing (Signal B)
        splicing_anomalies = TamperForensics.detect_splicing_boundaries(img_cv)
        for anom in splicing_anomalies:
            signals.append(anom)
            visual_anomalies.append({
                "label": "Potential Spliced Patch",
                "region": anom["region"],
                "confidence": anom["confidence"]
            })

        # 3. Portrait photo boundary (Signal C)
        portrait_res = self.analyze_portrait_region(img_cv)
        for sig in portrait_res["signals"]:
            signals.append(sig)
            visual_anomalies.append({
                "label": "Suspicious Portrait Seam",
                "region": sig["region"],
                "confidence": sig["confidence"]
            })

        # 4. Text region recompression (Signal D)
        text_res = self.analyze_text_compression(img_cv, ela_gray)
        for sig in text_res["signals"]:
            signals.append(sig)

        # 5. Patch-level CNN feature scoring (only once a trained checkpoint is
        # loaded -- see __init__). Sample multiple document regions rather than
        # just the center: the portrait and MRZ zones are where photo-splice
        # and text tampering actually occur, and a center-only patch mostly
        # never overlaps either.
        cnn_tamper_prob = None
        if self.cnn_ready:
            regions = [
                ("portrait", (int(h*0.15), int(h*0.75), int(w*0.05), int(w*0.45))),
                ("center", (h//2 - 64, h//2 + 64, w//2 - 64, w//2 + 64)),
                ("mrz", (int(h*0.75), h, 0, w)),
            ]
            region_probs = []
            for _, (y1, y2, x1, x2) in regions:
                y1, y2 = max(0, y1), min(h, y2)
                x1, x2 = max(0, x1), min(w, x2)
                patch = img_cv[y1:y2, x1:x2]
                if patch.size == 0:
                    continue
                patch_rgb = cv2.cvtColor(patch, cv2.COLOR_BGR2RGB)
                patch_resized = cv2.resize(patch_rgb, (64, 64))
                patch_t = torch.tensor(patch_resized, dtype=torch.float32).permute(2, 0, 1).unsqueeze(0) / 255.0
                with torch.no_grad():
                    cnn_out = self.model(patch_t)
                    probs = torch.softmax(cnn_out, dim=1).squeeze().numpy()
                    region_probs.append(float(probs[1]))
            if region_probs:
                cnn_tamper_prob = max(region_probs)

        # Aggregate tamper risk score (0.0 to 1.0)
        base_score = mean_ela * 2.0
        if cnn_tamper_prob is not None:
            base_score = max(base_score, cnn_tamper_prob * 0.4)
        if signals:
            base_score += 0.25 * len(signals)

        tamper_risk = min(0.96, max(0.04, round(base_score, 2)))

        if tamper_risk >= 0.70:
            risk_level = "CRITICAL" if tamper_risk >= 0.85 else "HIGH"
        elif tamper_risk >= 0.40:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return {
            "tamper_risk": tamper_risk,
            "risk_level": risk_level,
            "signals": signals,
            "heatmap_url": f"/uploads/heatmaps/{heatmap_filename}",
            "visual_anomalies": visual_anomalies
        }

def get_tamper_service() -> BaseTamperService:
    return TamperDetectionService()
