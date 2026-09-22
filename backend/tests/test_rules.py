from datetime import date
from app.services.rules_engine import DocumentRulesEngine

def test_document_rules_genuine():
    ocr_data = {
        "fields": {
            "full_name": "ARIHANT KAUL",
            "document_number": "X1234567",
            "country": "UTOPIA",
            "nationality": "UTOPIA"
        }
    }
    mrz_data = {
        "surname": "KAUL",
        "given_names": "ARIHANT",
        "document_number": "X1234567",
        "nationality": "UTO",
        "birth_date": "000101",
        "expiry_date": "300101", # Year 2030, in future
        "checksums": [
            {"field": "Document Number Checksum", "valid": True, "check_digit": "7", "calculated_check_digit": "7"},
            {"field": "Date of Birth Checksum", "valid": True, "check_digit": "1", "calculated_check_digit": "1"},
            {"field": "Expiry Date Checksum", "valid": True, "check_digit": "2", "calculated_check_digit": "2"},
            {"field": "Composite Checksum", "valid": True, "check_digit": "0", "calculated_check_digit": "0"}
        ]
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, mrz_data)
    assert eval_res["failed_count"] == 0
    assert eval_res["passed_count"] > 0
    assert len(eval_res["signals"]) == 0

def test_document_rules_expired():
    ocr_data = {"fields": {"document_number": "X1234567"}}
    mrz_data = {
        "surname": "KAUL",
        "document_number": "X1234567",
        "nationality": "UTO",
        "birth_date": "900101",
        "expiry_date": "200101", # Expired in 2020
        "checksums": []
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, mrz_data)
    assert any(s["signal"] == "Document Expired" for s in eval_res["signals"])
    expired_rule = [r for r in eval_res["rules_detail"] if r["rule"] == "DOCUMENT_EXPIRATION"][0]
    assert expired_rule["passed"] is False

def test_document_rules_mismatch():
    ocr_data = {"fields": {"document_number": "A9999999", "full_name": "JOHN DOE"}}
    mrz_data = {
        "surname": "DOE",
        "document_number": "B8888888", # Inconsistency between visual and MRZ
        "nationality": "UTO",
        "birth_date": "920510",
        "expiry_date": "300101",
        "checksums": []
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, mrz_data)
    assert any("Document Number Inconsistency" in s["signal"] for s in eval_res["signals"])

def test_sex_code_valid():
    ocr_data = {"fields": {"document_number": "X1234567"}}
    mrz_data = {
        "document_number": "X1234567",
        "nationality": "UTO",
        "birth_date": "000101",
        "expiry_date": "300101",
        "sex": "M",
        "checksums": []
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, mrz_data)
    sex_rule = [r for r in eval_res["rules_detail"] if r["rule"] == "SEX_CODE_FORMAT"][0]
    assert sex_rule["passed"] is True
    assert not any(s["signal"] == "Malformed Sex/Gender Code" for s in eval_res["signals"])

def test_sex_code_invalid():
    ocr_data = {"fields": {"document_number": "X1234567"}}
    mrz_data = {
        "document_number": "X1234567",
        "nationality": "UTO",
        "birth_date": "000101",
        "expiry_date": "300101",
        "sex": "1",
        "checksums": []
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, mrz_data)
    sex_rule = [r for r in eval_res["rules_detail"] if r["rule"] == "SEX_CODE_FORMAT"][0]
    assert sex_rule["passed"] is False
    assert any(s["signal"] == "Malformed Sex/Gender Code" for s in eval_res["signals"])

