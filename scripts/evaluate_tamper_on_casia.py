"""
Evaluates the CURRENTLY COMMITTED tamper_cnn.pth checkpoint (trained on our
own synthetic splice generator only -- see scripts/train_tamper_cnn.py) on
real, human-made splices from the CASIA v2.0 Image Tampering Detection
dataset. This is a held-out, out-of-distribution evaluation: CASIA data was
NOT used to train this checkpoint, so this measures how well the synthetic-
only model generalizes to real-world splice statistics (different camera
noise, JPEG history, splice shapes) it has never seen.

Get the data first:
    kaggle datasets download -d divg07/casia-20-image-tampering-detection-dataset -p data/CASIA2 --unzip

Run with:
    .venv-backend/Scripts/python.exe scripts/evaluate_tamper_on_casia.py [casia_root]
"""
import sys
from pathlib import Path

import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from app.ml.tamper_model import LightweightForensicCNN
from generate_tamper_training_data import load_casia_patches

WEIGHTS_PATH = PROJECT_ROOT / "backend" / "app" / "ml" / "weights" / "tamper_cnn.pth"


def find_casia_root(explicit: str = None) -> Path:
    if explicit:
        return Path(explicit)
    candidate = PROJECT_ROOT / "data" / "CASIA2"
    if (candidate / "Au").is_dir():
        return candidate
    # The Kaggle archive sometimes unzips one level deeper (e.g. CASIA2/CASIA2/Au).
    for sub in candidate.rglob("Au"):
        if sub.is_dir():
            return sub.parent
    return candidate


def main():
    casia_root = find_casia_root(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"CASIA root: {casia_root}")
    if not (casia_root / "Au").is_dir():
        print(f"ERROR: {casia_root}/Au not found. Pass the correct CASIA2 root as an argument.")
        sys.exit(1)

    if not WEIGHTS_PATH.exists():
        print(f"ERROR: no trained checkpoint at {WEIGHTS_PATH}. Run scripts/train_tamper_cnn.py first.")
        sys.exit(1)

    device = torch.device("cpu")  # matches TamperDetectionService's own inference device
    model = LightweightForensicCNN().to(device)
    model.load_state_dict(torch.load(WEIGHTS_PATH, map_location=device))
    model.eval()

    print("Loading CASIA v2.0 patches (2 patches/image, all available images)...")
    patches, labels = load_casia_patches(str(casia_root), patches_per_image=2)
    print(f"  {len(patches)} patches: {int((labels == 0).sum())} authentic, {int((labels == 1).sum())} tampered")

    x = torch.from_numpy(patches).permute(0, 3, 1, 2).float() / 255.0
    y = labels

    preds = []
    probs_tampered = []
    batch_size = 256
    with torch.no_grad():
        for i in range(0, len(x), batch_size):
            batch = x[i:i + batch_size].to(device)
            out = model(batch)
            probs = torch.softmax(out, dim=1).numpy()
            probs_tampered.extend(probs[:, 1].tolist())
            preds.extend(probs.argmax(axis=1).tolist())

    preds = np.array(preds)
    probs_tampered = np.array(probs_tampered)

    tp = int(((preds == 1) & (y == 1)).sum())
    fp = int(((preds == 1) & (y == 0)).sum())
    tn = int(((preds == 0) & (y == 0)).sum())
    fn = int(((preds == 0) & (y == 1)).sum())

    accuracy = (tp + tn) / len(y)
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else float("nan")
    far = fp / (fp + tn) if (fp + tn) else float("nan")  # authentic misclassified as tampered
    frr = fn / (fn + tp) if (fn + tp) else float("nan")  # tampered misclassified as authentic

    print(f"\n=== tamper_cnn.pth on CASIA v2.0 (out-of-distribution: trained on synthetic splices only) ===")
    print(f"n = {len(y)}  (authentic={int((y==0).sum())}, tampered={int((y==1).sum())})")
    print(f"Accuracy:  {accuracy:.3%}")
    print(f"Precision: {precision:.3%}  (of patches flagged tampered, how many really were)")
    print(f"Recall:    {recall:.3%}  (of truly tampered patches, how many were caught)")
    print(f"F1:        {f1:.3%}")
    print(f"Confusion: TP={tp}  FP={fp}  TN={tn}  FN={fn}")
    print(f"False-accept rate (authentic misclassified as tampered): {far:.3%}")
    print(f"False-reject rate (tampered misclassified as authentic): {frr:.3%}")
    print(f"Mean predicted tampered-probability -- authentic patches: {probs_tampered[y==0].mean():.3f}")
    print(f"Mean predicted tampered-probability -- tampered patches:  {probs_tampered[y==1].mean():.3f}")


if __name__ == "__main__":
    main()
