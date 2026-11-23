"""Deterministic parsing: amounts, dates and merchant names.

Nothing here calls the AI. These functions are the ground truth that every AI
answer is checked against: an amount the model reports must be one this module
can find in the document, and a date must be one it can parse.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# ── amounts ────────────────────────────────────────────────────────────────────

_CURRENCY_RE = re.compile(r"(?i)\b(?:usd|eur|gbp|thb|cad|aud|jpy|sgd|chf|inr)\b|[$€£¥฿₹₩]")
_CRDR_RE = re.compile(r"(?i)\s*\b(CR|DR)\.?\s*$")


def parse_amount(value, decimal_comma: bool | None = None) -> int | None:
    """Parse a money value into signed integer cents.

    Handles "$1,234.56", "-12.00", "(12.00)", "12.00-", "12.00 CR"/"DR",
    "1.234,56" and "12,50" (decimal comma), and the unicode minus sign.
    decimal_comma: True/False forces the separator, None guesses per value.
    Returns None when the value is not a plain amount (dates, words, ids).
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except InvalidOperation:
            return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("−", "-").replace("–", "-").replace("\xa0", " ")
    sign = 1
    m = _CRDR_RE.search(s)
    if m:
        if m.group(1).upper() == "DR":
            sign = -1
        s = s[: m.start()].strip()
    for _ in range(2):  # "($12.00)" and "$(12.00)"
        if s.startswith("(") and s.endswith(")"):
            sign = -sign
            s = s[1:-1].strip()
        s = _CURRENCY_RE.sub("", s).strip()
    if s.endswith("-"):
        sign = -sign
        s = s[:-1].strip()
    if s.startswith("-"):
        sign = -sign
        s = s[1:].strip()
    elif s.startswith("+"):
        s = s[1:].strip()
    s = s.replace(" ", "").replace("'", "")
    if not s or not re.fullmatch(r"[\d.,]+", s) or not re.search(r"\d", s):
        return None
    if decimal_comma is True:
        s = s.replace(".", "").replace(",", ".")
    elif decimal_comma is False:
        s = s.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+,\d{1,2}", s) or re.fullmatch(r"\d+,\d{1,2}", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    if s.count(".") > 1:
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return sign * int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def detect_decimal_comma(values) -> bool:
    """True when a column writes cents after a comma ("12,50", "1.234,56")."""
    comma = period = 0
    for v in values:
        s = str(v or "").strip()
        if re.search(r",\d{2}\s*(?:-|CR|DR|\))?$", s):
            comma += 1
        elif re.search(r"\.\d{2}\s*(?:-|CR|DR|\))?$", s):
            period += 1
    return comma > period


_MONEY_RE = re.compile(
    r"(?<![\w/.,:])"
    r"(?P<tok>\(?[-−+]?\s?(?:[$€£¥฿]\s?)?[-−]?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}\)?-?)"
    r"(?:\s?(?P<crdr>CR|DR)\b)?"
    r"(?![\w/%]|[.,]\d)"
)


def find_amounts(text: str) -> list[tuple[str, int]]:
    """All money tokens with two decimals in free text, as (token, cents)."""
    out = []
    for m in _MONEY_RE.finditer(text or ""):
        tok = m.group("tok")
        cents = parse_amount(tok + (" " + m.group("crdr") if m.group("crdr") else ""), decimal_comma=False)
        if cents is not None:
            out.append((tok.strip(), cents))
    return out


def amount_in_text(cents: int, text: str) -> bool:
    """Grounding check: does this amount (either sign) appear in the text?"""
    if cents is None:
        return False
    target = abs(cents)
    return any(abs(c) == target for _, c in find_amounts(text))


def fmt_cents(cents: int | None) -> str:
    if cents is None:
        return "?"
    return f"{'-' if cents < 0 else ''}{abs(cents) / 100:,.2f}"


# ── dates ──────────────────────────────────────────────────────────────────────