def test_document_number_crosscheck_survives_single_ocr_slip():
    """
    The visual-zone text and the MRZ line are two INDEPENDENT OCR passes over
    the same physical document number -- each can misread a different
    character. The old exact-or-substring check had no tolerance for this,
    so a single-character OCR slip in either pass alone (with no actual
    document tampering) would fire a false HIGH-severity "Document Number
    Inconsistency" signal, exactly the same OCR-noise-intolerance bug already
    fixed tonight for the MRZ composite checksum, nationality code, and
    watchlist matching.
    """
    ocr_data = {"fields": {"document_number": "X1B34567"}}  # '2' misread as 'B'
    mrz_data = {
        "surname": "KAUL",
        "document_number": "X1234567",
        "nationality": "UTO",
        "birth_date": "000101",
        "expiry_date": "300101",
        "checksums": []
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, mrz_data)
    assert not any("Document Number Inconsistency" in s["signal"] for s in eval_res["signals"])

def test_document_number_crosscheck_still_catches_real_mismatch():
    """Tolerance is bounded to a single edit -- a genuinely different document
    number must still be flagged."""
    ocr_data = {"fields": {"document_number": "A9999999", "full_name": "JOHN DOE"}}
    mrz_data = {
        "surname": "DOE",
        "document_number": "B8888888",
        "nationality": "UTO",
        "birth_date": "920510",
        "expiry_date": "300101",
        "checksums": []
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, mrz_data)
    assert any("Document Number Inconsistency" in s["signal"] for s in eval_res["signals"])

def test_document_number_crosscheck_rejects_a_trivially_short_ocr_reading():
    """
    Reproduces a real logic gap found while reviewing RULE 4's OCR-noise
    tolerance: alongside the bounded fuzzy-edit check, it also allows
    outright substring containment (`clean_ocr_no in clean_mrz_no`) with NO
    length floor. A near-degenerate OCR reading of the document number
    (e.g. a single surviving character out of a badly garbled read) is then
    trivially "contained" in almost any longer MRZ document number,
    regardless of how different the two actually are -- silently defeating
    the exact cross-check this rule exists to run. A genuinely truncated-
    but-real partial read (the case substring containment is meant to
    tolerate) is always several characters long; a bare single character is
    not a plausible partial read, it's a failed one, and must still be
    flagged.
    """
    ocr_data = {"fields": {"document_number": "7"}}  # OCR essentially failed
    mrz_data = {
        "surname": "KAUL",
        "document_number": "X1234567",  # happens to contain '7', but is a wholly different number
        "nationality": "UTO",
        "birth_date": "000101",
        "expiry_date": "300101",
        "checksums": []
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, mrz_data)
    assert any("Document Number Inconsistency" in s["signal"] for s in eval_res["signals"])

def test_aadhaar_document_not_penalized_for_missing_mrz():
    """
    Aadhaar cards are a national ID, not an ICAO 9303 travel document -- they
    have no MRZ by design (a QR code carries the machine-readable payload
    instead). Before document-type awareness, `evaluate()` flagged ANY
    document with no MRZ as "Missing Machine Readable Zone" (HIGH severity),
    which would misclassify every genuine Aadhaar card as suspicious.
    """
    ocr_data = {
        "fields": {
            "full_name": "RAVI KUMAR",
            "document_number": "123456789012",
            "nationality": "INDIA",
            "country": "INDIA",
            "document_type": "AADHAAR"
        }
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, None)
    assert not any(s["signal"] == "Missing Machine Readable Zone" for s in eval_res["signals"])
    mrz_rule = [r for r in eval_res["rules_detail"] if r["rule"] == "MRZ_PRESENCE"][0]
    assert mrz_rule["passed"] is True

def test_passport_without_mrz_still_flagged():
    """Non-Aadhaar documents missing an MRZ must still be flagged -- the
    Aadhaar exemption must not silently apply to every document type."""
    ocr_data = {"fields": {"full_name": "JOHN DOE", "document_number": "A9999999"}}
    eval_res = DocumentRulesEngine.evaluate(ocr_data, None)
    assert any(s["signal"] == "Missing Machine Readable Zone" for s in eval_res["signals"])

