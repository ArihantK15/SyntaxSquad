import pytest
from app.services.ocr_service import TesseractOCRService

svc = TesseractOCRService.__new__(TesseractOCRService)  # skip __init__'s tesseract binary check


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
