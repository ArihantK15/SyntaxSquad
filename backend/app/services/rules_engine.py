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

    # Document types with no ICAO 9303 Machine Readable Zone by design --
    # kept in sync with (but intentionally not imported from)
    # TesseractOCRService.NON_MRZ_DOCUMENT_TYPES in ocr_service.py, matching
    # this codebase's existing style of duplicating the "AADHAAR" check
    # independently at each of its call sites rather than sharing one
    # constant across the OCR and rules-engine modules.
    NON_MRZ_DOCUMENT_TYPES = ("AADHAAR", "PAN", "DRIVING_LICENSE")

    # CBDT's published PAN entity-type codes (the 4th of the 5 leading
    # letters). Only the well-established, commonly-cited codes are listed
    # here -- an unrecognized letter is flagged as suspicious (MEDIUM, not a
    # hard failure) rather than assumed exhaustive, since a rarer real code
    # this table is missing would otherwise be misclassified as fabricated.
    PAN_ENTITY_TYPES = {
        "P": "Individual",
        "C": "Company",
        "H": "Hindu Undivided Family (HUF)",
        "F": "Firm",
        "A": "Association of Persons (AOP)",
        "T": "Trust",
        "B": "Body of Individuals (BOI)",
        "L": "Local Authority",
        "J": "Artificial Juridical Person",
        "G": "Government",
    }

    @classmethod
    def parse_ddmmyyyy(cls, value: Optional[str]) -> Optional[date]:
        """
        Parses the DD/MM/YYYY date string TesseractOCRService._extract_date
        produces for document types with no MRZ (e.g. a Driving Licence's
        printed "Valid Till" field) -- distinct from parse_yymmdd, which
        parses the MRZ's own 6-digit YYMMDD format.
        """
        if not value:
            return None
        m = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', value)
        if not m:
            return None
        dd, mm, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1 <= mm <= 12 and 1 <= dd <= 31):
            return None
        try:
            return date(yyyy, mm, dd)
        except ValueError:
            return None

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
        elif fields.get("document_type") in cls.NON_MRZ_DOCUMENT_TYPES:
            # Aadhaar/PAN/Driving Licence are national IDs, not ICAO 9303
            # travel documents -- none of them carry an MRZ by design, so a
            # missing MRZ here is expected, not a red flag. Penalizing them
            # the same as a passport missing its MRZ would misclassify every
            # genuine card of these types as suspicious.
            results.append({
                "rule": "MRZ_PRESENCE",
                "passed": True,
                "severity": "LOW",
                "explanation": "Not applicable — this document type does not carry an ICAO Machine Readable Zone by design.",
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

        # RULE 1b: PAN Structural Format Validation
        #
        # Unlike an MRZ check digit, PAN's own final check character is
        # generated by an algorithm CBDT/NSDL/UTIITSL has never published --
        # there is no authoritative way to recompute it independently, and
        # claiming to validate it would be presenting an unverified guess as
        # a real checksum. What IS publicly documented and genuinely
        # checkable: the fixed 10-character structure itself, and the 4th
        # letter's entity-type encoding.
        if fields.get("document_type") == "PAN":
            pan_number = fields.get("document_number") or ""
            if not re.fullmatch(r'[A-Z]{5}[0-9]{4}[A-Z]', pan_number):
                results.append({
                    "rule": "PAN_FORMAT_VALIDATION",
                    "passed": False,
                    "severity": "HIGH",
                    "explanation": f"'{pan_number}' does not match the required PAN structure (5 letters, 4 digits, 1 letter).",
                    "confidence": 0.97
                })
                signals.append({
                    "module": "VALIDATION",
                    "signal": "Malformed PAN Structure",
                    "severity": "HIGH",
                    "confidence": 0.97,
                    "explanation": "Permanent Account Number does not conform to the CBDT-published 10-character format.",
                    "score_impact": 20.0
                })
            else:
                entity_letter = pan_number[3]
                entity_type = cls.PAN_ENTITY_TYPES.get(entity_letter)
                if entity_type:
                    results.append({
                        "rule": "PAN_FORMAT_VALIDATION",
                        "passed": True,
                        "severity": "LOW",
                        "explanation": f"Well-formed PAN; 4th character '{entity_letter}' indicates entity type {entity_type}.",
                        "confidence": 0.97
                    })
                else:
                    results.append({
                        "rule": "PAN_FORMAT_VALIDATION",
                        "passed": False,
                        "severity": "MEDIUM",
                        "explanation": f"PAN structure is well-formed, but 4th character '{entity_letter}' is not a recognized entity-type code.",
                        "confidence": 0.70
                    })
                    signals.append({
                        "module": "VALIDATION",
                        "signal": "Unrecognized PAN Entity-Type Code",
                        "severity": "MEDIUM",
                        "confidence": 0.70,
                        "explanation": f"4th PAN character '{entity_letter}' does not match any documented CBDT entity-type code.",
                        "score_impact": 8.0
                    })

        # RULE 2: Expiration Check
        expiry_date = None
        if mrz_data and mrz_data.get("expiry_date"):
            expiry_date = cls.parse_yymmdd(mrz_data["expiry_date"])
        elif fields.get("date_of_expiry"):
            # Non-MRZ documents with a genuine printed expiry (e.g. a
            # Driving Licence's "Valid Till") -- Aadhaar/PAN have no expiry
            # field by design and leave this None, so they correctly fall
            # through to the "pending visual confirmation" branch below
            # rather than being penalized for having no expiry to check.
            expiry_date = cls.parse_ddmmyyyy(fields["date_of_expiry"])

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
            # character, or one pass can genuinely truncate a few leading/
            # trailing characters (a real partial read, not a failed one).
            # Tolerate a single-edit difference (bounded, length-gated via
            # fuzzy_equal) or outright substring containment -- but only
            # when the SHORTER side is long enough to mean something: a
            # near-degenerate OCR reading (e.g. one surviving character out
            # of a badly garbled read) is trivially "contained" in almost
            # any longer number regardless of how different they really
            # are, which would silently defeat this exact cross-check.
            MIN_SUBSTRING_MATCH_LENGTH = 5
            shorter_len = min(len(clean_ocr_no), len(clean_mrz_no))
            is_consistent = (
                clean_ocr_no == clean_mrz_no
                or (
                    shorter_len >= MIN_SUBSTRING_MATCH_LENGTH
                    and (clean_ocr_no in clean_mrz_no or clean_mrz_no in clean_ocr_no)
                )
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

        # RULE 7: Sex/Gender Code Validation (ICAO 9303 — must be M, F, or X)
        if mrz_data and mrz_data.get("sex"):
            sex = mrz_data["sex"].upper()
            if sex in ("M", "F", "X"):
                results.append({
                    "rule": "SEX_CODE_FORMAT",
                    "passed": True,
                    "severity": "LOW",
                    "explanation": f"Valid ICAO sex/gender code: '{sex}'.",
                    "confidence": 0.98
                })
            else:
                results.append({
                    "rule": "SEX_CODE_FORMAT",
                    "passed": False,
                    "severity": "MEDIUM",
                    "explanation": f"Malformed sex/gender code in MRZ: '{sex}'. Expected M, F, or X.",
                    "confidence": 0.90
                })
                signals.append({
                    "module": "VALIDATION",
                    "signal": "Malformed Sex/Gender Code",
                    "severity": "MEDIUM",
                    "confidence": 0.90,
                    "explanation": f"MRZ sex/gender code '{sex}' violates ICAO 9303 format (expected M/F/X).",
                    "score_impact": 6.0
                })

        passed_count = sum(1 for r in results if r["passed"])
        failed_count = sum(1 for r in results if not r["passed"])

        return {
            "passed_count": passed_count,
            "failed_count": failed_count,
            "rules_detail": results,
            "signals": signals
        }
