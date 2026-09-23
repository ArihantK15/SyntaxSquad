"""
Fine-tune the project's InceptionResnetV1 (VGGFace2-pretrained) face embedder
on FG-NET + CALFW combined, for better cross-age (incl. child->adult) matching.

This supersedes the FG-NET+YLFW combined run in scripts/finetune_face_embedder.py
for one practical reason: YLFW-Dev-Train-Balanced is still gated behind a
license agreement that hasn't been obtained (see that script's own docstring
and SESSION_SUMMARY.md section 2/5). CALFW (Cross-Age LFW,
huggingface.co/datasets/marcelohaps/calfw) is a real, freely-downloadable,
purpose-built cross-age face-verification dataset -- exactly the kind of
same-identity-different-age diversity FG-NET alone lacked, which is what
caused the earlier FG-NET-only fine-tune's LFW same-age false-accept rate to
regress from 0.60% to 10.20% (see finetune_face_embedder.py's module
docstring and SESSION_SUMMARY.md section 3c/4).

Approach: IDENTICAL to finetune_face_embedder.py -- freeze all early conv
blocks, unfreeze only the last Inception block (block8) + last_linear +
last_bn (the embedding head). Train with a classification head (identity as
class) using cross-entropy, then discard the head and keep the fine-tuned
embedding backbone.

IMPORTANT -- merged, not sequential: FG-NET and CALFW identities are combined
into ONE label space and trained in a SINGLE pass over ONE DataLoader, not
two separate fit() calls. See finetune_face_embedder.py's module docstring
for why (catastrophic forgetting on the second pass otherwise).

Get the data first:
    .venv-train/Scripts/python.exe -c "
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id='marcelohaps/calfw', repo_type='dataset',
                       allow_patterns=['aligned/images/**', 'aligned/metadata.csv'],
                       local_dir='data/CALFW')
    "

Run with (.venv-train, GPU):
    .venv-train/Scripts/python.exe scripts/finetune_face_embedder_calfw.py

Inputs:
    data/FGNET/images/                 -- already extracted (1,002 images, 82 identities)
    data/CALFW/aligned/images/**        -- CALFW's aligned (already face-cropped, 224x224)
    data/CALFW/aligned/metadata.csv     -- identity label per image

Output:
    backend/app/ml/weights/face_embedder_finetuned_fgnet_calfw.pth (state_dict)
    -- deliberately NOT named face_embedder_finetuned.pth (the filename
    face_verifier.py auto-loads): this is a CANDIDATE checkpoint. Per the
    project's own policy after the FG-NET-only regression, a candidate must
    first pass scripts/evaluate_lfw_same_age.py's same-age regression check
    (>=95% accuracy) BEFORE being renamed/copied to the auto-loaded filename.
"""
import csv
import os
import random
import re
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
CALFW_ALIGNED_DIR = PROJECT_ROOT / "data" / "CALFW" / "aligned"
CALFW_METADATA_CSV = CALFW_ALIGNED_DIR / "metadata.csv"

CROP_CACHE_DIR = PROJECT_ROOT / "data" / ".face_crop_cache"
WEIGHTS_PATH = PROJECT_ROOT / "backend" / "app" / "ml" / "weights" / "face_embedder_finetuned_fgnet_calfw.pth"

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
EMBED_SIZE = (160, 160)
EPOCHS = 10
BATCH_SIZE = 32
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


def build_calfw_samples():
    """
    CALFW's aligned/images are already face-detected-and-aligned (224x224,
    one consistent crop convention) -- unlike FG-NET's raw photos, no MTCNN
    detection pass is needed here, just a resize to the embedder's input
    size. Identity comes straight from aligned/metadata.csv rather than
    re-parsing it out of filenames.
    """
    if not CALFW_METADATA_CSV.exists():
        print(f"WARNING: {CALFW_METADATA_CSV} not found -- skipping CALFW. "
              f"See this script's module docstring for the download command.")
        return []

    cache_dir = CROP_CACHE_DIR / "calfw"
    cache_dir.mkdir(parents=True, exist_ok=True)

    with open(CALFW_METADATA_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"CALFW: found {len(rows)} labeled images in metadata.csv")

    samples = []
    for i, row in enumerate(rows):
        rel_path = row["file_name"]  # e.g. "images/000/AJ_Cook_0001.jpg"
        identity = row["identity"]
        src_path = CALFW_ALIGNED_DIR / rel_path
        cache_path = cache_dir / (rel_path.replace("/", "__") + ".npy")
        if not cache_path.exists():
            img_bgr = cv2.imread(str(src_path))
            if img_bgr is None:
                continue
            rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            crop = cv2.resize(rgb, EMBED_SIZE)
            np.save(cache_path, crop)
        samples.append((str(cache_path), f"CALFW:{identity}"))
        if (i + 1) % 2000 == 0:
            print(f"  CALFW: processed {i + 1}/{len(rows)}")

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
    calfw_samples = build_calfw_samples()

    # Merge FIRST, into one identity-labeled pool -- see module docstring for
    # why this must be a single combined training set, not two sequential
    # fine-tuning passes.
    samples = fgnet_samples + calfw_samples
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
    n_calfw_ids = sum(1 for i in identities if i.startswith("CALFW:"))
    total_images = sum(len(v) for v in by_identity.values())
    print(f"\nCombined: {len(identities)} identities ({n_fgnet_ids} FG-NET, {n_calfw_ids} CALFW), "
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
                correct["calfw"] += (preds == y)[~is_fgnet].sum().item()
                total["calfw"] += int((~is_fgnet).sum().item())

        val_acc = correct["all"] / total["all"] if total["all"] else 0.0
        fgnet_acc = correct["fgnet"] / total["fgnet"] if total["fgnet"] else None
        calfw_acc = correct["calfw"] / total["calfw"] if total["calfw"] else None
        fmt = lambda a: f"{a:.3%}" if a is not None else "n/a"
        print(f"Epoch {epoch}/{EPOCHS}  train_loss={total_loss / n:.4f}  "
              f"val_acc={val_acc:.3%}  fgnet_acc={fmt(fgnet_acc)}  calfw_acc={fmt(calfw_acc)}")

        if val_acc >= best_val_acc:
            best_val_acc = val_acc
            torch.save(embedder.state_dict(), WEIGHTS_PATH)

    print(f"\nBest combined val identity-classification accuracy: {best_val_acc:.3%}")
    print(f"Saved fine-tuned embedder weights to {WEIGHTS_PATH}")
    print("\nThis is a CANDIDATE checkpoint, NOT yet wired into the app. Per policy "
          "(see this script's module docstring): before wiring it into "
          "backend/app/ml/face_verifier.py, run:\n"
          f"    .venv-train/Scripts/python.exe scripts/evaluate_lfw_same_age.py --weights {WEIGHTS_PATH}\n"
          "and confirm same-age accuracy does not regress below the 95% bar before "
          "renaming/copying it to backend/app/ml/weights/face_embedder_finetuned.pth "
          "(the filename face_verifier.py auto-loads) and re-running "
          "scripts/calibrate_face_threshold.py to recalibrate MATCH_THRESHOLD.")


if __name__ == "__main__":
    main()
