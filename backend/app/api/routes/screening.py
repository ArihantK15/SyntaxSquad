import os
import time
import random
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_db
from app.core.config import settings
from app.core.security import validate_image_upload, sanitize_filename, hash_identifier
from app.models import Case, DocumentAnalysis, RiskSignal, AuditLog
from app.services.ocr_service import get_ocr_service
from app.services.mrz_service import MRZService
from app.services.rules_engine import DocumentRulesEngine
from app.services.tamper_service import get_tamper_service
from app.services.face_service import get_face_service
from app.services.watchlist_service import get_watchlist_provider
from app.services.risk_engine import get_risk_engine
from app.services.audit_service import AuditService

router = APIRouter(prefix="/screening", tags=["screening"])

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    document_type: str = Form("Passport"),
    country: str = Form("Unknown"),
    db: Session = Depends(get_db)
):
    """
    Step 1 of Screening Pipeline:
    Uploads document image, creates new case record, and records initial audit log.
    """
    contents = await file.read()
    validate_image_upload(file.filename, len(contents))

    # Generate secure filename
    filename = sanitize_filename(file.filename)
    save_path = os.path.join(settings.UPLOAD_DIR, "documents", filename)
    with open(save_path, "wb") as f:
        f.write(contents)

    # Generate Case Number e.g. BM-2026-10482
    case_num = f"BM-2026-{random.randint(10000, 99999)}"

    # Create Case in DB
    new_case = Case(
        case_number=case_num,
        document_type=document_type,
        country=country,
        status="PROCESSING",
        risk_level="LOW",
        risk_score=0.0
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # Create DocumentAnalysis record
    analysis = DocumentAnalysis(
        case_id=new_case.id,
        document_type=document_type,
        document_image_path=save_path
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    # Audit Trail
    AuditService.log(
        db=db,
        action="DOCUMENT_UPLOADED",
        case_id=new_case.id,
        actor="OFFICER-DEMO-01",
        metadata={
            "filename": file.filename,
            "file_size": len(contents),
            "document_type": document_type
        }
    )

    return {
        "case_id": new_case.id,
        "case_number": new_case.case_number,
        "document_image_url": f"/uploads/documents/{filename}",
        "document_type": document_type,
        "status": new_case.status
    }


@router.post("/{case_id}/ocr")
def process_ocr(case_id: str, db: Session = Depends(get_db)):
    """
    Step 2: Preprocesses image and runs OCR extraction.
    """
    t0 = time.time()
    analysis = db.query(DocumentAnalysis).filter(DocumentAnalysis.case_id == case_id).first()
    if not analysis or not analysis.document_image_path:
        raise HTTPException(status_code=404, detail="Document analysis record not found.")

    ocr_svc = get_ocr_service()
    ocr_result = ocr_svc.extract_text(analysis.document_image_path)

    # Dedicated MRZ-band OCR pass (crop/upscale/binarize + restricted charset),
    # much more reliable for the small monospace MRZ font than the general
    # whole-document text pass above. Falls back gracefully if unavailable
    # (e.g. MockOCRService, which has no extract_mrz_lines method).
    if hasattr(ocr_svc, "extract_mrz_lines"):
        ocr_result["mrz_lines"] = ocr_svc.extract_mrz_lines(analysis.document_image_path)
    else:
        ocr_result["mrz_lines"] = []

    elapsed_ms = (time.time() - t0) * 1000.0
    analysis.ocr_result = ocr_result
    analysis.processing_time_ms += elapsed_ms
    db.commit()

    AuditService.log(
        db=db,
        action="OCR_COMPLETED",
        case_id=case_id,
        actor="AI-OCR-ENGINE",
        metadata={"confidence": ocr_result.get("confidence"), "elapsed_ms": round(elapsed_ms, 1)}
    )

    return {
        "case_id": case_id,
        "ocr_result": ocr_result,
        "elapsed_ms": round(elapsed_ms, 1)
    }


@router.post("/{case_id}/validate")
def process_mrz_and_validation(case_id: str, db: Session = Depends(get_db)):
    """
    Step 3: MRZ Parsing & Document Rules Engine Validation.
    """
    t0 = time.time()
    analysis = db.query(DocumentAnalysis).filter(DocumentAnalysis.case_id == case_id).first()
    case = db.query(Case).filter(Case.id == case_id).first()
    if not analysis or not case:
        raise HTTPException(status_code=404, detail="Case record not found.")

    ocr_result = analysis.ocr_result or {}
    detected_lines = ocr_result.get("detected_lines", [])
    mrz_lines = ocr_result.get("mrz_lines", [])

    # Prefer the dedicated MRZ-band OCR pass (crop/upscale/restricted-charset --
    # see TesseractOCRService.extract_mrz_lines) over lines from the general
    # whole-document pass, which is tuned for prose text and misreads the MRZ's
    # small monospace font far more often. Lines from the dedicated pass are
    # already isolated, so parse them directly rather than re-scanning.
    mrz_data = (
        MRZService.parse_pre_isolated_lines(mrz_lines)
        if len(mrz_lines) >= 2
        else None
    ) or MRZService.extract_mrz_from_lines(detected_lines)

    # Evaluate Document Rules
    validation_data = DocumentRulesEngine.evaluate(ocr_result, mrz_data)

    elapsed_ms = (time.time() - t0) * 1000.0
    analysis.mrz_result = mrz_data
    analysis.validation_result = validation_data
    analysis.processing_time_ms += elapsed_ms

    # Update Case country/fields if MRZ found
    if mrz_data:
        if mrz_data.get("country") and case.country in ["Unknown", ""]:
            case.country = mrz_data["country"]
        if mrz_data.get("document_number"):
            case.document_number_hash = hash_identifier(mrz_data["document_number"])
    elif ocr_result.get("fields", {}).get("document_number"):
        case.document_number_hash = hash_identifier(ocr_result["fields"]["document_number"])

    db.commit()

    AuditService.log(
        db=db,
        action="MRZ_VALIDATED",
        case_id=case_id,
        actor="AI-VALIDATION-ENGINE",
        metadata={
            "has_mrz": bool(mrz_data),
            "is_valid": mrz_data.get("is_valid", False) if mrz_data else False,
            "rules_passed": validation_data.get("passed_count", 0),
            "rules_failed": validation_data.get("failed_count", 0)
        }
    )

    return {
        "case_id": case_id,
        "mrz_result": mrz_data,
        "validation_result": validation_data,
        "elapsed_ms": round(elapsed_ms, 1)
    }


@router.post("/{case_id}/tamper")
def process_tamper_analysis(case_id: str, db: Session = Depends(get_db)):
    """
    Step 4: Forensic Tamper AI (ELA, edge splicing, portrait seam, texture anomalies).
    """
    t0 = time.time()
    analysis = db.query(DocumentAnalysis).filter(DocumentAnalysis.case_id == case_id).first()
    if not analysis or not analysis.document_image_path:
        raise HTTPException(status_code=404, detail="Document analysis record not found.")

    tamper_svc = get_tamper_service()
    tamper_result = tamper_svc.analyze(analysis.document_image_path, case_id)

    elapsed_ms = (time.time() - t0) * 1000.0
    analysis.tamper_result = tamper_result
    analysis.processing_time_ms += elapsed_ms
    db.commit()

    AuditService.log(
        db=db,
        action="TAMPER_ANALYSIS_COMPLETED",
        case_id=case_id,
        actor="AI-TAMPER-FORENSICS",
        metadata={
            "tamper_risk": tamper_result.get("tamper_risk"),
            "risk_level": tamper_result.get("risk_level"),
            "signals_count": len(tamper_result.get("signals", []))
        }
    )

    return {
        "case_id": case_id,
        "tamper_result": tamper_result,
        "elapsed_ms": round(elapsed_ms, 1)
    }


@router.post("/{case_id}/face")
async def process_face_verification(
    case_id: str,
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """
    Step 5: Biometric Face Verification between document portrait and live capture.
    """
    t0 = time.time()
    analysis = db.query(DocumentAnalysis).filter(DocumentAnalysis.case_id == case_id).first()
    if not analysis or not analysis.document_image_path:
        raise HTTPException(status_code=404, detail="Document analysis record not found.")

    live_face_path = None
    if file:
        contents = await file.read()
        validate_image_upload(file.filename, len(contents))
        fname = sanitize_filename(file.filename)
        live_face_path = os.path.join(settings.UPLOAD_DIR, "faces", fname)
        with open(live_face_path, "wb") as f:
            f.write(contents)
    else:
        # If no custom live image uploaded, check if analysis has one or generate matching demo capture
        live_face_path = os.path.join(settings.UPLOAD_DIR, "faces", f"{case_id}_live.jpg")
        from app.utils.synthetic_generator import SyntheticDocumentGenerator
        SyntheticDocumentGenerator.generate_live_face_image(live_face_path, variant=1)

    analysis.face_image_path = live_face_path

    face_svc = get_face_service()
    face_result = face_svc.verify(analysis.document_image_path, live_face_path, case_id)

    elapsed_ms = (time.time() - t0) * 1000.0
    analysis.face_result = face_result
    analysis.processing_time_ms += elapsed_ms
    db.commit()

    AuditService.log(
        db=db,
        action="FACE_VERIFIED",
        case_id=case_id,
        actor="AI-FACE-VERIFIER",
        metadata={
            "similarity": face_result.get("similarity"),
            "status": face_result.get("status")
        }
    )

    return {
        "case_id": case_id,
        "face_result": face_result,
        "elapsed_ms": round(elapsed_ms, 1)
    }


@router.post("/{case_id}/risk")
def process_risk_aggregation(case_id: str, db: Session = Depends(get_db)):
    """
    Step 6: Central Risk Engine Aggregation & Case File Finalization.
    """
    t0 = time.time()
    case = db.query(Case).filter(Case.id == case_id).first()
    analysis = db.query(DocumentAnalysis).filter(DocumentAnalysis.case_id == case_id).first()
    if not case or not analysis:
        raise HTTPException(status_code=404, detail="Case record not found.")

    # 1. Watchlist Query
    watchlist_provider = get_watchlist_provider()
    mrz_data = analysis.mrz_result or {}
    ocr_data = analysis.ocr_result or {}
    
    full_name = None
    if mrz_data.get("surname"):
        full_name = f"{mrz_data.get('surname')} {mrz_data.get('given_names', '')}".strip()
    elif ocr_data.get("fields", {}).get("full_name"):
        full_name = ocr_data["fields"]["full_name"]

    doc_no = mrz_data.get("document_number") or ocr_data.get("fields", {}).get("document_number")
    watchlist_match = watchlist_provider.check_watchlist(full_name, doc_no)

    # 2. Risk Engine Evaluation
    risk_engine = get_risk_engine()
    risk_res = risk_engine.calculate(
        mrz_data=analysis.mrz_result,
        validation_data=analysis.validation_result or {},
        tamper_data=analysis.tamper_result or {},
        face_data=analysis.face_result,
        watchlist_match=watchlist_match
    )

    # 3. Update Case
    case.risk_score = risk_res["risk_score"]
    case.risk_level = risk_res["risk_level"]
    case.recommendation = risk_res["recommendation"]
    case.status = f"{risk_res['risk_level']}_RISK" if risk_res["risk_level"] in ["LOW", "MEDIUM"] else ("CRITICAL" if risk_res["risk_level"] == "CRITICAL" else "REQUIRES_REVIEW")
    analysis.risk_breakdown = risk_res["breakdown"]

    # Clear existing signals if re-evaluating, then insert new ones
    db.query(RiskSignal).filter(RiskSignal.case_id == case_id).delete()
    for sig in risk_res["signals"]:
        risk_sig = RiskSignal(
            case_id=case_id,
            module=sig["module"],
            signal=sig["signal"],
            severity=sig.get("severity", "LOW"),
            confidence=sig.get("confidence", 0.9),
            explanation=sig["explanation"],
            score_impact=sig.get("score_impact", 0.0)
        )
        db.add(risk_sig)

    elapsed_ms = (time.time() - t0) * 1000.0
    analysis.processing_time_ms += elapsed_ms
    db.commit()
    db.refresh(case)

    AuditService.log(
        db=db,
        action="RISK_CALCULATED",
        case_id=case_id,
        actor="AI-RISK-ENGINE",
        metadata={
            "risk_score": case.risk_score,
            "risk_level": case.risk_level,
            "recommendation": case.recommendation
        }
    )

    return {
        "case_id": case_id,
        "risk_score": case.risk_score,
        "risk_level": case.risk_level,
        "recommendation": case.recommendation,
        "critical_floor_applied": risk_res.get("critical_floor_applied", False),
        "breakdown": risk_res["breakdown"],
        "signals": risk_res["signals"],
        "elapsed_ms": round(elapsed_ms, 1)
    }
