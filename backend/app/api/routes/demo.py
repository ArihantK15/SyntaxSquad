import os
import re
import uuid
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.api.deps import get_db
from app.core.config import settings
from app.models import Case, DocumentAnalysis, RiskSignal, AuditLog
from app.utils.synthetic_generator import SyntheticDocumentGenerator
from app.services.ocr_service import get_ocr_service
from app.services.mrz_service import MRZService
from app.services.rules_engine import DocumentRulesEngine
from app.services.tamper_service import get_tamper_service
from app.services.face_service import get_face_service
from app.services.watchlist_service import get_watchlist_provider
from app.services.risk_engine import get_risk_engine
from app.services.audit_service import AuditService
from app.core.security import hash_identifier

router = APIRouter(prefix="/demo", tags=["demo"])

# Real (AI-generated, non-real-person) face photos used for scenarios where a
# genuine biometric face-verification result matters. Hand-drawn cartoon
# avatars don't carry enough facial structure for a properly trained deep face
# model to discriminate on -- it correctly treats two flat vector portraits as
# "the same face" regardless of color/proportion differences, so a real photo
# is needed to demonstrate an actual match or mismatch.
_DEMO_FACES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "demo-data", "faces"))
PERSON_A = os.path.join(_DEMO_FACES_DIR, "person_a.jpg")
PERSON_B = os.path.join(_DEMO_FACES_DIR, "person_b.jpg")

SCENARIO_CONFIGS = {
    "genuine": {
        "title": "Genuine Document",
        "mode": "genuine",
        "surname": "KAUL",
        "given_names": "ARIHANT",
        "country_code": "UTO",
        "country_name": "REPUBLIC OF UTOPIA",
        "doc_number": "X1234567",
        "nationality": "UTOPIAN",
        "dob": "000101",
        "expiry": "300101",
        "doc_face_photo": PERSON_A, "live_face_photo": PERSON_A  # same person -> MATCH
    },
    "mrz_tampering": {
        "title": "MRZ Tampering",
        "mode": "mrz_tampered",
        "surname": "SHARMA",
        "given_names": "PRIYA",
        "country_code": "UTO",
        "country_name": "REPUBLIC OF UTOPIA",
        "doc_number": "P8892144",
        "nationality": "UTOPIAN",
        "dob": "950512",
        "expiry": "281115",
        "doc_face_photo": PERSON_A, "live_face_photo": PERSON_A  # same person -> MATCH
    },
    "photo_replacement": {
        "title": "Photo Replacement",
        "mode": "photo_replaced",
        "surname": "DOE",
        "given_names": "JOHN",
        "country_code": "DEM",
        "country_name": "DEMO STATE",
        "doc_number": "D5512398",
        "nationality": "DEMO CITIZEN",
        "dob": "880320",
        "expiry": "290814",
        # Document photo is Person A; the live subject is Person B -- simulates
        # someone presenting a passport with someone else's photo on it.
        "doc_face_photo": PERSON_A, "live_face_photo": PERSON_B
    },
    "expired": {
        "title": "Expired Document",
        "mode": "expired",
        "surname": "PATEL",
        "given_names": "ROHAN",
        "country_code": "UTO",
        "country_name": "REPUBLIC OF UTOPIA",
        "doc_number": "A9938210",
        "nationality": "UTOPIAN",
        "dob": "921010",
        "expiry": "220101", # Expired in 2022
        "doc_face_photo": PERSON_A, "live_face_photo": PERSON_A  # same person -> MATCH
    },
    "multiple_anomalies": {
        "title": "Multiple Anomalies",
        "mode": "multiple_anomalies",
        "surname": "KOROL",
        "given_names": "VIKTOR",
        "country_code": "ATL",
        "country_name": "ATLANTIS FEDERATION",
        "doc_number": "P8892144", # Matches demo watchlist entry
        "nationality": "ATLANTIAN",
        "dob": "850704",
        "expiry": "270420",
        "doc_face_photo": PERSON_A, "live_face_photo": PERSON_B  # mismatch, like photo_replacement
    }
}

