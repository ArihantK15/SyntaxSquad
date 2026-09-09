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
