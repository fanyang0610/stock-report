"""Quote checks for the results review (AGENTS.md rule 2): a finding counts only when its quote is in the source line
it cites (whitespace and full-width forms normalized)."""

import unicodedata

MIN_QUOTE = 6


def norm(text) -> str:
    """NFKC (full-width digits, brackets and colons to ASCII) without any whitespace."""
    return "".join(unicodedata.normalize("NFKC", str(text or "")).split())


def find(full: str, quote: str) -> int:
    """Position of the normalized quote in the normalized source text, -1 if absent or too short."""
    return full.find(quote) if len(quote) >= MIN_QUOTE else -1
