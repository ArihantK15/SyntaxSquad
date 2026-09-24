import os
import sys
from pathlib import Path

# scripts/ lives alongside backend/, not inside it -- add the repo root the
# same way app.main does before importing scripts.seed_cases (see
# backend/app/main.py's lifespan seeding block).
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base
from app.core.encryption import decrypt_bytes
from app.models import DocumentAnalysis
from scripts.seed_cases import SYNTHETIC_PROFILES, seed_initial_cases


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


def test_seed_initial_cases_stores_document_images_encrypted_at_rest(tmp_path, monkeypatch):
    """
    seed_initial_cases writes each seeded case's specimen document straight
    to disk via SyntheticDocumentGenerator.generate_document -- the same
    generator screening.py/demo.py also call, and both of THOSE callers
    immediately run encrypt_file_in_place() on the result, since the
    generator itself has no idea encryption exists (see app.core.encryption's
    own module docstring). seed_cases.py never did: every startup-seeded
    case's document image was left as a PLAINTEXT file under UPLOAD_DIR,
    contradicting main.py's own "every file under UPLOAD_DIR is encrypted"
    comment -- and worse, the decrypt-on-read /uploads route in main.py
    would raise InvalidToken trying to Fernet-decrypt a plain JPEG, breaking
    every seeded case's document image in the UI.

    Isolated from the real UPLOAD_DIR and from the shared persistent dev DB
    other test modules intentionally reuse (see test_identity_gallery_
    service.py's own comment on that convention) -- seed_initial_cases uses
    fixed case_number values, so calling it a second time against that
    shared DB would collide on the unique constraint the first time it
    already ran there.
    """
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    os.makedirs(os.path.join(tmp_path, "documents"), exist_ok=True)

    test_engine = create_engine(
        f"sqlite:///{tmp_path}/test_seed.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    try:
        seed_initial_cases(db)
        analyses = db.query(DocumentAnalysis).all()
        assert len(analyses) == len(SYNTHETIC_PROFILES)

        for da in analyses:
            with open(da.document_image_path, "rb") as f:
                on_disk = f.read()
            # A plaintext JPEG starts with the SOI marker \xff\xd8 -- real
            # Fernet ciphertext is base64-alphabet ASCII and never does.
            assert not on_disk.startswith(b"\xff\xd8"), (
                f"{da.document_image_path} was stored as a plaintext JPEG, not encrypted"
            )
            plaintext = decrypt_bytes(on_disk)
            assert plaintext.startswith(b"\xff\xd8")
    finally:
        db.close()
