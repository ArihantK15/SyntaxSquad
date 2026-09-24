"""
Targeted validation for the new FFT-based liveness/anti-spoofing heuristic
(FaceDetectorAndVerifier.analyze_frequency_artifacts, backend/app/ml/face_verifier.py)
-- mirrors scripts/check_exif_signal_on_casia.py's pattern: run the real
signal function against two labeled groups and report whether it actually
discriminates, before trusting it in the live pipeline.

HONEST DISCLOSURE, same posture as the tamper CNN's own synthetic-only
baseline before CASIA v2.0 got blended into its training data (see that
model's commit history, "Train the tamper-forensics CNN on real splice
data, activate Signal E"): there is no real presentation-attack dataset
behind this validation. This project has no camera-to-screen or
printed-and-rescanned spoof captures, and none are ethically fabricable in
the time available the way the tamper CNN's own synthetic splices were
(a rectangular copy-paste is something this project's own generator can
produce end-to-end; a real screen's refresh-rate/pixel-grid interaction
with a real camera sensor's Bayer/OLPF response is a physical capture
process, not something a synthetic proxy can reproduce exactly).

So this script validates against a SELF-GENERATED SYNTHETIC PROXY instead:
real face crops (LFW, real photographs of real people -- not this project's
own synthetic actors) with a synthetic moire grid or halftone dot pattern
overlaid directly in software. This confirms the heuristic's underlying
mechanism -- a real face's power spectrum falls off smoothly, an injected
periodic pattern produces a sharp radial peak -- actually separates clean
from patterned images. It does NOT confirm the heuristic catches a REAL
screen-replay or print-and-rescan attack, whose moire/halftone signature
comes from an actual optical/sampling process this proxy only approximates.
Treat this as evidence the mechanism works, not as a substitute for testing
against real spoof captures if/when this project ever obtains any.

Two bugs surfaced during this validation and were fixed before trusting any
result, the same "don't trust the first number" posture the tamper CNN's own
synthetic-only baseline run applied:
  - fetch_lfw_people returns float32 images already scaled to [0, 1], not
    [0, 255] (the same pitfall scripts/evaluate_gallery_scale_far.py's own
    comment flags for this exact dataset). An unscaled cast to uint8
    truncated every "real face crop" to solid black, so the very first run
    of this script was actually comparing an all-black canvas against an
    all-black canvas plus a sinusoid -- a meaningless test that happened to
    look clean (0% false-positive rate) purely because there was no real
    face texture in it at all to produce a false positive against.
  - Once that was fixed and real face texture was actually going through
    the heuristic, the first version of analyze_frequency_artifacts (a
    radially-averaged peak-to-median measure) had an 84% false-positive
    rate on clean, real LFW crops -- a single bright/dark outlier pixel is
    common in a real image's 2D spectrum and isn't on its own evidence of a
    periodic pattern. The heuristic was redesigned around energy
    CONCENTRATION in the band's top-K dominant bins instead (see
    FaceDetectorAndVerifier.FREQ_ARTIFACT_TOP_K_BINS's own comment for why
    that's a better-founded measure), which is what this script now
    validates.

Run with:
    .venv-train/Scripts/python.exe scripts/check_frequency_liveness_signal.py [n_samples]
"""
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from sklearn.datasets import fetch_lfw_people
from app.ml.face_verifier import FaceDetectorAndVerifier

N_SAMPLES_DEFAULT = 300


def apply_synthetic_moire(gray_u8: np.ndarray, freq_cycles: float, amplitude: float, angle_deg: float) -> np.ndarray:
    """
    Overlays a synthetic sinusoidal grating standing in for a screen-replay
    moire pattern. A real moire pattern comes from beat-frequency aliasing
    between a screen's pixel grid and a camera sensor's own sampling grid --
    a physical process this doesn't simulate. What it DOES reproduce
    honestly is the end RESULT that process is known to leave in the
    recaptured image: a regular, periodic band pattern at some orientation,
    which is exactly the kind of signal analyze_frequency_artifacts looks
    for in the frequency domain, regardless of which physical process
    produced it.
    """
    h, w = gray_u8.shape
    yy, xx = np.indices((h, w), dtype=np.float64)
    theta = np.deg2rad(angle_deg)
    xr = xx * np.cos(theta) + yy * np.sin(theta)
    grating = amplitude * np.sin(2 * np.pi * freq_cycles * xr / w)
    return np.clip(gray_u8.astype(np.float64) + grating, 0, 255).astype(np.uint8)


def apply_synthetic_halftone(gray_u8: np.ndarray, cell_size: float, amplitude: float, angle_deg: float) -> np.ndarray:
    """
    Overlays a synthetic 2D dot-grid texture standing in for a print
    halftone screen. Not generated via actual AM halftone dithering (which
    would threshold against local pixel intensity) -- this is a
    fixed-amplitude periodic dot-grid texture at the given cell size/angle,
    independent of the underlying image content. That's a real
    simplification versus an actual halftone-printed-and-rescanned photo,
    but it produces the same defining signature a real halftone screen
    does: a periodic 2D grid with energy concentrated at one characteristic
    frequency, which is what the heuristic actually targets.
    """
    h, w = gray_u8.shape
    yy, xx = np.indices((h, w), dtype=np.float64)
    theta = np.deg2rad(angle_deg)
    xr = xx * np.cos(theta) - yy * np.sin(theta)
    yr = xx * np.sin(theta) + yy * np.cos(theta)
    dot_pattern = np.cos(2 * np.pi * xr / cell_size) * np.cos(2 * np.pi * yr / cell_size)
    texture = amplitude * dot_pattern
    return np.clip(gray_u8.astype(np.float64) + texture, 0, 255).astype(np.uint8)


