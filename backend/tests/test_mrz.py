import pytest
from app.services.mrz_service import MRZService

def test_mrz_check_digit_calculation():
    """Validates the 7-3-1 ICAO 9303 check digit algorithm."""
    # Test doc number 'X1234567<' with weights:
    # X=33(x7=231), 1(x3=3), 2(x1=2), 3(x7=21), 4(x3=12), 5(x1=5), 6(x7=42), 7(x3=21), <=0(x1=0)
    # Sum = 231 + 3 + 2 + 21 + 12 + 5 + 42 + 21 + 0 = 337 -> 337 % 10 = 7
    # Let's test standard known values:
    cd1 = MRZService.compute_check_digit("L898902C<")
    assert cd1.isdigit()
    assert len(cd1) == 1

    # Date check digits: 740812 -> 7*7 + 4*3 + 0*1 + 8*7 + 1*3 + 2*1 = 49 + 12 + 0 + 56 + 3 + 2 = 122 -> 122 % 10 = 2
    assert MRZService.compute_check_digit("740812") == "2"

def test_mrz_td3_parsing():
    """Tests parsing a standard TD3 passport MRZ pair."""
    line1 = "P<UTOKAUL<<ARIHANT<<<<<<<<<<<<<<<<<<<<<<"
    # Line 2: doc=X1234567<, cd=7, nat=UTO, dob=000101, dob_cd=1, sex=M, exp=300101, exp_cd=2, opt=<<<<<<<<<<<<<<, comp_cd=...
    doc_raw = "X1234567<"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    dob_raw = "000101"
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_raw = "300101"
    exp_cd = MRZService.compute_check_digit(exp_raw)
    opt_raw = "<<<<<<<<<<<<<<<"
    comp_raw = doc_raw + doc_cd + dob_raw + dob_cd + exp_raw + exp_cd + opt_raw
    comp_cd = MRZService.compute_check_digit(comp_raw)

    line2 = f"{doc_raw}{doc_cd}UTO{dob_raw}{dob_cd}M{exp_raw}{exp_cd}{opt_raw}{comp_cd}"

    result = MRZService.parse_td3(line1, line2)
    assert result["format"] == "TD3"
    assert result["country"] == "UTO"
    assert result["surname"] == "KAUL"
    assert result["given_names"] == "ARIHANT"
    assert result["document_number"] == "X1234567"
    assert result["is_valid"] is True
    assert all(cs["valid"] for cs in result["checksums"])

def test_mrz_checksum_tampering_detection():
    """Verifies that tampering with a character or check digit fails validation."""
    line1 = "P<UTOKAUL<<ARIHANT<<<<<<<<<<<<<<<<<<<<<<"
    # Corrupt document check digit to '9'
    line2 = "X1234567<9UTO0001011M3001012<<<<<<<<<<<<<<00"
    result = MRZService.parse_td3(line1, line2)
    assert result["is_valid"] is False
    doc_cs = [cs for cs in result["checksums"] if "Document Number" in cs["field"]][0]
    assert doc_cs["valid"] is False


def test_reconstruct_length_pads_the_filler_run_not_the_end():
    """
    Regression guard: OCR on a dedicated MRZ-band pass reliably reads distinct
    characters but often undercounts a long run of the same repeated glyph
    ('<' filler) -- e.g. reading only 7 of a true 15-character '<' run, while
    still correctly reading the trailing composite check digit after it.
    Blind right-padding would push that trailing digit out of its fixed ICAO
    9303 position and corrupt checksum validation; the fix must pad inside the
    filler run instead, preserving trailing real characters.
    """
    doc_raw, dob_raw, exp_raw = "X1234567<", "000101", "300101"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_cd = MRZService.compute_check_digit(exp_raw)
    opt_raw = "<" * 15
    comp_cd = MRZService.compute_check_digit(doc_raw + doc_cd + dob_raw + dob_cd + exp_raw + exp_cd + opt_raw)

    full_line2 = f"{doc_raw}{doc_cd}UTO{dob_raw}{dob_cd}M{exp_raw}{exp_cd}{opt_raw}{comp_cd}"
    assert len(full_line2) == 44

    # Simulate OCR under-reading the filler run: keep the first 28 real chars
    # and the trailing composite check digit, but only 7 of the 15 '<' between them.
    undercounted = full_line2[:28] + ("<" * 7) + comp_cd
    assert len(undercounted) == 36

    reconstructed = MRZService._reconstruct_length(undercounted, 44)
    assert reconstructed == full_line2


