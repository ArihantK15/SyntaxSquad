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


def test_name_matches_multi_token_transliteration_variant():
    """
    Two independent one-edit spelling variants at once (a transliterated
    given name AND surname) -- 'MARCUS VANCE' -> 'MARKUS VANSE'. The old
    whole-string edit-distance check (budget 1 across the whole name) would
    reject this since the combined distance is 2; per-token matching allows
    each name part its own independent one-edit tolerance.
    """
    provider = MockWatchlistProvider()
    result = provider.check_watchlist(full_name="MARKUS VANSE", document_number=None)
    assert result is not None
    assert result["entry"]["watchlist_id"] == "WL-SIM-2026-103"


def test_name_matches_phonetic_variant_beyond_edit_distance():
    """
    A genuine phonetic/transliteration variant whose Levenshtein distance
    (3) is far outside a single-OCR-slip tolerance, but which shares the
    same Soundex AND Metaphone code as the watchlisted name -- 'MARCUS' vs
    'MARKOOS' is a stand-in for real-world cases like 'Mohammed'/'Muhammad'
    (also Soundex+Metaphone-identical despite distance 2).
    """
    provider = MockWatchlistProvider()
    result = provider.check_watchlist(full_name="MARKOOS VANCE", document_number=None)
    assert result is not None
    assert result["entry"]["watchlist_id"] == "WL-SIM-2026-103"


def test_name_matching_stays_narrow_for_unrelated_names():
    """Regression guard: phonetic matching must not turn into a blanket
    fuzzy match -- an unrelated name must still not match any entry."""
    provider = MockWatchlistProvider()
    result = provider.check_watchlist(full_name="JOHN SMITH", document_number=None)
    assert result is None