def _to_bgr(gray_u8: np.ndarray) -> np.ndarray:
    import cv2
    return cv2.cvtColor(gray_u8, cv2.COLOR_GRAY2BGR)


def _report(label: str, concentrations: np.ndarray, detected: np.ndarray):
    print(f"\n--- {label}: n={len(concentrations)} ---")
    print(f"moire_energy_concentration: mean={concentrations.mean():.3f}  std={concentrations.std():.3f}  "
          f"min={concentrations.min():.3f}  max={concentrations.max():.3f}  "
          f"p50={np.percentile(concentrations, 50):.3f}  p90={np.percentile(concentrations, 90):.3f}")
    print(f"frequency_artifact_detected rate: {detected.mean():.1%}")


def main():
    n_samples = int(sys.argv[1]) if len(sys.argv) > 1 else N_SAMPLES_DEFAULT
    rng = np.random.default_rng(42)

    print(f"Loading LFW people (real photographs of real people)...")
    data = fetch_lfw_people(min_faces_per_person=1, resize=1.0, color=False)
    print(f"Loaded {len(data.images)} images")

    idxs = rng.choice(len(data.images), size=min(n_samples, len(data.images)), replace=False)
    # fetch_lfw_people (unlike fetch_lfw_pairs) returns float32 images already
    # scaled to [0, 1], not [0, 255] -- an unscaled cast to uint8 truncates
    # every pixel to 0 (all-black), the same pitfall
    # scripts/evaluate_gallery_scale_far.py's own comment flags for this
    # exact dataset. Scale explicitly before casting.
    faces_u8 = [(data.images[i] * 255).astype(np.uint8) for i in idxs]

    clean_conc, clean_detected = [], []
    moire_conc, moire_detected = [], []
    halftone_conc, halftone_detected = [], []

    for i, gray in enumerate(faces_u8):
        r_clean = FaceDetectorAndVerifier.analyze_frequency_artifacts(_to_bgr(gray))
        clean_conc.append(r_clean["moire_energy_concentration"])
        clean_detected.append(r_clean["frequency_artifact_detected"])

        # Randomize attack parameters per-sample so the result isn't an
        # artifact of one lucky/unlucky frequency choice.
        freq = rng.uniform(8, 22)
        angle = rng.uniform(0, 90)
        moire_img = apply_synthetic_moire(gray, freq_cycles=freq, amplitude=rng.uniform(18, 35), angle_deg=angle)
        r_moire = FaceDetectorAndVerifier.analyze_frequency_artifacts(_to_bgr(moire_img))
        moire_conc.append(r_moire["moire_energy_concentration"])
        moire_detected.append(r_moire["frequency_artifact_detected"])

        cell = rng.uniform(4, 9)
        halftone_img = apply_synthetic_halftone(gray, cell_size=cell, amplitude=rng.uniform(18, 35), angle_deg=rng.uniform(0, 90))
        r_halftone = FaceDetectorAndVerifier.analyze_frequency_artifacts(_to_bgr(halftone_img))
        halftone_conc.append(r_halftone["moire_energy_concentration"])
        halftone_detected.append(r_halftone["frequency_artifact_detected"])

    clean_conc, clean_detected = np.array(clean_conc), np.array(clean_detected)
    moire_conc, moire_detected = np.array(moire_conc), np.array(moire_detected)
    halftone_conc, halftone_detected = np.array(halftone_conc), np.array(halftone_detected)

    print(f"\n=== Synthetic-proxy validation: does the heuristic separate "
          f"clean vs. synthetic-attack versions of the SAME real face crops? ===")
    _report("Clean (real LFW face crops, no overlay)", clean_conc, clean_detected)
    _report("Synthetic moire overlay", moire_conc, moire_detected)
    _report("Synthetic halftone overlay", halftone_conc, halftone_detected)

    false_positive_rate = clean_detected.mean()
    moire_recall = moire_detected.mean()
    halftone_recall = halftone_detected.mean()

    print(f"\n=== Summary at current threshold "
          f"(FaceDetectorAndVerifier.FREQ_ARTIFACT_CONCENTRATION_THRESHOLD="
          f"{FaceDetectorAndVerifier.FREQ_ARTIFACT_CONCENTRATION_THRESHOLD}) ===")
    print(f"False-positive rate on clean real face crops: {false_positive_rate:.1%}")
    print(f"Recall on synthetic moire overlay:             {moire_recall:.1%}")
    print(f"Recall on synthetic halftone overlay:           {halftone_recall:.1%}")

    print("\n=== Threshold sensitivity (for reference) ===")
    for t in (0.15, 0.18, 0.20, 0.22, 0.25, 0.28, 0.30, 0.35):
        fpr_t = (clean_conc >= t).mean()
        moire_recall_t = (moire_conc >= t).mean()
        halftone_recall_t = (halftone_conc >= t).mean()
        print(f"  threshold={t:5.2f}  clean FPR={fpr_t:.1%}  "
              f"moire recall={moire_recall_t:.1%}  halftone recall={halftone_recall_t:.1%}")


if __name__ == "__main__":
    main()