@router.post("/scenario")
def run_demo_scenario(scenario_key: str = Body(..., embed=True), db: Session = Depends(get_db)):
    """
    Executes an end-to-end demonstration scenario with 1-click execution.
    Generates appropriate synthetic document, runs all AI modules, computes risk,
    and returns completed case file.
    """
    key = scenario_key.lower().replace(" ", "_")
    if key not in SCENARIO_CONFIGS:
        raise HTTPException(status_code=400, detail=f"Unknown scenario '{scenario_key}'. Valid: {list(SCENARIO_CONFIGS.keys())}")

    cfg = SCENARIO_CONFIGS[key]
    case_uid = str(uuid.uuid4())
    random_num = uuid.uuid4().hex[:5].upper()
    case_num = f"BM-2026-{random_num}"

    # Generate document file
    doc_filename = f"specimen_{case_num}.jpg"
    doc_path = os.path.join(settings.UPLOAD_DIR, "documents", doc_filename)
    SyntheticDocumentGenerator.generate_document(
        out_path=doc_path,
        mode=cfg["mode"],
        surname=cfg["surname"],
        given_names=cfg["given_names"],
        country_code=cfg["country_code"],
        country_name=cfg["country_name"],
        doc_number=cfg["doc_number"],
        nationality=cfg["nationality"],
        dob_yymmdd=cfg["dob"],
        expiry_yymmdd=cfg["expiry"],
        face_photo_path=cfg["doc_face_photo"]
    )

    # Generate live face file
    live_filename = f"live_{case_num}.jpg"
    live_path = os.path.join(settings.UPLOAD_DIR, "faces", live_filename)
    SyntheticDocumentGenerator.generate_live_face_image(live_path, face_photo_path=cfg["live_face_photo"])

    # Create Case
    new_case = Case(
        id=case_uid,
        case_number=case_num,
        document_type="Passport",
        country=cfg["country_name"],
        document_number_hash=hash_identifier(cfg["doc_number"]),
        status="PROCESSING",
        risk_level="LOW",
        risk_score=0.0
    )
    db.add(new_case)
    db.commit()

    AuditService.log(db, "DOCUMENT_UPLOADED", case_uid, metadata={"scenario": cfg["title"], "specimen": doc_filename})

    # Step 2: OCR
    ocr_svc = get_ocr_service()
    ocr_result = ocr_svc.extract_text(doc_path)
    AuditService.log(db, "OCR_COMPLETED", case_uid, actor="AI-OCR-ENGINE", metadata={"conf": ocr_result.get("confidence")})

    # Step 3: MRZ & Validation -- prefer the dedicated MRZ-band OCR pass (see
    # TesseractOCRService.extract_mrz_lines / MRZService.parse_pre_isolated_lines)
    # over the general whole-document pass, same as the manual screening flow
    # in screening.py; the general pass misreads the small MRZ font far more.
    mrz_lines = ocr_svc.extract_mrz_lines(doc_path) if hasattr(ocr_svc, "extract_mrz_lines") else []
    mrz_data = (
        MRZService.parse_pre_isolated_lines(mrz_lines) if len(mrz_lines) >= 2 else None
    ) or MRZService.extract_mrz_from_lines(ocr_result.get("detected_lines", []))
    validation_data = DocumentRulesEngine.evaluate(ocr_result, mrz_data)
    AuditService.log(db, "MRZ_VALIDATED", case_uid, actor="AI-VALIDATION-ENGINE")

    # Step 4: Tamper Forensics
    tamper_svc = get_tamper_service()
    tamper_result = tamper_svc.analyze(doc_path, case_uid)
    AuditService.log(db, "TAMPER_ANALYSIS_COMPLETED", case_uid, actor="AI-TAMPER-FORENSICS")

    # Step 5: Face Verification
    face_svc = get_face_service()
    face_result = face_svc.verify(doc_path, live_path, case_uid)
    AuditService.log(db, "FACE_VERIFIED", case_uid, actor="AI-FACE-VERIFIER")

    # Step 6: Watchlist & Risk Engine
    full_name = f"{cfg['surname']} {cfg['given_names']}"
    watchlist_provider = get_watchlist_provider()
    watchlist_match = watchlist_provider.check_watchlist(full_name, cfg["doc_number"])

    risk_engine = get_risk_engine()
    risk_res = risk_engine.calculate(
        mrz_data=mrz_data,
        validation_data=validation_data,
        tamper_data=tamper_result,
        face_data=face_result,
        watchlist_match=watchlist_match
    )

    # Finalize Case
    new_case.risk_score = risk_res["risk_score"]
    new_case.risk_level = risk_res["risk_level"]
    new_case.recommendation = risk_res["recommendation"]
    new_case.status = f"{risk_res['risk_level']}_RISK" if risk_res["risk_level"] in ["LOW", "MEDIUM"] else ("CRITICAL" if risk_res["risk_level"] == "CRITICAL" else "REQUIRES_REVIEW")

    # Save DocumentAnalysis
    analysis = DocumentAnalysis(
        case_id=case_uid,
        document_type="Passport",
        document_image_path=doc_path,
        face_image_path=live_path,
        ocr_result=ocr_result,
        mrz_result=mrz_data,
        validation_result=validation_data,
        tamper_result=tamper_result,
        face_result=face_result,
        risk_breakdown=risk_res["breakdown"],
        processing_time_ms=2100.0
    )
    db.add(analysis)

    # Save Signals
    for sig in risk_res["signals"]:
        risk_sig = RiskSignal(
            case_id=case_uid,
            module=sig["module"],
            signal=sig["signal"],
            severity=sig.get("severity", "LOW"),
            confidence=sig.get("confidence", 0.9),
            explanation=sig["explanation"],
            score_impact=sig.get("score_impact", 0.0)
        )
        db.add(risk_sig)

    db.commit()
    AuditService.log(db, "RISK_CALCULATED", case_uid, actor="AI-RISK-ENGINE", metadata={"score": new_case.risk_score})

    return {
        "case_id": case_uid,
        "case_number": case_num,
        "scenario": cfg["title"],
        "risk_score": new_case.risk_score,
        "risk_level": new_case.risk_level,
        "recommendation": new_case.recommendation,
        "document_image_url": f"/uploads/documents/{doc_filename}",
        "live_face_url": f"/uploads/faces/{live_filename}"
    }


