from app.utils.text_similarity import levenshtein, fuzzy_equal


def test_levenshtein_identical_strings():
    assert levenshtein("X1234567", "X1234567") == 0


def test_levenshtein_single_substitution():
    assert levenshtein("X1234567", "X1B34567") == 1


def test_fuzzy_equal_within_tolerance():
    assert fuzzy_equal("X1234567", "X1B34567") is True


def test_fuzzy_equal_rejects_two_edits():
    assert fuzzy_equal("X1234567", "X1BB4567") is False


def test_fuzzy_equal_rejects_short_strings_even_with_one_edit():
    assert fuzzy_equal("ABCDE", "ABCDF") is False
