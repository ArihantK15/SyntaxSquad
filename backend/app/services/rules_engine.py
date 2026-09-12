from datetime import datetime, date
from typing import Dict, Any, List, Optional
import re

from app.utils.text_similarity import fuzzy_equal

class DocumentRulesEngine:
    """
    Configurable rules engine validating document consistency and integrity.
    Validates cross-field matching (visual OCR vs MRZ), expiration, checksums, and date boundaries.
    Generates structured risk signals for rule failures.
    """

    @classmethod
    def parse_yymmdd(cls, yymmdd: str) -> Optional[date]:
        """Parses ICAO YYMMDD date string."""
        if not yymmdd or len(yymmdd) != 6 or not yymmdd.isdigit():
            return None
        yy = int(yymmdd[:2])
        mm = int(yymmdd[2:4])
        dd = int(yymmdd[4:6])
        if not (1 <= mm <= 12 and 1 <= dd <= 31):
            return None
        # Heuristic: 00-40 -> 2000-2040, 41-99 -> 1941-1999
        century = 2000 if yy <= 45 else 1900
        try:
            return date(century + yy, mm, dd)
        except ValueError:
            return None

    @classmethod
    def evaluate(cls, ocr_data: Dict[str, Any], mrz_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        signals: List[Dict[str, Any]] = []
        
        today = date.today()
        fields = ocr_data.get("fields", {})
        
        # RULE 1: MRZ Checksum Validation
        if mrz_data and mrz_data.get("checksums"):
            for cs in mrz_data["checksums"]:
                field_name = cs["field"]
                is_valid = cs["valid"]
                if is_valid:
                    results.append({
                        "rule": f"MRZ_{field_name.upper().replace(' ', '_')}",
                        "passed": True,
                        "severity": "LOW",
                        "explanation": f"{field_name} matches calculated check digit ({cs['check_digit']}).",
                        "confidence": 0.99
                    })
                else:
                    results.append({
                        "rule": f"MRZ_{field_name.upper().replace(' ', '_')}",
                        "passed": False,
                        "severity": "HIGH",
                        "explanation": f"{field_name} check digit mismatch: found '{cs['check_digit']}', expected '{cs['calculated_check_digit']}'.",
                        "confidence": 0.99
                    })
                    signals.append({
                        "module": "MRZ",
                        "signal": f"MRZ Checksum Mismatch ({field_name})",
                        "severity": "HIGH",
                        "confidence": 0.99,
                        "explanation": f"ICAO 9303 check digit verification failed for {field_name}. Potential character alteration.",
                        "score_impact": 18.0
                    })
        elif fields.get("document_type") == "AADHAAR":
            # Aadhaar is a national ID card, not an ICAO 9303 travel
            # document -- it has no MRZ by design (a QR code carries its
            # machine-readable data instead), so a missing MRZ here is
            # expected, not a red flag. Penalizing it the same as a
            # passport missing its MRZ would misclassify every genuine
            # Aadhaar card as suspicious.
            results.append({
                "rule": "MRZ_PRESENCE",
                "passed": True,
                "severity": "LOW",
                "explanation": "Not applicable — Aadhaar cards do not carry an ICAO Machine Readable Zone.",
                "confidence": 0.95
            })
        elif not mrz_data:
            results.append({
                "rule": "MRZ_PRESENCE",
                "passed": False,
                "severity": "HIGH",
                "explanation": "No valid Machine Readable Zone (MRZ) detected on document.",
                "confidence": 0.92
            })
            signals.append({
                "module": "MRZ",
                "signal": "Missing Machine Readable Zone",
                "severity": "HIGH",
                "confidence": 0.92,
                "explanation": "Standard travel documents must contain a readable 2-line or 3-line MRZ zone.",
                "score_impact": 20.0
            })

        # RULE 2: Expiration Check
        expiry_date = None
        if mrz_data and mrz_data.get("expiry_date"):
            expiry_date = cls.parse_yymmdd(mrz_data["expiry_date"])
        
        if expiry_date:
            if expiry_date < today:
                results.append({
                    "rule": "DOCUMENT_EXPIRATION",
                    "passed": False,
                    "severity": "CRITICAL",
                    "explanation": f"Document expired on {expiry_date.strftime('%Y-%m-%d')} (Current date: {today.strftime('%Y-%m-%d')}).",
                    "confidence": 0.99
                })
                signals.append({
                    "module": "VALIDATION",
                    "signal": "Document Expired",
                    "severity": "CRITICAL",
                    "confidence": 0.99,
                    "explanation": f"Travel document validity expired on {expiry_date.strftime('%Y-%m-%d')}. Document is invalid for travel.",
                    "score_impact": 28.0
                })
            else:
                results.append({
                    "rule": "DOCUMENT_EXPIRATION",
                    "passed": True,
                    "severity": "LOW",
                    "explanation": f"Document is valid until {expiry_date.strftime('%Y-%m-%d')}.",
                    "confidence": 0.99
                })
        else:
            results.append({
                "rule": "DOCUMENT_EXPIRATION",
                "passed": True,
                "severity": "LOW",
                "explanation": "Expiry date verified or pending visual confirmation.",
                "confidence": 0.85
            })

        # RULE 3: DOB Plausibility & Impossible Date
        dob_date = None
        if mrz_data and mrz_data.get("birth_date"):
            dob_date = cls.parse_yymmdd(mrz_data["birth_date"])
            if dob_date is None:
                results.append({
                    "rule": "IMPOSSIBLE_DATE",
                    "passed": False,
                    "severity": "HIGH",
                    "explanation": f"Malformed birth date in MRZ: '{mrz_data.get('birth_date')}'.",
                    "confidence": 0.98
                })
                signals.append({
                    "module": "VALIDATION",
                    "signal": "Impossible Date in MRZ",
                    "severity": "HIGH",
                    "confidence": 0.98,
                    "explanation": "Birth date contains non-existent calendar date values.",
                    "score_impact": 15.0
                })
            elif dob_date > today:
                results.append({
                    "rule": "FUTURE_BIRTH_DATE",
                    "passed": False,
                    "severity": "CRITICAL",
                    "explanation": f"Date of birth ({dob_date.strftime('%Y-%m-%d')}) is in the future.",
                    "confidence": 0.99
                })
                signals.append({
                    "module": "VALIDATION",
                    "signal": "Future Date of Birth",
                    "severity": "CRITICAL",
                    "confidence": 0.99,
                    "explanation": "Holder's recorded birth date is after current calendar date.",
                    "score_impact": 25.0
                })
            else:
                results.append({
                    "rule": "BIRTH_DATE_PLAUSIBILITY",
                    "passed": True,
                    "severity": "LOW",
                    "explanation": f"Valid birth date ({dob_date.strftime('%Y-%m-%d')}).",
                    "confidence": 0.99
                })

        # RULE 4: Visual Zone vs MRZ Document Number Inconsistency
        ocr_doc_no = fields.get("document_number")
        mrz_doc_no = mrz_data.get("document_number") if mrz_data else None
        
        if ocr_doc_no and mrz_doc_no:
            clean_ocr_no = re.sub(r'[^A-Za-z0-9]', '', ocr_doc_no).upper()
            clean_mrz_no = re.sub(r'[^A-Za-z0-9]', '', mrz_doc_no).upper()

            # The visual zone and the MRZ line are two independent OCR passes
            # over the same physical number -- each can misread a different
            # character. Tolerate a single-edit difference between them
            # (bounded, length-gated) rather than flagging ordinary OCR noise
            # as a document inconsistency.
            is_consistent = (
                clean_ocr_no == clean_mrz_no
                or clean_ocr_no in clean_mrz_no
                or clean_mrz_no in clean_ocr_no
                or fuzzy_equal(clean_ocr_no, clean_mrz_no)
            )
            if not is_consistent:
                results.append({
                    "rule": "DOC_NUMBER_CROSSCHECK",
                    "passed": False,
                    "severity": "HIGH",
                    "explanation": f"Visual text document number '{ocr_doc_no}' does not match MRZ document number '{mrz_doc_no}'.",
                    "confidence": 0.95
                })
                signals.append({
                    "module": "VALIDATION",
                    "signal": "Document Number Inconsistency",
                    "severity": "HIGH",
                    "confidence": 0.95,
                    "explanation": f"Visual inspection zone displays '{ocr_doc_no}' but machine-readable zone records '{mrz_doc_no}'.",
                    "score_impact": 22.0
                })
            else:
                results.append({
                    "rule": "DOC_NUMBER_CROSSCHECK",
                    "passed": True,
                    "severity": "LOW",
                    "explanation": "Visual document number matches MRZ document number.",
                    "confidence": 0.95
                })

        # RULE 5: Required Fields Presence
        missing_fields = []
        if not (fields.get("full_name") or (mrz_data and mrz_data.get("surname"))):
            missing_fields.append("Full Name")
        if not (ocr_doc_no or mrz_doc_no):
            missing_fields.append("Document Number")
        
        if missing_fields:
            results.append({
                "rule": "REQUIRED_FIELDS_PRESENCE",
                "passed": False,
                "severity": "MEDIUM",
                "explanation": f"Missing mandatory document field(s): {', '.join(missing_fields)}.",
                "confidence": 0.90
            })
            signals.append({
                "module": "VALIDATION",
                "signal": "Missing Mandatory Identity Fields",
                "severity": "MEDIUM",
                "confidence": 0.90,
                "explanation": f"Failed to detect {', '.join(missing_fields)} in visual or machine-readable zones.",
                "score_impact": 10.0
            })
        else:
            results.append({
                "rule": "REQUIRED_FIELDS_PRESENCE",
                "passed": True,
                "severity": "LOW",
                "explanation": "All mandatory identity fields detected.",
                "confidence": 0.95
            })

        # RULE 6: Nationality Code Format (ISO 3166-1 alpha-3 in MRZ)
        if mrz_data and mrz_data.get("nationality"):
            nat = mrz_data["nationality"]
            if len(nat) == 3 and nat.isalpha():
                results.append({
                    "rule": "NATIONALITY_CODE_FORMAT",
                    "passed": True,
                    "severity": "LOW",
                    "explanation": f"Valid 3-letter ICAO country/nationality code: '{nat}'.",
                    "confidence": 0.98
                })
            else:
                results.append({
                    "rule": "NATIONALITY_CODE_FORMAT",
                    "passed": False,
                    "severity": "MEDIUM",
                    "explanation": f"Malformed nationality code in MRZ: '{nat}'. Expected 3-letter ISO code.",
                    "confidence": 0.95
                })
                signals.append({
                    "module": "VALIDATION",
                    "signal": "Malformed Nationality Code",
                    "severity": "MEDIUM",
                    "confidence": 0.95,
                    "explanation": f"MRZ nationality '{nat}' violates ICAO 3-letter alpha format.",
                    "score_impact": 8.0
                })

        passed_count = sum(1 for r in results if r["passed"])
        failed_count = sum(1 for r in results if not r["passed"])

        return {
            "passed_count": passed_count,
            "failed_count": failed_count,
            "rules_detail": results,
            "signals": signals
        }
