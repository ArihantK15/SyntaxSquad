import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "ai_engines" in data
    assert data["ai_engines"]["mrz_validator"] == "ONLINE"

def test_dashboard_stats_endpoint():
    response = client.get("/api/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    assert "documents_screened" in data
    assert data["documents_screened"] >= 0
    assert "risk_distribution" in data

def test_cases_list_endpoint():
    response = client.get("/api/cases")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0

def test_demo_scenario_execution():
    response = client.post("/api/demo/scenario", json={"scenario_key": "genuine"})
    assert response.status_code == 200
    data = response.json()
    assert "case_id" in data
    assert "case_number" in data
    assert data["risk_level"] == "LOW"

    # Fetch case detail
    case_res = client.get(f"/api/cases/{data['case_id']}")
    assert case_res.status_code == 200
    detail = case_res.json()
    assert detail["case_number"] == data["case_number"]
    assert len(detail["analyses"]) > 0

    # The risk engine's real per-factor breakdown must be persisted on the
    # analysis record, not just returned transiently by the risk step.
    breakdown = detail["analyses"][0]["risk_breakdown"]
    assert breakdown is not None
    assert len(breakdown) == 5
    factor_names = {b["factor"] for b in breakdown}
    assert "Forensic Tamper AI" in factor_names
    assert "Biometric Face Verification" in factor_names
    for factor in breakdown:
        assert "weight" in factor
        assert "raw_risk" in factor
        assert "weighted_contribution" in factor

def test_officer_decision_recording():
    # Fetch first case
    cases_res = client.get("/api/cases?limit=1")
    cases = cases_res.json()
    case_id = cases[0]["id"]

    decision_payload = {
        "decision": "REQUIRES_INSPECTION",
        "notes": "Test officer inspection note for SIH verification.",
        "officer_id": "OFFICER-TEST-99"
    }
    dec_res = client.post(f"/api/cases/{case_id}/decision", json=decision_payload)
    assert dec_res.status_code == 200
    updated_case = dec_res.json()
    assert updated_case["officer_decision"] == "REQUIRES_INSPECTION"

    # Verify audit log contains entry
    audit_res = client.get(f"/api/cases/{case_id}/audit")
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert any(log["action"] == "OFFICER_DECISION_RECORDED" for log in logs)

def test_central_audit_and_chain_verification():
    # 1. Test centralized audit list
    res = client.get("/api/audit?limit=10")
    assert res.status_code == 200
    logs = res.json()
    assert isinstance(logs, list)
    assert len(logs) > 0
    # Verify hash presence on blocks
    assert "entry_hash" in logs[0]
    assert "previous_hash" in logs[0]

    # 2. Test live cryptographic chain verification
    verify_res = client.get("/api/audit/verify")
    assert verify_res.status_code == 200
    vdata = verify_res.json()
    assert vdata["valid"] is True
    assert vdata["total_records"] > 0
    assert len(vdata["head_hash"]) == 64

    # 3. Test audit stats
    stats_res = client.get("/api/audit/stats")
    assert stats_res.status_code == 200
    sdata = stats_res.json()
    assert sdata["total_blocks"] > 0
    assert len(sdata["head_hash"]) == 64

def test_biometrics_purge_protocol():
    # Execute a demo scenario to create fresh case
    demo_res = client.post("/api/demo/scenario", json={"scenario_key": "genuine"})
    assert demo_res.status_code == 200
    case_id = demo_res.json()["case_id"]

    # Trigger biometrics purge
    purge_res = client.post(f"/api/cases/{case_id}/purge-biometrics")
    assert purge_res.status_code == 200
    pdata = purge_res.json()
    assert pdata["biometrics_purged"] is True
    assert pdata["case_id"] == case_id
    assert len(pdata["audit_hash"]) == 64

    # Verify case reflects purged biometrics
    case_res = client.get(f"/api/cases/{case_id}")
    assert case_res.status_code == 200
    cdata = case_res.json()
    assert cdata["biometrics_purged"] is True
    assert cdata["analyses"][0]["biometrics_purged"] is True
    assert cdata["analyses"][0]["document_image_path"] == "[PURGED_PRIVACY_COMPLIANCE]"

