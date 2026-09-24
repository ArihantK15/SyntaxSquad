from typing import Dict, Any, List, Optional
import numpy as np
from sqlalchemy.orm import Session

from app.models import FaceEmbeddingGallery
from app.ml.face_verifier import FaceDetectorAndVerifier
from app.core.encryption import encrypt_embedding, decrypt_embedding

# Stricter than the 0.72 same-session 1:1 MATCH_THRESHOLD (face_service.py).
# A 1:N gallery search's false-accept risk compounds across every entry
# checked -- at 0.72, LFW-measured FAR is 0.60% PER comparison, so expected
# false hits grow roughly linearly with gallery size (N * FAR). Re-measuring
# FAR at stricter thresholds against the same LFW impostor pairs
# calibrate_face_threshold.py uses: 0.00% observed at 0.80 (no false accepts
# in 500 impostor pairs -- the resolution floor of that test set, i.e.
# <=0.2%, not a proven zero). 0.80 is what keeps this usable as the gallery
# grows without accusing an innocent traveler of running a false identity.
GALLERY_MATCH_THRESHOLD = 0.80


class IdentityGalleryService:
    """
    Cross-case duplicate-identity detection: maintains a gallery of past
    screenings' LIVE face embeddings and does a 1:N similarity search
    against it on each new screening. Deliberately DB-only, no ML model
    loading of its own -- callers (screening.py, demo.py) already have the
    embedding from face_service.py's own model instance.
    """

    @staticmethod
    def find_gallery_match(
        db: Session,
        embedding: List[float],
        exclude_case_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Brute-force 1:N cosine-similarity search against every OTHER case's
        stored live-face embedding. Brute force is deliberate, not a
        shortcut -- at this app's scale (a demo/hackathon-sized case
        volume) an ANN index (FAISS etc.) is premature complexity with no
        measurable benefit; this is O(N) over a gallery that will
        realistically never reach a size where that matters.

        Returns the single BEST match at or above GALLERY_MATCH_THRESHOLD,
        or None. Excludes exclude_case_id so a case never matches its own
        just-stored embedding (the manual screening flow's /risk step can
        legitimately be re-run for the same case).
        """
        query = np.array(embedding, dtype=np.float64)

        best: Optional[Dict[str, Any]] = None
        entries = db.query(FaceEmbeddingGallery).filter(
            FaceEmbeddingGallery.case_id != exclude_case_id
        ).all()
        for entry in entries:
            candidate = np.array(decrypt_embedding(entry.embedding), dtype=np.float64)
            similarity = FaceDetectorAndVerifier.compare_faces(query, candidate)
            if similarity >= GALLERY_MATCH_THRESHOLD and (best is None or similarity > best["similarity"]):
                best = {
                    "case_id": entry.case_id,
                    "case_number": entry.case_number,
                    "full_name": entry.full_name,
                    "similarity": round(similarity, 3)
                }
        return best

    @staticmethod
    def store_gallery_embedding(
        db: Session,
        case_id: str,
        case_number: str,
        full_name: Optional[str],
        document_number_hash: Optional[str],
        embedding: List[float]
    ) -> None:
        """
        Replaces any existing gallery entry for this case rather than
        inserting a second row -- the manual screening flow's /risk step
        can legitimately be re-run for the same case, and a stale second
        embedding would otherwise sit in the gallery matching against
        every future screening indefinitely. Does not commit -- callers
        share a single request-scoped transaction with the rest of the
        risk step.
        """
        db.query(FaceEmbeddingGallery).filter(FaceEmbeddingGallery.case_id == case_id).delete()
        db.add(FaceEmbeddingGallery(
            case_id=case_id,
            case_number=case_number,
            full_name=full_name,
            document_number_hash=document_number_hash,
            embedding=encrypt_embedding(embedding)
        ))


def get_identity_gallery_service() -> IdentityGalleryService:
    return IdentityGalleryService()
