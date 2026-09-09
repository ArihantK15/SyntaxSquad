import {
  DashboardStats,
  CaseItem,
  CaseDetail,
  RiskSignal,
  AuditLog,
  OfficerDecision,
  ChainVerificationResult
} from '../types';

const API_BASE = '/api';

export const api = {
  async getHealth() {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error('Health check failed');
    return res.json();
  },

  async getDashboardStats(): Promise<DashboardStats> {
    const res = await fetch(`${API_BASE}/dashboard/stats`);
    if (!res.ok) throw new Error('Failed to fetch dashboard statistics');
    return res.json();
  },

  async listCases(params?: {
    status?: string;
    risk_level?: string;
    country?: string;
    limit?: number;
    offset?: number;
  }): Promise<CaseItem[]> {
    const query = new URLSearchParams();
    if (params?.status) query.append('status', params.status);
    if (params?.risk_level) query.append('risk_level', params.risk_level);
    if (params?.country) query.append('country', params.country);
    if (params?.limit) query.append('limit', params.limit.toString());
    if (params?.offset) query.append('offset', params.offset.toString());

    const res = await fetch(`${API_BASE}/cases?${query.toString()}`);
    if (!res.ok) throw new Error('Failed to fetch cases list');
    return res.json();
  },

  async getCaseDetail(caseId: string): Promise<CaseDetail> {
    const res = await fetch(`${API_BASE}/cases/${caseId}`);
    if (!res.ok) throw new Error(`Failed to fetch case ${caseId}`);
    return res.json();
  },

  async getCaseSignals(caseId: string): Promise<RiskSignal[]> {
    const res = await fetch(`${API_BASE}/cases/${caseId}/signals`);
    if (!res.ok) throw new Error('Failed to fetch risk signals');
    return res.json();
  },

  async getCaseAuditTrail(caseId: string): Promise<AuditLog[]> {
    const res = await fetch(`${API_BASE}/cases/${caseId}/audit`);
    if (!res.ok) throw new Error('Failed to fetch case audit trail');
    return res.json();
  },

  async recordOfficerDecision(
    caseId: string,
    decision: OfficerDecision,
    notes?: string
  ): Promise<CaseItem> {
    const res = await fetch(`${API_BASE}/cases/${caseId}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, notes, officer_id: 'OFFICER-DEMO-01' })
    });
    if (!res.ok) throw new Error('Failed to record officer decision');
    return res.json();
  },

  async deleteCase(caseId: string): Promise<{ message: string }> {
    const res = await fetch(`${API_BASE}/cases/${caseId}`, {
      method: 'DELETE'
    });
    if (!res.ok) throw new Error('Failed to delete case data');
    return res.json();
  },

  async purgeBiometrics(caseId: string): Promise<{
    case_id: string;
    message: string;
    biometrics_purged: boolean;
    purged_files_count: number;
    audit_hash: string;
  }> {
    const res = await fetch(`${API_BASE}/cases/${caseId}/purge-biometrics`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to purge case biometrics');
    return res.json();
  },

  async getAuditLogs(params?: {
    action?: string;
    actor?: string;
    case_id?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }): Promise<AuditLog[]> {
    const query = new URLSearchParams();
    if (params?.action) query.append('action', params.action);
    if (params?.actor) query.append('actor', params.actor);
    if (params?.case_id) query.append('case_id', params.case_id);
    if (params?.search) query.append('search', params.search);
    if (params?.limit) query.append('limit', params.limit.toString());
    if (params?.offset) query.append('offset', params.offset.toString());

    const res = await fetch(`${API_BASE}/audit?${query.toString()}`);
    if (!res.ok) throw new Error('Failed to fetch audit ledger logs');
    return res.json();
  },

  async verifyAuditChain(): Promise<ChainVerificationResult> {
    const res = await fetch(`${API_BASE}/audit/verify`);
    if (!res.ok) throw new Error('Audit ledger chain verification failed');
    return res.json();
  },

  async verifyCaseChain(caseId: string): Promise<ChainVerificationResult> {
    const res = await fetch(`${API_BASE}/audit/cases/${caseId}/verify`);
    if (!res.ok) throw new Error('Case chain verification failed');
    return res.json();
  },

  // --- Staged Screening Pipeline Steps ---
  async uploadScreeningDocument(
    file: File,
    documentType: string = 'Passport',
    country: string = 'Unknown'
  ): Promise<{
    case_id: string;
    case_number: string;
    document_image_url: string;
    document_type: string;
    status: string;
  }> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('document_type', documentType);
    formData.append('country', country);

    const res = await fetch(`${API_BASE}/screening/upload`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(err.detail || 'Upload failed');
    }
    return res.json();
  },

  async runStepOCR(caseId: string) {
    const res = await fetch(`${API_BASE}/screening/${caseId}/ocr`, { method: 'POST' });
    if (!res.ok) throw new Error('OCR extraction failed');
    return res.json();
  },

  async runStepValidate(caseId: string) {
    const res = await fetch(`${API_BASE}/screening/${caseId}/validate`, { method: 'POST' });
    if (!res.ok) throw new Error('MRZ and rules validation failed');
    return res.json();
  },

  async runStepTamper(caseId: string) {
    const res = await fetch(`${API_BASE}/screening/${caseId}/tamper`, { method: 'POST' });
    if (!res.ok) throw new Error('Tamper forensics failed');
    return res.json();
  },

  async runStepFace(caseId: string, liveFaceFile?: File) {
    const formData = new FormData();
    if (liveFaceFile) {
      formData.append('file', liveFaceFile);
    }
    const res = await fetch(`${API_BASE}/screening/${caseId}/face`, {
      method: 'POST',
      body: liveFaceFile ? formData : undefined
    });
    if (!res.ok) throw new Error('Face verification failed');
    return res.json();
  },

  async runStepRisk(caseId: string) {
    const res = await fetch(`${API_BASE}/screening/${caseId}/risk`, { method: 'POST' });
    if (!res.ok) throw new Error('Risk score aggregation failed');
    return res.json();
  },

  // --- Demo Scenario Automation ---
  async runDemoScenario(scenarioKey: string) {
    const res = await fetch(`${API_BASE}/demo/scenario`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario_key: scenarioKey })
    });
    if (!res.ok) throw new Error('Failed to run demo scenario');
    return res.json();
  },

  async generateSpecimenDoc(params: {
    mode: string;
    surname?: string;
    given_names?: string;
    doc_number?: string;
    country_name?: string;
  }) {
    const res = await fetch(`${API_BASE}/demo/generate-doc`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params)
    });
    if (!res.ok) throw new Error('Failed to generate specimen document');
    return res.json();
  }
};
