import pytest
from fastapi.testclient import TestClient
from app.main import app

# Starlette's TestClient only runs the app's lifespan (startup/shutdown --
# here, Base.metadata.create_all plus initial seeding) when entered as a
# context manager; a bare `TestClient(app)` never triggers it, leaving every
# DB-backed endpoint below failing with "no such table". Enter it once for
# the whole module so all tests keep sharing state/order as originally
# written, and close it after the last test.
_client_cm = TestClient(app)
client = _client_cm.__enter__()


def teardown_module(module):
    _client_cm.__exit__(None, None, None)

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

def test_dashboard_latency_breakdown_reflects_real_audit_timestamps():
    """
    latency_breakdown used to not exist -- the "Component Processing
    Latency" chart on the Analytics page was a hardcoded array
    (Normalization: 140ms, OCR: 520ms, ...) never measured from anything.
    Every case's audit trail already timestamps each pipeline step
    (DOCUMENT_UPLOADED, OCR_COMPLETED, MRZ_VALIDATED, ...), so the per-module
    average can be computed for real from those deltas. Run an actual
    scenario and confirm each module's reported time is a genuine
    measurement (backed by at least one real sample), not a placeholder.
    """
    demo_res = client.post("/api/demo/scenario", json={"scenario_key": "genuine"})
    assert demo_res.status_code == 200

    stats = client.get("/api/dashboard/stats").json()
    breakdown = {b["module"]: b for b in stats["latency_breakdown"]}
    assert "OCR Extraction" in breakdown
    assert "Risk Engine" in breakdown
    for module in breakdown.values():
        assert module["sample_count"] >= 1
        assert module["time_ms"] > 0

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

def test_watchlist_evasion_scenario_still_flags_near_miss():
    """
    The 'watchlist_evasion' demo scenario is a document with a valid MRZ, a
    matching face, and no tamper signals -- everything about it looks clean
    except that the name and document number are each a single character
    away from a real watchlist entry (WL-SIM-2026-081). An exact-match-only
    watchlist check (what this system had before the fuzzy-matching fix)
    would have missed both and cleared this as LOW risk; the fuzzy check
    must still catch it and floor the outcome to at least HIGH, since a
    CRITICAL-severity watchlist hit is a hard-stop regardless of how clean
    every other signal is.
    """
    response = client.post("/api/demo/scenario", json={"scenario_key": "watchlist_evasion"})
    assert response.status_code == 200
    data = response.json()
    assert data["risk_level"] in ("HIGH", "CRITICAL")

    detail = client.get(f"/api/cases/{data['case_id']}").json()
    analysis = detail["analyses"][0]
    assert analysis["mrz_result"]["is_valid"] is True
    assert analysis["face_result"]["status"] == "MATCH"
    assert analysis["tamper_result"]["risk_level"] in ("LOW", "MEDIUM")

    breakdown = analysis["risk_breakdown"]
    watchlist_factor = next(b for b in breakdown if b["factor"] == "Simulated Watchlist Adapter")
    assert watchlist_factor["raw_risk"] == 100.0

def test_get_policy_settings_returns_defaults():
    response = client.get("/api/settings/policy")
    assert response.status_code == 200
    data = response.json()
    total = (data["weight_mrz"] + data["weight_tamper"] + data["weight_face"]
             + data["weight_consistency"] + data["weight_watchlist"])
    assert abs(total - 1.0) < 0.01

def test_update_policy_rejects_weights_not_summing_to_100():
    bad_policy = {
        "weight_mrz": 0.5, "weight_tamper": 0.5, "weight_face": 0.5,
        "weight_consistency": 0.1, "weight_watchlist": 0.05,
        "threshold_low": 24, "threshold_medium": 49, "threshold_high": 74
    }
    response = client.post("/api/settings/policy", json=bad_policy)
    assert response.status_code == 400
    assert "100%" in response.json()["detail"]

