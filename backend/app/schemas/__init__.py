from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

# --- Audit Schemas ---
class AuditLogBase(BaseModel):
    action: str
    actor: str = "OFFICER-DEMO-01"
    metadata_json: Optional[Dict[str, Any]] = None

class AuditLogCreate(AuditLogBase):
    case_id: Optional[str] = None

class AuditLogOut(AuditLogBase):
    id: str
    case_id: Optional[str] = None
    timestamp: datetime
    previous_hash: Optional[str] = None
    entry_hash: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ChainVerificationOut(BaseModel):
    valid: bool
    total_records: int
    head_hash: Optional[str] = None
    genesis_hash: str
    verified_at: datetime
    compromised_id: Optional[str] = None
    reason: Optional[str] = None


class PurgeBiometricsResponse(BaseModel):
    case_id: str
    message: str
    biometrics_purged: bool
    purged_files_count: int
    audit_hash: str


# --- Risk Signal Schemas ---
class RiskSignalOut(BaseModel):
    id: Optional[str] = None
    case_id: Optional[str] = None
    module: str
    signal: str
    severity: str # LOW, MEDIUM, HIGH, CRITICAL
    confidence: float
    explanation: str
    score_impact: float = 0.0

    model_config = ConfigDict(from_attributes=True)


# --- Sub-Module Analysis Result Schemas ---
class OCRFieldItem(BaseModel):
    value: str
    confidence: float

class OCRResultOut(BaseModel):
    raw_text: str
    fields: Dict[str, Any]
    confidence: float
    detected_lines: List[str] = []

class MRZChecksumDetail(BaseModel):
    field: str
    value: str
    check_digit: str
    calculated_check_digit: str
    valid: bool

class MRZResultOut(BaseModel):
    format: str # TD3, TD1, TD2, NONE
    line1: str
    line2: str
    line3: Optional[str] = None
    document_type: str
    country: str
    surname: str
    given_names: str
    document_number: str
    nationality: str
    birth_date: str # YYMMDD
    sex: str
    expiry_date: str # YYMMDD
    optional_data: Optional[str] = None
    checksums: List[MRZChecksumDetail]
    is_valid: bool

class RuleValidationItem(BaseModel):
    rule: str
    passed: bool
    severity: str # LOW, MEDIUM, HIGH, CRITICAL
    explanation: str
    confidence: float

class ValidationResultOut(BaseModel):
    passed_count: int
    failed_count: int
    rules_detail: List[RuleValidationItem]

class TamperSignalItem(BaseModel):
    type: str # compression_anomaly, edge_discontinuity, photo_boundary_anomaly, font_inconsistency
    confidence: float
    region: List[int] = [] # [x, y, w, h]
    explanation: str

class TamperResultOut(BaseModel):
    tamper_risk: float # 0.0 to 1.0
    risk_level: str # LOW, MEDIUM, HIGH, CRITICAL
    signals: List[TamperSignalItem]
    heatmap_url: Optional[str] = None
    visual_anomalies: List[Dict[str, Any]] = []

class FaceVerificationOut(BaseModel):
    similarity: float
    status: str # MATCH, REVIEW_REQUIRED, NO_FACE_DETECTED, MULTIPLE_FACES
    document_face_url: Optional[str] = None
    live_face_url: Optional[str] = None
    quality_checks: Dict[str, Any] = {}
    anti_spoofing_score: float = 0.95


# --- Full Risk Breakdown ---
class RiskFactorBreakdown(BaseModel):
    factor: str
    weight: float
    raw_risk: float
    weighted_contribution: float
    top_signals: List[str]

class RiskEngineResult(BaseModel):
    risk_score: float # 0 to 100
    risk_level: str # LOW, MEDIUM, HIGH, CRITICAL
    recommendation: str
    breakdown: List[RiskFactorBreakdown]
    signals: List[RiskSignalOut]


# --- Case Schemas ---
class CaseBase(BaseModel):
    document_type: str = "Passport"
    country: str = "Unknown"

class CaseCreate(CaseBase):
    case_number: Optional[str] = None

class OfficerDecisionRequest(BaseModel):
    decision: str # CLEARED, REQUIRES_INSPECTION, ESCALATED
    notes: Optional[str] = None
    officer_id: str = "OFFICER-DEMO-01"

class DocumentAnalysisOut(BaseModel):
    id: str
    document_type: str
    document_image_path: Optional[str] = None
    face_image_path: Optional[str] = None
    biometrics_purged: bool = False
    ocr_result: Optional[Dict[str, Any]] = None
    mrz_result: Optional[Dict[str, Any]] = None
    validation_result: Optional[Dict[str, Any]] = None
    tamper_result: Optional[Dict[str, Any]] = None
    face_result: Optional[Dict[str, Any]] = None
    risk_breakdown: Optional[List[RiskFactorBreakdown]] = None
    processing_time_ms: float = 0.0

    model_config = ConfigDict(from_attributes=True)

class CaseOut(BaseModel):
    id: str
    case_number: str
    created_at: datetime
    updated_at: datetime
    document_type: str
    document_number_hash: Optional[str] = None
    country: str
    risk_score: float
    risk_level: str
    recommendation: str
    status: str
    officer_decision: str
    officer_notes: Optional[str] = None
    biometrics_purged: bool = False

    model_config = ConfigDict(from_attributes=True)

class CaseDetailOut(CaseOut):
    analyses: List[DocumentAnalysisOut] = []
    risk_signals: List[RiskSignalOut] = []
    audit_logs: List[AuditLogOut] = []


# --- Dashboard Stats Schemas ---
class DashboardStatsOut(BaseModel):
    documents_screened: int
    high_risk_cases: int
    critical_cases: int
    cases_requiring_review: int
    cleared_cases: int
    avg_processing_time_ms: float
    risk_distribution: Dict[str, int] # {"LOW": 12, "MEDIUM": 5, "HIGH": 4, "CRITICAL": 2}
    document_types: Dict[str, int]
    top_risk_reasons: List[Dict[str, Any]]
    recent_cases: List[CaseOut]
