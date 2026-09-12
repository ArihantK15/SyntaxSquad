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
