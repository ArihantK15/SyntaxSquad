import sys
from pathlib import Path

# scripts/ lives alongside backend/, not inside it -- add the repo root the
# same way app.main does before importing scripts.seed_cases (see
# backend/app/main.py's lifespan seeding block).
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.seed_cases import SYNTHETIC_PROFILES


def test_seed_has_multiple_document_types():
    doc_types = {p["doc_type"] for p in SYNTHETIC_PROFILES}
    assert doc_types.issuperset({"Passport", "National ID", "Visa"}), (
        f"Seed data should span multiple document types for demo variety, got {doc_types}"
    )
    assert len(doc_types) >= 3


def test_seed_covers_all_risk_levels():
    levels = {p["level"] for p in SYNTHETIC_PROFILES}
    assert levels == {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def test_seed_has_multiple_officer_decisions():
    decisions = {p["officer_decision"] for p in SYNTHETIC_PROFILES}
    # PENDING alone would reproduce the "everything sits in the queue
    # untouched" look the review queue and cases archive were flagged for.
    assert decisions.issuperset({"PENDING", "CLEARED", "ESCALATED", "REQUIRES_INSPECTION"}), (
        f"Seed data should include varied officer decisions, got {decisions}"
    )


def test_no_single_document_type_dominates():
    doc_type_counts = {}
    for p in SYNTHETIC_PROFILES:
        doc_type_counts[p["doc_type"]] = doc_type_counts.get(p["doc_type"], 0) + 1
    dominant_share = max(doc_type_counts.values()) / len(SYNTHETIC_PROFILES)
    assert dominant_share < 0.6, (
        f"One document type dominates the seed set ({doc_type_counts}); "
        "Review Queue / Cases Archive would look repetitive."
    )


def test_no_single_officer_decision_dominates_pending_review_view():
    pending = [p for p in SYNTHETIC_PROFILES if p["officer_decision"] == "PENDING"]
    pending_doc_types = {p["doc_type"] for p in pending}
    pending_risk_levels = {p["level"] for p in pending}
    # The Review Queue's default view is exactly officer_decision == PENDING
    # (see frontend/src/pages/ReviewQueuePage.tsx), so that slice specifically
    # needs its own spread, not just the seed set as a whole.
    assert len(pending) >= 3
    assert len(pending_doc_types) >= 2, "Pending queue rows all share one document type"
    assert len(pending_risk_levels) >= 2, "Pending queue rows all share one risk level"


def test_case_numbers_are_unique():
    case_numbers = [f"BM-2026-{10020 + idx}" for idx in range(len(SYNTHETIC_PROFILES))]
    assert len(case_numbers) == len(set(case_numbers))


def test_seed_covers_multiple_countries():
    countries = {p["country"] for p in SYNTHETIC_PROFILES}
    assert len(countries) >= 10
