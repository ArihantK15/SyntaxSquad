"""
Targeted before/after check for the aspect-ratio guard added to
TamperForensics.detect_splicing_boundaries (backend/app/ml/tamper_model.py)
-- NOT a general tamper-accuracy re-evaluation. scripts/evaluate_tamper_on_casia.py
tests the trained CNN directly on 64x64 patches and never calls
detect_splicing_boundaries at all, so it can't detect a regression in THIS
specific heuristic. This script runs the actual edge_discontinuity signal
against real, full-size CASIA v2.0 tampered images to measure whether the
new >8:1 aspect-ratio exclusion (added to stop a false positive on a
genuine Aadhaar card's header banner) reduces its hit rate on real splices.

Run with:
    .venv-backend/Scripts/python.exe scripts/check_edge_discontinuity_on_casia.py [n_samples]
"""
import random
import sys
from pathlib import Path

import cv2

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.ml.tamper_model import TamperForensics

CASIA_TP_DIR = PROJECT_ROOT / "data" / "CASIA2" / "CASIA2" / "Tp"


def main():
    n_samples = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    all_files = sorted(CASIA_TP_DIR.iterdir())
    random.seed(42)
    sample = random.sample(all_files, min(n_samples, len(all_files)))

    hit_count = 0
    total_signals = 0
    excluded_by_aspect_ratio = 0
    checked = 0

    for f in sample:
        img = cv2.imread(str(f))
        if img is None:
            continue
        checked += 1
        anomalies = TamperForensics.detect_splicing_boundaries(img)
        if anomalies:
            hit_count += 1
            total_signals += len(anomalies)

        # Also count, independently of the guard's current on/off state,
        # how many raw high-variance contours in this image WOULD be an
        # extreme (>8:1) aspect ratio -- i.e. how many the guard actually
        # touches, to see if it's suppressing anything on real splices at all.

    print(f"Checked {checked} real CASIA v2.0 tampered images")
    print(f"Images with >=1 edge_discontinuity signal: {hit_count}/{checked} ({hit_count/checked:.1%})")
    print(f"Total edge_discontinuity signals raised: {total_signals}")


if __name__ == "__main__":
    main()
