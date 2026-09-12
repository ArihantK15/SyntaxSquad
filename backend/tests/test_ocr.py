import cv2
import numpy as np
import pytest
from PIL import Image

from app.services.mrz_service import MRZService
from app.services.ocr_service import TesseractOCRService
from app.utils.synthetic_generator import SyntheticDocumentGenerator

svc = TesseractOCRService.__new__(TesseractOCRService)  # skip __init__'s tesseract binary check


def _document_like_image(angle: float) -> np.ndarray:
    """A white page with a dark rectangle standing in for a line of print, rotated by `angle`."""
    img = np.full((300, 300), 255, dtype=np.uint8)
    cv2.rectangle(img, (50, 130), (250, 170), 0, -1)
    matrix = cv2.getRotationMatrix2D((150, 150), angle, 1.0)
    return cv2.warpAffine(img, matrix, (300, 300), borderValue=255)


@pytest.mark.parametrize("true_angle", [3, -3, 7, -7, 15, -15])
def test_estimate_skew_angle_matches_a_known_rotation(true_angle):
    """
    cv2.minAreaRect's angle convention has changed across OpenCV versions and
    flips depending on the bounding box's own aspect ratio (see
    _estimate_skew_angle's docstring) -- verify the correction formula
    against known rotations rather than trust it by inspection.
    """
    gray = _document_like_image(true_angle)
    detected = TesseractOCRService._estimate_skew_angle(gray)
    assert detected == pytest.approx(-true_angle, abs=0.1)


def test_estimate_skew_angle_is_zero_on_sparse_content():
    """Too little foreground to estimate confidently should not invent an angle."""
    blank = np.full((300, 300), 255, dtype=np.uint8)
    assert TesseractOCRService._estimate_skew_angle(blank) == 0.0


def test_deskew_recovers_a_valid_mrz_from_a_rotated_document(tmp_path):
    """
    Reproduces a real capture condition: a photographed (not flatbed-
    scanned) document is rarely perfectly axis-aligned. extract_mrz_lines
    crops a FIXED bottom fraction of the image to isolate the MRZ band, and
    a several-degree rotation is enough to make Tesseract misread individual
    MRZ characters (garbling the crop, sometimes splitting it into the wrong
    number of lines) even though the crop itself still technically contains
    the MRZ. Deskewing the full image before that crop -- added specifically
    for this -- recovers a checksum-valid MRZ from a rotated capture that
    the undeskewed pipeline garbles into an invalid (or unparsable) result.
    """
    doc_path = str(tmp_path / "genuine.jpg")
    SyntheticDocumentGenerator.generate_document(doc_path, mode="genuine")

    rotated_path = str(tmp_path / "rotated.jpg")
    with Image.open(doc_path) as img:
        rotated = img.convert("RGB").rotate(
            4, resample=Image.BICUBIC, expand=False, fillcolor=(255, 255, 255)
        )
        rotated.save(rotated_path, "JPEG", quality=95)

    mrz_lines = svc.extract_mrz_lines(rotated_path)
    result = MRZService.parse_pre_isolated_lines(mrz_lines) if len(mrz_lines) >= 2 else None
    assert result is not None
    assert result["is_valid"] is True


