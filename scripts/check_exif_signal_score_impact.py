"""
Follow-up to check_exif_signal_on_casia.py: that script found
exif_metadata_missing fires on ~90% of real CASIA Authentic (Au) images
(their EXIF was evidently stripped by dataset packaging, long before this
project ever sees them) vs 0% of Tampered (Tp) images -- backwards from what
the signal is meant to catch, unlike exif_editing_software (Au=2.4% vs
Tp=99.8%) and exif_date_inconsistency (Au=4.0% vs Tp=11.1%), which are both
strongly correct-direction discriminators on this same real dataset.

This script measures the ACTUAL scoring consequence: for a sample of real
authentic images, compute tamper_risk (and its LOW/MEDIUM/HIGH/CRITICAL
tier) via TamperDetectionService._aggregate_tamper_score WITH vs WITHOUT
the EXIF signals actually produced for that image, to see how many genuine
documents would have their risk tier pushed up by this feature alone.

Run with:
    .venv-backend/Scripts/python.exe scripts/check_exif_signal_score_impact.py [n_samples]
"""
import random
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.ml.tamper_model import TamperForensics
from app.services.tamper_service import TamperDetectionService

AU_DIR = PROJECT_ROOT / "data" / "CASIA2" / "CASIA2" / "Au"


def _tier(score: float) -> str:
    if score >= 0.85:
        return "CRITICAL"
    if score >= 0.70:
        return "HIGH"
    if score >= 0.40:
        return "MEDIUM"
    return "LOW"


def main():
    n_samples = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    random.seed(42)

    files = sorted(AU_DIR.iterdir())
    sample = random.sample(files, min(n_samples, len(files)))

    service = TamperDetectionService()
    tmpdir = Path(tempfile.mkdtemp())

    checked = 0
    tier_changed = 0
    score_deltas = []

    for f in sample:
        heatmap_path = str(tmpdir / f"{f.stem}_heatmap.jpg")
        try:
            mean_ela, _ = TamperForensics.generate_ela(str(f), heatmap_path)
        except Exception:
            continue
        exif_result = service.analyze_exif_metadata(str(f))
        exif_signals = exif_result["signals"]

        score_without = TamperDetectionService._aggregate_tamper_score(mean_ela, None, [])
        score_with = TamperDetectionService._aggregate_tamper_score(mean_ela, None, exif_signals)

        tier_without = _tier(score_without)
        tier_with = _tier(score_with)

        checked += 1
        score_deltas.append(score_with - score_without)
        if tier_without != tier_with:
            tier_changed += 1
            print(f"  TIER CHANGE: {f.name}: {score_without:.2f} ({tier_without}) -> {score_with:.2f} ({tier_with}) "
                  f"[signals: {[s['type'] for s in exif_signals]}]")

    print(f"\n=== Checked {checked} real authentic CASIA images ===")
    print(f"Risk tier changed by adding EXIF signal: {tier_changed}/{checked} ({tier_changed/checked:.1%})")
    print(f"Mean score delta from EXIF signal: {sum(score_deltas)/len(score_deltas):+.4f}")
    print(f"Max score delta from EXIF signal: {max(score_deltas):+.4f}")


if __name__ == "__main__":
    main()
