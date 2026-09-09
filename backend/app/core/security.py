import hashlib
import re
import os
import uuid
from pathlib import Path
from fastapi import HTTPException

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024 # 10 MB

def hash_identifier(identifier: str) -> str:
    """Hashes a document number or sensitive identity attribute using SHA-256 for privacy."""
    if not identifier:
        return ""
    clean = re.sub(r"[^A-Za-z0-9]", "", identifier).upper()
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()

def sanitize_filename(filename: str) -> str:
    """Generates a secure, non-colliding filename preventing directory traversal attacks."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".jpg"
    return f"{uuid.uuid4().hex}{ext}"

def validate_image_upload(filename: str, file_size: int):
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum allowed limit of {MAX_FILE_SIZE // (1024*1024)}MB"
        )
