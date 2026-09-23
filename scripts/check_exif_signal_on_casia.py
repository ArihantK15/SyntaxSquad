"""
Targeted hit-rate check for the new EXIF metadata signal
(TamperDetectionService.analyze_exif_metadata, backend/app/services/tamper_service.py)
-- NOT a general tamper-accuracy re-evaluation. scripts/evaluate_tamper_on_casia.py
tests the trained CNN directly on 64x64 patches and never touches
TamperDetectionService at all, so it can't measure this signal's behavior.

The EXIF signal is deliberately new (real photographs' own EXIF is untouched
by this project's synthetic specimen generator, which never embeds or reads
EXIF at all), so the risk worth measuring here is a FALSE-POSITIVE one: real,
authentic CASIA photos may have had their EXIF stripped by dataset
packaging/re-hosting long before this ever reaches TamperDetectionService,
which would make "exif_metadata_missing" fire near-uniformly on genuine
images too and add noise rather than signal.

This script runs the real analyze_exif_metadata() against full-size CASIA
v2.0 Authentic (Au) and Tampered (Tp) images and reports the hit rate for
each EXIF signal type on each side, so that noise can be seen and judged
before trusting the signal in the live aggregate score.

Run with:
    .venv-backend/Scripts/python.exe scripts/check_exif_signal_on_casia.py [n_samples]
"""
import random
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.tamper_service import TamperDetectionService

CASIA_ROOT = PROJECT_ROOT / "data" / "CASIA2" / "CASIA2"
AU_DIR = CASIA_ROOT / "Au"
TP_DIR = CASIA_ROOT / "Tp"


def _scan(service: TamperDetectionService, files, label: str):
    type_counts = Counter()
    any_signal_count = 0
    checked = 0
    for f in files:
        try:
            result = service.analyze_exif_metadata(str(f))
        except Exception:
            continue
        checked += 1
        sigs = result["signals"]
        if sigs:
            any_signal_count += 1
        for sig in sigs:
            type_counts[sig["type"]] += 1

    print(f"\n--- {label}: checked {checked} images ---")
    print(f"Images with >=1 EXIF signal: {any_signal_count}/{checked} ({any_signal_count/checked:.1%})")
    for sig_type, count in type_counts.most_common():
        print(f"  {sig_type}: {count} ({count/checked:.1%})")
    return type_counts, checked


def main():
    n_samples = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    random.seed(42)

    au_files = sorted(AU_DIR.iterdir())
    tp_files = sorted(TP_DIR.iterdir())
    au_sample = random.sample(au_files, min(n_samples, len(au_files)))
    tp_sample = random.sample(tp_files, min(n_samples, len(tp_files)))

    service = TamperDetectionService()

    au_counts, au_checked = _scan(service, au_sample, "CASIA v2.0 Authentic (Au)")
    tp_counts, tp_checked = _scan(service, tp_sample, "CASIA v2.0 Tampered (Tp)")

    print("\n=== Summary: does the signal actually discriminate? ===")
    for sig_type in set(au_counts) | set(tp_counts):
        au_rate = au_counts.get(sig_type, 0) / au_checked
        tp_rate = tp_counts.get(sig_type, 0) / tp_checked
        print(f"  {sig_type}: Au={au_rate:.1%}  Tp={tp_rate:.1%}  (delta={tp_rate - au_rate:+.1%})")


if __name__ == "__main__":
    main()
