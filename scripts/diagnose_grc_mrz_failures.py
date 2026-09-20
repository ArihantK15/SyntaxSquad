"""
Diagnostic: dumps ground-truth vs. OCR'd MRZ lines side by side for
grc_passport images where the checksum failed, to find a systematic
(fixable) cause rather than just reporting the aggregate failure rate.
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.ocr_service import get_ocr_service
from app.services.mrz_service import MRZService

MIDV_ROOT = PROJECT_ROOT / "data" / "MIDV2020_templates"


def main():
    ocr_svc = get_ocr_service()
    doctype = "grc_passport"
    ann = json.loads((MIDV_ROOT / "annotations" / f"{doctype}.json").read_text(encoding="utf-8"))
    img_dir = MIDV_ROOT / "images" / doctype

    shown = 0
    for key, entry in ann["_via_img_metadata"].items():
        if shown >= 8:
            break
        fname = entry["filename"]
        img_path = img_dir / fname
        if not img_path.exists():
            continue
        regions = {r["region_attributes"]["field_name"]: r["region_attributes"]["value"] for r in entry["regions"]}
        gt_l0, gt_l1 = regions.get("mrz_line0"), regions.get("mrz_line1")
        if not gt_l0 or not gt_l1:
            continue
        gt_parsed = MRZService.parse_td3(gt_l0, gt_l1)
        if not gt_parsed["is_valid"]:
            continue

        mrz_lines = ocr_svc.extract_mrz_lines(str(img_path))
        ocr_parsed = MRZService.parse_pre_isolated_lines(mrz_lines) if len(mrz_lines) >= 2 else None
        if ocr_parsed and ocr_parsed["is_valid"]:
            continue  # only show failures

        shown += 1
        print(f"=== {fname} ===")
        print(f"GT  l0: {gt_l0}")
        print(f"GT  l1: {gt_l1}")
        for i, line in enumerate(mrz_lines):
            print(f"OCR l{i}: {line}")
        if ocr_parsed:
            print(f"checksums: {[(c['field'], c['valid']) for c in ocr_parsed['checksums']]}")
        print()


if __name__ == "__main__":
    main()
