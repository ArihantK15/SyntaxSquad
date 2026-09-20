"""
Fine-tune the project's InceptionResnetV1 (VGGFace2-pretrained) face embedder
on FG-NET + YLFW-Dev-Train-Balanced combined, for better cross-age (incl.
child->adult) matching.

Approach: freeze all early conv blocks, unfreeze only the last Inception
block (block8) + last_linear + last_bn (the embedding head). Train with a
classification head (identity as class) using cross-entropy, then discard the
head and keep the fine-tuned embedding backbone. This is the standard cheap
way to adapt a metric-learning embedding to a new distribution without
needing triplet mining, and it's far less prone to overfitting on a few
thousand images than fine-tuning the whole network.

IMPORTANT -- merged, not sequential: FG-NET and YLFW identities are combined
into ONE label space and trained in a SINGLE pass over ONE DataLoader, not
two separate fit() calls (FG-NET then YLFW, or vice versa). Fine-tuning
sequentially on dataset A and then dataset B lets the second pass's gradient
updates drift the unfrozen weights away from whatever A taught it --
classic catastrophic forgetting -- since nothing in the second pass's loss
references A anymore. Interleaving both datasets' identities as classes of
the same softmax, in the same batches, forces every gradient step to stay
consistent with both distributions at once.

Run with (.venv-train, GPU):
    .venv-train/Scripts/python.exe scripts/finetune_face_embedder.py

Inputs:
    data/FGNET/images/                     -- already extracted (1,002 images, 82 identities)
    data/YLFW/Train-Balanced/<id>/*.png     -- or set YLFW_TRAIN_BALANCED_DIR env var.
        YLFW_Dev is gated behind visteam-isr-uc's license agreement (see
        github.com/visteam-isr-uc/YLFW -> JessyFrish/YLFW_Links) -- get the
        archive + password yourself, extract it, and point this script at
        the "Train-Balanced" split directory (LFW-style: one subfolder per
        identity, images inside).

Output:
    backend/app/ml/weights/face_embedder_finetuned.pth (state_dict, drop-in
    for InceptionResnetV1 -- see the loading snippet at the bottom of this
    file's module docstring... actually see README note printed at the end
    of main()).
"""
import os
import re
import random
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from facenet_pytorch import MTCNN, InceptionResnetV1

PROJECT_ROOT = Path(__file__).resolve().parent.parent

FGNET_IMAGES_DIR = PROJECT_ROOT / "data" / "FGNET" / "images"

# YLFW_Dev's internal layout isn't known ahead of time (it's password-gated,
# can't inspect it here) -- YLFW_TRAIN_BALANCED_DIR lets you point directly
# at the right folder once you've extracted the archive. Falls back to a
# search under data/YLFW for a directory that looks like the balanced train
# split.
YLFW_TRAIN_BALANCED_DIR = os.environ.get("YLFW_TRAIN_BALANCED_DIR")

CROP_CACHE_DIR = PROJECT_ROOT / "data" / ".face_crop_cache"
WEIGHTS_PATH = PROJECT_ROOT / "backend" / "app" / "ml" / "weights" / "face_embedder_finetuned.pth"

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
EMBED_SIZE = (160, 160)
EPOCHS = 10
BATCH_SIZE = 32  # doubled vs. the FG-NET-only CPU run (16) -- GPU + more data can afford it
LR = 1e-4
VAL_FRACTION = 0.15
SEED = 42
MIN_IMAGES_PER_IDENTITY = 2  # identities with fewer images than this are dropped (can't train+val split them)

random.seed(SEED)
torch.manual_seed(SEED)

FGNET_FNAME_RE = re.compile(r"^(\d{3})[Aa](\d{2})", re.IGNORECASE)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def parse_fgnet_identity(fname: str):
    m = FGNET_FNAME_RE.match(fname)
    if not m:
        return None
    return m.group(1)


def discover_ylfw_train_balanced_dir() -> Path | None:
    """Find the Train-Balanced split directory under data/YLFW/ if the caller
    didn't set YLFW_TRAIN_BALANCED_DIR explicitly. Looks for a directory
    whose name contains both "train" and "balanced" (case-insensitive) --
    the exact nesting depends on how the gated archive unpacks, which isn't
    knowable in advance."""
    if YLFW_TRAIN_BALANCED_DIR:
        p = Path(YLFW_TRAIN_BALANCED_DIR)
        return p if p.is_dir() else None

    ylfw_root = PROJECT_ROOT / "data" / "YLFW"
    if not ylfw_root.is_dir():
        return None

    for candidate in ylfw_root.rglob("*"):
        if candidate.is_dir():
            name = candidate.name.lower()
            if "train" in name and "balanced" in name:
                return candidate
    return None