def test_update_policy_rejects_non_ascending_thresholds():
    bad_policy = {
        "weight_mrz": 0.25, "weight_tamper": 0.30, "weight_face": 0.30,
        "weight_consistency": 0.10, "weight_watchlist": 0.05,
        "threshold_low": 50, "threshold_medium": 30, "threshold_high": 74
    }
    response = client.post("/api/settings/policy", json=bad_policy)
    assert response.status_code == 400

def test_policy_change_actually_changes_a_real_screening_result():
    """
    This is the entire point of the fix: the Settings page's sliders used to
    update local React state only -- "Apply Policy Configuration" was
    entirely cosmetic and never reached the risk engine. Changing a weight
    here must change a real demo scenario's computed risk breakdown.
    """
    # Push MRZ weight to its max and zero out everything else the
    # "expired" scenario doesn't otherwise trigger, so the MRZ factor's
    # contribution to the total score is unmistakable.
    new_policy = {
        "weight_mrz": 0.70, "weight_tamper": 0.10, "weight_face": 0.10,
        "weight_consistency": 0.05, "weight_watchlist": 0.05,
        "threshold_low": 24, "threshold_medium": 49, "threshold_high": 74
    }
    update_res = client.post("/api/settings/policy", json=new_policy)
    assert update_res.status_code == 200
    assert update_res.json()["weight_mrz"] == 0.70

    demo_res = client.post("/api/demo/scenario", json={"scenario_key": "expired"})
    assert demo_res.status_code == 200
    detail = client.get(f"/api/cases/{demo_res.json()['case_id']}").json()
    breakdown = detail["analyses"][0]["risk_breakdown"]
    mrz_factor = next(b for b in breakdown if b["factor"] == "MRZ & Document Validation")
    assert mrz_factor["weight"] == 0.70

    # Restore defaults so later tests in this module aren't affected.
    client.post("/api/settings/policy", json={
        "weight_mrz": 0.25, "weight_tamper": 0.30, "weight_face": 0.30,
        "weight_consistency": 0.10, "weight_watchlist": 0.05,
        "threshold_low": 24, "threshold_medium": 49, "threshold_high": 74
    })

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

def test_cors_does_not_reflect_arbitrary_origins():
    """
    ALLOWED_ORIGINS previously included a bare "*" alongside explicit
    origins, with allow_credentials=True on the CORS middleware. Starlette's
    documented behavior in that combination is to reflect whatever Origin
    header the request actually sent instead of a literal "*" -- verified
    against the real running server with a fake origin before this was
    fixed, which made the explicit allowlist meaningless. Locks in that an
    arbitrary origin no longer gets echoed back.
    """
    response = client.get("/api/health", headers={"Origin": "http://evil.example.com"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") != "http://evil.example.com"

def test_update_policy_service_rejects_bad_weights_even_bypassing_the_route():
    """
    The weights-sum-to-100% check used to live only in the API route, not in
    update_policy() itself -- so any other future caller of the service
    function would silently write an inconsistent policy row with no error.
    Calling the service directly (bypassing the route's own validation
    entirely) must still reject a bad payload and must not mutate the
    stored policy.
    """
    from app.core.database import SessionLocal
    from app.services.policy_service import get_policy, update_policy, PolicyValidationError

    db = SessionLocal()
    try:
        before = get_policy(db)
        before_weights = (
            before.weight_mrz, before.weight_tamper, before.weight_face,
            before.weight_consistency, before.weight_watchlist
        )

        with pytest.raises(PolicyValidationError):
            update_policy(
                db,
                weight_mrz=0.9, weight_tamper=0.9, weight_face=0.9,
                weight_consistency=0.1, weight_watchlist=0.05,
                threshold_low=before.threshold_low,
                threshold_medium=before.threshold_medium,
                threshold_high=before.threshold_high,
            )

        db.rollback()
        after = get_policy(db)
        after_weights = (
            after.weight_mrz, after.weight_tamper, after.weight_face,
            after.weight_consistency, after.weight_watchlist
        )
        assert after_weights == before_weights
    finally:
        db.close()

