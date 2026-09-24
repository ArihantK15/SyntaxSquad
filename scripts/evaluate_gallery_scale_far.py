"""
1:N false-accept-rate check for the cross-case duplicate-identity gallery's
GALLERY_MATCH_THRESHOLD (backend/app/services/identity_gallery_service.py).

That threshold (0.80) was chosen from scripts/calibrate_face_threshold.py's
1:1 LFW pairs benchmark: 0.00% false-accept rate across 500 impostor PAIRS.
identity_gallery_service.py's own comment already flags the gap this script
closes -- a 1:N gallery search's false-accept risk compounds across every
entry in the gallery, which a 1:1 pairs benchmark cannot measure, and 0.00%
on 500 pairs is "not a proven zero," only the resolution floor of that test
(<=0.2%).

This script builds an actual 1,000+ identity gallery from LFW (distinct real
people, one embedding each), then runs it as this project's real
IdentityGalleryService.find_gallery_match / FaceDetectorAndVerifier.compare_faces
math would: MAX similarity across the whole gallery per probe, not per-pair.

Three probe sets:
  1. Impostor probes -- real people who are NOT in the gallery at all. The
     fraction whose max similarity against the gallery clears the threshold
     IS the real 1:N false-accept rate this script exists to measure.
  2. Genuine-duplicate probes -- a second, different photo of someone WHO IS
     in the gallery. Confirms the threshold still recognizes a real repeat
     screening once there are 1,000+ other candidates for that comparison to
     get lost among (i.e. adjusting the threshold upward to fix (1), if
     needed, doesn't quietly break the exact case this gallery exists for).
  3. Genuine-duplicate identity-confusion check -- for each genuine-duplicate
     probe, confirms the single best match returned is the CORRECT gallery
     identity, not some other person who happened to score even higher (a
     worse failure mode than a plain miss: it would misattribute a real
     repeat screening to the wrong prior case).

Run with:
    .venv-train/Scripts/python.exe scripts/evaluate_gallery_scale_far.py
"""
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from sklearn.datasets import fetch_lfw_people
from app.ml.face_verifier import FaceDetectorAndVerifier

# Mirrors IdentityGalleryService.GALLERY_MATCH_THRESHOLD (identity_gallery_service.py)
# -- not imported directly since that module pulls in app.core.config, which needs
# pydantic_settings (a backend-only dependency not installed in .venv-train), the
# same reason scripts/evaluate_lfw_same_age.py hardcodes its own threshold mirror.
GALLERY_MATCH_THRESHOLD = 0.80

GALLERY_SIZE = 1200
N_IMPOSTOR_PROBES = 500
N_DUPLICATE_PROBES = 30


def _embed_fn(det: FaceDetectorAndVerifier):
    # LFW images are small (125x94) headshots -- if MTCNN can't find a face at
    # that resolution, fall back to treating the whole (already-cropped) frame
    # as the face, same convention as calibrate_face_threshold.py /
    # evaluate_lfw_same_age.py use for this exact dataset.
    fallback = (0.05, 0.05, 0.90, 0.90)

    def embed(img_rgb: np.ndarray):
        # fetch_lfw_people (unlike fetch_lfw_pairs) returns float32 images
        # already scaled to [0, 1], not [0, 255] -- an unscaled cast to
        # uint8 truncates every pixel to 0 (all-black), which silently
        # produces one fixed, identical embedding for every input instead
        # of a shape/dtype error. Scale explicitly, matching the *255 cast
        # calibrate_face_threshold.py/evaluate_lfw_same_age.py apply to
        # fetch_lfw_pairs' own [0, 1] images.
        img_bgr = (img_rgb[:, :, ::-1] * 255).astype(np.uint8)
        boxes = det.detect_face(img_bgr, fallback_rect=fallback)
        if not boxes:
            return None
        x, y, w, h = boxes[0]
        crop = img_bgr[y:y + h, x:x + w]
        if crop.size == 0:
            return None
        return det.extract_embedding(crop)

    return embed