def build_fgnet_samples(mtcnn: MTCNN):
    """Detect+crop the face in every FG-NET image once, cache to disk so
    re-runs skip the slow MTCNN pass. Returns list of (crop_path, identity)."""
    if not FGNET_IMAGES_DIR.is_dir():
        print(f"WARNING: {FGNET_IMAGES_DIR} not found -- skipping FG-NET.")
        return []

    cache_dir = CROP_CACHE_DIR / "fgnet"
    cache_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(f for f in os.listdir(FGNET_IMAGES_DIR) if f.upper().endswith(".JPG"))
    print(f"FG-NET: found {len(files)} images")

    samples = []
    for i, fname in enumerate(files):
        identity = parse_fgnet_identity(fname)
        if identity is None:
            continue
        cache_path = cache_dir / (fname + ".npy")
        if not cache_path.exists():
            img_bgr = cv2.imread(str(FGNET_IMAGES_DIR / fname))
            if img_bgr is None:
                continue
            rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            box, _ = mtcnn.detect(rgb)
            if box is not None and len(box) > 0:
                x1, y1, x2, y2 = [int(max(0, v)) for v in box[0]]
                crop = rgb[y1:y2, x1:x2]
            else:
                crop = rgb  # fallback: whole image (FG-NET images are mostly tight portraits)
            if crop.size == 0:
                crop = rgb
            crop = cv2.resize(crop, EMBED_SIZE)
            np.save(cache_path, crop)
        samples.append((str(cache_path), f"FGNET:{identity}"))
        if (i + 1) % 200 == 0:
            print(f"  FG-NET: processed {i + 1}/{len(files)}")

    return samples


def build_ylfw_samples(mtcnn: MTCNN):
    """LFW-style layout: one subdirectory per identity, images inside.
    Returns list of (crop_path, identity)."""
    root = discover_ylfw_train_balanced_dir()
    if root is None:
        print("WARNING: YLFW Train-Balanced directory not found (checked "
              "YLFW_TRAIN_BALANCED_DIR env var and data/YLFW/**). "
              "Training will proceed on FG-NET alone -- see the script's "
              "module docstring for how to obtain YLFW_Dev. Results won't "
              "reflect the intended combined fine-tune until this is fixed.")
        return []

    print(f"YLFW: using Train-Balanced directory {root}")
    cache_dir = CROP_CACHE_DIR / "ylfw"
    cache_dir.mkdir(parents=True, exist_ok=True)

    identity_dirs = sorted(d for d in root.iterdir() if d.is_dir())
    print(f"YLFW: found {len(identity_dirs)} identity folders")

    samples = []
    n_files = 0
    for idx, id_dir in enumerate(identity_dirs):
        identity = id_dir.name
        for fname in sorted(os.listdir(id_dir)):
            if Path(fname).suffix.lower() not in IMAGE_EXTS:
                continue
            n_files += 1
            cache_path = cache_dir / f"{identity}__{fname}.npy"
            if not cache_path.exists():
                img_bgr = cv2.imread(str(id_dir / fname))
                if img_bgr is None:
                    continue
                rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                box, _ = mtcnn.detect(rgb)
                if box is not None and len(box) > 0:
                    x1, y1, x2, y2 = [int(max(0, v)) for v in box[0]]
                    crop = rgb[y1:y2, x1:x2]
                else:
                    crop = rgb  # YLFW images are typically already tight face crops
                if crop.size == 0:
                    crop = rgb
                crop = cv2.resize(crop, EMBED_SIZE)
                np.save(cache_path, crop)
            samples.append((str(cache_path), f"YLFW:{identity}"))
        if (idx + 1) % 100 == 0:
            print(f"  YLFW: processed {idx + 1}/{len(identity_dirs)} identities ({n_files} files so far)")

    return samples


class FaceIdentityDataset(Dataset):
    def __init__(self, samples, label_map):
        self.samples = samples
        self.label_map = label_map

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, identity = self.samples[idx]
        crop = np.load(path)  # HWC RGB uint8, already 160x160
        tensor = torch.from_numpy(crop).permute(2, 0, 1).float()
        tensor = (tensor - 127.5) / 128.0  # match project's _fixed_image_standardization
        label = self.label_map[identity]
        return tensor, label


