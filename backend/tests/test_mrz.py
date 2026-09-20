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


def test_composite_checksum_survives_ocr_noise_in_optional_data_field():
    """
    Reproduces a real failure found against genuine MIDV-2020 Greek passport
    scans (scripts/evaluate_mrz_on_midv2020.py): the optional-data field's
    trailing character -- a literal '0' immediately before the composite
    check digit -- was consistently OCR'd as the letter 'Q'. Every other
    field (doc number, DOB, expiry, names) read perfectly and passed its own
    checksum, but the composite was computed from optional_raw completely
    un-normalized (unlike every other field feeding it), so this single
    ordinary OCR slip alone dropped the composite pass rate for this
    document type from a would-be ~100% to 14%. This is the same class of
    bug as test_composite_checksum_survives_ocr_digit_letter_confusion above,
    just in the field that fix accidentally skipped.

    Note: this bug's first fix attempt over-corrected by blanket-normalizing
    optional_raw for the composite calculation -- see
    test_composite_checksum_tolerates_genuine_alphanumeric_optional_data
    below for why that was reverted in favor of trying both interpretations.
    """
    line1 = "P<GRCPAPAGO<<GABRIEL<<<<<<<<<<<<<<<<<<<<<<<<"
    doc_raw, dob_raw, exp_raw = "AK6995574", "870102", "230317"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_cd = MRZService.compute_check_digit(exp_raw)
    opt_raw = "<" * 14 + "0"  # genuine trailing '0', not filler
    comp_cd = MRZService.compute_check_digit(doc_raw + doc_cd + dob_raw + dob_cd + exp_raw + exp_cd + opt_raw)

    # OCR misread the optional field's trailing '0' as the letter 'Q'.
    ocr_opt_raw = "<" * 14 + "Q"
    line2 = f"{doc_raw}{doc_cd}GRC{dob_raw}{dob_cd}M{exp_raw}{exp_cd}{ocr_opt_raw}{comp_cd}"

    result = MRZService.parse_td3(line1, line2)
    comp_cs = [cs for cs in result["checksums"] if "Composite" in cs["field"]][0]
    assert comp_cs["valid"] is True
    assert result["is_valid"] is True


def test_composite_checksum_tolerates_genuine_alphanumeric_optional_data():
    """
    Regression guard for a real over-correction caught against genuine
    MIDV-2020 Azerbaijani passport scans: an earlier fix for the Greek-
    passport bug above blanket-normalized optional_raw (treating it as
    strictly numeric, the same way DOB/expiry are). That broke 61/100
    genuine, unmodified Azerbaijani ground-truth records, whose optional
    field carries a real alphanumeric personal-ID code (e.g. "KEK2K556")
    -- normalize_digits rewrote real letters (S->5, O->0, etc.) as if they
    were OCR noise, corrupting the checksum on entirely valid documents.
    ICAO 9303 does not mandate optional data be numeric, so this MUST keep
    validating when the field is genuinely alphanumeric and untouched by OCR.
    """
    line1 = "P<AZEABDULLAYEV<<DIL<<<<<<<<<<<<<<<<<<<<<<<<"
    doc_raw, dob_raw, exp_raw = "C19389564", "940814", "280815"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_cd = MRZService.compute_check_digit(exp_raw)
    opt_raw = "KEK2K556<<<<<<<"  # genuine alphanumeric personal-ID code, padded to the 15-char field width
    comp_cd = MRZService.compute_check_digit(doc_raw + doc_cd + dob_raw + dob_cd + exp_raw + exp_cd + opt_raw)
    line2 = f"{doc_raw}{doc_cd}AZE{dob_raw}{dob_cd}M{exp_raw}{exp_cd}{opt_raw}{comp_cd}"

    result = MRZService.parse_td3(line1, line2)
    comp_cs = [cs for cs in result["checksums"] if "Composite" in cs["field"]][0]
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


