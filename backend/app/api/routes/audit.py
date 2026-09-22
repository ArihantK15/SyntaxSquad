from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from typing import Optional, List, Dict, Any

from app.api.deps import get_db, require_officer_auth
from app.models import AuditLog, BlockchainAnchor
from app.schemas import AuditLogOut, ChainVerificationOut, BlockchainAnchorOut
from app.services.audit_service import AuditService
from app.services.blockchain_anchor_service import get_blockchain_anchor_service, AnchorConfigurationError

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


@router.post("/anchor", response_model=BlockchainAnchorOut)
def anchor_audit_chain(db: Session = Depends(get_db), _auth: None = Depends(require_officer_auth)):
    """
    On-demand: publishes the audit ledger's current head hash to a public
    blockchain testnet (Ethereum Sepolia). The head hash already commits to the
    FULL chain history by construction (see AuditService), so this lets an
    independent verifier -- e.g. a judge -- check it on a public block
    explorer without trusting this application's own database at all.

    Officer-authenticated like case deletion/biometric purge: this triggers
    a real (though free) testnet transaction, so it shouldn't fire on a
    bare, credential-free request. Deliberately NOT called from
    AuditService.log()/verify_chain()'s hot path -- see blockchain_anchor_service.py.
    """
    verification = AuditService.verify_chain(db)
    if verification["total_records"] == 0:
        raise HTTPException(status_code=400, detail="Cannot anchor an empty audit ledger.")

    try:
        anchor_svc = get_blockchain_anchor_service()
        result = anchor_svc.anchor(verification["head_hash"])
    except AnchorConfigurationError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Blockchain anchoring failed: {e}")

    record = BlockchainAnchor(
        head_hash=verification["head_hash"],
        total_records_at_anchor=verification["total_records"],
        network=result["network"],
        chain_id=result["chain_id"],
        tx_hash=result["tx_hash"],
        block_number=result.get("block_number"),
        explorer_url=result["explorer_url"],
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/anchors", response_model=List[BlockchainAnchorOut])
def list_blockchain_anchors(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """History of past anchor transactions. No auth required -- everything
    here is already public on-chain once anchored (a tx hash and an
    explorer link), same as the audit logs list above."""
    return (
        db.query(BlockchainAnchor)
        .order_by(desc(BlockchainAnchor.created_at))
        .limit(limit)
        .all()
    )
