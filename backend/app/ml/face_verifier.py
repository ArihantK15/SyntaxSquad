import os
import cv2
import numpy as np
import torch
from typing import Tuple, Optional, Dict, Any, List
from facenet_pytorch import MTCNN, InceptionResnetV1


def _fixed_image_standardization(image_tensor: torch.Tensor) -> torch.Tensor:
    """Matches facenet-pytorch's own preprocessing so embeddings from a manually
    cropped/resized face patch land in the same distribution the model was
    trained on."""
    return (image_tensor - 127.5) / 128.0


class FaceDetectorAndVerifier:
    """
    Face detection + verification backed by pretrained deep models:
    - MTCNN for face detection (facenet-pytorch).
    - InceptionResnetV1, pretrained on VGGFace2, for 512-d L2-normalized face
      embeddings (facenet-pytorch).

    The MATCH threshold in face_service.py is calibrated against the LFW
    face-verification benchmark -- see scripts/calibrate_face_threshold.py.
    """

    EMBED_SIZE = (160, 160)  # InceptionResnetV1's expected input size

    def __init__(self):
        self.device = torch.device("cpu")
        self.mtcnn = MTCNN(keep_all=True, device=self.device, post_process=False)
        self.embedder = InceptionResnetV1(pretrained="vggface2").eval().to(self.device)

        # Interim FG-NET-only fine-tune (block8 + last_linear + last_bn unfrozen,
        # see scripts/finetune_face_embedder.py) for better cross-age matching.
        # This is a sanity-check checkpoint trained on FG-NET alone (82
        # identities) -- NOT the intended FG-NET+YLFW combined fine-tune, which
        # is still pending YLFW-Dev-Train-Balanced access. Swap this out once
        # that combined checkpoint exists.
        finetuned_path = os.path.join(os.path.dirname(__file__), "weights", "face_embedder_finetuned.pth")
        if os.path.exists(finetuned_path):
            state_dict = torch.load(finetuned_path, map_location=self.device)
            self.embedder.load_state_dict(state_dict)
            self.embedder.eval()

    def detect_face(
        self,
        img_bgr: np.ndarray,
        max_w_ratio: float = 1.0,
        max_h_ratio: float = 1.0,
        fallback_rect: Optional[Tuple[float, float, float, float]] = None,
    ) -> List[Tuple[int, int, int, int]]:
        """
        Detects faces in a BGR image. Returns list of (x, y, w, h).

        max_w_ratio/max_h_ratio bound the plausible face size as a fraction of the
        input frame -- a document's inset portrait is normally a modest fraction
        of the full page, so document-scoped callers should pass a tighter bound.

        fallback_rect, if given, is a fractional (x, y, w, h) region used when no
        plausible face is detected (e.g. a stylized/synthetic avatar MTCNN can't
        recognize as a face). Callers know their own frame's geometry, so they
        should supply this explicitly rather than relying on a generic guess.
        """
        ih, iw = img_bgr.shape[:2]
        try:
            rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            boxes, probs = self.mtcnn.detect(rgb)
            if boxes is not None:
                plausible = []
                for box, prob in zip(boxes, probs):
                    if prob is None or prob < 0.90:
                        continue
                    x1, y1, x2, y2 = box
                    w, h = x2 - x1, y2 - y1
                    if w <= iw * max_w_ratio and h <= ih * max_h_ratio:
                        plausible.append((
                            int(max(0, x1)), int(max(0, y1)),
                            int(min(w, iw)), int(min(h, ih))
                        ))
                if plausible:
                    return plausible
        except Exception:
            pass

        # Fallback: no plausible detection, use caller-supplied or generic region.
        if fallback_rect is not None:
            fx, fy, fw, fh = fallback_rect
            return [(int(iw * fx), int(ih * fy), int(iw * fw), int(ih * fh))]

        if iw > ih:
            # Document layout: portrait in left region
            return [(int(iw * 0.05), int(ih * 0.15), int(iw * 0.35), int(ih * 0.55))]
        else:
            # Centered live webcam frame
            return [(int(iw * 0.15), int(ih * 0.15), int(iw * 0.70), int(ih * 0.70))]

    # Radial band (as a fraction of the crop's Nyquist radius) a screen-replay
    # or print-halftone recapture's periodic grid pattern shows up in --
    # excludes the DC-adjacent low band (bulk face content: skin gradients,
    # facial structure) and the extreme high-frequency tail (dominated by
    # resize/JPEG-block noise on real captures, not a moire signal). Picked
    # from where synthetic_moire/synthetic_halftone's own injected
    # frequencies land in scripts/check_frequency_liveness_signal.py's
    # validation, not tuned against any real spoof capture (see that
    # script's own disclosure).
    FREQ_ARTIFACT_BAND = (0.12, 0.55)

    # How many of the band's dominant frequency bins (by energy) count
    # toward FREQ_ARTIFACT_CONCENTRATION below. A single injected sinusoid
    # (screen-replay moire) concentrates into its fundamental frequency plus
    # its mirror image about the FFT's DC center (2 bins); a 2D dot-grid
    # (print halftone) into up to 4 symmetric frequency pairs (8 bins). 8 is
    # sized for the richer halftone case; a real face crop's texture has no
    # such small set of dominant bins to fit this budget with.
    FREQ_ARTIFACT_TOP_K_BINS = 8

    # Fraction of the band's total energy concentrated in its top-K bins
    # above which a face crop is flagged as having a suspicious periodic
    # pattern. Calibrated against scripts/check_frequency_liveness_signal.py's
    # synthetic moire/halftone proxy (see that script's own disclosure of
    # what this is and is not validated against) -- an earlier peak-to-
    # median version of this heuristic looked clean against an accidentally
    # all-black test image but had an 84% false-positive rate once tested
    # against REAL face texture (a single bright/dark outlier pixel in the
    # 2D spectrum is common in real images and isn't itself evidence of a
    # periodic pattern); this top-K energy-share version held up much
    # better under the same real-face-texture test. At this threshold, on an
    # n=800 run: 5.4% false-positive rate on clean real (LFW) face crops,
    # 98.5% recall on the synthetic moire proxy, 41.9% recall on the
    # synthetic halftone proxy (see that script's own output for the full
    # sweep, including the threshold trade-off curve).
    FREQ_ARTIFACT_CONCENTRATION_THRESHOLD = 0.25

    @staticmethod
    def analyze_frequency_artifacts(face_bgr: np.ndarray) -> Dict[str, Any]:
        """
        FFT-based heuristic for screen-replay / print-halftone recapture:
        photographing a face off an LCD/OLED screen or a printed/halftone
        photo (rather than the live person) imprints a regular, spatially
        periodic pattern -- a pixel/subpixel moire grid, or a halftone dot
        screen -- that a direct live capture does not have. In the 2D
        frequency domain, a periodic spatial pattern concentrates almost all
        of its energy into a small, fixed number of frequency bins (its
        fundamental frequency and the mirror image every real-valued
        image's FFT has about the DC center -- see FREQ_ARTIFACT_TOP_K_BINS)
        -- unlike a real face crop's texture, whose energy in the same band
        is spread broadly across many bins with no such small dominant set.
        An earlier version of this heuristic instead radially averaged the
        spectrum and looked at peak-to-median (a much simpler measure) -- it
        had an 84% false-positive rate once tested against real face
        texture (see scripts/check_frequency_liveness_signal.py's own
        disclosure of that run): a single bright outlier pixel is common in
        a real image's 2D spectrum and isn't on its own evidence of a
        periodic pattern the way concentrated ENERGY SHARE across the whole
        band is.

        A staticmethod (not just called as one), same rationale as
        compare_faces: it's a pure numpy/OpenCV computation with no model
        state, so a caller (or a validation script) can reuse it without
        instantiating FaceDetectorAndVerifier and loading MTCNN/
        InceptionResnetV1 just to compute an FFT.

        NOT a certified Presentation Attack Detection (PAD) system -- no
        ISO/IEC 30107-3 conformant liveness testing has been done on it, and
        there is no real spoof-attempt dataset behind the threshold below.
        It is validated only against a SELF-GENERATED synthetic proxy (real
        face crops with a synthetic moire/halftone pattern overlaid --
        scripts/check_frequency_liveness_signal.py), exactly as honestly
        disclosed as the tamper CNN's own synthetic-only baseline was before
        CASIA v2.0 got blended into its training data (see that model's own
        commit history). Treat this as a coarse, LOW-severity, non-blocking
        heuristic indicator only -- never a pass/fail liveness verdict.
        """
        size = 128
        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        # Fixed size so frequency bins (and the FREQ_ARTIFACT_BAND fractions
        # above) are comparable across differently-sized face crops.
        gray = cv2.resize(gray, (size, size))

        # Hann window: suppresses the spectral leakage a hard image-edge
        # discontinuity would otherwise inject as spurious high-frequency
        # energy, unrelated to any real periodic pattern in the content.
        window = np.outer(np.hanning(size), np.hanning(size))
        windowed = gray * window

        spectrum = np.fft.fftshift(np.fft.fft2(windowed))
        magnitude = np.abs(spectrum)

        center = size // 2
        yy, xx = np.indices((size, size))
        radius = np.sqrt((xx - center) ** 2 + (yy - center) ** 2)
        max_radius = float(center)

        # Raw 2D bins within the band annulus (NOT radially averaged --
        # averaging over a whole ring dilutes a real periodic pattern's
        # peak, since it's concentrated at one angle/orientation, not
        # spread uniformly around the ring at that radius).
        band_lo = max_radius * FaceDetectorAndVerifier.FREQ_ARTIFACT_BAND[0]
        band_hi = max_radius * FaceDetectorAndVerifier.FREQ_ARTIFACT_BAND[1]
        annulus = (radius >= band_lo) & (radius < band_hi)
        band_vals = magnitude[annulus]

        energy = band_vals.astype(np.float64) ** 2
        total_energy = float(energy.sum())
        if total_energy <= 0 or band_vals.size == 0:
            return {"moire_energy_concentration": 0.0, "frequency_artifact_detected": False}

        k = min(FaceDetectorAndVerifier.FREQ_ARTIFACT_TOP_K_BINS, energy.size)
        top_k_energy = float(np.sort(energy)[-k:].sum())
        concentration = top_k_energy / total_energy

        return {
            "moire_energy_concentration": round(concentration, 3),
            "frequency_artifact_detected": (
                concentration >= FaceDetectorAndVerifier.FREQ_ARTIFACT_CONCENTRATION_THRESHOLD
            )
        }

    def check_quality(self, face_bgr: np.ndarray) -> Dict[str, Any]:
        """Quality and anti-spoofing checks.

        `liveness_score` is a coarse HEURISTIC INDICATOR only -- blur/
        brightness quality plus the FFT-based moire/halftone signal below --
        not a certified Presentation Attack Detection (PAD) verdict. No
        ISO/IEC 30107-3 conformant liveness testing has been done on this
        pipeline; see analyze_frequency_artifacts' own docstring for exactly
        what the frequency component is (and isn't) validated against.
        """
        h, w = face_bgr.shape[:2]
        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)

        # Brightness check
        mean_brightness = float(np.mean(gray))
        is_dark = mean_brightness < 45
        is_overexposed = mean_brightness > 220

        # Sharpness / blurriness check via Laplacian variance
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        is_blurry = lap_var < 35.0

        freq_analysis = self.analyze_frequency_artifacts(face_bgr)

        liveness_score = 0.95
        if is_blurry:
            liveness_score -= 0.25
        if is_dark or is_overexposed:
            liveness_score -= 0.15
        if freq_analysis["frequency_artifact_detected"]:
            liveness_score -= 0.35

        return {
            "resolution": f"{w}x{h}",
            "mean_brightness": round(mean_brightness, 1),
            "laplacian_sharpness": round(lap_var, 1),
            "is_blurry": is_blurry,
            "is_dark": is_dark,
            "is_overexposed": is_overexposed,
            "moire_energy_concentration": freq_analysis["moire_energy_concentration"],
            "frequency_artifact_detected": freq_analysis["frequency_artifact_detected"],
            "liveness_score": round(max(0.20, liveness_score), 2)
        }

    def extract_embedding(self, face_bgr: np.ndarray) -> Optional[np.ndarray]:
        """Extracts a 512-d L2-normalized VGGFace2 face embedding from a face crop."""
        if face_bgr is None or face_bgr.size == 0:
            return None
        rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, self.EMBED_SIZE)
        tensor = torch.from_numpy(resized).permute(2, 0, 1).float().unsqueeze(0)
        tensor = _fixed_image_standardization(tensor)
        with torch.no_grad():
            emb = self.embedder(tensor.to(self.device))
        return emb.squeeze(0).cpu().numpy()

    @staticmethod
    def compare_faces(emb1: Optional[np.ndarray], emb2: Optional[np.ndarray]) -> float:
        """
        Cosine similarity between two face embeddings, mapped to 0..1. A
        staticmethod (not just called as one) so callers -- e.g.
        identity_gallery_service.py's 1:N gallery search -- can reuse this
        exact comparison without instantiating FaceDetectorAndVerifier and
        loading its MTCNN/InceptionResnetV1 models just for a numpy op.
        """
        if emb1 is None or emb2 is None:
            return 0.0
        norm1, norm2 = np.linalg.norm(emb1), np.linalg.norm(emb2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        cos_sim = float(np.dot(emb1, emb2) / (norm1 * norm2))
        return max(0.0, min(1.0, (cos_sim + 1.0) / 2.0))
