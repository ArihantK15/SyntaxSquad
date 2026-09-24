import cv2
import numpy as np
import pytesseract
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


def test_extract_mrz_lines_degrades_to_empty_list_on_tesseract_engine_failure(tmp_path, monkeypatch):
    """
    Reproduces a real deployment gap: extract_mrz_lines had no exception
    handling around its pytesseract call, unlike extract_text's own
    try/except -- a missing/misconfigured Tesseract binary
    (TesseractNotFoundError) or any other OCR engine failure propagated
    straight up through screening.py/demo.py uncaught, crashing the whole
    screening request instead of degrading. It must instead return [] on
    any OCR engine failure, exactly like the existing "unreadable image" /
    "empty crop" cases already do -- so the caller's existing missing-MRZ
    handling (rules_engine.py RULE 1's "elif not mrz_data" branch) routes
    the case to review instead of crashing outright.
    """
    doc_path = str(tmp_path / "genuine.jpg")
    SyntheticDocumentGenerator.generate_document(doc_path, mode="genuine")

    def _boom(*args, **kwargs):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr("pytesseract.image_to_string", _boom)

    assert svc.extract_mrz_lines(doc_path) == []


def test_extract_text_uses_single_column_page_segmentation(monkeypatch):
    """
    Reproduces a real failure found by running an actual photographed
    Aadhaar card (not a synthetic specimen) through the live pipeline:
    Tesseract's default automatic page segmentation (PSM 3) produced
    near-total garbage on that real, denser, mixed-script/QR-code layout
    (OSD orientation/script confidence near zero), while explicitly
    forcing PSM 4 (already used by extract_mrz_lines for the same reason)
    recovered the document almost completely -- confirmed byte-for-byte
    identical output to the old default on every synthetic specimen
    tested, so this is a real-document robustness fix with no observed
    synthetic-path regression risk. Asserted here as "the config passed to
    Tesseract requests single-column segmentation" rather than depending
    on a real Tesseract install being present in every test environment.
    """
    captured_config = {}

    def _capture(image, config="", **kwargs):
        captured_config["value"] = config
        return ""

    monkeypatch.setattr(svc, "preprocess_image", lambda path: None)
    monkeypatch.setattr("pytesseract.image_to_data", lambda *a, **k: {"conf": []})
    monkeypatch.setattr("pytesseract.image_to_string", _capture)

    svc.extract_text("unused.jpg")

    assert "--psm 4" in captured_config["value"]


def test_extract_date_rejects_an_implausible_year_from_incidental_digit_runs():
    """
    Reproduces a real failure observed on an actual Aadhaar photo: DOB
    label-matching (see parse_aadhaar_fields) fell through to an unrelated
    line containing a 6-digit PIN code ("PIN Code: 560039"), and the
    separator-tolerant date regex happily assembled "05/06/0039" out of
    it -- syntactically date-shaped but an impossible birth/issue/expiry
    year. A real date's 4-digit year must fall within a plausible range.
    """
    assert svc._extract_date("PIN Code: 560039 DOB is based on...") is None


