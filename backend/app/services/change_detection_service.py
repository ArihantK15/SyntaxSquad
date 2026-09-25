from typing import Dict, Any, List, Optional

from app.services.rules_engine import DocumentRulesEngine


class ChangeDetectionService:
    """
    Field-level diff between two MRZ-parsed submissions of what is claimed to
    be the SAME identity ("version 1" vs "version 2" of one specimen,
    e.g. a re-scan or resubmission). Distinct from DocumentRulesEngine's own
    MRZ checksum validation: a checksum only proves a document's OWN printed
    fields are internally self-consistent, not that they match what was
    printed the first time this identity was seen. A forger who edits a
    field and regenerates the check digit for the new value passes checksum
    validation on BOTH submissions independently -- this comparison is what
    actually catches that a specific field moved between them.

    Compares MRZ-sourced fields only (not the noisier free-text OCR pass):
    MRZService's parsed output is already normalized per-field, which a
    label-anchored OCR field scan is not guaranteed to be.
    """

    # (mrz_key, display label, severity if this field changed between
    # submissions). document_number/surname/given_names at CRITICAL: a
    # change there means the two submissions aren't even claiming to be the
    # same identity/document. birth_date/expiry_date at HIGH: the two
    # concrete examples this scenario demonstrates. sex/nationality/country
    # at MEDIUM: plausible clerical correction, still worth a look.
    _FIELD_DEFS: List[tuple] = [
        ("document_number", "Document Number", "CRITICAL"),
        ("surname", "Surname", "CRITICAL"),
        ("given_names", "Given Names", "CRITICAL"),
        ("birth_date", "Date of Birth", "HIGH"),
        ("expiry_date", "Date of Expiry", "HIGH"),
        ("sex", "Sex", "MEDIUM"),
        ("nationality", "Nationality", "MEDIUM"),
        ("country", "Issuing Country", "MEDIUM"),
    ]

    _DATE_FIELDS = {"birth_date", "expiry_date"}

    @classmethod
    def _display_value(cls, field: str, raw: Optional[str]) -> Optional[str]:
        if raw is None:
            return None
        if field in cls._DATE_FIELDS:
            parsed = DocumentRulesEngine.parse_yymmdd(raw)
            return parsed.strftime("%d/%m/%Y") if parsed else raw
        return raw

    @classmethod
    def compare_mrz_identity(
        cls, mrz_v1: Optional[Dict[str, Any]], mrz_v2: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Returns one diff entry per tracked field, each carrying both the
        raw MRZ value (for exact-match logic) and a human-readable display
        value (for the UI), regardless of whether it changed -- an unchanged
        field is just as important to show as a changed one, to demonstrate
        the comparison isn't just flagging everything.
        """
        mrz_v1 = mrz_v1 or {}
        mrz_v2 = mrz_v2 or {}
        diffs = []
        for field, label, severity in cls._FIELD_DEFS:
            raw_v1 = mrz_v1.get(field)
            raw_v2 = mrz_v2.get(field)
            changed = (raw_v1 or None) != (raw_v2 or None)
            diffs.append({
                "field": field,
                "label": label,
                "v1_value": cls._display_value(field, raw_v1),
                "v2_value": cls._display_value(field, raw_v2),
                "changed": changed,
                "severity": severity if changed else "LOW",
            })
        return diffs
