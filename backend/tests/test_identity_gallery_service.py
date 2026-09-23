import uuid
import numpy as np
import pytest

from app.core.database import Base, SessionLocal, engine
from app.models import Case, FaceEmbeddingGallery
from app.services.identity_gallery_service import (
    IdentityGalleryService,
    GALLERY_MATCH_THRESHOLD,
)

# Other test modules (test_api.py) create tables via the app's lifespan,
# entered through TestClient as a context manager -- this module talks to
# the DB directly via SessionLocal with no app/lifespan involved, so the
# new face_embedding_gallery table needs creating explicitly. Idempotent:
# create_all only creates tables that don't already exist.
Base.metadata.create_all(bind=engine)


def _make_unit_embedding() -> list:
    """
    A fresh, unseeded L2-normalized 512-d vector -- realistic enough shape
    for compare_faces' cosine-similarity math without needing a real face.

    Deliberately NOT seeded to a fixed integer: this test module talks to
    the real persistent dev DB (see the create_all note above, matching
    this codebase's existing test convention of not mocking the database),
    which accumulates FaceEmbeddingGallery rows across every past test run
    rather than resetting between runs. A fixed seed would regenerate the
    exact same vector on every run, colliding with a leftover row from a
    PRIOR run and matching the wrong case_id -- observed live when this
    was seeded. A fresh random vector each call makes cross-run collision
    astronomically unlikely without needing any cleanup.
    """
    v = np.random.default_rng().normal(size=512)
    v = v / np.linalg.norm(v)
    return v.tolist()


def _mix_toward(embedding: list, weight: float) -> list:
    """
    Blends `embedding` with a different random unit vector, weighted mostly
    toward `embedding` (e.g. weight=0.80 keeps ~98.5% cosine similarity to
    the original -- empirically checked, not guessed) -- stands in for two
    different-but-close live captures of the same real person, distinct
    from an exact duplicate of the same stored vector.
    """
    base = np.array(embedding)
    other = np.array(_make_unit_embedding())
    v = weight * base + (1 - weight) * other
    v = v / np.linalg.norm(v)
    return v.tolist()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _create_case(db, case_number: str) -> str:
    case = Case(case_number=case_number, status="LOW_RISK", risk_level="LOW", risk_score=5.0)
    db.add(case)
    db.commit()
    db.refresh(case)
    return case.id


def test_find_gallery_match_returns_none_when_gallery_is_empty(db):
    case_id = _create_case(db, f"BM-2026-TEST{uuid.uuid4().hex[:5]}")
    result = IdentityGalleryService.find_gallery_match(
        db, embedding=_make_unit_embedding(), exclude_case_id=case_id
    )
    assert result is None


def test_find_gallery_match_finds_a_match_above_threshold(db):
    prior_case_id = _create_case(db, f"BM-2026-PRIOR{uuid.uuid4().hex[:4]}")
    base_embedding = _make_unit_embedding()
    IdentityGalleryService.store_gallery_embedding(
        db, case_id=prior_case_id, case_number="BM-2026-PRIOR",
        full_name="RAJESH VERMA", document_number_hash="deadbeef",
        embedding=base_embedding
    )
    db.commit()

    current_case_id = _create_case(db, f"BM-2026-CURR{uuid.uuid4().hex[:5]}")
    # Same underlying vector (same real person's live capture) -- similarity ~1.0.
    result = IdentityGalleryService.find_gallery_match(
        db, embedding=base_embedding, exclude_case_id=current_case_id
    )
    assert result is not None
    assert result["case_id"] == prior_case_id
    assert result["full_name"] == "RAJESH VERMA"
    assert result["similarity"] >= GALLERY_MATCH_THRESHOLD


def test_find_gallery_match_ignores_matches_below_threshold(db):
    prior_case_id = _create_case(db, f"BM-2026-PRIOR{uuid.uuid4().hex[:4]}")
    IdentityGalleryService.store_gallery_embedding(
        db, case_id=prior_case_id, case_number="BM-2026-PRIOR2",
        full_name="A PERSON", document_number_hash="abc123",
        embedding=_make_unit_embedding()
    )
    db.commit()

    current_case_id = _create_case(db, f"BM-2026-CURR{uuid.uuid4().hex[:5]}")
    # An unrelated random vector -- essentially orthogonal, similarity ~0.5
    # under the (cos+1)/2 mapping, well below the gallery threshold.
    result = IdentityGalleryService.find_gallery_match(
        db, embedding=_make_unit_embedding(), exclude_case_id=current_case_id
    )
    assert result is None


def test_find_gallery_match_excludes_the_given_case_id(db):
    """A case must never match its own just-stored embedding."""
    case_id = _create_case(db, f"BM-2026-SELF{uuid.uuid4().hex[:5]}")
    embedding = _make_unit_embedding()
    IdentityGalleryService.store_gallery_embedding(
        db, case_id=case_id, case_number="BM-2026-SELF",
        full_name="SOLO PERSON", document_number_hash="cafef00d",
        embedding=embedding
    )
    db.commit()

    result = IdentityGalleryService.find_gallery_match(
        db, embedding=embedding, exclude_case_id=case_id
    )
    assert result is None


def test_find_gallery_match_returns_the_best_match_when_multiple_exceed_threshold(db):
    base_embedding = _make_unit_embedding()
    close_case_id = _create_case(db, f"BM-2026-CLOSE{uuid.uuid4().hex[:4]}")
    IdentityGalleryService.store_gallery_embedding(
        db, case_id=close_case_id, case_number="BM-2026-CLOSE",
        full_name="CLOSE MATCH", document_number_hash="1111",
        embedding=_mix_toward(base_embedding, weight=0.80)
    )
    exact_case_id = _create_case(db, f"BM-2026-EXACT{uuid.uuid4().hex[:4]}")
    IdentityGalleryService.store_gallery_embedding(
        db, case_id=exact_case_id, case_number="BM-2026-EXACT",
        full_name="EXACT MATCH", document_number_hash="2222",
        embedding=base_embedding
    )
    db.commit()

    current_case_id = _create_case(db, f"BM-2026-CURR{uuid.uuid4().hex[:5]}")
    result = IdentityGalleryService.find_gallery_match(
        db, embedding=base_embedding, exclude_case_id=current_case_id
    )
    assert result["case_id"] == exact_case_id


def test_store_gallery_embedding_replaces_any_existing_entry_for_the_same_case(db):
    """The risk step can legitimately be re-run for the same case (e.g. the
    manual screening flow's separate per-step endpoints) -- storing again
    must replace, not duplicate."""
    case_id = _create_case(db, f"BM-2026-DUP{uuid.uuid4().hex[:5]}")
    IdentityGalleryService.store_gallery_embedding(
        db, case_id=case_id, case_number="BM-2026-DUP",
        full_name="FIRST NAME", document_number_hash="aaa",
        embedding=_make_unit_embedding()
    )
    db.commit()
    IdentityGalleryService.store_gallery_embedding(
        db, case_id=case_id, case_number="BM-2026-DUP",
        full_name="UPDATED NAME", document_number_hash="bbb",
        embedding=_make_unit_embedding()
    )
    db.commit()

    entries = db.query(FaceEmbeddingGallery).filter(FaceEmbeddingGallery.case_id == case_id).all()
    assert len(entries) == 1
    assert entries[0].full_name == "UPDATED NAME"
