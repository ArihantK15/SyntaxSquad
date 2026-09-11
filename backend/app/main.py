import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.api.routes import health, screening, cases, dashboard, demo, audit, settings as settings_routes

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes database tables and auto-seeds synthetic cases if empty."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        from app.models import Case
        case_count = db.query(Case).count()
        if case_count == 0:
            print("[BorderMesh] Empty database detected. Seeding initial synthetic screening cases...")
            # `scripts/` lives alongside `backend/`, not inside it, so it isn't on
            # sys.path when running via `--app-dir backend` / PYTHONPATH=backend
            # (locally) or WORKDIR /app (Docker). Add the repo root explicitly.
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            if repo_root not in sys.path:
                sys.path.insert(0, repo_root)
            from scripts.seed_cases import seed_initial_cases
            seed_initial_cases(db)
            print("[BorderMesh] Seed completed successfully.")
    except Exception as e:
        print(f"[BorderMesh] Startup seed note: {e}")
    finally:
        db.close()
    yield

app = FastAPI(
    title="BorderMesh API",
    description=(
        "AI-Based Fake Identity & Document Screening System — SIH 2026 Prototype.\n\n"
        "Integrates OCR, ICAO 9303 MRZ Checksums, Multi-Signal Tamper AI (ELA, Splicing, Seams), "
        "Biometric Face Verification, and an Explainable Risk Engine for border immigration officers."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static uploads directory for document images, heatmaps, and face crops
uploads_path = os.path.abspath(settings.UPLOAD_DIR)
os.makedirs(uploads_path, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_path), name="uploads")

# Include Routers
app.include_router(health.router, prefix=settings.API_V1_STR)
app.include_router(screening.router, prefix=settings.API_V1_STR)
app.include_router(cases.router, prefix=settings.API_V1_STR)
app.include_router(dashboard.router, prefix=settings.API_V1_STR)
app.include_router(demo.router, prefix=settings.API_V1_STR)
app.include_router(audit.router, prefix=settings.API_V1_STR)
app.include_router(settings_routes.router, prefix=settings.API_V1_STR)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
