"""Quote verification for the deep-dive lane (AGENTS.md rule 2): a fact counts only when its quoted sentence is in the
filing text (whitespace and full-width forms normalized), its number is in the quote, and its unit right after the number
or in a unit line (e.g. "单位：元 币种：人民币") shortly before it. The number is parsed from the quote, never the answer."""

import re
import unicodedata

SCALES = [(r"千万|千萬", 1e7), (r"百万|百萬|million|mn\b|(\$|RMB|HKD|USD)m\b", 1e6), (r"亿|億", 1e8), (r"billion|bn\b", 1e9),
          (r"万|萬", 1e4), (r"千|thousand|'000", 1e3)]
CURRENCIES = [(r"人民币|人民幣|RMB|CNY", "CNY"), (r"港币|港幣|港元|HK\$|HKD", "HKD"), (r"美元|US\$|USD|\$", "USD")]
INLINE = re.compile(r"(千万|千萬|百万|百萬|亿|億|万|萬|千|billion|bn|million|mn|thousand)?(元|港元|美元|股|shares)?", re.I)
NEAR = 8000  # a table's unit line may be up to this many characters before the quoted row
MIN_QUOTE = 6


def norm(text) -> str:
    """NFKC (full-width digits, brackets and colons to ASCII) without any whitespace."""
    return "".join(unicodedata.normalize("NFKC", str(text or "")).split())


def number(raw: str) -> float | None:
    """'1,234.5' -> 1234.5; '(12)' and '-12' -> -12; '35.2%' -> 35.2 (the caller divides percentages)."""
    s = norm(raw).replace(",", "").removesuffix("%")
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    try:
        value = float(s.strip("()-"))
    except ValueError:
        return None
    return -value if neg else value


def scale_of(text: str) -> float:
    return next((s for p, s in SCALES if re.search(p, text, re.I)), 1.0)


def currency_of(text: str) -> str | None:
    return next((c for p, c in CURRENCIES if re.search(p, text)), None)


def find(full: str, quote: str) -> int:
    """Position of the normalized quote in the normalized filing text, -1 if absent or too short."""
    return full.find(quote) if len(quote) >= MIN_QUOTE else -1


def check(item: dict, full: str, default_currency: str | None = None, numeric: bool = True) -> dict | None:
    """The verified fact {quote, value, currency, pct} or None. `full` is norm(filing text). Text-only facts
    (numeric=False) need just the quote."""
    quote = norm(item.get("quote"))
    at = find(full, quote)
    if at < 0:
        return None
    spaced = " ".join(unicodedata.normalize("NFKC", str(item["quote"])).split())  # table cells stay apart
    fact = {"quote": spaced}
    if not numeric:
        return fact
    num = norm(item.get("number"))
    hit = re.search(r"(?<![\d.,])" + re.escape(num) + r"(?![\d]|[.,]\d)", spaced) if num else None
    value = number(num) if hit else None
    if value is None:
        return None
    before, after = norm(spaced[max(0, hit.start() - 8):hit.start()]), norm(spaced[hit.end():hit.end() + 16])
    if num.endswith("%") or after.startswith("%"):
        return fact | {"value": value / 100, "currency": None, "pct": True}
    unit = INLINE.match(after).group(0)  # "12.5亿元", "1,234万股", "1.5billion", "每股12.50港元"
    if not unit:  # a table row: the unit line must be in the filing, at most NEAR characters before the quoted row
        unit = norm(item.get("unit_quote"))
        where = full.rfind(unit, 0, at + len(quote)) if len(unit) >= 2 else -1
        if where < 0 or at - where > NEAR:
            return None
    return fact | {"value": value * scale_of(unit), "currency": currency_of(before + unit) or default_currency,
                   "pct": False}


def code_in(item: dict) -> str | None:
    """A listed stake's security code, only if it is written in the quote: 6 digits (CN), 4-5 digits (HK, padded
    to 5) or an upper-case ticker (US)."""
    code, quote = norm(item.get("code")).upper(), norm(item.get("quote"))
    if not code or code not in quote.upper():
        return None
    if re.fullmatch(r"\d{6}", code):
        return code
    if re.fullmatch(r"\d{4,5}", code):
        return code.zfill(5)
    return code if re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", code) else None
