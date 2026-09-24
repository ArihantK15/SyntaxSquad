import os

import pytest
from cryptography.fernet import InvalidToken

from app.core.encryption import (
    encrypt_bytes,
    decrypt_bytes,
    write_encrypted_file,
    encrypt_file_in_place,
    decrypted_tempfile,
    encrypt_embedding,
    decrypt_embedding,
)


def test_encrypt_decrypt_bytes_roundtrip():
    plaintext = b"\xff\xd8\xff\xe0not really a jpeg but binary-ish bytes"
    ciphertext = encrypt_bytes(plaintext)
    assert ciphertext != plaintext
    assert decrypt_bytes(ciphertext) == plaintext


def test_encrypting_the_same_plaintext_twice_produces_different_ciphertext():
    """Fernet embeds a random IV and timestamp per call -- if two encryptions
    of the same bytes ever produced identical ciphertext, that would mean
    the IV isn't actually varying, which defeats the point of authenticated
    encryption (pattern/repetition would leak through)."""
    plaintext = b"the same biometric bytes"
    assert encrypt_bytes(plaintext) != encrypt_bytes(plaintext)


def test_decrypting_corrupted_ciphertext_raises_invalid_token():
    """Reproduces the tamper/corruption case: a biometric file that fails to
    decrypt (bit rot, disk corruption, someone editing the ciphertext) must
    surface as a clear failure, never silently return garbage bytes as if
    they were the real image."""
    ciphertext = bytearray(encrypt_bytes(b"some biometric image bytes"))
    ciphertext[10] ^= 0xFF  # flip a bit in the middle of the token
    with pytest.raises(InvalidToken):
        decrypt_bytes(bytes(ciphertext))


def test_decrypting_arbitrary_non_fernet_bytes_raises_invalid_token():
    with pytest.raises(InvalidToken):
        decrypt_bytes(b"this was never encrypted with Fernet at all")


def test_write_encrypted_file_stores_ciphertext_not_plaintext(tmp_path):
    plaintext = b"raw document image bytes"
    path = str(tmp_path / "document.jpg")
    write_encrypted_file(path, plaintext)

    with open(path, "rb") as f:
        on_disk = f.read()
    assert on_disk != plaintext
    assert decrypt_bytes(on_disk) == plaintext


def test_decrypted_tempfile_yields_a_plaintext_copy_and_cleans_up(tmp_path):
    plaintext = b"a live face capture, pretend jpeg bytes"
    encrypted_path = str(tmp_path / "faces" / "live.jpg")
    os.makedirs(os.path.dirname(encrypted_path))
    write_encrypted_file(encrypted_path, plaintext)

    captured_tmp_path = None
    with decrypted_tempfile(encrypted_path) as tmp_path_inner:
        captured_tmp_path = tmp_path_inner
        assert tmp_path_inner != encrypted_path
        assert tmp_path_inner.endswith(".jpg")
        with open(tmp_path_inner, "rb") as f:
            assert f.read() == plaintext
        # The original encrypted file on disk must be untouched.
        with open(encrypted_path, "rb") as f:
            assert decrypt_bytes(f.read()) == plaintext

    # Temp file must be gone once the block exits.
    assert not os.path.exists(captured_tmp_path)


def test_decrypted_tempfile_cleans_up_even_when_the_caller_raises(tmp_path):
    encrypted_path = str(tmp_path / "document.jpg")
    write_encrypted_file(encrypted_path, b"some document bytes")

    captured_tmp_path = None
    with pytest.raises(RuntimeError):
        with decrypted_tempfile(encrypted_path) as tmp_path_inner:
            captured_tmp_path = tmp_path_inner
            raise RuntimeError("simulated OCR/tamper/face service failure")

    assert captured_tmp_path is not None
    assert not os.path.exists(captured_tmp_path)


def test_decrypted_tempfile_raises_on_a_corrupted_encrypted_file(tmp_path):
    """A corrupted file already persisted at rest must fail loudly when
    re-read for processing, not silently hand a garbage/empty file to the
    OCR/tamper/face pipeline."""
    encrypted_path = str(tmp_path / "document.jpg")
    with open(encrypted_path, "wb") as f:
        f.write(b"not a valid fernet token")

    with pytest.raises(InvalidToken):
        with decrypted_tempfile(encrypted_path):
            pass


def test_encrypt_file_in_place_converts_a_plaintext_file_to_ciphertext(tmp_path):
    """Covers the synthetic generator / face crop / tamper heatmap path:
    existing code that writes a plaintext file directly to its final
    resting path, unaware encryption exists."""
    path = str(tmp_path / "specimen.jpg")
    plaintext = b"\xff\xd8\xff a generated specimen image"
    with open(path, "wb") as f:
        f.write(plaintext)

    encrypt_file_in_place(path)

    with open(path, "rb") as f:
        on_disk = f.read()
    assert on_disk != plaintext
    assert decrypt_bytes(on_disk) == plaintext


def test_embedding_encrypt_decrypt_roundtrip():
    embedding = [0.123, -0.456, 0.0, 1.0, -1.0] * 100  # 500 floats, real embeddings are 512-d
    blob = encrypt_embedding(embedding)
    assert isinstance(blob, bytes)
    recovered = decrypt_embedding(blob)
    assert recovered == embedding


def test_embedding_blob_is_not_readable_json():
    """The whole point: a DB dump of this column must not hand over a
    readable float vector."""
    embedding = [0.1, 0.2, 0.3]
    blob = encrypt_embedding(embedding)
    assert b"0.1" not in blob
    assert b"[" not in blob


def test_decrypt_embedding_raises_on_corrupted_blob():
    blob = bytearray(encrypt_embedding([0.1, 0.2, 0.3]))
    blob[5] ^= 0xFF
    with pytest.raises(InvalidToken):
        decrypt_embedding(bytes(blob))