def test_garbled_sex_code_is_preserved_not_silently_defaulted_to_m():
    """
    Reproduces a real gap found while reviewing MRZ parsing against Rule 7
    (SEX_CODE_FORMAT, backend/app/services/rules_engine.py, added
    specifically to catch a malformed sex/gender code): parse_td3 replaced
    ANY sex character that wasn't already M/F/X/'<' with a hardcoded 'M'
    before returning it, so a genuine OCR misread (e.g. 'G' instead of 'M')
    was silently rewritten into a valid code -- meaning Rule 7 could never
    actually fire against real OCR'd data, only against a hand-built
    mrz_data dict that bypasses the parser entirely (as the existing
    test_sex_code_invalid in test_rules.py does). The parser must pass the
    raw (uppercased) character through untouched -- other than mapping
    literal '<' filler to 'X' (ICAO 9303's own "unspecified" code) -- so
    downstream validation can see and flag it.
    """
    line1 = "P<UTOKAUL<<ARIHANT<<<<<<<<<<<<<<<<<<<<<<"
    doc_raw, dob_raw, exp_raw = "X1234567<", "000101", "300101"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_cd = MRZService.compute_check_digit(exp_raw)
    opt_raw = "<" * 15
    comp_cd = MRZService.compute_check_digit(doc_raw + doc_cd + dob_raw + dob_cd + exp_raw + exp_cd + opt_raw)

    # OCR misread the sex character 'M' as 'G' (visually plausible OCR slip,
    # and definitely not a valid ICAO sex code).
    line2 = f"{doc_raw}{doc_cd}UTO{dob_raw}{dob_cd}G{exp_raw}{exp_cd}{opt_raw}{comp_cd}"

    result = MRZService.parse_td3(line1, line2)
    assert result["sex"] == "G"


def test_mrz_td1_parsing():
    """Tests parsing a standard TD1 national-ID-card MRZ triplet."""
    doc_raw = "I12345678"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    optional1_raw = "<" * 15
    line1 = f"I<UTO{doc_raw}{doc_cd}{optional1_raw}"
    assert len(line1) == 30

    dob_raw = "000101"
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_raw = "300101"
    exp_cd = MRZService.compute_check_digit(exp_raw)
    optional2_raw = "<" * 11
    comp_raw = doc_raw + doc_cd + optional1_raw + dob_raw + dob_cd + exp_raw + exp_cd + optional2_raw
    comp_cd = MRZService.compute_check_digit(comp_raw)
    line2 = f"{dob_raw}{dob_cd}M{exp_raw}{exp_cd}UTO{optional2_raw}{comp_cd}"
    assert len(line2) == 30

    line3 = "KAUL<<ARIHANT".ljust(30, '<')

    result = MRZService.parse_td1(line1, line2, line3)
    assert result["format"] == "TD1"
    assert result["country"] == "UTO"
    assert result["nationality"] == "UTO"
    assert result["document_number"] == "I12345678"
    assert result["surname"] == "KAUL"
    assert result["given_names"] == "ARIHANT"
    assert result["sex"] == "M"
    assert result["is_valid"] is True
    assert all(cs["valid"] for cs in result["checksums"])


def test_mrz_td1_checksum_tampering_detected():
    """Corrupting the TD1 document-number check digit must fail validation."""
    doc_raw = "I12345678"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    corrupted_cd = "9" if doc_cd != "9" else "8"
    optional1_raw = "<" * 15
    line1 = f"I<UTO{doc_raw}{corrupted_cd}{optional1_raw}"

    dob_raw = "000101"
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_raw = "300101"
    exp_cd = MRZService.compute_check_digit(exp_raw)
    optional2_raw = "<" * 11
    comp_raw = doc_raw + doc_cd + optional1_raw + dob_raw + dob_cd + exp_raw + exp_cd + optional2_raw
    comp_cd = MRZService.compute_check_digit(comp_raw)
    line2 = f"{dob_raw}{dob_cd}M{exp_raw}{exp_cd}UTO{optional2_raw}{comp_cd}"
    line3 = "KAUL<<ARIHANT".ljust(30, '<')

    result = MRZService.parse_td1(line1, line2, line3)
    assert result["is_valid"] is False
    doc_cs = [cs for cs in result["checksums"] if "Document Number" in cs["field"]][0]
    assert doc_cs["valid"] is False


