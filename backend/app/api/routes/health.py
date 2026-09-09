from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()

@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "BorderMesh API",
        "version": "1.0.0-sih2026",
        "demo_mode": settings.DEMO_MODE,
        "ai_engines": {
            "ocr": "ONLINE",
            "mrz_validator": "ONLINE",
            "tamper_ai": "ONLINE",
            "face_verification": "ONLINE",
            "risk_engine": "ONLINE",
            "watchlist_adapter": "ONLINE (SIMULATED)"
        },
        "disclaimer": settings.DISCLAIMER_TEXT
    }