# Matches the jurisdiction dropdown in frontend/src/pages/ScreeningPage.tsx.
# Falls back to deriving a plausible 3-letter code for any other free-text
# country name, since the generator itself accepts arbitrary strings.
KNOWN_COUNTRY_CODES = {
    "REPUBLIC OF UTOPIA": "UTO",
    "DEMO STATE": "DEM",
    "ATLANTIS FEDERATION": "ATL",
    "INDIA": "IND",
    "UNITED KINGDOM": "GBR",
}


def _country_code_for(country_name: str) -> str:
    known = KNOWN_COUNTRY_CODES.get(country_name.strip().upper())
    if known:
        return known
    letters = re.sub(r'[^A-Z]', '', country_name.upper())
    return (letters + "XXX")[:3] if letters else "UTO"


@router.post("/generate-doc")
def generate_specimen_doc(
    mode: str = Body("genuine", embed=True),
    surname: str = Body("KAUL", embed=True),
    given_names: str = Body("ARIHANT", embed=True),
    doc_number: str = Body("X1234567", embed=True),
    country_name: str = Body("REPUBLIC OF UTOPIA", embed=True)
):
    """Utility to generate a download-ready synthetic document."""
    fname = f"specimen_{uuid.uuid4().hex[:6]}.jpg"
    out_path = os.path.join(settings.UPLOAD_DIR, "documents", fname)
    # country_code/nationality previously defaulted to "UTO"/"UTOPIAN"
    # unconditionally (they were never derived from country_name), so any
    # jurisdiction other than the default rendered an internally
    # inconsistent document -- header said e.g. "ATLANTIS FEDERATION" while
    # the printed NATIONALITY field and MRZ country code both said UTO.
    country_code = _country_code_for(country_name)
    info = SyntheticDocumentGenerator.generate_document(
        out_path=out_path,
        mode=mode,
        surname=surname,
        given_names=given_names,
        doc_number=doc_number,
        country_name=country_name,
        country_code=country_code,
        nationality=f"{country_code} CITIZEN"
    )
    return {
        "filename": fname,
        "url": f"/uploads/documents/{fname}",
        "mode": mode,
        "doc_number": doc_number
    }
