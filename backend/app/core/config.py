import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

# Root project directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "BorderMesh — AI-Based Fake Identity & Document Screening System"
    API_V1_STR: str = "/api"
    ENVIRONMENT: str = "development"
    DEMO_MODE: bool = True
    
    # Database
    DATABASE_URL: str = "sqlite:///./border_mesh.db"
    
    # Uploads
    UPLOAD_DIR: str = str(BASE_DIR / "uploads")
    
    # Security
    SECRET_KEY: str = "bordermesh-sih2026-demo-secret-key-change-in-production"

    # Minimal API-key gate (X-API-Key header) required for the two most
    # sensitive, irreversible actions: permanent case deletion and the
    # biometric purge protocol. This is NOT a full auth/session system --
    # there is no per-user identity behind it, and since the frontend has to
    # embed this key to call those two endpoints, it's a shared secret
    # visible in the frontend bundle, not a real access-control boundary
    # against a determined attacker. What it does close: neither endpoint
    # can currently be triggered by a bare, credential-free request (e.g. a
    # stray script, a scanner, an unauthenticated curl) -- which is the gap
    # this was added to close before SIH judging. Revisit with real
    # per-officer auth before any non-demo deployment.
    OFFICER_API_KEY: str = "bordermesh-sih2026-officer-key-change-in-production"
    # No wildcard here: FastAPI/Starlette combines allow_credentials=True with
    # a "*" entry by reflecting whatever Origin header the request actually
    # sent, rather than a literal "*" -- which makes this list into a no-op
    # allowlist that accepts every origin with credentials attached. The
    # deployed frontend never needs a third-party origin anyway: nginx proxies
    # /api and /uploads under the same origin the page was loaded from, so
    # this list only matters for local dev tooling hitting the API directly.
    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    
    # Risk Engine Weights (Sum to 1.0)
    WEIGHT_MRZ: float = 0.25
    WEIGHT_TAMPER: float = 0.30
    WEIGHT_FACE: float = 0.30
    WEIGHT_CONSISTENCY: float = 0.10
    WEIGHT_WATCHLIST: float = 0.05
    
    # Risk Thresholds
    THRESHOLD_LOW: int = 24
    THRESHOLD_MEDIUM: int = 49
    THRESHOLD_HIGH: int = 74
    
    # OCR Settings
    OCR_ENGINE: str = "pytesseract"
    # Empty by default: ocr_service.py only overrides pytesseract's tesseract_cmd
    # when this path actually exists, otherwise it falls back to pytesseract's
    # own PATH search -- which is what works across machines/OSes as long as
    # tesseract-ocr is installed. A hardcoded Homebrew-only default here
    # (previously "/opt/homebrew/bin/tesseract") silently only worked on
    # Apple Silicon Macs; set this explicitly if your tesseract binary isn't
    # already on PATH.
    TESSERACT_PATH: str = ""
    
    # Privacy & Disclaimer
    DISCLAIMER_TEXT: str = (
        "PROTOTYPE SYSTEM — Smart India Hackathon 2026 Demo. "
        "Simulated watchlist and demo risk indicators. "
        "Requires human officer review; never makes definitive legal assertions."
    )
    
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

# Ensure required upload directories exist
os.makedirs(os.path.join(settings.UPLOAD_DIR, "documents"), exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "faces"), exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "heatmaps"), exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "crops"), exist_ok=True)