def test_mrz_td2_parsing():
    """Tests parsing a standard TD2 (visa / ID card) MRZ pair."""
    line1 = "I<UTOKAUL<<ARIHANT".ljust(36, '<')
    assert len(line1) == 36

    doc_raw = "X1234567<"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    dob_raw = "000101"
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_raw = "300101"
    exp_cd = MRZService.compute_check_digit(exp_raw)
    optional_raw = "<" * 7
    comp_raw = doc_raw + doc_cd + dob_raw + dob_cd + exp_raw + exp_cd + optional_raw
    comp_cd = MRZService.compute_check_digit(comp_raw)
    line2 = f"{doc_raw}{doc_cd}UTO{dob_raw}{dob_cd}M{exp_raw}{exp_cd}{optional_raw}{comp_cd}"
    assert len(line2) == 36

    result = MRZService.parse_td2(line1, line2)
    assert result["format"] == "TD2"
    assert result["country"] == "UTO"
    assert result["surname"] == "KAUL"
    assert result["given_names"] == "ARIHANT"
    assert result["document_number"] == "X1234567"
    assert result["nationality"] == "UTO"
    assert result["is_valid"] is True
    assert all(cs["valid"] for cs in result["checksums"])


def test_mrz_td2_checksum_tampering_detected():
    """Corrupting the TD2 composite check digit must fail validation."""
    line1 = "I<UTOKAUL<<ARIHANT".ljust(36, '<')
    doc_raw = "X1234567<"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    dob_raw = "000101"
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_raw = "300101"
    exp_cd = MRZService.compute_check_digit(exp_raw)
    optional_raw = "<" * 7
    comp_raw = doc_raw + doc_cd + dob_raw + dob_cd + exp_raw + exp_cd + optional_raw
    comp_cd = MRZService.compute_check_digit(comp_raw)
    corrupted_comp_cd = "9" if comp_cd != "9" else "8"
    line2 = f"{doc_raw}{doc_cd}UTO{dob_raw}{dob_cd}M{exp_raw}{exp_cd}{optional_raw}{corrupted_comp_cd}"

    result = MRZService.parse_td2(line1, line2)
    assert result["is_valid"] is False


def test_parse_pre_isolated_lines_dispatches_td1_from_three_lines():
    """Three isolated MRZ lines must be parsed as TD1, not forced into TD3."""
    doc_raw = "I12345678"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    optional1_raw = "<" * 15
    line1 = f"I<UTO{doc_raw}{doc_cd}{optional1_raw}"

    dob_raw = "000101"
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_raw = "300101"
    exp_cd = MRZService.compute_check_digit(exp_raw)
    optional2_raw = "<" * 11
    comp_raw = doc_raw + doc_cd + optional1_raw + dob_raw + dob_cd + exp_raw + exp_cd + optional2_raw
    comp_cd = MRZService.compute_check_digit(comp_raw)
    line2 = f"{dob_raw}{dob_cd}M{exp_raw}{exp_cd}UTO{optional2_raw}{comp_cd}"
    line3 = "KAUL<<ARIHANT".ljust(30, '<')

    result = MRZService.parse_pre_isolated_lines([line1, line2, line3])
    assert result is not None
    assert result["format"] == "TD1"
    assert result["is_valid"] is True


def test_parse_pre_isolated_lines_defaults_ambiguous_two_line_input_to_td3():
    """
    TD2 and TD3 share an identical line2 prefix layout and differ only in
    the optional-data field's length, immediately before the final
    composite check digit -- so whenever that field ends in '<' filler (the
    common case, exercised here with an all-filler optional field), a
    genuine TD2 line ALSO parses as a checksum-valid TD3, since appending
    extra zero-value filler at the tail of a checksum payload can't change
    its sum. A checksum-based tiebreak between the two is therefore not a
    real tiebreak. TD3 (passports) is this system's dominant real-world
    case, so the dispatcher deliberately defaults ambiguous 2-line input to
    it rather than guess; parse_td2 remains directly callable and correct
    for a caller that already knows its input is TD2.
    """
    line1 = "I<UTOKAUL<<ARIHANT".ljust(36, '<')
    doc_raw = "X1234567<"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    dob_raw = "000101"
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_raw = "300101"
    exp_cd = MRZService.compute_check_digit(exp_raw)
    optional_raw = "<" * 7
    comp_raw = doc_raw + doc_cd + dob_raw + dob_cd + exp_raw + exp_cd + optional_raw
    comp_cd = MRZService.compute_check_digit(comp_raw)
    line2 = f"{doc_raw}{doc_cd}UTO{dob_raw}{dob_cd}M{exp_raw}{exp_cd}{optional_raw}{comp_cd}"

    result = MRZService.parse_pre_isolated_lines([line1, line2])
    assert result is not None
    assert result["format"] == "TD3"
    assert result["is_valid"] is True
    # The fields that matter downstream are still correct regardless of the
    # format label, since TD2 and TD3 share this prefix layout exactly.
    assert result["document_number"] == "X1234567"
    assert result["nationality"] == "UTO"


