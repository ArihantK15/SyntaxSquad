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
    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "*"]
    
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
