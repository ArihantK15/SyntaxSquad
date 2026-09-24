import json
import os
import tempfile
from contextlib import contextmanager
from typing import Any, Iterator, List

from cryptography.fernet import Fernet

from app.core.config import settings

# Fernet (AES-128-CBC + HMAC-SHA256, authenticated) rather than a hand-rolled
# AES mode -- it handles IV generation, padding, and authentication itself,
# which matters far more than the choice of cipher: a subtly-wrong hand-
# rolled mode (ECB, a reused IV, no authentication tag) is exactly the kind
# of thing this would be worse for shipping than not encrypting at all.
_fernet = Fernet(settings.BIOMETRIC_ENCRYPTION_KEY.encode("utf-8"))


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet.encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    """Raises cryptography.fernet.InvalidToken on a corrupted, truncated, or
    non-Fernet-encrypted input -- deliberately left uncaught here, the same
    way a corrupted plaintext image already surfaces as an uncaught
    ValueError from cv2.imread elsewhere in this codebase. A biometric file
    that fails to decrypt is a genuine integrity failure, not something to
    paper over."""
    return _fernet.decrypt(token)


def write_encrypted_file(path: str, raw_bytes: bytes) -> None:
    """Encrypts `raw_bytes` and writes the ciphertext to `path`. Used at the
    upload boundary, where bytes come straight from an HTTP request body."""
    with open(path, "wb") as f:
        f.write(encrypt_bytes(raw_bytes))


def encrypt_file_in_place(path: str) -> None:
    """
    Reads a plaintext file at `path` and overwrites it with its encrypted
    form. Used for artifacts that existing, unmodified code (the synthetic
    specimen generator, face_service.py's crop_and_save, tamper_service.py's
    ELA heatmap writer) writes directly to its final on-disk path as
    plaintext -- rather than teach each of those to encrypt, the caller
    converts the file to ciphertext immediately after that call returns.
    """
    with open(path, "rb") as f:
        raw = f.read()
    write_encrypted_file(path, raw)


@contextmanager
def decrypted_tempfile(encrypted_path: str) -> Iterator[str]:
    """
    Decrypts the file at `encrypted_path` into a plaintext temporary file
    and yields its path, so existing path-based code (cv2, PIL, pytesseract
    -- the OCR/tamper/face services, completely unaware encryption exists)
    can keep working exactly as before. The temp file is always removed on
    exit, including when the caller's `with` block raises.
    """
    with open(encrypted_path, "rb") as f:
        ciphertext = f.read()
    plaintext = decrypt_bytes(ciphertext)

    suffix = os.path.splitext(encrypted_path)[1] or ".jpg"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as tmp_f:
            tmp_f.write(plaintext)
        yield tmp_path
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def encrypt_embedding(embedding: List[float]) -> bytes:
    """Serializes a face embedding to JSON and encrypts it -- for the
    FaceEmbeddingGallery.embedding column, which the model docstring itself
    already calls out as raw biometric data, arguably more sensitive than
    the photo it was derived from since it's already in matchable form."""
    return encrypt_bytes(json.dumps(embedding).encode("utf-8"))


def decrypt_embedding(blob: bytes) -> Any:
    return json.loads(decrypt_bytes(bytes(blob)).decode("utf-8"))
