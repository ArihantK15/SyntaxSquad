import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from typing import Dict, Any, Tuple, Optional
from datetime import datetime, date

from app.services.mrz_service import MRZService

class SyntheticDocumentGenerator:
    """
    Generates high-fidelity synthetic travel documents for demonstration and testing.
    All data is strictly fictional: 'DEMO TRAVEL DOCUMENT / REPUBLIC OF UTOPIA'.
    Supports genuine document generation and controlled synthetic tampering:
    - altered text
    - replaced portrait photo
    - MRZ checksum tampering
    - expired validity
    - multi-signal forensic anomalies
    """

    WIDTH = 1000
    HEIGHT = 650

    @classmethod
    def _paste_photo(cls, img: Image.Image, photo_path: str, x: int, y: int, w: int, h: int):
        """
        Pastes a real face photo into the given box, center-cropped to fill it.

        Used instead of _draw_avatar when a genuine face-verification mismatch
        needs to be demonstrable: a real trained face-embedding model weighs
        facial structure far more than the hand-drawn vector avatar's color
        scheme, so two flat cartoon avatars are correctly recognized as "the
        same face" regardless of how their proportions are varied. A real (here,
        AI-generated, non-real-person) photo gives the model genuine structure
        to discriminate on.
        """
        photo = Image.open(photo_path).convert("RGB")
        pw, ph = photo.size
        target_ratio = w / h
        src_ratio = pw / ph
        if src_ratio > target_ratio:
            new_w = int(ph * target_ratio)
            left = (pw - new_w) // 2
            photo = photo.crop((left, 0, left + new_w, ph))
        else:
            new_h = int(pw / target_ratio)
            top = (ph - new_h) // 2
            photo = photo.crop((0, top, pw, top + new_h))
        photo = photo.resize((w, h), Image.LANCZOS)
        img.paste(photo, (x, y))

    @classmethod
    def _draw_avatar(cls, draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, variant: int = 1):
        """
        Draws a clean biometric avatar portrait with face contours.

        variant controls both coloring AND facial geometry (face proportions,
        eye spacing/position, hair coverage) -- a real face-embedding model
        weighs structure far more than color, so two avatars that only differ
        in palette are correctly recognized as "the same face" by a properly
        trained model (this was validated against the LFW benchmark). To
        simulate a genuine face mismatch (e.g. photo-replacement fraud), the
        variants must look like structurally different people, not just a
        different color scheme.
        """
        # Background
        bg_color = (210, 225, 240) if variant == 1 else (240, 220, 210)
        draw.rectangle([x, y, x + w, y + h], fill=bg_color, outline=(150, 160, 180), width=2)

        cx, cy = x + w // 2, y + h // 2

        # Shoulders
        shoulder_color = (40, 60, 90) if variant == 1 else (90, 40, 50)
        draw.ellipse([cx - int(w * 0.45), y + int(h * 0.65), cx + int(w * 0.45), y + int(h * 1.35)], fill=shoulder_color)

        # Neck
        neck_color = (235, 195, 165) if variant == 1 else (200, 155, 120)
        draw.rectangle([cx - int(w * 0.12), cy + int(h * 0.10), cx + int(w * 0.12), cy + int(h * 0.35)], fill=neck_color)

        # Head / Face -- variant 2 is narrower/longer, a structurally different shape
        face_w = int(w * (0.32 if variant == 1 else 0.27))
        face_h = int(h * (0.40 if variant == 1 else 0.46))
        draw.ellipse([cx - face_w, cy - int(face_h * 0.8), cx + face_w, cy + int(face_h * 0.6)], fill=neck_color, outline=(180, 140, 120), width=2)

        # Hair -- variant 2 covers more of the head and sits lower (different hairline)
        hair_color = (30, 25, 20) if variant == 1 else (90, 60, 30)
        hair_bottom = -0.1 if variant == 1 else 0.15
        draw.chord([cx - face_w - 2, cy - int(face_h * 0.95), cx + face_w + 2, cy - int(face_h * hair_bottom)], 180, 360, fill=hair_color)

        # Eyes -- variant 2 has wider-set eyes at a different vertical position
        eye_y = cy - int(face_h * (0.15 if variant == 1 else 0.05))
        eye_inner = 0.25 if variant == 1 else 0.40
        eye_outer = 0.55 if variant == 1 else 0.75
        draw.ellipse([cx - int(face_w * eye_outer), eye_y - 4, cx - int(face_w * eye_inner), eye_y + 6], fill=(30, 30, 30))
        draw.ellipse([cx + int(face_w * eye_inner), eye_y - 4, cx + int(face_w * eye_outer), eye_y + 6], fill=(30, 30, 30))

        # Nose & Mouth
        draw.line([cx, eye_y + 6, cx, eye_y + 22], fill=(180, 130, 100), width=2)
        draw.arc([cx - 15, eye_y + 24, cx + 15, eye_y + 36], 0, 180, fill=(160, 70, 70), width=3)

    @classmethod
    def generate_live_face_image(cls, out_path: str, variant: int = 1, face_photo_path: Optional[str] = None):
        """Generates a matching or mismatched live webcam frame with avatar."""
        img = Image.new("RGB", (400, 400), color=(25, 30, 42))
        if face_photo_path:
            cls._paste_photo(img, face_photo_path, 50, 50, 300, 300)
        else:
            draw = ImageDraw.Draw(img)
            cls._draw_avatar(draw, 50, 50, 300, 300, variant=variant)

        # Subtle vignette / lighting gradient
        img = img.filter(ImageFilter.SMOOTH_MORE)
        img.save(out_path, "JPEG", quality=92)
        return out_path

    @classmethod
    def generate_document(
        cls,
        out_path: str,
        mode: str = "genuine",
        surname: str = "KAUL",
        given_names: str = "ARIHANT",
        country_code: str = "UTO",
        country_name: str = "REPUBLIC OF UTOPIA",
        doc_number: str = "X1234567",
        nationality: str = "UTOPIAN",
        dob_yymmdd: str = "000101", # 01 Jan 2000
        expiry_yymmdd: str = "300101", # 01 Jan 2030
        sex: str = "M",
        face_photo_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a synthetic document image with specified properties.
        Modes: 'genuine', 'altered_text', 'mrz_tampered', 'photo_replaced', 'expired', 'multiple_anomalies'.
        """
        w, h = cls.WIDTH, cls.HEIGHT
        img = Image.new("RGB", (w, h), color=(248, 250, 252))
        draw = ImageDraw.Draw(img)

        # 1. Subtle security guilloche pattern / microprint background
        for y in range(0, h - 140, 12):
            color = (230, 238, 248) if (y // 12) % 2 == 0 else (238, 244, 252)
            draw.line([(0, y), (w, y)], fill=color, width=1)
        for x in range(0, w, 24):
            draw.line([(x, 0), (x, h - 140)], fill=(240, 246, 254), width=1)

        # 2. Header banner (Navy Security Operations style)
        draw.rectangle([0, 0, w, 70], fill=(15, 23, 42))
        draw.rectangle([0, 70, w, 74], fill=(59, 130, 246)) # Cyan/blue accent line

        # Title text
        draw.text((25, 16), "DEMO TRAVEL DOCUMENT", fill=(255, 255, 255))
        draw.text((25, 42), f"{country_name} • FICTIONAL TEST SPECIMEN", fill=(148, 163, 184))
        draw.text((w - 220, 25), "TYPE: P  CODE: " + country_code, fill=(203, 213, 225))

        # 3. Avatar Portrait (Left side: 40, 100 to 280, 420)
        avatar_variant = 2 if mode in ["photo_replaced", "multiple_anomalies"] else 1
        if face_photo_path:
            cls._paste_photo(img, face_photo_path, 40, 100, 240, 320)
            draw.rectangle([40, 100, 40 + 240, 100 + 320], outline=(150, 160, 180), width=2)
        else:
            cls._draw_avatar(draw, 40, 100, 240, 320, variant=avatar_variant)

        # 4. Identity Fields
        left_text = 320
        fields = [
            ("SURNAME / NOM", surname),
            ("GIVEN NAMES / PRENOMS", given_names),
            ("NATIONALITY / NATIONALITE", nationality),
            ("DOCUMENT NO / NO DU PASSEPORT", doc_number),
            ("DATE OF BIRTH / DATE DE NAISSANCE", f"{dob_yymmdd[4:6]}/{dob_yymmdd[2:4]}/20{dob_yymmdd[:2]}"),
            ("SEX / SEXE", sex),
            ("DATE OF EXPIRY / DATE D'EXPIRATION", f"{expiry_yymmdd[4:6]}/{expiry_yymmdd[2:4]}/20{expiry_yymmdd[:2]}")
        ]

        if mode == "expired":
            # Change expiry to 2022
            expiry_yymmdd = "220101"
            fields[6] = ("DATE OF EXPIRY / DATE D'EXPIRATION", "01/01/2022")

        if mode == "altered_text":
            # Tamper visual expiry date to 2035 while MRZ stays 2030
            fields[6] = ("DATE OF EXPIRY / DATE D'EXPIRATION", "01/01/2035")

        cur_y = 95
        for label, val in fields:
            draw.text((left_text, cur_y), label, fill=(100, 116, 139))
            draw.text((left_text, cur_y + 18), str(val), fill=(15, 23, 42))
            cur_y += 48

        # 5. Security emblem stamp watermark
        draw.ellipse([w - 180, 250, w - 40, 390], outline=(219, 234, 254), width=4)
        draw.text((w - 165, 310), "SIMULATED\nSECURITY", fill=(191, 219, 254))

        if mode in ["stamp_manipulated", "multiple_anomalies"]:
            # Simulated unauthorized pasted secondary stamp
            draw.rectangle([w - 240, 180, w - 60, 240], fill=(254, 242, 242), outline=(220, 38, 38), width=2)
            draw.text((w - 230, 195), "VISA EXEMPTION\n[SIMULATED PATCH]", fill=(185, 28, 28))

        # 6. MRZ Zone (Bottom 150px)
        draw.rectangle([0, h - 145, w, h], fill=(255, 255, 255), outline=(226, 232, 240), width=1)
        
        # Build TD3 lines
        # Line 1: P<[Country 3][Surname]<<[Given Names]...
        clean_surn = surname.replace(" ", "<").upper()
        clean_giv = given_names.replace(" ", "<").upper()
        l1_name = f"{clean_surn}<<{clean_giv}"
        line1 = f"P<{country_code}{l1_name}".ljust(44, '<')[:44]

        # Line 2:
        # [Doc# 9][Doc# CD 1][Nat 3][DOB 6][DOB CD 1][Sex 1][Expiry 6][Expiry CD 1][Optional 14][Comp CD 1]
        doc_raw = doc_number.ljust(9, '<')[:9]
        doc_cd = MRZService.compute_check_digit(doc_raw)
        
        dob_raw = dob_yymmdd.ljust(6, '0')[:6]
        dob_cd = MRZService.compute_check_digit(dob_raw)
        
        exp_raw = expiry_yymmdd.ljust(6, '0')[:6]
        exp_cd = MRZService.compute_check_digit(exp_raw)
        
        optional_raw = "".ljust(15, '<')
        
        comp_payload = doc_raw + doc_cd + dob_raw + dob_cd + exp_raw + exp_cd + optional_raw
        comp_cd = MRZService.compute_check_digit(comp_payload)

        # Inject tampering if requested
        if mode in ["mrz_tampered", "multiple_anomalies"]:
            # Intentionally corrupt check digits
            exp_cd = "9" if exp_cd != "9" else "8"
            comp_cd = "4" if comp_cd != "4" else "3"

        line2 = f"{doc_raw}{doc_cd}{country_code}{dob_raw}{dob_cd}{sex}{exp_raw}{exp_cd}{optional_raw}{comp_cd}"

        # Draw OCR-B / Monospace font in MRZ zone
        font_mrz = None
        for font_candidate in ["/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]:
            if os.path.exists(font_candidate):
                try:
                    font_mrz = ImageFont.truetype(font_candidate, 22)
                    break
                except Exception:
                    pass
        if font_mrz is None:
            font_mrz = ImageFont.load_default(size=22)

        draw.text((45, h - 120), line1, fill=(15, 23, 42), font=font_mrz)
        draw.text((45, h - 65), line2, fill=(15, 23, 42), font=font_mrz)

        # Save base image
        img.save(out_path, "JPEG", quality=95)

        # 7. Apply forensic tampering if mode requires photo replacement or compression anomaly
        if mode in ["photo_replaced", "multiple_anomalies"]:
            cv_img = cv2.imread(out_path)
            # Add subtle splicing seam around photo box
            cv2.rectangle(cv_img, (38, 98), (282, 422), (180, 160, 140), 1)
            # Add localized compression noise
            patch = cv_img[100:420, 40:280]
            noisy_patch = cv2.convertScaleAbs(patch, alpha=1.05, beta=10)
            cv_img[100:420, 40:280] = noisy_patch
            cv2.imwrite(out_path, cv_img, [cv2.IMWRITE_JPEG_QUALITY, 75])

        if mode == "altered_text":
            cv_img = cv2.imread(out_path)
            # Add recompression boundary around date field
            cv2.rectangle(cv_img, (left_text - 5, cur_y - 50), (left_text + 200, cur_y - 20), (220, 220, 220), 1)
            cv2.imwrite(out_path, cv_img, [cv2.IMWRITE_JPEG_QUALITY, 80])

        if mode == "brightness_manipulated":
            cv_img = cv2.imread(out_path)
            # Apply non-uniform brightness manipulation hotspot over text zone
            cv_img[100:320, 320:800] = cv2.convertScaleAbs(cv_img[100:320, 320:800], alpha=1.35, beta=35)
            cv2.imwrite(out_path, cv_img, [cv2.IMWRITE_JPEG_QUALITY, 85])

        return {
            "image_path": out_path,
            "mode": mode,
            "line1": line1,
            "line2": line2,
            "doc_number": doc_number,
            "surname": surname,
            "given_names": given_names,
            "country": country_name
        }
