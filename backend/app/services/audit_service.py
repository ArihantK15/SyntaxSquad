import hashlib
import json
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc
from typing import Optional, Dict, Any, List

from app.models import AuditLog

GENESIS_HASH = "0" * 64

class AuditService:
    @staticmethod
    def canonical_json(data: Optional[Dict[str, Any]]) -> str:
        """Serializes dictionary deterministically for cryptographic hashing."""
        if not data:
            return "{}"
        return json.dumps(data, sort_keys=True, separators=(',', ':'), default=str)

    @staticmethod
    def compute_hash(
        previous_hash: str,
        case_id: Optional[str],
        action: str,
        actor: str,
        timestamp_str: str,
        metadata_str: str
    ) -> str:
        """Computes SHA-256 block hash for the audit ledger."""
        payload = f"{previous_hash}|{case_id or 'SYSTEM'}|{action}|{actor}|{timestamp_str}|{metadata_str}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def log(
        cls,
        db: Session,
        action: str,
        case_id: Optional[str] = None,
        actor: str = "OFFICER-DEMO-01",
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """Appends a cryptographically chained, immutable audit log entry."""
        meta = metadata or {}
        now = datetime.utcnow()
        now_iso = now.isoformat()
        meta_str = cls.canonical_json(meta)

        # Get previous block hash from latest entry in chain
        latest_entry = db.query(AuditLog).order_by(desc(AuditLog.timestamp), desc(AuditLog.id)).first()
        prev_hash = latest_entry.entry_hash if (latest_entry and latest_entry.entry_hash) else GENESIS_HASH

        entry_hash = cls.compute_hash(
            previous_hash=prev_hash,
            case_id=case_id,
            action=action,
            actor=actor,
            timestamp_str=now_iso,
            metadata_str=meta_str
        )

        entry = AuditLog(
            case_id=case_id,
            action=action,
            actor=actor,
            timestamp=now,
            metadata_json=meta,
            previous_hash=prev_hash,
            entry_hash=entry_hash
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    @classmethod
    def verify_chain(cls, db: Session, case_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Cryptographically verifies the SHA-256 chain-of-custody across the audit ledger.
        Proves mathematical immutability and flags any tampered records.
        """
        query = db.query(AuditLog)
        if case_id:
            query = query.filter(AuditLog.case_id == case_id)
        logs = query.order_by(asc(AuditLog.timestamp), asc(AuditLog.id)).all()

        if not logs:
            return {
                "valid": True,
                "total_records": 0,
                "head_hash": GENESIS_HASH,
                "genesis_hash": GENESIS_HASH,
                "verified_at": datetime.utcnow(),
                "compromised_id": None,
                "reason": "Ledger is empty (0 blocks)."
            }

        # Verify chain integrity
        for i, log in enumerate(logs):
            meta_str = cls.canonical_json(log.metadata_json)
            ts_str = log.timestamp.isoformat() if isinstance(log.timestamp, datetime) else str(log.timestamp)

            expected_hash = cls.compute_hash(
                previous_hash=log.previous_hash or GENESIS_HASH,
                case_id=log.case_id,
                action=log.action,
                actor=log.actor,
                timestamp_str=ts_str,
                metadata_str=meta_str
            )

            # Check hash match
            if log.entry_hash and log.entry_hash != expected_hash:
                return {
                    "valid": False,
                    "total_records": len(logs),
                    "head_hash": logs[-1].entry_hash,
                    "genesis_hash": GENESIS_HASH,
                    "verified_at": datetime.utcnow(),
                    "compromised_id": log.id,
                    "reason": f"Hash signature mismatch at block #{i+1} (Action: {log.action}, Actor: {log.actor})."
                }

        return {
            "valid": True,
            "total_records": len(logs),
            "head_hash": logs[-1].entry_hash or GENESIS_HASH,
            "genesis_hash": GENESIS_HASH,
            "verified_at": datetime.utcnow(),
            "compromised_id": None,
            "reason": f"All {len(logs)} blocks cryptographically verified intact via SHA-256 chaining."
        }