def main():
    print(f"Device: {DEVICE}" + (f" ({torch.cuda.get_device_name(0)})" if DEVICE.type == "cuda" else ""))
    if DEVICE.type != "cuda":
        print("WARNING: no CUDA device visible -- this will be slow. Run under "
              ".venv-train (pip install ... --index-url https://download.pytorch.org/whl/cu128).")

    mtcnn = MTCNN(keep_all=False, device=DEVICE, post_process=False)

    fgnet_samples = build_fgnet_samples(mtcnn)
    ylfw_samples = build_ylfw_samples(mtcnn)

    # Merge FIRST, into one identity-labeled pool -- see module docstring for
    # why this must be a single combined training set, not two sequential
    # fine-tuning passes.
    samples = fgnet_samples + ylfw_samples
    if not samples:
        print("ERROR: no training samples found from either dataset. Aborting.")
        sys.exit(1)

    by_identity = defaultdict(list)
    for s in samples:
        by_identity[s[1]].append(s)

    dropped = {ident: items for ident, items in by_identity.items() if len(items) < MIN_IMAGES_PER_IDENTITY}
    if dropped:
        print(f"Dropping {len(dropped)} identities with < {MIN_IMAGES_PER_IDENTITY} images "
              f"({sum(len(v) for v in dropped.values())} images total)")
        by_identity = {k: v for k, v in by_identity.items() if k not in dropped}

    identities = sorted(by_identity.keys())
    label_map = {ident: i for i, ident in enumerate(identities)}
    n_fgnet_ids = sum(1 for i in identities if i.startswith("FGNET:"))
    n_ylfw_ids = sum(1 for i in identities if i.startswith("YLFW:"))
    total_images = sum(len(v) for v in by_identity.values())
    print(f"\nCombined: {len(identities)} identities ({n_fgnet_ids} FG-NET, {n_ylfw_ids} YLFW), "
          f"{total_images} usable images")

    train_samples, val_samples = [], []
    for ident, items in by_identity.items():
        random.shuffle(items)
        n_val = max(1, int(len(items) * VAL_FRACTION)) if len(items) > 3 else 0
        val_samples += items[:n_val]
        train_samples += items[n_val:]

    print(f"Train: {len(train_samples)}  Val: {len(val_samples)}")

    train_ds = FaceIdentityDataset(train_samples, label_map)
    val_ds = FaceIdentityDataset(val_samples, label_map)
    pin_memory = DEVICE.type == "cuda"
    train_dl = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, pin_memory=pin_memory)
    val_dl = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, pin_memory=pin_memory)

    embedder = InceptionResnetV1(pretrained="vggface2").to(DEVICE)

    # Freeze everything except the last block + embedding head.
    unfreeze = {"block8", "last_linear", "last_bn"}
    for name, param in embedder.named_parameters():
        param.requires_grad = any(name.startswith(u) for u in unfreeze)

    classifier = nn.Linear(512, len(identities)).to(DEVICE)

    params = [p for p in embedder.parameters() if p.requires_grad] + list(classifier.parameters())
    optimizer = torch.optim.Adam(params, lr=LR)
    criterion = nn.CrossEntropyLoss()

    print(f"Trainable params: {sum(p.numel() for p in params):,}")

    best_val_acc = 0.0
    WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    for epoch in range(1, EPOCHS + 1):
        embedder.train()
        classifier.train()
        total_loss, n = 0.0, 0
        for x, y in train_dl:
            x, y = x.to(DEVICE), y.to(DEVICE)
            optimizer.zero_grad()
            emb = embedder(x)
            logits = classifier(emb)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * x.size(0)
            n += x.size(0)

        # Validation: identity classification accuracy as a proxy for "did
        # the embedding get better at separating these identities", split
        # out per-dataset since a combined figure can hide one dataset
        # regressing while the other (likely larger) dataset dominates it.
        embedder.eval()
        classifier.eval()
        correct = defaultdict(int)
        total = defaultdict(int)
        with torch.no_grad():
            for x, y in val_dl:
                x, y = x.to(DEVICE), y.to(DEVICE)
                emb = embedder(x)
                logits = classifier(emb)
                preds = logits.argmax(dim=1)
                is_fgnet = torch.tensor(
                    [identities[label].startswith("FGNET:") for label in y.cpu().tolist()],
                    device=DEVICE,
                )
                correct["all"] += (preds == y).sum().item()
                total["all"] += x.size(0)
                correct["fgnet"] += (preds == y)[is_fgnet].sum().item()
                total["fgnet"] += int(is_fgnet.sum().item())
                correct["ylfw"] += (preds == y)[~is_fgnet].sum().item()
                total["ylfw"] += int((~is_fgnet).sum().item())

        val_acc = correct["all"] / total["all"] if total["all"] else 0.0
        fgnet_acc = correct["fgnet"] / total["fgnet"] if total["fgnet"] else None
        ylfw_acc = correct["ylfw"] / total["ylfw"] if total["ylfw"] else None
        fmt = lambda a: f"{a:.3%}" if a is not None else "n/a"
        print(f"Epoch {epoch}/{EPOCHS}  train_loss={total_loss / n:.4f}  "
              f"val_acc={val_acc:.3%}  fgnet_acc={fmt(fgnet_acc)}  ylfw_acc={fmt(ylfw_acc)}")

        if val_acc >= best_val_acc:
            best_val_acc = val_acc
            torch.save(embedder.state_dict(), WEIGHTS_PATH)

    print(f"\nBest combined val identity-classification accuracy: {best_val_acc:.3%}")
    print(f"Saved fine-tuned embedder weights to {WEIGHTS_PATH}")
    print("\nNOT yet wired into the app. To use it, in backend/app/ml/face_verifier.py's "
          "FaceDetectorAndVerifier.__init__, after creating self.embedder, add:\n"
          "    import os\n"
          "    _w = os.path.join(os.path.dirname(__file__), 'weights', 'face_embedder_finetuned.pth')\n"
          "    if os.path.exists(_w):\n"
          "        self.embedder.load_state_dict(torch.load(_w, map_location=self.device))\n"
          "        self.embedder.eval()\n"
          "Then RE-RUN scripts/calibrate_face_threshold.py against the new weights -- "
          "fine-tuning shifts the embedding space, so the existing MATCH threshold in "
          "face_service.py is not guaranteed to still be correct.")


if __name__ == "__main__":
    main()