def main():
    print("Loading LFW people (min_faces_per_person=1)...")
    t0 = time.time()
    data = fetch_lfw_people(min_faces_per_person=1, resize=1.0, color=True)
    print(f"Loaded in {time.time() - t0:.1f}s -- {len(data.images)} images, "
          f"{len(data.target_names)} distinct identities")

    # Group image indices by identity so gallery/impostor/duplicate-probe
    # identity sets can be built disjoint from each other on purpose.
    images_by_identity = defaultdict(list)
    for idx, person_id in enumerate(data.target):
        images_by_identity[person_id].append(idx)

    all_person_ids = list(images_by_identity.keys())
    rng = np.random.default_rng(42)
    rng.shuffle(all_person_ids)

    det = FaceDetectorAndVerifier()
    embed = _embed_fn(det)

    # --- Build the gallery: one embedding (first photo) per distinct identity ---
    print(f"\nBuilding a {GALLERY_SIZE}-identity gallery...")
    t0 = time.time()
    gallery_vecs = []
    gallery_names = []
    gallery_person_ids = set()
    person_id_cursor = 0
    while len(gallery_vecs) < GALLERY_SIZE and person_id_cursor < len(all_person_ids):
        pid = all_person_ids[person_id_cursor]
        person_id_cursor += 1
        img_idx = images_by_identity[pid][0]
        vec = embed(data.images[img_idx])
        if vec is None:
            continue
        gallery_vecs.append(vec)
        gallery_names.append(data.target_names[pid])
        gallery_person_ids.add(pid)
    gallery_matrix = np.array(gallery_vecs, dtype=np.float64)
    gallery_norms = np.linalg.norm(gallery_matrix, axis=1)
    print(f"Gallery built: {len(gallery_vecs)} entries in {time.time() - t0:.1f}s")

    def max_similarity_against_gallery(probe_vec: np.ndarray):
        """
        Same per-pair formula as FaceDetectorAndVerifier.compare_faces
        ((cos_sim + 1) / 2), vectorized across the whole gallery matrix at
        once -- this IS the 1:N search find_gallery_match performs (best
        match across every OTHER case's stored embedding), just batched for
        speed instead of looped.
        """
        probe_norm = np.linalg.norm(probe_vec)
        if probe_norm == 0:
            return 0.0, -1
        cos_sims = (gallery_matrix @ probe_vec) / (gallery_norms * probe_norm)
        similarities = np.clip((cos_sims + 1.0) / 2.0, 0.0, 1.0)
        best_idx = int(np.argmax(similarities))
        return float(similarities[best_idx]), best_idx

    # --- Impostor probes: real people who are NOT in the gallery at all ---
    print(f"\nRunning {N_IMPOSTOR_PROBES} impostor probes (identities absent from the gallery)...")
    t0 = time.time()
    impostor_max_sims = []
    probes_run = 0
    while probes_run < N_IMPOSTOR_PROBES and person_id_cursor < len(all_person_ids):
        pid = all_person_ids[person_id_cursor]
        person_id_cursor += 1
        if pid in gallery_person_ids:
            continue  # shouldn't happen given the disjoint cursor, guarded anyway
        img_idx = images_by_identity[pid][0]
        vec = embed(data.images[img_idx])
        if vec is None:
            continue
        max_sim, _ = max_similarity_against_gallery(np.array(vec, dtype=np.float64))
        impostor_max_sims.append(max_sim)
        probes_run += 1
    impostor_max_sims = np.array(impostor_max_sims)
    print(f"Ran {len(impostor_max_sims)} impostor probes in {time.time() - t0:.1f}s")

    false_accepts = int((impostor_max_sims >= GALLERY_MATCH_THRESHOLD).sum())
    far_1n = false_accepts / len(impostor_max_sims)
    print(f"\n=== 1:N False-Accept Rate at threshold {GALLERY_MATCH_THRESHOLD:.2f} ===")
    print(f"Gallery size: {len(gallery_vecs)}")
    print(f"Impostor probes: {len(impostor_max_sims)}")
    print(f"False accepts (max similarity >= threshold): {false_accepts}")
    print(f"Empirical 1:N FAR: {far_1n:.3%}")
    print(f"Impostor max-similarity distribution: mean={impostor_max_sims.mean():.3f} "
          f"std={impostor_max_sims.std():.3f} max={impostor_max_sims.max():.3f} "
          f"p99={np.percentile(impostor_max_sims, 99):.3f}")

    # --- Genuine-duplicate probes: a second photo of someone already in the gallery ---
    dup_candidates = [pid for pid in gallery_person_ids if len(images_by_identity[pid]) >= 2]
    n_dup = min(N_DUPLICATE_PROBES, len(dup_candidates))
    print(f"\nRunning {n_dup} genuine-duplicate probes "
          f"(second photo of someone already in the gallery)...")
    t0 = time.time()
    dup_sims = []
    dup_correct_identity = 0
    for pid in dup_candidates[:n_dup]:
        second_img_idx = images_by_identity[pid][1]
        vec = embed(data.images[second_img_idx])
        if vec is None:
            continue
        best_sim, best_idx = max_similarity_against_gallery(np.array(vec, dtype=np.float64))
        dup_sims.append(best_sim)
        if gallery_names[best_idx] == data.target_names[pid]:
            dup_correct_identity += 1
    dup_sims = np.array(dup_sims)
    print(f"Ran {len(dup_sims)} genuine-duplicate probes in {time.time() - t0:.1f}s")

    dup_recall = (dup_sims >= GALLERY_MATCH_THRESHOLD).mean() if len(dup_sims) else float("nan")
    print(f"\n=== Genuine-Duplicate Recall at threshold {GALLERY_MATCH_THRESHOLD:.2f} ===")
    print(f"Genuine-duplicate probes: {len(dup_sims)}")
    print(f"Correctly flagged as a match (best sim >= threshold): "
          f"{int((dup_sims >= GALLERY_MATCH_THRESHOLD).sum())} ({dup_recall:.3%})")
    print(f"Correctly attributed to the RIGHT prior identity "
          f"(not a different, higher-scoring false lead): "
          f"{dup_correct_identity}/{len(dup_sims)}")
    print(f"Genuine-duplicate similarity distribution: mean={dup_sims.mean():.3f} "
          f"std={dup_sims.std():.3f} min={dup_sims.min():.3f}")

    # --- What a higher threshold would cost, if 0.80 doesn't hold ---
    print("\n=== Threshold sensitivity (for reference, if 0.80 needs raising) ===")
    for t in (0.80, 0.82, 0.85, 0.88, 0.90):
        far_t = (impostor_max_sims >= t).mean()
        frr_t = (dup_sims < t).mean() if len(dup_sims) else float("nan")
        print(f"  threshold={t:.2f}  1:N FAR={far_t:.3%}  duplicate false-reject rate={frr_t:.3%}")


if __name__ == "__main__":
    main()
