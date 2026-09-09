from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from typing import Optional, List, Dict, Any

from app.api.deps import get_db
from app.models import AuditLog
from app.schemas import AuditLogOut, ChainVerificationOut
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["audit"])

@router.get("", response_model=List[AuditLogOut])
def list_audit_logs(
    action: Optional[str] = None,
    actor: Optional[str] = None,
    case_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Centralized, paginated query of immutable blockchain-style audit ledger events.
    Supports filtering by action, actor, case_id, or general search query.
    """
    query = db.query(AuditLog)
    
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    if actor:
        query = query.filter(AuditLog.actor.ilike(f"%{actor}%"))
    if case_id:
        query = query.filter(AuditLog.case_id == case_id)
    if search:
        s = f"%{search}%"
        query = query.filter(
            or_(
                AuditLog.action.ilike(s),
                AuditLog.actor.ilike(s),
                AuditLog.case_id.ilike(s)
            )
        )

    logs = query.order_by(desc(AuditLog.timestamp), desc(AuditLog.id)).offset(offset).limit(limit).all()
    return logs


@router.get("/verify", response_model=ChainVerificationOut)
def verify_audit_ledger_integrity(db: Session = Depends(get_db)):
    """
    Cryptographically verifies the entire SHA-256 chain of custody across all audit logs.
    Theme: Blockchain & Cybersecurity — Proves zero unauthorized tampering or log reordering.
    """
    result = AuditService.verify_chain(db)
    return result


@router.get("/cases/{case_id}/verify", response_model=ChainVerificationOut)
def verify_case_chain_integrity(case_id: str, db: Session = Depends(get_db)):
    """
    Cryptographically verifies the chain of custody for a specific case.
    """
    result = AuditService.verify_chain(db, case_id=case_id)
    return result


@router.get("/stats")
def get_audit_ledger_stats(db: Session = Depends(get_db)):
    """
    Returns high-level statistics about the cryptographic audit ledger.
    """
    total = db.query(AuditLog).count()
    latest = db.query(AuditLog).order_by(desc(AuditLog.timestamp), desc(AuditLog.id)).first()
    
    return {
        "total_blocks": total,
        "head_hash": latest.entry_hash if latest else "0" * 64,
        "genesis_hash": "0" * 64,
        "last_event_timestamp": latest.timestamp.isoformat() if latest else None
    }