def test_pan_document_not_penalized_for_missing_mrz():
    """PAN cards are an Income Tax Department ID, not an ICAO 9303 travel
    document -- like Aadhaar, they must not be flagged for having no MRZ."""
    ocr_data = {
        "fields": {
            "full_name": "RAVI KUMAR SHARMA",
            "document_number": "ABCPK1234F",
            "document_type": "PAN"
        }
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, None)
    assert not any(s["signal"] == "Missing Machine Readable Zone" for s in eval_res["signals"])
    mrz_rule = [r for r in eval_res["rules_detail"] if r["rule"] == "MRZ_PRESENCE"][0]
    assert mrz_rule["passed"] is True

def test_dl_document_not_penalized_for_missing_mrz():
    """Driving Licences carry no ICAO MRZ either -- same exemption as
    Aadhaar/PAN."""
    ocr_data = {
        "fields": {
            "full_name": "RAVI KUMAR SHARMA",
            "document_number": "MH1220110012345",
            "document_type": "DRIVING_LICENSE"
        }
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, None)
    assert not any(s["signal"] == "Missing Machine Readable Zone" for s in eval_res["signals"])

def test_pan_format_validation_passes_for_well_formed_pan_and_decodes_entity_type():
    ocr_data = {
        "fields": {
            "full_name": "RAVI KUMAR SHARMA",
            "document_number": "ABCPK1234F",
            "document_type": "PAN"
        }
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, None)
    pan_rule = [r for r in eval_res["rules_detail"] if r["rule"] == "PAN_FORMAT_VALIDATION"][0]
    assert pan_rule["passed"] is True
    assert "Individual" in pan_rule["explanation"]
    assert not any("PAN" in s["signal"] for s in eval_res["signals"])

def test_pan_format_validation_fails_for_malformed_structure():
    """A structurally invalid PAN (wrong character classes/length) is a real,
    verifiable format violation -- CBDT's published PAN structure is fixed
    (5 letters, 4 digits, 1 letter), not free text."""
    ocr_data = {
        "fields": {
            "full_name": "RAVI KUMAR SHARMA",
            "document_number": "ABCP1234F",  # only 4 letters before the digits
            "document_type": "PAN"
        }
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, None)
    pan_rule = [r for r in eval_res["rules_detail"] if r["rule"] == "PAN_FORMAT_VALIDATION"][0]
    assert pan_rule["passed"] is False
    assert any(s["signal"] == "Malformed PAN Structure" for s in eval_res["signals"])

def test_pan_format_validation_flags_unrecognized_entity_letter():
    """The 4th PAN character encodes a documented, enumerable entity type
    (P=Individual, C=Company, etc.) -- a structurally valid PAN whose 4th
    letter isn't one of those codes is suspicious even though the shape is
    otherwise fine."""
    ocr_data = {
        "fields": {
            "full_name": "RAVI KUMAR SHARMA",
            "document_number": "ABCZK1234F",  # 'Z' is not a recognized entity-type code
            "document_type": "PAN"
        }
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, None)
    assert any(s["signal"] == "Unrecognized PAN Entity-Type Code" for s in eval_res["signals"])

def test_pan_rule_skipped_for_non_pan_documents():
    """A passport document number that happens to be PAN-shaped must not
    trigger PAN-specific validation -- the rule is gated on document_type,
    not on the number's shape alone."""
    ocr_data = {"fields": {"document_number": "ABCPK1234F", "document_type": "PASSPORT"}}
    eval_res = DocumentRulesEngine.evaluate(ocr_data, None)
    assert not any(r["rule"] == "PAN_FORMAT_VALIDATION" for r in eval_res["rules_detail"])

