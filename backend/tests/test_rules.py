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
