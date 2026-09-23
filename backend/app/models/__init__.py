import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, DateTime, Text, JSON, ForeignKey, Integer, Boolean
from sqlalchemy.orm import relationship

from app.core.database import Base

class Case(Base):
    __tablename__ = "cases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_number = Column(String(32), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    document_type = Column(String(64), default="Passport")
    document_number_hash = Column(String(64), index=True, nullable=True)
    country = Column(String(64), default="Unknown")
    
    risk_score = Column(Float, default=0.0)
    risk_level = Column(String(32), default="LOW") # LOW, MEDIUM, HIGH, CRITICAL
    recommendation = Column(String(128), default="CLEAR FOR ENTRY")
    status = Column(String(32), default="PROCESSING") # PROCESSING, LOW_RISK, MEDIUM_RISK, HIGH_RISK, CRITICAL, CLEARED, REQUIRES_REVIEW, ESCALATED
    
    officer_decision = Column(String(64), default="PENDING") # PENDING, CLEARED, REQUIRES_INSPECTION, ESCALATED
    officer_notes = Column(Text, nullable=True)
    biometrics_purged = Column(Boolean, default=False)

    # Relationships
    analyses = relationship("DocumentAnalysis", back_populates="case", cascade="all, delete-orphan")
    risk_signals = relationship("RiskSignal", back_populates="case", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="case", cascade="all, delete-orphan")
    gallery_entries = relationship("FaceEmbeddingGallery", back_populates="case", cascade="all, delete-orphan")


class DocumentAnalysis(Base):
    __tablename__ = "document_analysis"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    
    document_type = Column(String(64), default="Passport")
    document_image_path = Column(String(255), nullable=True)
    face_image_path = Column(String(255), nullable=True)
    biometrics_purged = Column(Boolean, default=False)
    
    ocr_result = Column(JSON, nullable=True)
    mrz_result = Column(JSON, nullable=True)
    validation_result = Column(JSON, nullable=True)
    tamper_result = Column(JSON, nullable=True)
    face_result = Column(JSON, nullable=True)
    risk_breakdown = Column(JSON, nullable=True)
    
    processing_time_ms = Column(Float, default=0.0)

    case = relationship("Case", back_populates="analyses")


class RiskSignal(Base):
    __tablename__ = "risk_signals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    
    module = Column(String(64), nullable=False) # OCR, MRZ, VALIDATION, TAMPER, FACE, WATCHLIST
    signal = Column(String(128), nullable=False)
    severity = Column(String(32), default="LOW") # LOW, MEDIUM, HIGH, CRITICAL
    confidence = Column(Float, default=0.95)
    explanation = Column(Text, nullable=False)
    score_impact = Column(Float, default=0.0)

    case = relationship("Case", back_populates="risk_signals")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True)
    
    action = Column(String(128), nullable=False) # DOCUMENT_UPLOADED, OCR_COMPLETED, MRZ_VALIDATED, TAMPER_ANALYSIS_COMPLETED, FACE_VERIFIED, RISK_CALCULATED, CASE_VIEWED, OFFICER_DECISION_RECORDED, BIOMETRICS_PURGED
    actor = Column(String(128), default="OFFICER-DEMO-01")
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    metadata_json = Column(JSON, nullable=True)

    previous_hash = Column(String(64), nullable=True) # SHA-256 hash of previous block (Blockchain Chain-of-Custody)
    entry_hash = Column(String(64), nullable=True)    # SHA-256 hash of current block

    case = relationship("Case", back_populates="audit_logs")


class BlockchainAnchor(Base):
    """
    On-demand, best-effort anchoring of the audit ledger's head hash (see
    AuditService -- the head hash already commits to the FULL chain history
    by construction, since each entry_hash embeds the previous one, so
    anchoring it is equivalent to anchoring a Merkle root) to a public
    blockchain testnet. This lets an independent verifier confirm a specific
    hash value existed at a specific, un-forgeable block time, without
    trusting this application's own database at all.

    Deliberately isolated from AuditService.log()/verify_chain(): this table
    and the service that writes to it (app.services.blockchain_anchor_service)
    are never called from that hot path, so a testnet RPC outage or an empty
    faucet wallet cannot affect the core, already-working local hash-chain
    audit trail.
    """
    __tablename__ = "blockchain_anchors"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    head_hash = Column(String(64), nullable=False)
    total_records_at_anchor = Column(Integer, nullable=False)
    network = Column(String(64), nullable=False)  # e.g. "Ethereum Sepolia"
    chain_id = Column(Integer, nullable=False)
    tx_hash = Column(String(66), nullable=False, unique=True)
    block_number = Column(Integer, nullable=True)
    explorer_url = Column(String(255), nullable=False)
    anchored_by = Column(String(128), default="OFFICER-DEMO-01")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FaceEmbeddingGallery(Base):
    """
    Best-effort 1:N cross-case face-embedding gallery for duplicate-identity
    detection (see identity_gallery_service.py) -- built from each
    screening's LIVE facial capture (the actual physically-present person),
    not the document photo, since the question this answers is "has this
    real person been screened before under a different claimed identity."

    Denormalizes case_number/full_name/document_number_hash rather than
    joining back to Case/DocumentAnalysis on every 1:N lookup -- this table
    exists purely to be scanned on every new screening, and these are
    exactly the values a matched signal needs to display.

    Deleted (not anonymized) on both the biometric purge endpoint and full
    case deletion -- a stored embedding IS raw biometric data, arguably
    more sensitive than the photo it was derived from since it's already
    in matchable form, so it gets the same privacy-by-design treatment as
    every other biometric artifact in this app.
    """
    __tablename__ = "face_embedding_gallery"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    case_number = Column(String(32), nullable=False)
    full_name = Column(String(255), nullable=True)
    document_number_hash = Column(String(64), nullable=True)
    embedding = Column(JSON, nullable=False)  # 512-d L2-normalized VGGFace2 embedding
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    case = relationship("Case", back_populates="gallery_entries")


class PolicySettings(Base):
    """
    Single-row table (id is always 1) holding the live-editable risk engine
    policy -- the Settings page used to let an officer drag these same
    weights/thresholds and click "Apply", but nothing was ever persisted or
    read back by the risk engine. Defaults to app.core.config.settings'
    static values the first time it's read; from then on, the risk engine
    reads its weights and thresholds from here instead.
    """
    __tablename__ = "policy_settings"

    id = Column(Integer, primary_key=True, default=1)
    weight_mrz = Column(Float, nullable=False)
    weight_tamper = Column(Float, nullable=False)
    weight_face = Column(Float, nullable=False)
    weight_consistency = Column(Float, nullable=False)
    weight_watchlist = Column(Float, nullable=False)
    threshold_low = Column(Float, nullable=False)
    threshold_medium = Column(Float, nullable=False)
    threshold_high = Column(Float, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