def test_extract_mrz_from_lines_still_finds_td3_pair_among_prose():
    """Regression guard: whole-document scanning must still recognize TD3."""
    line1 = "P<UTOKAUL<<ARIHANT<<<<<<<<<<<<<<<<<<<<<<"
    doc_raw, dob_raw, exp_raw = "X1234567<", "000101", "300101"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_cd = MRZService.compute_check_digit(exp_raw)
    opt_raw = "<" * 15
    comp_cd = MRZService.compute_check_digit(doc_raw + doc_cd + dob_raw + dob_cd + exp_raw + exp_cd + opt_raw)
    line2 = f"{doc_raw}{doc_cd}UTO{dob_raw}{dob_cd}M{exp_raw}{exp_cd}{opt_raw}{comp_cd}"

    text_lines = ["DEMO TRAVEL DOCUMENT", "SURNAME: KAUL", line1, line2]
    result = MRZService.extract_mrz_from_lines(text_lines)
    assert result is not None
    assert result["format"] == "TD3"
    assert result["is_valid"] is True


def test_extract_mrz_from_lines_finds_td1_triplet_among_prose():
    """Whole-document scanning must recognize a TD1 triplet, not just TD3 pairs."""
    doc_raw = "I12345678"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    optional1_raw = "<" * 15
    line1 = f"I<UTO{doc_raw}{doc_cd}{optional1_raw}"

    dob_raw = "000101"
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_raw = "300101"
    exp_cd = MRZService.compute_check_digit(exp_raw)
    optional2_raw = "<" * 11
    comp_raw = doc_raw + doc_cd + optional1_raw + dob_raw + dob_cd + exp_raw + exp_cd + optional2_raw
    comp_cd = MRZService.compute_check_digit(comp_raw)
    line2 = f"{dob_raw}{dob_cd}M{exp_raw}{exp_cd}UTO{optional2_raw}{comp_cd}"
    line3 = "KAUL<<ARIHANT".ljust(30, '<')

    text_lines = ["NATIONAL IDENTITY CARD", "REPUBLIC OF UTOPIA", line1, line2, line3]
    result = MRZService.extract_mrz_from_lines(text_lines)
    assert result is not None
    assert result["format"] == "TD1"
    assert result["is_valid"] is True


def test_td3_with_heavily_undercounted_filler_is_not_misrouted_to_td2():
    """
    Reproduces a real failure: a genuine TD3 document whose trailing '<'
    filler run OCR'd short enough that neither line reached 40 characters
    (line2 read at 39) got misrouted into parse_td2 by a naive
    "length >= 40 -> TD3, else TD2" dispatch -- TD2's field offsets are
    completely different from TD3's, so every checksum on this entirely
    genuine document came out wrong. Since TD2 cannot exceed 36 real
    characters, a 39-character line is unambiguous proof of TD3 regardless
    of how short the OTHER line (here, a heavily undercounted line1) reads.
    """
    doc_raw, dob_raw, exp_raw = "P8B92144<", "850704", "300420"
    doc_cd = MRZService.compute_check_digit(doc_raw)
    dob_cd = MRZService.compute_check_digit(dob_raw)
    exp_cd = MRZService.compute_check_digit(exp_raw)
    opt_raw = "<" * 15
    comp_cd = MRZService.compute_check_digit(doc_raw + doc_cd + dob_raw + dob_cd + exp_raw + exp_cd + opt_raw)

    line1 = "P<ATLKOROL<<VICTOR<<<<<<<<"  # 26 chars: filler run undercounted
    full_line2 = f"{doc_raw}{doc_cd}ATL{dob_raw}{dob_cd}M{exp_raw}{exp_cd}{opt_raw}{comp_cd}"
    assert len(full_line2) == 44
    # Simulate OCR undercounting the filler run (15 '<' read as 10), while
    # still correctly reading the real composite check digit right after it.
    line2 = full_line2[:-(len(opt_raw) + 1)] + ("<" * 10) + comp_cd
    assert len(line2) == 39

    result = MRZService.parse_pre_isolated_lines([line1, line2])
    assert result is not None
    assert result["format"] == "TD3"
    assert result["document_number"] == "P8B92144"
    assert result["is_valid"] is True


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
