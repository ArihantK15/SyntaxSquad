"""
"Same-age LFW regression check" -- run this against ANY candidate face
embedder checkpoint BEFORE wiring it into face_verifier.py, to confirm it
doesn't regress same-age verification accuracy before deploying it.

Same methodology and dataset as scripts/calibrate_face_threshold.py (500
genuine "same person" pairs, 500 impostor "different person" pairs, via
scikit-learn's LFW test split) -- this script exists separately so a
candidate checkpoint can be evaluated WITHOUT touching face_verifier.py's
loading path or source at all: it builds a normal FaceDetectorAndVerifier
(which loads only what's already wired in, i.e. currently the stock
VGGFace2 embedder) and, if --weights is passed, swaps the candidate
state_dict into that already-constructed instance's embedder in memory
for this evaluation run only. Nothing on disk under
backend/app/ml/weights/ is read or written by this script.

Run with:
    .venv-train/Scripts/python.exe scripts/evaluate_lfw_same_age.py
    .venv-train/Scripts/python.exe scripts/evaluate_lfw_same_age.py --weights path/to/candidate.pth
"""
import argparse
import os
import sys
import time
from typing import Optional

import numpy as np
import torch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sklearn.datasets import fetch_lfw_pairs
from app.ml.face_verifier import FaceDetectorAndVerifier

# Mirrors FaceVerificationService.MATCH_THRESHOLD (backend/app/services/face_service.py)
# -- not imported directly since face_service.py pulls in app.core.config, which
# needs pydantic_settings (a backend-only dependency not installed in .venv-train).
PRODUCTION_MATCH_THRESHOLD = 0.72


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", default=None, help="Candidate embedder state_dict .pth to evaluate instead of the stock/currently-wired embedder.")
    args = parser.parse_args()

    print("Loading LFW test pairs (500 genuine, 500 impostor)...")
    data = fetch_lfw_pairs(subset="test", color=True, resize=1.0)
    pairs = data.pairs  # (1000, 2, H, W, 3), float in [0,1]
    labels = data.target  # 1 = same person, 0 = different

    det = FaceDetectorAndVerifier()
    if args.weights:
        print(f"Loading candidate embedder weights from {args.weights} (in-memory only -- "
              f"not touching backend/app/ml/weights/ on disk)")
        state_dict = torch.load(args.weights, map_location=det.device)
        det.embedder.load_state_dict(state_dict)
        det.embedder.eval()
    else:
        print("Evaluating the stock/currently-wired embedder (no --weights given).")

    production_threshold = PRODUCTION_MATCH_THRESHOLD

    # LFW images are small (125x94) headshots -- if MTCNN can't find a face at
    # that resolution, fall back to treating the whole (already-cropped) frame
    # as the face, same convention as a live selfie capture in face_service.py.
    fallback = (0.05, 0.05, 0.90, 0.90)

    def embed(img_rgb: np.ndarray) -> Optional[np.ndarray]:
        img_bgr = img_rgb[:, :, ::-1].copy()
        boxes = det.detect_face(img_bgr, fallback_rect=fallback)
        if not boxes:
            return None
        x, y, w, h = boxes[0]
        crop = img_bgr[y:y + h, x:x + w]
        if crop.size == 0:
            return None
        return det.extract_embedding(crop)

    scores = []
    kept_labels = []
    no_face_count = 0
    t0 = time.time()

    for i in range(len(pairs)):
        img_a = (pairs[i, 0] * 255).astype(np.uint8)
        img_b = (pairs[i, 1] * 255).astype(np.uint8)

        emb_a = embed(img_a)
        emb_b = embed(img_b)

        if emb_a is None or emb_b is None:
            no_face_count += 1
            continue

        score = det.compare_faces(emb_a, emb_b)
        scores.append(score)
        kept_labels.append(labels[i])

        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(pairs)} pairs processed ({time.time() - t0:.0f}s elapsed)")

    scores = np.array(scores)
    kept_labels = np.array(kept_labels)
    print(f"\nProcessed {len(scores)}/{len(pairs)} pairs "
          f"({no_face_count} skipped, no face detected in one or both images)")

    genuine = scores[kept_labels == 1]
    impostor = scores[kept_labels == 0]
    print(f"Genuine (same person)   pairs: n={len(genuine)}  mean={genuine.mean():.3f}  std={genuine.std():.3f}")
    print(f"Impostor (diff person)  pairs: n={len(impostor)}  mean={impostor.mean():.3f}  std={impostor.std():.3f}")

    def report_at_threshold(t: float, label: str):
        preds = scores >= t
        acc = (preds == kept_labels.astype(bool)).mean()
        tp = ((preds == 1) & (kept_labels == 1)).sum()
        fp = ((preds == 1) & (kept_labels == 0)).sum()
        tn = ((preds == 0) & (kept_labels == 0)).sum()
        fn = ((preds == 0) & (kept_labels == 1)).sum()
        far = fp / (fp + tn) if (fp + tn) else float("nan")
        frr = fn / (fn + tp) if (fn + tp) else float("nan")
        print(f"\n=== {label} (threshold={t:.2f}) ===")
        print(f"Accuracy: {acc:.3%}")
        print(f"False-accept rate (impostor scored as MATCH): {far:.3%}")
        print(f"False-reject rate (genuine scored as no-MATCH): {frr:.3%}")
        return acc

    report_at_threshold(production_threshold, "At current production MATCH_THRESHOLD")

    best_thresh, best_acc = None, -1
    for t in np.arange(0.05, 0.95, 0.01):
        preds = scores >= t
        acc = (preds == kept_labels.astype(bool)).mean()
        if acc > best_acc:
            best_acc, best_thresh = acc, t
    report_at_threshold(best_thresh, "At best achievable threshold for this embedder")


if __name__ == "__main__":
    main()