def test_composite_checksum_survives_ocr_digit_letter_confusion():
    """
    Reproduces a real failure found on a genuine generated specimen: OCR
    misread the first digit of the date-of-birth field ('0' -> 'O'). The
    individual Date of Birth checksum already correctly normalizes this
    (normalize_digits converts O->0 before computing/comparing), so it
    passes. But the composite checksum was computed from a raw line2 slice
    (line2[13:20]) that still contained the un-normalized 'O' -- 'O' and '0'
    have different ICAO character values (24 vs 0), so the composite sum
    came out wrong even though the document is entirely genuine and every
    individual field checksum is valid. This is a false tampering signal on
    a clean document, triggered by completely ordinary OCR noise the rest of
    the parser is specifically designed to tolerate.
    """
    line1 = "P<UTOKAUL<<ARIHANT<<<<<<<<<<<<<<<<<<<<<<"
    doc_raw, dob_raw, exp_raw = "X1234567<", "000101", "300101"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_cd = MRZService.compute_check_digit(exp_raw)
    opt_raw = "<" * 15
    comp_cd = MRZService.compute_check_digit(doc_raw + doc_cd + dob_raw + dob_cd + exp_raw + exp_cd + opt_raw)

    # OCR misread the DOB field's leading '0' as the letter 'O'.
    ocr_dob_raw = "O00101"
    line2 = f"{doc_raw}{doc_cd}UTO{ocr_dob_raw}{dob_cd}M{exp_raw}{exp_cd}{opt_raw}{comp_cd}"

    result = MRZService.parse_td3(line1, line2)
    dob_cs = [cs for cs in result["checksums"] if "Date of Birth" in cs["field"]][0]
    comp_cs = [cs for cs in result["checksums"] if "Composite" in cs["field"]][0]
    assert dob_cs["valid"] is True
    assert comp_cs["valid"] is True
    assert result["is_valid"] is True


def test_nationality_survives_ocr_letter_digit_confusion():
    """
    Reproduces a real false positive found on a genuine generated specimen:
    Tesseract read the printed MRZ nationality code 'UTO' as 'UT0' (letter
    'O' misread as digit '0'). Unlike the numeric fields (doc number, dates),
    nationality/country are taken raw with no OCR-noise correction, so this
    single-character OCR slip flowed straight through parse_td3 into
    DocumentRulesEngine's alpha-format check, which flagged an entirely
    genuine document with a "Malformed Nationality Code" signal.
    """
    line1 = "P<UTOKAUL<<ARIHANT<<<<<<<<<<<<<<<<<<<<<<"
    doc_raw, dob_raw, exp_raw = "X1234567<", "000101", "300101"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_cd = MRZService.compute_check_digit(exp_raw)
    opt_raw = "<" * 15
    comp_cd = MRZService.compute_check_digit(doc_raw + doc_cd + dob_raw + dob_cd + exp_raw + exp_cd + opt_raw)

    # OCR misread nationality 'UTO' as 'UT0'.
    line2 = f"{doc_raw}{doc_cd}UT0{dob_raw}{dob_cd}M{exp_raw}{exp_cd}{opt_raw}{comp_cd}"

    result = MRZService.parse_td3(line1, line2)
    assert result["nationality"] == "UTO"


def test_country_survives_ocr_letter_digit_confusion():
    """Same OCR-noise problem, but for line1's country code."""
    line1 = "P<UT0KAUL<<ARIHANT<<<<<<<<<<<<<<<<<<<<<<"
    doc_raw, dob_raw, exp_raw = "X1234567<", "000101", "300101"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_cd = MRZService.compute_check_digit(exp_raw)
    opt_raw = "<" * 15
    comp_cd = MRZService.compute_check_digit(doc_raw + doc_cd + dob_raw + dob_cd + exp_raw + exp_cd + opt_raw)
    line2 = f"{doc_raw}{doc_cd}UTO{dob_raw}{dob_cd}M{exp_raw}{exp_cd}{opt_raw}{comp_cd}"

    result = MRZService.parse_td3(line1, line2)
    assert result["country"] == "UTO"


def test_parse_pre_isolated_lines_handles_short_ocr_output():
    """A dedicated MRZ-band OCR pass may return lines shorter than 44 chars if
    the trailing filler run was undercounted; parse_pre_isolated_lines must
    still recover a checksum-valid result rather than requiring full length."""
    short_line1 = "P<UTOKAUL<<ARIHANT<<<<<"  # 23 chars, missing tail padding
    doc_raw, dob_raw, exp_raw = "X1234567<", "000101", "300101"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_cd = MRZService.compute_check_digit(exp_raw)
    opt_raw = "<" * 15
    comp_cd = MRZService.compute_check_digit(doc_raw + doc_cd + dob_raw + dob_cd + exp_raw + exp_cd + opt_raw)
    short_line2 = doc_raw + doc_cd + "UTO" + dob_raw + dob_cd + "M" + exp_raw + exp_cd + ("<" * 7) + comp_cd

    result = MRZService.parse_pre_isolated_lines([short_line1, short_line2])
    assert result is not None
    assert result["document_number"] == "X1234567"
    assert result["is_valid"] is True
