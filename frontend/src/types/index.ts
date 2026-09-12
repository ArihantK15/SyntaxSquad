export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type CaseStatus = 'PROCESSING' | 'LOW_RISK' | 'MEDIUM_RISK' | 'HIGH_RISK' | 'CRITICAL' | 'CLEARED' | 'REQUIRES_REVIEW' | 'ESCALATED';
export type OfficerDecision = 'PENDING' | 'CLEARED' | 'REQUIRES_INSPECTION' | 'ESCALATED';

export interface AuditLog {
  id: string;
  case_id?: string;
  action: string;
  actor: string;
  timestamp: string;
  metadata_json?: Record<string, any>;
  previous_hash?: string;
  entry_hash?: string;
}

export interface ChainVerificationResult {
  valid: boolean;
  total_records: number;
  head_hash?: string;
  genesis_hash: string;
  verified_at: string;
  compromised_id?: string;
  reason?: string;
}

export interface RiskSignal {
  id?: string;
  case_id?: string;
  module: string;
  signal: string;
  severity: RiskLevel;
  confidence: number;
  explanation: string;
  score_impact: number;
}

export interface MRZChecksum {
  field: string;
  value: string;
  check_digit: string;
  calculated_check_digit: string;
  valid: boolean;
}

export interface MRZResult {
  format: string;
  line1: string;
  line2: string;
  line3?: string;
  document_type: string;
  country: string;
  surname: string;
  given_names: string;
  document_number: string;
  nationality: string;
  birth_date: string;
  sex: string;
  expiry_date: string;
  optional_data?: string;
  checksums: MRZChecksum[];
  is_valid: boolean;
}

export interface OCRResult {
  raw_text: string;
  fields: {
    full_name?: string;
    document_number?: string;
    country?: string;
    nationality?: string;
    date_of_birth?: string;
    date_of_issue?: string;
    date_of_expiry?: string;
    sex?: string;
  };
  confidence: number;
  detected_lines: string[];
}

export interface TamperSignal {
  type: string;
  confidence: number;
  region: number[];
  explanation: string;
}

export interface TamperResult {
  tamper_risk: number;
  risk_level: RiskLevel;
  signals: TamperSignal[];
  heatmap_url?: string;
  visual_anomalies: Array<{
    label: string;
    region: number[];
    confidence: number;
  }>;
}

export interface FaceVerificationResult {
  similarity: number;
  status: 'MATCH' | 'REVIEW_REQUIRED' | 'NO_FACE_DETECTED' | 'MULTIPLE_FACES';
  document_face_url?: string;
  live_face_url?: string;
  quality_checks: Record<string, any>;
  anti_spoofing_score: number;
  match_threshold: number;
  signals?: RiskSignal[];
}

export interface RuleValidationItem {
  rule: string;
  passed: boolean;
  severity: RiskLevel;
  explanation: string;
  confidence: number;
}

export interface ValidationResult {
  passed_count: number;
  failed_count: number;
  rules_detail: RuleValidationItem[];
  signals?: RiskSignal[];
}

export interface RiskFactorContribution {
  factor: string;
  weight: number;
  raw_risk: number;
  weighted_contribution: number;
  top_signals: string[];
}

export interface RiskEngineResult {
  risk_score: number;
  risk_level: RiskLevel;
  recommendation: string;
  breakdown: RiskFactorContribution[];
  signals: RiskSignal[];
  elapsed_ms?: number;
}

export interface DocumentAnalysis {
  id: string;
  document_type: string;
  document_image_path?: string;
  face_image_path?: string;
  biometrics_purged?: boolean;
  ocr_result?: OCRResult;
  mrz_result?: MRZResult;
  validation_result?: ValidationResult;
  tamper_result?: TamperResult;
  face_result?: FaceVerificationResult;
  risk_breakdown?: RiskFactorContribution[];
  processing_time_ms: number;
}

export interface CaseItem {
  id: string;
  case_number: string;
  created_at: string;
  updated_at: string;
  document_type: string;
  document_number_hash?: string;
  country: string;
  risk_score: number;
  risk_level: RiskLevel;
  recommendation: string;
  status: CaseStatus;
  officer_decision: OfficerDecision;
  officer_notes?: string;
  biometrics_purged?: boolean;
}

export interface CaseDetail extends CaseItem {
  analyses: DocumentAnalysis[];
  risk_signals: RiskSignal[];
  audit_logs: AuditLog[];
}

export interface PolicySettings {
  weight_mrz: number;
  weight_tamper: number;
  weight_face: number;
  weight_consistency: number;
  weight_watchlist: number;
  threshold_low: number;
  threshold_medium: number;
  threshold_high: number;
}

export interface DashboardStats {
  documents_screened: number;
  high_risk_cases: number;
  critical_cases: number;
  cases_requiring_review: number;
  cleared_cases: number;
  avg_processing_time_ms: number;
  risk_distribution: Record<RiskLevel, number>;
  latency_breakdown: Array<{ module: string; time_ms: number; sample_count: number }>;
  document_types: Record<string, number>;
  top_risk_reasons: Array<{ reason: string; count: number }>;
  recent_cases: CaseItem[];
}