def test_aadhaar_dob_skips_a_labeled_line_with_no_real_date_and_keeps_searching():
    """
    Reproduces a real failure observed on an actual Aadhaar photo: the
    card's own generic informational disclaimer text ("...not of
    citizenship or date of birth (DOB)...") mentions the word "DOB" before
    the holder's own labeled DOB field appears further down the page. The
    old code committed to the FIRST line matching \\bDOB\\b and its
    immediate next line unconditionally, landing on an unrelated PIN-code
    line with no real date on it at all instead of continuing to search
    for a line that actually contains one.
    """
    raw_text = (
        "Government of India\n"
        "RAVI KUMAR\n"
        "Aadhaar is proof of identity, not of citizenship or date of birth (DOB).\n"
        "PIN Code: 560039 DOB is based on information supported by proof of DOB document\n"
        "Sex) DOB: 15/08/1990\n"
        "MALE\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_aadhaar_fields(raw_text, lines)
    assert fields["date_of_birth"] == "15/08/1990"


def test_aadhaar_full_name_rejects_a_single_garbled_ocr_token():
    """
    Reproduces a real failure observed on an actual (unusually noisy)
    Aadhaar capture: a single OCR-garbled token from unrelated boilerplate/
    watermark text ("cendaiead.") happened to fullmatch the letters-only
    name-shaped pattern and won as the "name" before the real, correctly-
    read "Sharaj R Shetty" line was ever reached. A real printed name is
    virtually always multiple space-separated words, so requiring at least
    two tokens rejects this whole class of single-word OCR garbage without
    needing to know anything about what the garbage actually says.

    Note: this does NOT fix every real-world full_name failure -- a
    multi-word garbled fragment that also happens to dodge the boilerplate
    keyword exclusion list (e.g. "Unique" OCR'd as "Unaque") can still win.
    That residual gap is real and not addressed here; this test covers the
    specific single-token failure mode observed and fixed.
    """
    raw_text = (
        "Government of India\n"
        "cendaiead.\n"
        "Unique Identification Authority of India\n"
        "Sharaj R Shetty\n"
        "DOB: 30/07/2007\n"
        "MALE\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_aadhaar_fields(raw_text, lines)
    assert fields["full_name"] == "Sharaj R Shetty"


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


def test_aadhaar_number_survives_a_single_dropped_group_separator():
    """
    Reproduces a real failure observed by running an actual image through
    live Tesseract (not just fabricated raw text): "1234 5678 9012" was
    OCR'd as "12345678 9012" -- ONE of the two group spaces silently
    dropped, the other preserved. The old regex required a mandatory single
    space at BOTH boundaries and missed this mixed case entirely.
    """
    raw_text = "Government of India\n12345678 9012\n"
    assert svc._extract_aadhaar_number(raw_text) == "123456789012"


def test_aadhaar_number_survives_both_group_separators_dropped():
    raw_text = "Government of India\n123456789012\n"
    assert svc._extract_aadhaar_number(raw_text) == "123456789012"


def test_aadhaar_full_name_survives_merged_header_words():
    """
    Reproduces a real failure observed by running an actual image through
    live Tesseract: "Government of India" was OCR'd as "Governmentof India"
    (space dropped between "Government" and "of"). The old exclusion list
    checked for the whole phrase "GOVERNMENT OF INDIA" as one substring,
    which no longer matched the merged word -- the boilerplate header line
    was then mistaken for the holder's name.
    """
    raw_text = (
        "Governmentof India\n"
        "Unique Identification Authority of India\n"
        "Ravi Kumar\n"
        "DOB 15/08/1990\n"
        "MALE\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_aadhaar_fields(raw_text, lines)
    assert fields["full_name"] == "Ravi Kumar"


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


def test_detect_document_type_recognizes_pan_markers():
    raw_text = "INCOME TAX DEPARTMENT\nGOVT. OF INDIA\nPermanent Account Number Card\n"
    assert TesseractOCRService._detect_document_type(raw_text) == "PAN"


def test_detect_document_type_recognizes_driving_licence_markers():
    raw_text = "TRANSPORT DEPARTMENT\nGOVERNMENT OF MAHARASHTRA\nDRIVING LICENCE\n"
    assert TesseractOCRService._detect_document_type(raw_text) == "DRIVING_LICENSE"


def test_extract_pan_number_isolates_valid_pan_format():
    raw_text = "INCOME TAX DEPARTMENT\nGOVT. OF INDIA\nABCPK1234F\nName\nRAVI KUMAR SHARMA\n"
    assert svc._extract_pan_number(raw_text) == "ABCPK1234F"


def test_extract_pan_number_ignores_non_pan_shaped_tokens():
    """
    A 9-digit Aadhaar-shaped or 8-digit passport-shaped number nearby must
    not be mistaken for a PAN -- the structural anchor (5 letters, 4 digits,
    1 letter, exactly 10 characters with word boundaries on both sides) is
    what makes this a real format check rather than a loose "any letters and
    digits" scan.
    """
    raw_text = "INCOME TAX DEPARTMENT\nRef No: AB123456789\nGOVT. OF INDIA\n"
    assert svc._extract_pan_number(raw_text) is None


def test_pan_fields_extract_name_father_name_and_dob():
    raw_text = (
        "INCOME TAX DEPARTMENT\n"
        "GOVT. OF INDIA\n"
        "Permanent Account Number Card\n"
        "ABCPK1234F\n"
        "Name\n"
        "RAVI KUMAR SHARMA\n"
        "Father's Name\n"
        "SURESH KUMAR SHARMA\n"
        "Date of Birth\n"
        "15/08/1990\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_pan_fields(raw_text, lines)
    assert fields["document_number"] == "ABCPK1234F"
    assert fields["full_name"] == "RAVI KUMAR SHARMA"
    assert fields["date_of_birth"] == "15/08/1990"
    assert fields["nationality"] == "INDIA"
    assert fields["date_of_expiry"] is None  # PAN has no expiry by design


def test_extract_text_routes_to_pan_parser_and_tags_document_type(monkeypatch):
    pan_raw = (
        "INCOME TAX DEPARTMENT\n"
        "GOVT. OF INDIA\n"
        "ABCPK1234F\n"
        "Name\n"
        "RAVI KUMAR SHARMA\n"
        "Father's Name\n"
        "SURESH KUMAR SHARMA\n"
        "Date of Birth\n"
        "15/08/1990\n"
    )
    monkeypatch.setattr(svc, "preprocess_image", lambda path: None)
    monkeypatch.setattr("pytesseract.image_to_data", lambda *a, **k: {"conf": []})
    monkeypatch.setattr("pytesseract.image_to_string", lambda *a, **k: pan_raw)

    result = svc.extract_text("unused.jpg")
    assert result["fields"]["document_type"] == "PAN"
    assert result["fields"]["document_number"] == "ABCPK1234F"
    assert result["fields"]["full_name"] == "RAVI KUMAR SHARMA"


def test_extract_dl_number_normalizes_separators():
    raw_text = "DRIVING LICENCE\nDL No\nMH-12 2011-0012345\nName\nRAVI KUMAR SHARMA\n"
    assert svc._extract_dl_number(raw_text) == "MH1220110012345"


def test_dl_fields_extract_name_dob_issue_and_expiry():
    raw_text = (
        "TRANSPORT DEPARTMENT\n"
        "GOVERNMENT OF MAHARASHTRA\n"
        "DRIVING LICENCE\n"
        "DL No\n"
        "MH1220110012345\n"
        "Name\n"
        "RAVI KUMAR SHARMA\n"
        "Date of Birth\n"
        "15/08/1990\n"
        "Valid From\n"
        "20/03/2011\n"
        "Valid Till\n"
        "20/03/2031\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_dl_fields(raw_text, lines)
    assert fields["document_number"] == "MH1220110012345"
    assert fields["full_name"] == "RAVI KUMAR SHARMA"
    assert fields["date_of_birth"] == "15/08/1990"
    assert fields["date_of_issue"] == "20/03/2011"
    assert fields["date_of_expiry"] == "20/03/2031"
    assert fields["nationality"] == "INDIA"


def test_dl_expiry_survives_tesseract_misreading_valid_as_vaud():
    """
    Reproduces a real failure found by running an actual photographed
    (expired) Driving Licence through the live pipeline: Tesseract read the
    genuine printed "VALID TILL" label as "VAUD TILL" -- VALID -> VAUD is a
    2-edit slip (L misread as U, the I dropped) that the exact \bVALID
    TILL\b match in parse_dl_fields never catches. date_of_expiry came back
    None, so rules_engine.py's expiration check (the entire point of this
    scenario -- a DL has no MRZ, so this printed field is its only expiry
    signal) silently never fired at all, and a genuinely expired licence
    screened as LOW risk / clear for entry.
    """
    raw_text = (
        "TRANSPORT DEPARTMENT\n"
        "DL NO\n"
        "KA0320110098765\n"
        "NAME\n"
        "KIRAN REDDY\n"
        "DATE OF BIRTH\n"
        "10/02/1988\n"
        "VAUD FROM\n"
        "20/03/2011\n"
        "VAUD TILL\n"
        "01/01/2020\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_dl_fields(raw_text, lines)
    assert fields["date_of_issue"] == "20/03/2011"
    assert fields["date_of_expiry"] == "01/01/2020"


def test_dl_fuzzy_label_match_does_not_fire_on_unrelated_lines():
    """
    Guards against the fuzzy fallback being too permissive: a line that
    merely contains short, common words must not be mistaken for a
    misread "VALID TILL"/"VALID FROM" label just because both are absent
    from the document entirely.
    """
    raw_text = (
        "TRANSPORT DEPARTMENT\n"
        "NAME\n"
        "KIRAN REDDY\n"
        "REMARKS\n"
        "NIL\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_dl_fields(raw_text, lines)
    assert fields["date_of_issue"] is None
    assert fields["date_of_expiry"] is None


def test_extract_text_routes_to_dl_parser_and_tags_document_type(monkeypatch):
    dl_raw = (
        "TRANSPORT DEPARTMENT\n"
        "GOVERNMENT OF MAHARASHTRA\n"
        "DRIVING LICENCE\n"
        "DL No\n"
        "MH1220110012345\n"
        "Name\n"
        "RAVI KUMAR SHARMA\n"
        "Valid Till\n"
        "20/03/2031\n"
    )
    monkeypatch.setattr(svc, "preprocess_image", lambda path: None)
    monkeypatch.setattr("pytesseract.image_to_data", lambda *a, **k: {"conf": []})
    monkeypatch.setattr("pytesseract.image_to_string", lambda *a, **k: dl_raw)

    result = svc.extract_text("unused.jpg")
    assert result["fields"]["document_type"] == "DRIVING_LICENSE"
    assert result["fields"]["document_number"] == "MH1220110012345"
    assert result["fields"]["date_of_expiry"] == "20/03/2031"


def test_detect_document_type_recognizes_voter_id_markers():
    raw_text = "ELECTION COMMISSION OF INDIA\nELECTORS PHOTO IDENTITY CARD\nEPIC NO\nABC1234567\n"
    assert TesseractOCRService._detect_document_type(raw_text) == "VOTER_ID"


def test_extract_voter_id_number_isolates_valid_epic_format():
    raw_text = "ELECTION COMMISSION OF INDIA\nEPIC NO\nABC1234567\nElector's Name\nANJALI NAIR\n"
    assert svc._extract_voter_id_number(raw_text) == "ABC1234567"


def test_extract_voter_id_number_ignores_non_epic_shaped_tokens():
    """
    A PAN-shaped (5 letters + 4 digits + 1 letter) or Aadhaar-shaped
    (12-digit) number nearby must not be mistaken for an EPIC number -- the
    structural anchor (exactly 3 letters, then exactly 7 digits, with word
    boundaries on both sides) is what makes this a real format check rather
    than a loose "any letters and digits" scan.
    """
    raw_text = "ELECTION COMMISSION OF INDIA\nRef No: AB123456789\nEPIC NO\n"
    assert svc._extract_voter_id_number(raw_text) is None


def test_voter_id_fields_extract_name_dob_and_sex_while_skipping_relation_name():
    raw_text = (
        "ELECTION COMMISSION OF INDIA\n"
        "ELECTORS PHOTO IDENTITY CARD\n"
        "EPIC NO\n"
        "ABC1234567\n"
        "Elector's Name\n"
        "ANJALI NAIR\n"
        "Father's Name\n"
        "SURESH NAIR\n"
        "Sex\n"
        "FEMALE\n"
        "Date of Birth\n"
        "22/04/1997\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_voter_id_fields(raw_text, lines)
    assert fields["document_number"] == "ABC1234567"
    assert fields["full_name"] == "ANJALI NAIR"
    assert fields["date_of_birth"] == "22/04/1997"
    assert fields["sex"] == "F"
    assert fields["nationality"] == "INDIA"
    assert fields["date_of_expiry"] is None  # Voter ID has no expiry by design


def test_extract_text_routes_to_voter_id_parser_and_tags_document_type(monkeypatch):
    voter_id_raw = (
        "ELECTION COMMISSION OF INDIA\n"
        "ELECTORS PHOTO IDENTITY CARD\n"
        "EPIC NO\n"
        "ABC1234567\n"
        "Elector's Name\n"
        "ANJALI NAIR\n"
        "Sex\n"
        "FEMALE\n"
        "Date of Birth\n"
        "22/04/1997\n"
    )
    monkeypatch.setattr(svc, "preprocess_image", lambda path: None)
    monkeypatch.setattr("pytesseract.image_to_data", lambda *a, **k: {"conf": []})
    monkeypatch.setattr("pytesseract.image_to_string", lambda *a, **k: voter_id_raw)

    result = svc.extract_text("unused.jpg")
    assert result["fields"]["document_type"] == "VOTER_ID"
    assert result["fields"]["document_number"] == "ABC1234567"
    assert result["fields"]["full_name"] == "ANJALI NAIR"


def test_detect_document_type_recognizes_visa_markers():
    raw_text = "ENTRY VISA\nBUREAU OF IMMIGRATION • REPUBLIC OF UTOPIA\nVISA NUMBER\nUV1234567\n"
    assert TesseractOCRService._detect_document_type(raw_text) == "VISA"


def test_visa_marker_does_not_collide_with_stamp_manipulated_passport_text():
    """
    generate_document's own 'stamp_manipulated'/'multiple_anomalies' modes
    draw a simulated pasted stamp reading "VISA EXEMPTION [SIMULATED
    PATCH]" directly onto a PASSPORT specimen (see synthetic_generator.py).
    A bare "VISA" substring marker would misroute that tampered passport to
    the visa field parser instead of the passport one -- VISA_MARKERS must
    require a more specific phrase that this stamp text never contains.
    """
    raw_text = (
        "DEMO TRAVEL DOCUMENT\n"
        "REPUBLIC OF UTOPIA • FICTIONAL TEST SPECIMEN\n"
        "VISA EXEMPTION\n"
        "[SIMULATED PATCH]\n"
    )
    assert TesseractOCRService._detect_document_type(raw_text) == "PASSPORT"


def test_visa_fields_extract_all_four_new_fields_plus_baseline():
    raw_text = (
        "ENTRY VISA\n"
        "BUREAU OF IMMIGRATION\n"
        "VISA NUMBER\n"
        "UV1234567\n"
        "FULL NAME\n"
        "CARLOS MENDEZ\n"
        "NATIONALITY\n"
        "UTOPIAN\n"
        "DATE OF BIRTH\n"
        "14/03/1985\n"
        "VISA TYPE\n"
        "BUSINESS\n"
        "ENTRY VALIDATION\n"
        "MULTIPLE ENTRY\n"
        "DATE OF ISSUE\n"
        "01/01/2026\n"
        "STAY DURATION\n"
        "30/06/2026\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_visa_fields(raw_text, lines)
    assert fields["document_number"] == "UV1234567"
    assert fields["full_name"] == "CARLOS MENDEZ"
    assert fields["nationality"] == "UTOPIAN"
    assert fields["date_of_birth"] == "14/03/1985"
    assert fields["visa_type"] == "BUSINESS"
    assert fields["entry_validation"] == "MULTIPLE ENTRY"
    assert fields["date_of_issue"] == "01/01/2026"
    assert fields["stay_duration_until"] == "30/06/2026"
    assert fields["country"] == "REPUBLIC OF UTOPIA"


def test_visa_number_survives_tesseract_misreading_number_as_numbef():
    """
    Reproduces a real failure found by rendering an actual visa specimen
    through real Tesseract: the small label-font "R" in "VISA NUMBER" was
    misread as "VISA NUMBEF" -- an exact-match \bVISA NUMBER\b search
    returns None entirely on this single-character slip. Same class of bug
    DL's "VALID TILL" -> "VAUD TILL" fix addressed.
    """
    raw_text = (
        "ENTRY VISA\n"
        "VISA NUMBEF\n"
        "UV1234567\n"
    )
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_visa_fields(raw_text, lines)
    assert fields["document_number"] == "UV1234567"


def test_visa_stay_duration_is_none_when_label_missing():
    """No fabricated date when the field simply isn't present on the document."""
    raw_text = "ENTRY VISA\nBUREAU OF IMMIGRATION\nVISA NUMBER\nUV1234567\n"
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    fields = svc.parse_visa_fields(raw_text, lines)
    assert fields["stay_duration_until"] is None


def test_extract_text_routes_to_visa_parser_and_tags_document_type(monkeypatch):
    visa_raw = (
        "ENTRY VISA\n"
        "BUREAU OF IMMIGRATION\n"
        "VISA NUMBER\n"
        "UV1234567\n"
        "FULL NAME\n"
        "CARLOS MENDEZ\n"
        "VISA TYPE\n"
        "BUSINESS\n"
        "ENTRY VALIDATION\n"
        "MULTIPLE ENTRY\n"
        "STAY DURATION\n"
        "30/06/2026\n"
    )
    monkeypatch.setattr(svc, "preprocess_image", lambda path: None)
    monkeypatch.setattr("pytesseract.image_to_data", lambda *a, **k: {"conf": []})
    monkeypatch.setattr("pytesseract.image_to_string", lambda *a, **k: visa_raw)

    result = svc.extract_text("unused.jpg")
    assert result["fields"]["document_type"] == "VISA"
    assert result["fields"]["document_number"] == "UV1234567"
    assert result["fields"]["stay_duration_until"] == "30/06/2026"
