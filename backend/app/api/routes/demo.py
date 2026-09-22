import os
import re
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.api.deps import get_db
from app.api.routes.screening import MAX_CASE_NUMBER_ATTEMPTS
from app.core.config import settings
from app.models import Case, DocumentAnalysis, RiskSignal, AuditLog
from app.utils.synthetic_generator import SyntheticDocumentGenerator
from app.services.ocr_service import get_ocr_service, TesseractOCRService
from app.services.mrz_service import MRZService
from app.services.rules_engine import DocumentRulesEngine
from app.services.tamper_service import get_tamper_service
from app.services.face_service import get_face_service
from app.services.watchlist_service import get_watchlist_provider
from app.services.risk_engine import get_risk_engine
from app.services.policy_service import get_policy
from app.services.audit_service import AuditService
from app.core.security import hash_identifier
from app.core.demo_faces import PERSON_A, PERSON_B

router = APIRouter(prefix="/demo", tags=["demo"])

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
    },
    "watchlist_evasion": {
        "title": "Watchlist Evasion Attempt",
        "mode": "genuine",
        "surname": "KOROL",
        "given_names": "VICTOR",  # 'VIKTOR' -> 'VICTOR': one-letter difference from the watchlist name
        "country_code": "ATL",
        "country_name": "ATLANTIS FEDERATION",
        "doc_number": "P8B92144",  # 'P8892144' -> 'P8B92144': one-character difference (8 -> B)
        "nationality": "ATLANTIAN",
        "dob": "850704",
        "expiry": "300420",
        # Every other signal is deliberately clean (valid MRZ, no tamper, face
        # match) so the demo isolates one thing: a document number and name
        # each a single edit away from a real watchlist entry (WL-SIM-2026-081,
        # "VIKTOR KOROL" / "P8892144") still gets caught. An exact-match-only
        # watchlist check -- what this system had before tonight -- would
        # have missed both and cleared this traveler as LOW risk.
        "doc_face_photo": PERSON_A, "live_face_photo": PERSON_A
    },
    "pan_card": {
        "title": "PAN Card Verification",
        "mode": "genuine",
        "document_type": "PAN",
        "surname": "VERMA",
        "given_names": "ANANYA",
        "father_name": "RAJESH VERMA",
        "country_name": "INDIA",
        # 5th letter 'V' matches the surname's first letter (the documented
        # convention for individual PANs); 4th letter 'P' decodes as
        # Individual -- see rules_engine.py's PAN_ENTITY_TYPES.
        "doc_number": "ABCPV1234F",
        "dob": "920615",
        "doc_face_photo": PERSON_A, "live_face_photo": PERSON_A  # same person -> MATCH
    },
    "driving_license": {
        "title": "Driving Licence — Expired",
        "mode": "expired",
        "document_type": "DRIVING_LICENSE",
        "surname": "REDDY",
        "given_names": "KIRAN",
        "state_code": "KA",
        "state_name": "KARNATAKA",
        "country_name": "INDIA",
        "doc_number": "KA0320110098765",
        "dob": "880210",
        "issue": "110320",
        "expiry": "310320",  # overridden to a fixed past date by generate_driving_license's 'expired' mode
        "doc_face_photo": PERSON_A, "live_face_photo": PERSON_A  # same person -> MATCH
    },
    "voter_id": {
        "title": "Voter ID (EPIC) Verification",
        "mode": "genuine",
        "document_type": "VOTER_ID",
        "surname": "NAIR",
        "given_names": "ANJALI",
        "relation_name": "SURESH NAIR",
        "country_name": "INDIA",
        "doc_number": "MLD1234567",
        "dob": "970422",
        "sex": "FEMALE",
        "doc_face_photo": PERSON_A, "live_face_photo": PERSON_A  # same person -> MATCH
    }
}

