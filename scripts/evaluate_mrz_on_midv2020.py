"""
Evaluates the project's real MRZ pipeline -- TesseractOCRService.extract_mrz_lines
(backend/app/services/ocr_service.py) feeding MRZService.parse_pre_isolated_lines
(backend/app/services/mrz_service.py) -- against MIDV-2020's genuine ground-truth
MRZ text (mrz_line0/mrz_line1 field values in the annotation JSONs), across all
4 MRZ-bearing document types in the "templates" subset (aze_passport, grc_passport,
lva_passport, srb_passport -- 100 images each). See scripts/finetune_face_embedder.py's
sibling data-provenance note: MIDV-2020's OFFICIAL 124GB archive is license-gated
(sFTP, University of La Rochelle); this uses a Kaggle mirror
(pushpraj23/midvtemplates) of the same VIA-format ground truth described in this
codebase's own SIDTD loader (generate_tamper_training_data.load_sidtd_patches).

Deliberately OUT of scope: the whole-document "fields" dict (full_name, dob,
etc.) extractor in TesseractOCRService.parse_passport_fields and friends is
anchored on this project's OWN synthetic bilingual French/English label layout
(see _value_after_label) -- it was never designed to generalize to MIDV-2020's
10 distinct real national document layouts/languages, so evaluating it here
would just be measuring a known, expected mismatch, not a real gap. The MRZ
pipeline is different: ICAO 9303 standardizes MRZ position, font (OCR-B), and
format across every issuing country, so it SHOULD generalize -- this measures
whether it actually does.

NOTE: these are clean, un-photographed digital template renders (no camera
noise, no lighting/glare/perspective) -- an easier case than a real phone
photo of a physical document, which is this project's actual production input
(see ocr_service.py's deskew/CLAHE/denoise pipeline, built for exactly that
harder case). A low error rate here does not guarantee the same on real
photos; a high error rate here is a lower bound on the real problem.

Run with:
    .venv-backend/Scripts/python.exe scripts/evaluate_mrz_on_midv2020.py
"""
import json
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.ocr_service import get_ocr_service
from app.services.mrz_service import MRZService

MIDV_ROOT = PROJECT_ROOT / "data" / "MIDV2020_templates"
PASSPORT_TYPES = ["aze_passport", "grc_passport", "lva_passport", "srb_passport"]

COMPARE_FIELDS = ["document_number", "birth_date", "expiry_date", "surname", "given_names", "nationality", "sex"]


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (0 if ca == cb else 1))
        prev = curr
    return prev[len(b)]


def best_line_match(candidates, target: str) -> Optional[str]:
    """Picks whichever OCR candidate line is closest (by edit distance) to the
    target ground-truth line -- extract_mrz_lines returns however many
    plausible lines it found, not necessarily in the right order/count."""
    if not candidates:
        return None
    return min(candidates, key=lambda c: levenshtein(c, target))


def main():
    ocr_svc = get_ocr_service()
    if ocr_svc.__class__.__name__ != "TesseractOCRService":
        print(f"ERROR: get_ocr_service() returned {ocr_svc.__class__.__name__}, not "
              f"TesseractOCRService -- check TESSERACT_PATH / that OCR_BACKEND isn't forced to mock.")
        sys.exit(1)

    total_images = 0
    line_char_accuracies = []
    checksum_pass_count = 0
    mrz_not_found_count = 0
    field_match_counts = {f: 0 for f in COMPARE_FIELDS}
    field_total_counts = {f: 0 for f in COMPARE_FIELDS}
    per_type_stats = {}

    for doctype in PASSPORT_TYPES:
        ann_path = MIDV_ROOT / "annotations" / f"{doctype}.json"
        img_dir = MIDV_ROOT / "images" / doctype
        ann = json.loads(ann_path.read_text(encoding="utf-8"))

        type_checksum_pass = 0
        type_total = 0
        type_line_acc = []

        for key, entry in ann["_via_img_metadata"].items():
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
                continue  # skip the rare malformed ground-truth record itself

            total_images += 1
            type_total += 1

            mrz_lines = ocr_svc.extract_mrz_lines(str(img_path))
            if len(mrz_lines) < 2:
                mrz_not_found_count += 1
                continue

            # Character-level accuracy: match each ground-truth line against
            # whichever OCR candidate is closest to it.
            for gt_line in (gt_l0, gt_l1):
                match = best_line_match(mrz_lines, gt_line)
                if match:
                    acc = 1.0 - (levenshtein(match, gt_line) / max(len(gt_line), len(match)))
                    line_char_accuracies.append(acc)
                    type_line_acc.append(acc)

            ocr_parsed = MRZService.parse_pre_isolated_lines(mrz_lines)
            if ocr_parsed and ocr_parsed.get("is_valid"):
                checksum_pass_count += 1
                type_checksum_pass += 1

            if ocr_parsed:
                for f in COMPARE_FIELDS:
                    field_total_counts[f] += 1
                    if str(ocr_parsed.get(f, "")).strip() == str(gt_parsed.get(f, "")).strip():
                        field_match_counts[f] += 1

        per_type_stats[doctype] = {
            "n": type_total,
            "checksum_pass_rate": type_checksum_pass / type_total if type_total else 0.0,
            "mean_line_char_acc": sum(type_line_acc) / len(type_line_acc) if type_line_acc else 0.0,
        }

    print(f"=== MRZ pipeline evaluation on MIDV-2020 templates (n={total_images} genuine-MRZ passport images) ===\n")

    print("Per document type:")
    for doctype, stats in per_type_stats.items():
        print(f"  {doctype:18s}  n={stats['n']:3d}  checksum_pass={stats['checksum_pass_rate']:.1%}  "
              f"mean_line_char_acc={stats['mean_line_char_acc']:.1%}")

    print(f"\nOverall:")
    print(f"  MRZ band not found (< 2 candidate lines returned): {mrz_not_found_count}/{total_images} "
          f"({mrz_not_found_count/total_images:.1%})")
    if line_char_accuracies:
        print(f"  Mean per-line character accuracy (of images where MRZ was found): "
              f"{sum(line_char_accuracies)/len(line_char_accuracies):.1%}")
    print(f"  End-to-end ICAO checksum pass rate (OCR'd MRZ parses as fully valid): "
          f"{checksum_pass_count}/{total_images} ({checksum_pass_count/total_images:.1%})")

    print(f"\nField-level exact-match rate (only counted when OCR produced a parseable MRZ at all):")
    for f in COMPARE_FIELDS:
        n = field_total_counts[f]
        matched = field_match_counts[f]
        rate = matched / n if n else float("nan")
        print(f"  {f:18s}  {matched}/{n}  ({rate:.1%})" if n else f"  {f:18s}  n/a")


if __name__ == "__main__":
    main()