# Formats with a year, most common first. Year-less ones only when nothing else fits.
DATE_FORMATS = [
    "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m/%d/%y", "%d/%m/%y", "%Y/%m/%d",
    "%m-%d-%Y", "%d-%m-%Y", "%d.%m.%Y", "%d.%m.%y", "%Y%m%d",
    "%d %b %Y", "%d-%b-%Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y",
    "%d-%b-%y", "%d %b %y", "%b. %d, %Y",
]
YEARLESS_FORMATS = ["%m/%d", "%d/%m", "%b %d", "%d %b", "%m-%d"]
_DAYFIRST_PAIRS = {
    "%m/%d/%Y": "%d/%m/%Y", "%m/%d/%y": "%d/%m/%y", "%m-%d-%Y": "%d-%m-%Y", "%m/%d": "%d/%m",
}
_TIME_TAIL = re.compile(
    r"(?i)[ T]\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?\s*(?:am|pm)?\s*(?:z|[+-]\d{2}:?\d{2})?$"
)
_WEEKDAY_HEAD = re.compile(r"(?i)^(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)[a-z]*\.?,?\s+")


def _clean_date(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value or "").strip().strip('"').strip()
    s = _TIME_TAIL.sub("", s).strip()
    s = _WEEKDAY_HEAD.sub("", s)
    return re.sub(r"\s+", " ", s)


def _strptime(s: str, fmt: str) -> date | None:
    try:
        return datetime.strptime(s, fmt).date()
    except ValueError:
        return None


def parse_date(value, fmt: str | None = None, year_for=None) -> str | None:
    """Parse to ISO YYYY-MM-DD. fmt=None tries every format with a year.

    year_for: callable(month, day) -> year, used by year-less formats.
    """
    s = _clean_date(value)
    if not s:
        return None
    if fmt in YEARLESS_FORMATS:
        d = _strptime(f"{s} 2000", fmt + " %Y")  # leap year so 02/29 parses
        if d is None:
            return None
        year = year_for(d.month, d.day) if year_for else date.today().year
        try:
            return d.replace(year=year).isoformat()
        except ValueError:
            return None
    for f in ([fmt] if fmt else DATE_FORMATS):
        d = _strptime(s, f)
        if d is not None and 1970 <= d.year <= 2100:
            return d.isoformat()
    return None


def detect_date_format(values, prefer_dayfirst: bool = False) -> tuple[str | None, float, bool]:
    """Pick the format that parses the most values.

    Returns (format, share parsed, ambiguous). Ambiguous means month/day and
    day/month both fit every value (all days <= 12), so the locale decided.
    """
    cleaned = [_clean_date(v) for v in values if str(v or "").strip()]
    if not cleaned:
        return None, 0.0, False
    best, best_rate = None, 0.0
    rates = {}
    for fmt in DATE_FORMATS:
        ok = sum(1 for s in cleaned if (d := _strptime(s, fmt)) and 1970 <= d.year <= 2100)
        rates[fmt] = ok / len(cleaned)
        if rates[fmt] > best_rate:
            best, best_rate = fmt, rates[fmt]
    if best_rate < 0.6:
        for fmt in YEARLESS_FORMATS:
            ok = sum(1 for s in cleaned if _strptime(f"{s} 2000", fmt + " %Y"))
            rates[fmt] = ok / len(cleaned)
            if rates[fmt] > best_rate:
                best, best_rate = fmt, rates[fmt]
    if best is None:
        return None, 0.0, False
    ambiguous = False
    for mfirst, dfirst in _DAYFIRST_PAIRS.items():
        if best in (mfirst, dfirst) and rates.get(mfirst, 0) == rates.get(dfirst, 0):
            ambiguous = True
            best = dfirst if prefer_dayfirst else mfirst
    return best, best_rate, ambiguous


