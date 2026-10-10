"""Low-level parsers for amounts, dates and currencies found in financial documents."""

from __future__ import annotations

import math
import re
from datetime import date, datetime

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR"}
CURRENCY_CODES = ("USD", "EUR", "GBP", "CAD", "AUD", "JPY", "INR", "CHF", "NZD")

# A money-looking token: optional sign/parens/currency, digits with separators, optional decimals.
AMOUNT_RE = re.compile(
    r"(?<![\w.])"
    r"(?P<neg>[-(])?\s?"
    r"(?:[$€£¥₹]|USD|EUR|GBP|CAD|AUD)?\s?"
    r"(?P<num>\d{1,3}(?:[,.]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
    r"(?P<close>\))?"
    r"(?:\s?(?P<crdr>CR|DR|Cr|Dr))?"
    r"(?!\.?\w)"
)


def parse_amount(text: str | float | int | None) -> float | None:
    """Parse a monetary string into a float.

    Handles thousands separators (US and European style), currency symbols,
    accounting-style parentheses for negatives, trailing minus and CR/DR markers.
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return None if math.isnan(text) else float(text)
    s = str(text).strip()
    if not s:
        return None

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    upper = s.upper()
    if upper.endswith("DR"):
        negative, s = True, s[:-2]
    elif upper.endswith("CR"):
        s = s[:-2]
    s = s.strip()
    if s.endswith("-"):
        negative, s = True, s[:-1]
    if s.startswith("-"):
        negative, s = True, s[1:]
    s = re.sub(r"[^\d.,]", "", s)
    if not s or not re.search(r"\d", s):
        return None

    if "," in s and "." in s:
        # Whichever separator appears last is the decimal separator.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        # "12,50" is a European decimal; "1,250" is a thousands separator.
        s = f"{head.replace(',', '')}.{tail}" if len(tail) in (1, 2) else s.replace(",", "")
    elif s.count(".") > 1:
        head, _, tail = s.rpartition(".")
        s = f"{head.replace('.', '')}.{tail}" if len(tail) in (1, 2) else s.replace(".", "")

    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


def find_amounts(line: str) -> list[float]:
    """Return every amount-like value in a line, in order of appearance."""
    out = []
    for m in AMOUNT_RE.finditer(line):
        raw = m.group(0).strip()
        # Ignore bare integers that are probably quantities, years or ids unless
        # they carry a currency marker.
        has_decimals = re.search(r"[.,]\d{1,2}\)?(?:\s?(?:CR|DR|Cr|Dr))?$", raw)
        has_currency = re.search(r"[$€£¥₹]|USD|EUR|GBP|CAD|AUD", raw)
        if not (has_decimals or has_currency):
            continue
        if m.group("neg") == "(" and not m.group("close"):
            raw = raw[1:]
        value = parse_amount(raw)
        if value is not None:
            out.append(value)
    return out


_MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
DATE_RE = re.compile(
    r"\b("
    r"\d{4}-\d{1,2}-\d{1,2}"
    r"|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"
    rf"|\d{{1,2}}\s+{_MONTHS},?\s+\d{{4}}"
    rf"|{_MONTHS}\s+\d{{1,2}},?\s+\d{{4}}"
    rf"|\d{{1,2}}[- ]{_MONTHS}[- ]\d{{2,4}}"
    r")\b",
    re.IGNORECASE,
)

_FORMATS_MDY = ["%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y", "%m.%d.%Y"]
_FORMATS_DMY = ["%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y"]
_FORMATS_TEXT = [
    "%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y",
    "%d-%b-%Y", "%d-%b-%y", "%d %b %y",
]


def parse_date(text, day_first: bool = False) -> date | None:
    """Parse a date in any of the common formats used on statements and invoices."""
    if text is None:
        return None
    if isinstance(text, datetime):
        return text.date()
    if isinstance(text, date):
        return text
    s = re.sub(r"\s+", " ", str(text).strip().replace(",", ""))
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s)
    s = re.sub(r"\b(Sept)\b", "Sep", s, flags=re.IGNORECASE)
    s = re.sub(r"\b([A-Za-z]{3})[a-z]*\.", r"\1", s)
    if " " in s and re.match(r"^\d{4}-\d{2}-\d{2} ", s):
        s = s.split(" ")[0]  # pandas-style timestamp "2024-01-05 00:00:00"
    numeric = _FORMATS_DMY + _FORMATS_MDY if day_first else _FORMATS_MDY + _FORMATS_DMY
    for fmt in _FORMATS_TEXT + numeric:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Full month names that strptime's %b won't accept when abbreviated oddly.
    try:
        return datetime.strptime(s.title(), "%B %d %Y").date()
    except ValueError:
        return None


def find_dates(text: str, day_first: bool = False) -> list[date]:
    out = []
    for m in DATE_RE.finditer(text):
        d = parse_date(m.group(1), day_first=day_first)
        if d:
            out.append(d)
    return out


def detect_currency(text: str) -> str | None:
    counts: dict[str, int] = {}
    for sym, code in CURRENCY_SYMBOLS.items():
        n = text.count(sym)
        if n:
            counts[code] = counts.get(code, 0) + n
    for code in CURRENCY_CODES:
        n = len(re.findall(rf"\b{code}\b", text))
        if n:
            counts[code] = counts.get(code, 0) + n
    if not counts:
        return None
    return max(counts, key=counts.get)