# Case.document_type / DocumentAnalysis.document_type display labels, keyed
# by the SCENARIO_CONFIGS "document_type" tag (which is also what a real
# OCR pass on the rendered specimen tags itself via
# TesseractOCRService._detect_document_type -- see the fields["document_type"]
# assertions in test_api.py's PAN/DL demo scenario tests). Distinct from
# that tag: this is purely the free-text label shown in the UI, matching
# the style of frontend/src/pages/ScreeningPage.tsx's own dropdown options
# ("Passport", "National ID", "Visa").
DOCUMENT_TYPE_LABELS = {
    "PASSPORT": "Passport",
    "PAN": "PAN",
    "DRIVING_LICENSE": "Driving Licence",
    "VOTER_ID": "Voter ID",
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

    # Specimen filenames are keyed on case_uid (a full UUID4, already
    # collision-proof) rather than the shorter, human-facing case_number
    # below -- so a case_number collision (see _generate_unique_case_number)
    # never has to redo the already-generated specimen images on retry.
    doc_type = cfg.get("document_type", "PASSPORT")
    doc_filename = f"specimen_{case_uid}.jpg"
    doc_path = os.path.join(settings.UPLOAD_DIR, "documents", doc_filename)

    if doc_type == "PAN":
        SyntheticDocumentGenerator.generate_pan_card(
            out_path=doc_path,
            mode=cfg["mode"],
            surname=cfg["surname"],
            given_names=cfg["given_names"],
            father_name=cfg["father_name"],
            doc_number=cfg["doc_number"],
            dob_yymmdd=cfg["dob"],
            face_photo_path=cfg["doc_face_photo"]
        )
    elif doc_type == "DRIVING_LICENSE":
        SyntheticDocumentGenerator.generate_driving_license(
            out_path=doc_path,
            mode=cfg["mode"],
            surname=cfg["surname"],
            given_names=cfg["given_names"],
            state_code=cfg["state_code"],
            state_name=cfg["state_name"],
            doc_number=cfg["doc_number"],
            dob_yymmdd=cfg["dob"],
            issue_yymmdd=cfg["issue"],
            expiry_yymmdd=cfg["expiry"],
            face_photo_path=cfg["doc_face_photo"]
        )
    elif doc_type == "VOTER_ID":
        SyntheticDocumentGenerator.generate_voter_id_card(
            out_path=doc_path,
            mode=cfg["mode"],
            surname=cfg["surname"],
            given_names=cfg["given_names"],
            relation_name=cfg["relation_name"],
            doc_number=cfg["doc_number"],
            dob_yymmdd=cfg["dob"],
            sex=cfg["sex"],
            face_photo_path=cfg["doc_face_photo"]
        )
    else:
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
    live_filename = f"live_{case_uid}.jpg"
    live_path = os.path.join(settings.UPLOAD_DIR, "faces", live_filename)
    SyntheticDocumentGenerator.generate_live_face_image(live_path, face_photo_path=cfg["live_face_photo"])

    # Create Case (case_number retried on the rare unique-constraint
    # collision -- see screening.py's _create_case_with_unique_number for
    # why this matters; a much larger 16^5 space than the manual-upload
    # flow's 90,000, but not zero).
    case_num = None
    for attempt in range(MAX_CASE_NUMBER_ATTEMPTS):
        case_num = f"BM-2026-{uuid.uuid4().hex[:5].upper()}"
        new_case = Case(
            id=case_uid,
            case_number=case_num,
            document_type=DOCUMENT_TYPE_LABELS.get(doc_type, "Passport"),
            country=cfg["country_name"],
            document_number_hash=hash_identifier(cfg["doc_number"]),
            status="PROCESSING",
            risk_level="LOW",
            risk_score=0.0
        )
        db.add(new_case)
        try:
            db.commit()
            break
        except IntegrityError:
            db.rollback()
            if attempt == MAX_CASE_NUMBER_ATTEMPTS - 1:
                raise

    AuditService.log(db, "DOCUMENT_UPLOADED", case_uid, metadata={"scenario": cfg["title"], "specimen": doc_filename})

    try:
        # Real wall-clock timing per step -- this used to be a hardcoded
        # processing_time_ms=2100.0 below, which fed a fake-looking-real number
        # into the dashboard's "Average Pipeline Latency" KPI for every demo-
        # generated case (the majority of cases in this database). Measuring it
        # for real here matches what the manual screening flow (screening.py)
        # already does per step.
        step_start = time.perf_counter()

        # Step 2: OCR
        ocr_svc = get_ocr_service()
        ocr_result = ocr_svc.extract_text(doc_path)
        AuditService.log(db, "OCR_COMPLETED", case_uid, actor="AI-OCR-ENGINE", metadata={"conf": ocr_result.get("confidence")})

        # Step 3: MRZ & Validation -- prefer the dedicated MRZ-band OCR pass (see
        # TesseractOCRService.extract_mrz_lines / MRZService.parse_pre_isolated_lines)
        # over the general whole-document pass, same as the manual screening flow
        # in screening.py; the general pass misreads the small MRZ font far more.
        #
        # Skipped entirely for Aadhaar/PAN/Driving Licence, exactly like
        # screening.py's own equivalent guard: none of them have an ICAO MRZ
        # by design, so scanning the bottom band for one anyway risks
        # fabricating a fake MRZ from the card's own boilerplate/signature
        # text whose checksums then "fail" against a genuine, unaltered
        # card -- corrupting the MRZ risk factor for every PAN/DL demo
        # scenario. This module had no non-passport demo scenario until the
        # PAN/DL specimens below, so this gap was latent but never
        # exercised until now.
        if ocr_result.get("fields", {}).get("document_type") in TesseractOCRService.NON_MRZ_DOCUMENT_TYPES:
            mrz_data = None
        else:
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

        risk_engine = get_risk_engine(get_policy(db))
        risk_res = risk_engine.calculate(
            mrz_data=mrz_data,
            validation_data=validation_data,
            tamper_data=tamper_result,
            face_data=face_result,
            watchlist_match=watchlist_match
        )

        total_processing_ms = (time.perf_counter() - step_start) * 1000.0

        # Finalize Case
        new_case.risk_score = risk_res["risk_score"]
        new_case.risk_level = risk_res["risk_level"]
        new_case.recommendation = risk_res["recommendation"]
        new_case.status = f"{risk_res['risk_level']}_RISK" if risk_res["risk_level"] in ["LOW", "MEDIUM"] else ("CRITICAL" if risk_res["risk_level"] == "CRITICAL" else "REQUIRES_REVIEW")

        # Save DocumentAnalysis
        analysis = DocumentAnalysis(
            case_id=case_uid,
            document_type=DOCUMENT_TYPE_LABELS.get(doc_type, "Passport"),
            document_image_path=doc_path,
            face_image_path=live_path,
            ocr_result=ocr_result,
            mrz_result=mrz_data,
            validation_result=validation_data,
            tamper_result=tamper_result,
            face_result=face_result,
            risk_breakdown=risk_res["breakdown"],
            processing_time_ms=round(total_processing_ms, 1)
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
    except Exception:
        # Any failure past this point (OCR/tamper/face engines, risk
        # calculation, etc. -- e.g. a missing Tesseract binary) used to leave
        # the Case committed above stuck at status="PROCESSING",
        # risk_level="LOW", risk_score=0.0 forever: a zombie row that reads
        # exactly like a genuine cleared case in the Review Queue and Cases
        # Archive. Roll back any uncommitted work from this attempt, then
        # delete the case itself (cascades to its already-committed audit
        # entries -- see the delete-orphan relationships on Case) so a
        # failed demo run leaves no trace instead of a fake result.
        db.rollback()
        zombie_case = db.query(Case).filter(Case.id == case_uid).first()
        if zombie_case:
            db.delete(zombie_case)
            db.commit()
        raise


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
        nationality=f"{country_code} CITIZEN",
        # Without a real embedded face, MTCNN can't detect a face in the
        # hand-drawn avatar fallback at all -- face verification against a
        # New Screening-generated specimen would silently compare two
        # undetected avatar crops via a real face model and present a
        # meaningless similarity score as if it were a genuine result. See
        # app.core.demo_faces for why a real (AI-generated) photo is needed.
        face_photo_path=PERSON_A
    )
    return {
        "filename": fname,
        "url": f"/uploads/documents/{fname}",
        "mode": mode,
        "doc_number": doc_number
    }
