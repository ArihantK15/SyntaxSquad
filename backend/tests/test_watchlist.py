from app.services.watchlist_service import MockWatchlistProvider


def test_exact_match_still_works():
    """Baseline: exact document number match must keep working."""
    provider = MockWatchlistProvider()
    result = provider.check_watchlist(full_name="VIKTOR KOROL", document_number="P8892144")
    assert result is not None
    assert result["match_field"] == "Document Number"


def test_document_number_survives_single_ocr_digit_confusion():
    """
    Reproduces a real screening gap: OCR on a genuinely watchlisted document
    misreads one character in the document number (e.g. '8' -> 'B', a common
    Tesseract confusion). The old exact-string check silently misses this --
    the core purpose of the watchlist check is to catch flagged identities
    fed by a noisy OCR pipeline, so a single-character OCR slip should not be
    enough to hide a real match.
    """
    provider = MockWatchlistProvider()
    result = provider.check_watchlist(full_name=None, document_number="P8B92144")
    assert result is not None
    assert result["entry"]["watchlist_id"] == "WL-SIM-2026-081"


def test_full_name_survives_single_ocr_character_confusion():
    """Same OCR-noise problem, but for the name field: 'O' misread as '0'."""
    provider = MockWatchlistProvider()
    result = provider.check_watchlist(full_name="VIKT0R KOROL", document_number=None)
    assert result is not None
    assert result["entry"]["watchlist_id"] == "WL-SIM-2026-081"


def test_unrelated_document_number_does_not_match():
    """Fuzzy tolerance must stay narrow enough not to invent false positives."""
    provider = MockWatchlistProvider()
    result = provider.check_watchlist(full_name=None, document_number="X1234567")
    assert result is None


def test_unrelated_name_does_not_match():
    provider = MockWatchlistProvider()
    result = provider.check_watchlist(full_name="JOHN SMITH", document_number=None)
    assert result is None


def test_document_number_with_two_differences_does_not_match():
    """Tolerance is calibrated for a single OCR slip, not a genuinely different number."""
    provider = MockWatchlistProvider()
    result = provider.check_watchlist(full_name=None, document_number="P8B92l44")
    assert result is None
