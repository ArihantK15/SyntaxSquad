"""
Synthetic training-data generator for the tamper-forensics CNN
(backend/app/ml/tamper_model.py: LightweightForensicCNN).

Produces labeled 64x64 patches:
  - label 0 (authentic): patches from freshly generated, un-tampered documents.
  - label 1 (tampered):  patches containing a synthetic splice -- a rectangular
    region copy-pasted from a DIFFERENT document and re-encoded at a different
    JPEG quality before pasting, which is exactly the kind of copy-paste /
    recompression artifact ELA and edge-discontinuity heuristics are designed
    to catch. This is the standard way to build a labeled dataset for a patch
    splice-detector without any external data: the ground truth is known
    exactly because we created the splice ourselves.

Not run automatically -- this only builds the dataset in memory / on disk.
Actual training happens in scripts/train_tamper_cnn.py, which imports
`generate_dataset` from this module.
"""
import os
import sys
import random
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.utils.synthetic_generator import SyntheticDocumentGenerator

PATCH_SIZE = 64

_SURNAMES = ["KAUL", "SHARMA", "DOE", "PATEL", "KOROL", "MEHTA", "SINGH", "REYES",
             "MULLER", "IVANOV", "NAKAMURA", "OKAFOR", "GARCIA", "KIM", "ANDERSSON"]
_GIVEN = ["ARIHANT", "PRIYA", "JOHN", "ROHAN", "VIKTOR", "ANITA", "RAVI", "MARIA",
          "HANS", "ELENA", "YUKI", "CHIOMA", "CARLOS", "JIWOO", "ERIK"]
_COUNTRIES = [("UTO", "REPUBLIC OF UTOPIA"), ("DEM", "DEMO STATE"),
              ("ATL", "ATLANTIS FEDERATION"), ("NOR", "NORTHLANDIA"), ("VER", "VERITAS UNION")]


def _random_doc_kwargs() -> dict:
    code, country_name = random.choice(_COUNTRIES)
    return {
        "surname": random.choice(_SURNAMES),
        "given_names": random.choice(_GIVEN),
        "country_code": code,
        "country_name": country_name,
        "doc_number": f"{random.choice('ABDPX')}{random.randint(1000000, 9999999)}",
        "dob_yymmdd": f"{random.randint(60,99)}{random.randint(1,12):02d}{random.randint(1,28):02d}",
        "expiry_yymmdd": f"{random.randint(26,35)}{random.randint(1,12):02d}{random.randint(1,28):02d}",
    }


def _generate_genuine_doc(tmp_dir: str) -> np.ndarray:
    """Generates one genuine synthetic document and returns it as a BGR array."""
    out_path = os.path.join(tmp_dir, f"doc_{random.randint(0, 1_000_000)}.jpg")
    SyntheticDocumentGenerator.generate_document(out_path=out_path, mode="genuine", **_random_doc_kwargs())
    img = cv2.imread(out_path)
    os.remove(out_path)
    return img


def _splice(base: np.ndarray, donor: np.ndarray, tmp_dir: str) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
    """
    Pastes a random rectangular region from `donor` onto `base`, after
    re-encoding the donor patch at a different JPEG quality (simulating a
    realistic copy-paste forgery's recompression artifact). Returns the
    modified image and the (x, y, w, h) region that was spliced.
    """
    h, w = base.shape[:2]
    pw, ph = random.randint(80, 180), random.randint(60, 140)
    x = random.randint(0, max(1, w - pw))
    y = random.randint(0, max(1, h - ph))

    dh, dw = donor.shape[:2]
    dx = random.randint(0, max(1, dw - pw))
    dy = random.randint(0, max(1, dh - ph))
    donor_patch = donor[dy:dy + ph, dx:dx + pw]
    if donor_patch.size == 0:
        return base, (0, 0, 0, 0)

    # Re-encode at a different quality to introduce a genuine recompression
    # mismatch, then decode back -- this is what makes ELA/CNN splice cues real.
    tmp_path = os.path.join(tmp_dir, f"patch_{random.randint(0, 1_000_000)}.jpg")
    cv2.imwrite(tmp_path, donor_patch, [cv2.IMWRITE_JPEG_QUALITY, random.choice([55, 65, 97])])
    reencoded = cv2.imread(tmp_path)
    os.remove(tmp_path)
    if reencoded is None or reencoded.shape[:2] != (ph, pw):
        reencoded = cv2.resize(donor_patch, (pw, ph)) if reencoded is None else cv2.resize(reencoded, (pw, ph))

    spliced = base.copy()
    spliced[y:y + ph, x:x + pw] = reencoded
    return spliced, (x, y, pw, ph)


