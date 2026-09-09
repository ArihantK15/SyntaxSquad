"""
One-off calibration script (not part of the app runtime).

Downloads the standard LFW face-verification test pairs (500 genuine "same
person" pairs, 500 impostor "different person" pairs) via scikit-learn and
uses them to pick a defensible MATCH threshold for the facenet-pytorch
(MTCNN + InceptionResnetV1/VGGFace2) similarity score used in
backend/app/ml/face_verifier.py.

Run with: SSL_CERT_FILE=$(python3 -c "import certifi;print(certifi.where())") \
  venv/bin/python3 scripts/calibrate_face_threshold.py
"""
import sys
import os
import time
import numpy as np
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sklearn.datasets import fetch_lfw_pairs
from app.ml.face_verifier import FaceDetectorAndVerifier


def main():
    print("Loading LFW test pairs...")
    data = fetch_lfw_pairs(subset="test", color=True, resize=1.0)
    pairs = data.pairs  # (1000, 2, H, W, 3), float in [0,1]
    labels = data.target  # 1 = same person, 0 = different

    det = FaceDetectorAndVerifier()
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

        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(pairs)} pairs processed ({time.time() - t0:.0f}s elapsed)")

    scores = np.array(scores)
    kept_labels = np.array(kept_labels)
    print(f"\nProcessed {len(scores)}/{len(pairs)} pairs "
          f"({no_face_count} skipped, no face detected in one or both images)")

    genuine = scores[kept_labels == 1]
    impostor = scores[kept_labels == 0]
    print(f"\nGenuine (same person)   pairs: n={len(genuine)}  mean={genuine.mean():.3f}  "
          f"std={genuine.std():.3f}  min={genuine.min():.3f}  max={genuine.max():.3f}")
    print(f"Impostor (diff person)  pairs: n={len(impostor)}  mean={impostor.mean():.3f}  "
          f"std={impostor.std():.3f}  min={impostor.min():.3f}  max={impostor.max():.3f}")

    best_thresh, best_acc = None, -1
    for t in np.arange(0.05, 0.95, 0.01):
        preds = scores >= t
        acc = (preds == kept_labels.astype(bool)).mean()
        if acc > best_acc:
            best_acc, best_thresh = acc, t

    preds = scores >= best_thresh
    tp = ((preds == 1) & (kept_labels == 1)).sum()
    fp = ((preds == 1) & (kept_labels == 0)).sum()
    tn = ((preds == 0) & (kept_labels == 0)).sum()
    fn = ((preds == 0) & (kept_labels == 1)).sum()

    print(f"\n=== Optimal threshold: {best_thresh:.2f} ===")
    print(f"Accuracy: {best_acc:.3%}")
    print(f"True positive (correct MATCH):        {tp}")
    print(f"False positive (wrong MATCH):          {fp}  <- false-accept rate: {fp / (fp + tn):.2%}")
    print(f"True negative (correct REVIEW):        {tn}")
    print(f"False negative (wrong REVIEW):          {fn}  <- false-reject rate: {fn / (fn + tp):.2%}")


if __name__ == "__main__":
    main()
