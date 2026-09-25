"""Normalize barcode text from a keyboard-wedge scanner."""


def normalize_barcode(raw: str | None) -> str | None:
    """Strip scanner whitespace. Empty input becomes None."""
    if raw is None:
        return None
    cleaned = raw.strip()
    return cleaned or None