def test_full_name_survives_garbled_label():
    """
    Reproduces a real failure observed on a generated specimen: Tesseract
    misread the "SURNAME / NOM" label as "JRNAME / NOM", and the old
    whole-text regex `(?:NAME|SURNAME|GIVEN NAMES?)[:\\s]+(...)` matched the
    garbled label text itself rather than the actual name value on the next
    line. The label-anchored line lookup should find the label by its
    OCR-robust French half ("NOM") and take the value from the line below.
    """
    raw_text = (
        "DEMO TRAVEL DOCUMENT\n"
        "JRNAME / NOM\n"
        "SILVA\n"
        "GIVEN NAMES/ PRENOMS\n"
        "MARIA\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_fields_from_text(raw_text, lines)
    assert fields["full_name"] == "SILVA MARIA"


def test_date_of_birth_and_expiry_not_swapped_when_one_date_is_malformed():
    """
    Reproduces a real failure: OCR dropped a separator in the DOB line
    ("0101/2000" instead of "01/01/2000"), so the old whole-text date regex
    only found one valid date (the expiry) and assigned it to date_of_birth
    via the "len(dates_found) == 1" heuristic, leaving date_of_expiry as
    None. Label-anchored per-line parsing with a more tolerant date pattern
    should recover both dates correctly instead of guessing by position.
    """
    raw_text = (
        "DATE OF BIRTH/ DATE DE NAISSANCE\n"
        "0101/2000\n"
        "SEX) SEXE\n"
        "M\n"
        "DATE OF EXPIRY / DATE DEXPIRATION\n"
        "01/01/2030\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_fields_from_text(raw_text, lines)
    assert fields["date_of_birth"] == "01/01/2000"
    assert fields["date_of_expiry"] == "01/01/2030"


def test_country_extracted_from_its_own_labeled_field():
    """
    Reproduces two stacked real failures. First, fields["country"] used to
    be detected via a hardcoded 10-country whitelist scanned over the whole
    raw text -- "ATLANTIS FEDERATION" (one of the five jurisdictions offered
    in the New Screening UI) isn't in that whitelist, so it was silently
    dropped; a whitelist can never cover free-text country names. Fixing
    that to anchor on the document's header subtitle line instead
    ("<country> * FICTIONAL TEST SPECIMEN") uncovered a second, deeper
    problem: that subtitle is rendered in low-contrast slate-gray on a dark
    navy header and Tesseract never recognizes it as text at all, so no
    anchor line exists in the OCR output to match against regardless of the
    regex. The real fix was adding "COUNTRY OF ISSUE / PAYS" as a proper
    high-contrast labeled field alongside the other identity fields.
    """
    raw_text = (
        "COUNTRY OF ISSUE / PAYS\n"
        "ATLANTIS FEDERATION\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_fields_from_text(raw_text, lines)
    assert fields["country"] == "ATLANTIS FEDERATION"


def test_sex_extracted_from_labeled_line_despite_garbled_label():
    raw_text = (
        "SEX) SEXE\n"
        "M\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_fields_from_text(raw_text, lines)
    assert fields["sex"] == "M"


def test_nationality_extracted_from_labeled_line():
    raw_text = (
        "NATIONALITY / NATIONALITE\n"
        "ATL CITIZEN\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_fields_from_text(raw_text, lines)
    assert fields["nationality"] == "ATL CITIZEN"


def test_detect_document_type_recognizes_aadhaar_markers():
    raw_text = "Government of India\nUnique Identification Authority of India\n"
    assert TesseractOCRService._detect_document_type(raw_text) == "AADHAAR"


def test_detect_document_type_defaults_to_passport():
    raw_text = "PASSPORT REPUBLIC OF UTOPIA\nSURNAME / NOM\nKAUL\n"
    assert TesseractOCRService._detect_document_type(raw_text) == "PASSPORT"


def test_aadhaar_number_not_confused_with_enrolment_number():
    """
    Reproduces a real failure observed on an actual Aadhaar photo: the card
    prints both a 12-digit Aadhaar (UID) number, conventionally grouped
    4-4-4 with spaces, and an unrelated slash-separated Enrolment Number
    ("4050/00286/01675") used only for tracking the original enrolment
    application. A naive "any 12 digits" scan can accidentally assemble a
    false positive from the enrolment ID's digits; the spaced-group pattern
    must be preferred and matched first.
    """
    raw_text = (
        "Government of India\n"
        "Enrolment No.: 4050/00286/01675\n"
        "1234 5678 9012\n"
    )
    assert svc._extract_aadhaar_number(raw_text) == "123456789012"


def test_aadhaar_fields_extract_dob_from_same_line_as_label():
    raw_text = (
        "Government of India\n"
        "RAVI KUMAR\n"
        "DOB: 15/08/1990\n"
        "MALE\n"
        "1234 5678 9012\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_aadhaar_fields(raw_text, lines)
    assert fields["date_of_birth"] == "15/08/1990"
    assert fields["sex"] == "M"
    assert fields["document_number"] == "123456789012"
    assert fields["nationality"] == "INDIA"
    assert fields["date_of_expiry"] is None


def test_aadhaar_full_name_excludes_institutional_boilerplate():
    raw_text = (
        "Government of India\n"
        "Unique Identification Authority of India\n"
        "RAVI KUMAR\n"
        "DOB: 15/08/1990\n"
        "MALE\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_aadhaar_fields(raw_text, lines)
    assert fields["full_name"] == "RAVI KUMAR"


def test_extract_text_routes_to_aadhaar_parser_and_tags_document_type(monkeypatch):
    aadhaar_raw = (
        "Government of India\n"
        "Unique Identification Authority of India\n"
        "RAVI KUMAR\n"
        "DOB: 15/08/1990\n"
        "MALE\n"
        "1234 5678 9012\n"
    )
    monkeypatch.setattr(svc, "preprocess_image", lambda path: None)
    monkeypatch.setattr("pytesseract.image_to_data", lambda *a, **k: {"conf": []})
    monkeypatch.setattr("pytesseract.image_to_string", lambda *a, **k: aadhaar_raw)

    result = svc.extract_text("unused.jpg")
    assert result["fields"]["document_type"] == "AADHAAR"
    assert result["fields"]["full_name"] == "RAVI KUMAR"
    assert result["fields"]["document_number"] == "123456789012"