def test_dl_expiry_uses_ocr_field_when_no_mrz_present():
    """
    A Driving Licence has a genuine printed expiry ("Valid Till") but no
    MRZ -- RULE 2 (DOCUMENT_EXPIRATION) was previously MRZ-only, so an
    expired DL was silently never checked at all. It must be checked the
    same way an expired passport is.
    """
    ocr_data = {
        "fields": {
            "document_number": "MH1220110012345",
            "document_type": "DRIVING_LICENSE",
            "date_of_expiry": "20/03/2020"  # expired
        }
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, None)
    assert any(s["signal"] == "Document Expired" for s in eval_res["signals"])
    expired_rule = [r for r in eval_res["rules_detail"] if r["rule"] == "DOCUMENT_EXPIRATION"][0]
    assert expired_rule["passed"] is False

def test_dl_valid_expiry_passes():
    ocr_data = {
        "fields": {
            "document_number": "MH1220110012345",
            "document_type": "DRIVING_LICENSE",
            "date_of_expiry": "20/03/2031"  # not yet expired
        }
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, None)
    expired_rule = [r for r in eval_res["rules_detail"] if r["rule"] == "DOCUMENT_EXPIRATION"][0]
    assert expired_rule["passed"] is True
    assert not any(s["signal"] == "Document Expired" for s in eval_res["signals"])

def test_voter_id_document_not_penalized_for_missing_mrz():
    """Voter ID (EPIC) cards are an Election Commission of India ID, not an
    ICAO 9303 travel document -- same MRZ exemption as Aadhaar/PAN/DL."""
    ocr_data = {
        "fields": {
            "full_name": "ANJALI NAIR",
            "document_number": "ABC1234567",
            "document_type": "VOTER_ID"
        }
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, None)
    assert not any(s["signal"] == "Missing Machine Readable Zone" for s in eval_res["signals"])
    mrz_rule = [r for r in eval_res["rules_detail"] if r["rule"] == "MRZ_PRESENCE"][0]
    assert mrz_rule["passed"] is True

def test_voter_id_format_validation_passes_for_well_formed_epic_number():
    ocr_data = {
        "fields": {
            "full_name": "ANJALI NAIR",
            "document_number": "ABC1234567",
            "document_type": "VOTER_ID"
        }
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, None)
    voter_id_rule = [r for r in eval_res["rules_detail"] if r["rule"] == "VOTER_ID_FORMAT_VALIDATION"][0]
    assert voter_id_rule["passed"] is True
    assert not any("EPIC" in s["signal"] for s in eval_res["signals"])

def test_voter_id_format_validation_flags_non_standard_structure_as_medium_not_high():
    """
    Unlike PAN's CBDT-enforced format (no legitimate exceptions), EPIC
    numbering has well-documented real-world non-conformance -- older and
    non-standard/duplicate registrations are a known, ECI-acknowledged
    issue. A non-conforming EPIC number is therefore a caution (MEDIUM),
    not a hard structural failure the way a malformed PAN is (HIGH).
    """
    ocr_data = {
        "fields": {
            "full_name": "ANJALI NAIR",
            "document_number": "AB123456789",  # wrong shape: 2 letters + 9 digits
            "document_type": "VOTER_ID"
        }
    }
    eval_res = DocumentRulesEngine.evaluate(ocr_data, None)
    voter_id_rule = [r for r in eval_res["rules_detail"] if r["rule"] == "VOTER_ID_FORMAT_VALIDATION"][0]
    assert voter_id_rule["passed"] is False
    assert voter_id_rule["severity"] == "MEDIUM"
    signal = [s for s in eval_res["signals"] if s["signal"] == "Non-Standard EPIC Format"][0]
    assert signal["severity"] == "MEDIUM"

def test_voter_id_rule_skipped_for_non_voter_id_documents():
    """An EPIC-shaped document number on a passport must not trigger
    Voter-ID-specific validation -- the rule is gated on document_type."""
    ocr_data = {"fields": {"document_number": "ABC1234567", "document_type": "PASSPORT"}}
    eval_res = DocumentRulesEngine.evaluate(ocr_data, None)
    assert not any(r["rule"] == "VOTER_ID_FORMAT_VALIDATION" for r in eval_res["rules_detail"])