def year_resolver(period_start: str | None = None, period_end: str | None = None, today: date | None = None):
    """Year for month/day dates: inside the statement period if known, else not in the future."""
    today = today or date.today()

    def resolve(month: int, day: int) -> int:
        if period_start and period_end:
            ps, pe = date.fromisoformat(period_start), date.fromisoformat(period_end)
            for y in range(ps.year, pe.year + 1):
                try:
                    if ps - timedelta(days=7) <= date(y, month, day) <= pe + timedelta(days=7):
                        return y
                except ValueError:
                    continue
            return pe.year
        year = today.year
        try:
            if date(year, month, day) > today + timedelta(days=7):
                year -= 1
        except ValueError:
            pass
        return year

    return resolve


DATE_TOKEN_PATTERN = (
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.? \d{1,2}(?:,? \d{4})?|"
    r"\d{1,2} (?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?(?: \d{2,4})?)\b"
)
DATE_TOKEN_RE = re.compile(DATE_TOKEN_PATTERN, re.I)


def find_dates(text: str, prefer_dayfirst: bool = False, year_for=None) -> list[tuple[str, str]]:
    """Every parseable date in free text, as (token, iso)."""
    out = []
    for m in DATE_TOKEN_RE.finditer(text or ""):
        tok = m.group(0)
        iso = parse_date(tok)
        if iso is None:
            fmt, _, _ = detect_date_format([tok], prefer_dayfirst)
            iso = parse_date(tok, fmt, year_for) if fmt else None
        if iso:
            out.append((tok, iso))
    return out


# ── merchants ──────────────────────────────────────────────────────────────────

_MERCHANT_NOISE = {
    "POS", "DEBIT", "CREDIT", "CARD", "PURCHASE", "PURCHASES", "AUTHORIZED", "AUTH", "ON", "ACH", "PPD", "CCD",
    "WEB", "TEL", "ONLINE", "RECURRING", "CHECKCARD", "CHKCARD", "VISA", "MC", "MASTERCARD", "SQ", "TST", "SP",
    "PAYPAL", "PP", "DES", "ID", "INDN", "CO", "ENTRY", "DESCR", "ORIG", "NAME", "WWW", "HTTPS", "HTTP",
    "PREAUTHORIZED", "ELECTRONIC", "TRANSACTION", "TXN", "REF", "THE", "INC", "LLC", "LTD", "COM", "NET", "ORG",
    "TO", "FROM", "FOR", "AT", "OF",
}
_US_STATES = set(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK "
    "OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)


def clean_description(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:200]


def merchant_key(description: str) -> str:
    """Stable grouping key for a merchant: noise, numbers and locations removed.

    "POS PURCHASE WHOLE FOODS MKT #10234 SEATTLE WA" -> "WHOLE FOODS MKT"
    "SQ *BLUE BOTTLE COFFEE 1234"                   -> "BLUE BOTTLE COFFEE"
    """
    upper = clean_description(description).upper()
    tokens = [t for t in re.split(r"[^A-Z0-9&']+", upper) if t]
    kept = []
    for t in tokens:
        if any(ch.isdigit() for ch in t) or re.fullmatch(r"X{2,}", t):
            continue
        if t in _MERCHANT_NOISE or len(t) == 1:
            continue
        kept.append(t.strip("'"))
    while len(kept) > 1 and kept[-1] in _US_STATES:
        kept.pop()
    key = " ".join(kept[:3])
    return key or re.sub(r"[^A-Z ]+", "", upper)[:30].strip() or upper[:30]


def pretty_merchant(key: str) -> str:
    return " ".join(w.capitalize() if len(w) > 3 else w for w in (key or "").split()) or "Unknown"


def merchant_similar(a: str, b: str) -> bool:
    """Two descriptions share a meaningful merchant word."""
    ta = {t for t in merchant_key(a).split() if len(t) >= 3}
    tb = {t for t in merchant_key(b).split() if len(t) >= 3}
    return bool(ta & tb)
