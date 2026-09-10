import os
import re
import cv2
import numpy as np
import pytesseract
from PIL import Image
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from app.core.config import settings

class BaseOCRService(ABC):
    @abstractmethod
    def extract_text(self, image_path: str) -> Dict[str, Any]:
        """Extracts text, parsed fields, and confidence from document image."""
        pass

class TesseractOCRService(BaseOCRService):
    def __init__(self):
        # Point to configured tesseract binary if available
        if os.path.exists(settings.TESSERACT_PATH):
            pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_PATH

    def preprocess_image(self, image_path: str) -> np.ndarray:
        """
        OpenCV image preprocessing pipeline:
        1. Read image
        2. Resize / normalize resolution (e.g. 1500px width minimum)
        3. Convert to grayscale
        4. CLAHE contrast enhancement
        5. Denoise
        """
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Unable to read image at {image_path}")

        h, w = img.shape[:2]
        target_w = max(w, 1600)
        scale = target_w / w
        target_h = int(h * scale)
        resized = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        # Contrast Limited Adaptive Histogram Equalization
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Subtle Gaussian blur to reduce high-frequency noise
        denoised = cv2.GaussianBlur(enhanced, (3, 3), 0)
        return denoised

    def extract_mrz_lines(self, image_path: str) -> List[str]:
        """
        Dedicated MRZ-band OCR pass, separate from general document-field OCR.

        The general pass is tuned for mixed-case prose text across the whole
        document and struggles with the MRZ's small monospace OCR-B font --
        misreading '<' fillers, confusing O/0, etc. This crops just the bottom
        band where ICAO 9303 places the MRZ, upscales it heavily, binarizes it,
        and constrains Tesseract to the MRZ character set (A-Z0-9<) with a
        single-uniform-block page segmentation mode, which is the standard
        technique for reliable MRZ OCR.
        """
        img = cv2.imread(image_path)
        if img is None:
            return []

        h, w = img.shape[:2]
        # ICAO 9303 places the MRZ in the bottom portion of the bio-data page;
        # crop generously (bottom 25%) so both TD3 lines fit with margin.
        band = img[int(h * 0.75):h, 0:w]
        if band.size == 0:
            return []

        band_gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)

        # Upscale substantially -- small monospace glyphs need real pixel height
        # for Tesseract to resolve them reliably.
        bh, bw = band_gray.shape[:2]
        scale = max(1.0, 2200 / bw)
        upscaled = cv2.resize(
            band_gray, (int(bw * scale), int(bh * scale)), interpolation=cv2.INTER_CUBIC
        )

        # Otsu binarization: MRZ print is high-contrast dark-on-light, so a
        # global threshold is robust and avoids adaptive-threshold noise on
        # otherwise-blank background.
        _, binarized = cv2.threshold(upscaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Generous white padding: without it, Tesseract can silently drop the
        # last character of a line (observed with `--psm 6` when the trailing
        # glyph sits close to the image edge -- font rendering differences
        # between environments shift exactly how close). Padding plus `--psm 4`
        # (assume a single column of text, appropriate for MRZ's left-aligned
        # block) eliminated this in testing; `--psm 6` did not.
        padded = cv2.copyMakeBorder(binarized, 20, 20, 20, 60, cv2.BORDER_CONSTANT, value=255)

        mrz_config = (
            "--psm 4 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
        )
        raw = pytesseract.image_to_string(padded, config=mrz_config)

        candidates = [
            re.sub(r'[^A-Z0-9<]', '', line.upper())
            for line in raw.splitlines()
        ]
        # MRZ lines are long (44 chars for TD3) and filler-heavy; keep only
        # lines that plausibly are MRZ rather than OCR noise.
        return [line for line in candidates if len(line) >= 20 and '<' in line]

    @staticmethod
    def _value_after_label(lines: List[str], keyword_pattern: str) -> Optional[str]:
        """
        Our synthetic documents render every field as a label line immediately
        followed by its value line (see SyntheticDocumentGenerator: label at
        y, value at y+18). Anchoring on the label's distinctive French half
        (e.g. "NOM", "NAISSANCE") and reading the line below it survives
        Tesseract garbling the English half of the label -- which regexing
        over the whole raw-text blob for the value itself cannot, since a
        mangled label often still contains real letters that a value-shaped
        pattern can accidentally match.
        """
        pattern = re.compile(keyword_pattern, re.IGNORECASE)
        for i, line in enumerate(lines):
            if pattern.search(line) and i + 1 < len(lines):
                return lines[i + 1].strip()
        return None

    @staticmethod
    def _extract_date(value_line: Optional[str]) -> Optional[str]:
        """
        Parses a date from a single labeled value line with a separator-
        tolerant pattern (day/month/year each 1-2 digits, 0-2 arbitrary
        non-digit separator characters between them) rather than requiring
        exact DD/MM/YYYY -- Tesseract sometimes drops a separator entirely
        (e.g. "01/01/2000" -> "0101/2000"), which a strict pattern misses.
        """
        if not value_line:
            return None
        m = re.search(r'(\d{1,2})\D{0,2}(\d{1,2})\D{0,2}(\d{4})', value_line)
        if not m:
            return None
        return f"{m.group(1).zfill(2)}/{m.group(2).zfill(2)}/{m.group(3)}"

    def parse_fields_from_text(self, raw_text: str, lines: List[str]) -> Dict[str, Any]:
        """Extracts structured document fields, anchored on each field's own label line."""
        fields: Dict[str, Any] = {
            "full_name": None,
            "document_number": None,
            "nationality": None,
            "country": None,
            "date_of_birth": None,
            "date_of_issue": None,
            "date_of_expiry": None,
            "sex": None
        }

        # Search for document numbers (letters followed by 7-8 digits, e.g. A1234567, X12345678, P1234567)
        doc_no_match = re.search(r'\b([A-Z]{1,2}\d{7,8})\b', raw_text)
        if doc_no_match:
            fields["document_number"] = doc_no_match.group(1)

        fields["date_of_birth"] = self._extract_date(self._value_after_label(lines, r'\bNAISSANCE\b'))
        # No leading \b: the apostrophe in "D'EXPIRATION" is frequently
        # dropped by OCR, fusing it into "DEXPIRATION" with no word boundary
        # before EXPIRATION itself -- only require the trailing boundary.
        fields["date_of_expiry"] = self._extract_date(self._value_after_label(lines, r'EXPIRATION\b'))

        fields["country"] = self._value_after_label(lines, r'\bPAYS\b')
        fields["nationality"] = self._value_after_label(lines, r'\bNATIONALITE\b')

        sex_value = self._value_after_label(lines, r'\bSEXE\b')
        if sex_value and sex_value[:1].upper() in ("M", "F", "X"):
            fields["sex"] = sex_value[:1].upper()

        surname = self._value_after_label(lines, r'\bNOM\b')
        given_names = self._value_after_label(lines, r'\bPRENOM')
        if surname and given_names:
            fields["full_name"] = f"{surname} {given_names}"
        elif surname or given_names:
            fields["full_name"] = surname or given_names
        else:
            # Fallback for documents that don't follow our label-above-value
            # layout: scan upper case lines before the MRZ.
            for line in lines[:8]:
                clean_l = line.strip()
                if len(clean_l) > 4 and clean_l.isupper() and not any(k in clean_l for k in ["PASSPORT", "REPUBLIC", "DEMO", "TRAVEL", "DOCUMENT"]):
                    fields["full_name"] = clean_l
                    break

        return fields

    def extract_text(self, image_path: str) -> Dict[str, Any]:
        try:
            preprocessed = self.preprocess_image(image_path)
            
            # Use PyTesseract with both text and layout analysis
            ocr_data = pytesseract.image_to_data(preprocessed, output_type=pytesseract.Output.DICT)
            raw_text = pytesseract.image_to_string(preprocessed)

            # Compute average confidence over non-empty words
            confs = [float(c) for c in ocr_data.get("conf", []) if str(c).replace("-1", "").strip()]
            avg_conf = (sum(confs) / len(confs) / 100.0) if confs else 0.88
            avg_conf = max(0.40, min(0.99, round(avg_conf, 2)))

            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            fields = self.parse_fields_from_text(raw_text, lines)

            return {
                "raw_text": raw_text.strip(),
                "fields": fields,
                "confidence": avg_conf,
                "detected_lines": lines
            }
        except Exception as e:
            # Fallback if tesseract fails or has binary issue
            return {
                "raw_text": f"Error running Tesseract engine: {str(e)}",
                "fields": {
                    "full_name": None,
                    "document_number": None,
                    "nationality": "UNKNOWN",
                    "country": "UNKNOWN",
                    "date_of_birth": None,
                    "date_of_issue": None,
                    "date_of_expiry": None,
                    "sex": None
                },
                "confidence": 0.50,
                "detected_lines": []
            }

class MockOCRService(BaseOCRService):
    """Fallback OCR service for deterministic demo runs or lightweight tests."""
    def extract_text(self, image_path: str) -> Dict[str, Any]:
        return {
            "raw_text": "PASSPORT REPUBLIC OF UTOPIA\nSURNAME: KAUL\nGIVEN NAMES: ARIHANT\nNATIONALITY: UTOPIAN\nDOB: 01/01/2000\nDOC NO: X1234567\nEXPIRY: 01/01/2030\nP<UTOKAUL<<ARIHANT<<<<<<<<<<<<<<<<<<<<<<\nX1234567<8UTO0001011M3001012<<<<<<<<<<<<<<02",
            "fields": {
                "full_name": "ARIHANT KAUL",
                "document_number": "X1234567",
                "nationality": "UTOPIA",
                "country": "UTOPIA",
                "date_of_birth": "01/01/2000",
                "date_of_issue": "01/01/2020",
                "date_of_expiry": "01/01/2030",
                "sex": "M"
            },
            "confidence": 0.96,
            "detected_lines": [
                "PASSPORT REPUBLIC OF UTOPIA",
                "SURNAME: KAUL",
                "GIVEN NAMES: ARIHANT",
                "DOB: 01/01/2000",
                "DOC NO: X1234567",
                "EXPIRY: 01/01/2030",
                "P<UTOKAUL<<ARIHANT<<<<<<<<<<<<<<<<<<<<<<",
                "X1234567<8UTO0001011M3001012<<<<<<<<<<<<<<02"
            ]
        }

def get_ocr_service() -> BaseOCRService:
    if settings.OCR_ENGINE == "mock":
        return MockOCRService()
    return TesseractOCRService()