def _random_patch(img: np.ndarray, region: Tuple[int, int, int, int] = None) -> np.ndarray:
    """Extracts a PATCH_SIZE x PATCH_SIZE patch, either from a given (x,y,w,h)
    region (jittered within it) or from a random location in the image."""
    h, w = img.shape[:2]
    if region is not None:
        x, y, rw, rh = region
        cx = x + random.randint(0, max(1, rw - 1))
        cy = y + random.randint(0, max(1, rh - 1))
    else:
        cx = random.randint(0, max(1, w - 1))
        cy = random.randint(0, max(1, h - 1))

    x1 = max(0, min(w - PATCH_SIZE, cx - PATCH_SIZE // 2))
    y1 = max(0, min(h - PATCH_SIZE, cy - PATCH_SIZE // 2))
    patch = img[y1:y1 + PATCH_SIZE, x1:x1 + PATCH_SIZE]
    if patch.shape[:2] != (PATCH_SIZE, PATCH_SIZE):
        patch = cv2.resize(patch, (PATCH_SIZE, PATCH_SIZE))
    return cv2.cvtColor(patch, cv2.COLOR_BGR2RGB)


def generate_dataset(n_docs: int = 60, patches_per_doc: int = 6, seed: int = 42) -> Tuple[np.ndarray, np.ndarray]:
    """
    Builds a labeled patch dataset.

    Returns (patches, labels):
      patches: uint8 array, shape (N, 64, 64, 3), RGB.
      labels:  int64 array, shape (N,), 0=authentic, 1=tampered.
    """
    random.seed(seed)
    np.random.seed(seed)

    patches: List[np.ndarray] = []
    labels: List[int] = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        docs = [_generate_genuine_doc(tmp_dir) for _ in range(n_docs)]

        # Authentic patches: random locations across genuine documents.
        for doc in docs:
            for _ in range(patches_per_doc):
                patches.append(_random_patch(doc))
                labels.append(0)

        # Tampered patches: splice a donor region into a base doc, then sample
        # patches from inside the spliced region (label 1) and a few from
        # elsewhere in the same modified doc, which remain genuinely authentic
        # (label 0) -- this teaches the model the difference is localized, not
        # "this whole document is suspicious".
        for i, base in enumerate(docs):
            donor = docs[(i + 1) % len(docs)]
            spliced_img, region = _splice(base, donor, tmp_dir)
            if region == (0, 0, 0, 0):
                continue
            for _ in range(patches_per_doc):
                patches.append(_random_patch(spliced_img, region))
                labels.append(1)
            for _ in range(patches_per_doc // 2):
                # Sample away from the splice region for the "elsewhere" negatives.
                h, w = spliced_img.shape[:2]
                rx, ry = random.randint(0, w - 1), random.randint(0, h - 1)
                rx1, ry1, rw, rh = region
                if rx1 <= rx <= rx1 + rw and ry1 <= ry <= ry1 + rh:
                    continue
                patches.append(_random_patch(spliced_img))
                labels.append(0)

    return np.stack(patches).astype(np.uint8), np.array(labels, dtype=np.int64)


def _patch_centered_at(img: np.ndarray, cx: int, cy: int) -> np.ndarray:
    """Extracts a PATCH_SIZE x PATCH_SIZE RGB patch centered at (cx, cy), clamped to bounds."""
    h, w = img.shape[:2]
    x1 = max(0, min(w - PATCH_SIZE, cx - PATCH_SIZE // 2))
    y1 = max(0, min(h - PATCH_SIZE, cy - PATCH_SIZE // 2))
    patch = img[y1:y1 + PATCH_SIZE, x1:x1 + PATCH_SIZE]
    if patch.shape[:2] != (PATCH_SIZE, PATCH_SIZE):
        patch = cv2.resize(patch, (PATCH_SIZE, PATCH_SIZE))
    return cv2.cvtColor(patch, cv2.COLOR_BGR2RGB)


def load_casia_patches(
    casia_root: str,
    n_authentic: Optional[int] = None,
    n_tampered: Optional[int] = None,
    patches_per_image: int = 2,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Samples labeled 64x64 patches from the CASIA v2.0 image tampering
    detection dataset (real photographs, real human-made splices -- not
    documents, but a far richer and less predictable splice signature than
    our own synthetic generator's plain rectangular copy-paste). Get it via:

        kaggle datasets download -d divg07/casia-20-image-tampering-detection-dataset -p <dir> --unzip

    Expects the standard CASIA2 layout under `casia_root`:
        Au/                       authentic photos
        Tp/                       tampered photos
        CASIA 2 Groundtruth/      per-tampered-image binary masks, named
                                   "<tp_filename_without_ext>_gt.png"

    Authentic patches are random crops from Au/ images. Tampered patches are
    centered on actual masked (truly-spliced) pixels -- sampled directly from
    the mask's nonzero coordinates rather than its bounding box, since CASIA
    masks are often irregular shapes where the bounding box contains plenty
    of untouched background; centering on the box instead of the mask itself
    would mislabel clean patches as tampered. n_authentic/n_tampered default
    to None, meaning use every available image (the model is tiny -- a few
    tens of thousands of parameters -- so wall-clock time is dominated by
    image I/O, not training compute; there's no accuracy reason to subsample
    a real, labeled dataset). A handful of files in this dataset are known to
    be corrupt/truncated; those are skipped rather than failing the whole run.
    """
    random.seed(seed)
    np.random.seed(seed)

    root = Path(casia_root)
    au_dir, tp_dir, gt_dir = root / "Au", root / "Tp", root / "CASIA 2 Groundtruth"

    au_files = [f for f in au_dir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".bmp")]
    tp_files = [f for f in tp_dir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".tif", ".tiff")]
    random.shuffle(au_files)
    random.shuffle(tp_files)
    if n_authentic is not None:
        au_files = au_files[:n_authentic]
    if n_tampered is not None:
        tp_files = tp_files[:n_tampered]

    patches: List[np.ndarray] = []
    labels: List[int] = []

    for f in au_files:
        img = cv2.imread(str(f))
        if img is None or img.shape[0] < PATCH_SIZE or img.shape[1] < PATCH_SIZE:
            continue
        for _ in range(patches_per_image):
            patches.append(_random_patch(img))
            labels.append(0)

    for f in tp_files:
        gt_path = gt_dir / f"{f.stem}_gt.png"
        if not gt_path.exists():
            continue
        img = cv2.imread(str(f))
        mask = cv2.imread(str(gt_path), cv2.IMREAD_GRAYSCALE)
        if img is None or mask is None or img.shape[0] < PATCH_SIZE or img.shape[1] < PATCH_SIZE:
            continue
        ys, xs = np.nonzero(mask > 10)
        if len(xs) == 0:
            continue
        # Sample patch centers directly from true mask pixels, jittering the
        # index (not the pixel coordinate) so we still cover the mask's
        # extent rather than always the same spot.
        idxs = np.random.choice(len(xs), size=patches_per_image, replace=True)
        for idx in idxs:
            patches.append(_patch_centered_at(img, int(xs[idx]), int(ys[idx])))
            labels.append(1)

    return np.stack(patches).astype(np.uint8), np.array(labels, dtype=np.int64)


if __name__ == "__main__":
    p, l = generate_dataset()
    print(f"Generated {len(p)} patches: {int((l == 0).sum())} authentic, {int((l == 1).sum())} tampered")
    print(f"Patch shape: {p.shape[1:]}, dtype: {p.dtype}")
