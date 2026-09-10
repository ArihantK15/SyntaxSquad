"""
Trains LightweightForensicCNN (backend/app/ml/tamper_model.py) on a splice-
detection dataset (see generate_tamper_training_data.py) and saves the
checkpoint that TamperDetectionService loads automatically at startup
(backend/app/services/tamper_service.py: WEIGHTS_PATH).

Run with:
    PYTHONPATH=backend venv/bin/python3 scripts/train_tamper_cnn.py

Takes a few minutes on CPU. Until this has been run at least once, the tamper
service safely ignores the CNN entirely and relies on its forensic heuristics
(ELA, edge discontinuity, portrait-seam, compression-mismatch) alone -- see
the `cnn_ready` gate in TamperDetectionService.__init__.

By default this trains on synthetic patches only (self-contained, no
external download). If the CASIA v2.0 dataset (real photos, real human-made
splices -- see generate_tamper_training_data.load_casia_patches for how to
get it) is present at the path in CASIA2_DIR below, its patches are blended
in too: real splice statistics generalize better than our synthetic
generator's narrow rectangular-copy-paste signature. The dataset itself is
never committed to this repo -- only the small trained checkpoint is.
"""
import os
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader, random_split

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.ml.tamper_model import LightweightForensicCNN
from generate_tamper_training_data import generate_dataset, load_casia_patches

WEIGHTS_PATH = Path(__file__).resolve().parent.parent / "backend" / "app" / "ml" / "weights" / "tamper_cnn.pth"

# Set the CASIA2_DIR env var to a local CASIA v2.0 extraction path (the
# directory containing Au/, Tp/, and "CASIA 2 Groundtruth/") to blend real
# splice data into training. Unset/absent means synthetic data only.
CASIA2_DIR = os.environ.get("CASIA2_DIR")

EPOCHS = 12
BATCH_SIZE = 32
LEARNING_RATE = 1e-3
VAL_FRACTION = 0.2


def to_tensor_dataset(patches: np.ndarray, labels: np.ndarray) -> TensorDataset:
    x = torch.from_numpy(patches).permute(0, 3, 1, 2).float() / 255.0  # N,H,W,C -> N,C,H,W
    y = torch.from_numpy(labels).long()
    return TensorDataset(x, y)


def main():
    print("Generating training data (synthetic splice patches)...")
    patches, labels = generate_dataset(n_docs=80, patches_per_doc=8)
    print(f"  {len(patches)} patches: {int((labels==0).sum())} authentic, {int((labels==1).sum())} tampered")

    if CASIA2_DIR and Path(CASIA2_DIR).is_dir():
        print(f"\nBlending in real splice data from {CASIA2_DIR} (using all available images) ...")
        casia_patches, casia_labels = load_casia_patches(CASIA2_DIR)
        print(f"  {len(casia_patches)} CASIA patches: "
              f"{int((casia_labels==0).sum())} authentic, {int((casia_labels==1).sum())} tampered")
        patches = np.concatenate([patches, casia_patches], axis=0)
        labels = np.concatenate([labels, casia_labels], axis=0)
        print(f"  combined total: {len(patches)} patches")

    dataset = to_tensor_dataset(patches, labels)
    n_val = int(len(dataset) * VAL_FRACTION)
    n_train = len(dataset) - n_val
    train_ds, val_ds = random_split(dataset, [n_train, n_val], generator=torch.Generator().manual_seed(42))

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False)

    model = LightweightForensicCNN()
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
    criterion = nn.CrossEntropyLoss()

    print(f"\nTraining for {EPOCHS} epochs on {n_train} patches ({n_val} held out for validation)...")
    best_val_acc = -1.0
    best_state = None
    for epoch in range(1, EPOCHS + 1):
        model.train()
        total_loss = 0.0
        for xb, yb in train_loader:
            optimizer.zero_grad()
            out = model(xb)
            loss = criterion(out, yb)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * xb.size(0)
        train_loss = total_loss / n_train

        model.eval()
        correct = 0
        with torch.no_grad():
            for xb, yb in val_loader:
                preds = model(xb).argmax(dim=1)
                correct += (preds == yb).sum().item()
        val_acc = correct / max(1, n_val)
        marker = ""
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            marker = "  (best so far)"
        print(f"  epoch {epoch:2d}/{EPOCHS}  train_loss={train_loss:.4f}  val_acc={val_acc:.3%}{marker}")

    WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save(best_state, WEIGHTS_PATH)
    print(f"\nBest validation accuracy: {best_val_acc:.3%}")
    print(f"Saved best-epoch checkpoint to {WEIGHTS_PATH}")
    print("Restart the backend (or the docker container) to pick it up --")
    print("TamperDetectionService loads it automatically on startup.")


if __name__ == "__main__":
    main()
