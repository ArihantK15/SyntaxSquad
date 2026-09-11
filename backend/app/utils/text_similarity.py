def levenshtein(a: str, b: str) -> int:
    """Small edit-distance helper for tolerating single-character OCR slips
    between two independently-read copies of the same short string (a
    document number, a name, a code) -- no extra dependency needed for
    strings this short."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + (0 if ca == cb else 1)
            )
        prev = curr
    return prev[len(b)]


def fuzzy_equal(a: str, b: str, max_distance: int = 1, min_length: int = 6) -> bool:
    """True if a and b are identical or within max_distance edits of each
    other, gated by min_length and a length-difference cap so short strings
    (where a 1-edit tolerance is far more likely to produce a coincidental
    collision) never qualify."""
    if not a or not b:
        return False
    if len(a) < min_length or abs(len(a) - len(b)) > max_distance:
        return False
    return levenshtein(a, b) <= max_distance
