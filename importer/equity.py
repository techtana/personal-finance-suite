"""RSU grant notices: the award agreement an employer sends when it grants restricted stock units.

Read twice, like receipts and pay stubs: by rules (the labelled fields every notice of grant
has) and, when the rules miss something, by the model. A value from the model is kept only if
it appears in the document. The result is one proposed RSU grant for the Plan, with the vest
dates and quantities taken from the document rather than a guessed cliff schedule.

The ticker is never in these documents; the owner types it during review.
"""

from __future__ import annotations

import re

from importer import ai_tools
from importer.core import Ctx, ImportFailure, Proposal
from importer.parsing import parse_date

MILLI = 1000  # shares are stored in thousandths, like the Plan's RSU form

NOT_A_GRANT = (
    "This looks like a stock-plan document, but not an RSU grant notice (with a grant date, the number of units "
    "and the vest dates), which is the one kind Import reads so far. Add or update the grant by hand under Plan "
    "(New entry, type RSU grant or ESPP). If this is really a statement, a receipt or a pay stub, pick that type "
    "above and click Re-read."
)

_NUM = r"([0-9][0-9,]*(?:\.[0-9]+)?)"
_DATE = r"([0-9]{1,4}[-/ .][A-Za-z0-9]{1,9}[-/ .,]{1,2}[0-9]{2,4}|[A-Za-z]{3,9}\.? [0-9]{1,2},? [0-9]{4})"
_SEP = r"\s*[:#]?\s*"

_GRANT_NUMBER = re.compile(r"(?i)\b(?:grant|award)\s+(?:number|no\.?|id|#)" + _SEP + r"([A-Z0-9][A-Z0-9-]{3,})")
_GRANT_DATE = re.compile(r"(?i)\b(?:date\s+of\s+(?:grant|award)|grant\s+date|award\s+date)" + _SEP + _DATE)
# "Total Number of Shares Subject to\n Restricted Stock Units: 125" spans two lines in many notices.
_TOTAL = re.compile(
    r"(?i)\b(?:total\s+number\s+of\s+(?:shares|units|rsus)(?:\s+subject\s+to\s+(?:the\s+)?(?:restricted\s+stock\s+units|award))?"
    r"|number\s+of\s+(?:restricted\s+stock\s+units|rsus|units|shares)\s+(?:granted|awarded)"
    r"|(?:rsus|units|shares)\s+granted)" + _SEP + _NUM)
_VEST_DATE = re.compile(r"(?i)\bvest(?:ing)?\s+date" + _SEP + _DATE)
_VEST_QTY = re.compile(r"(?i)\bvest(?:ing)?\s+(?:quantity|shares|units|amount)" + _SEP + _NUM)
_TABLE_ROW = re.compile(r"^\s*" + _DATE + r"\s{2,}" + _NUM + r"\s*$")
_COMPANY = re.compile(r"^\s*([A-Z][A-Za-z0-9&.,' -]{2,60}?,?\s+(?:INC|CORPORATION|CORP|LTD|LLC|PLC|N\.V|S\.A|AG|SE)\.?)\s*$",
                      re.IGNORECASE)


def _num(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except (AttributeError, ValueError):
        return None


def _milli(value) -> int | None:
    n = _num(str(value)) if value is not None else None
    return int(round(n * MILLI)) if n is not None and n > 0 else None


def is_grant_notice(text: str) -> bool:
    low = text.lower()
    return bool(re.search(r"restricted stock unit|\brsus?\b|stock unit award", low)) and bool(
        _GRANT_DATE.search(text) or re.search(r"notice of (?:restricted stock unit )?grant|award agreement", low))


def read_by_rules(text: str) -> dict:
    out: dict = {"grant_number": None, "grant_date": None, "total": None, "vests": [], "company": None}
    if m := _GRANT_NUMBER.search(text):
        out["grant_number"] = m.group(1)
    if m := _GRANT_DATE.search(text):
        out["grant_date"] = parse_date(m.group(1))
    if m := _TOTAL.search(text):
        out["total"] = _milli(m.group(1))

    dates = [parse_date(m.group(1)) for m in _VEST_DATE.finditer(text)]
    qtys = [_milli(m.group(1)) for m in _VEST_QTY.finditer(text)]
    vests = [{"date": d, "shares": q} for d, q in zip(dates, qtys) if d and q]
    if not vests:
        # A schedule table: "15-Sep-2026     125" under a heading that mentions vesting.
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            if re.search(r"(?i)vest", ln) and not _VEST_DATE.search(ln):
                for row in lines[i + 1:i + 60]:
                    if m := _TABLE_ROW.match(row):
                        d, q = parse_date(m.group(1)), _milli(m.group(2))
                        if d and q:
                            vests.append({"date": d, "shares": q})
                    elif vests and row.strip():
                        break
                if vests:
                    break
    out["vests"] = sorted(vests, key=lambda v: v["date"])

    for ln in text.splitlines()[:25]:
        if (m := _COMPANY.match(ln)) and not re.search(r"(?i)plan|agreement|notice", ln):
            out["company"] = re.sub(r"\s+", " ", m.group(1)).strip().rstrip(",")
            break
    return out


def _appears(value: str, text: str) -> bool:
    flat = re.sub(r"[\s,]", "", text).lower()
    return bool(value) and re.sub(r"[\s,]", "", str(value)).lower() in flat


def read_by_ai(llm, text: str) -> dict | None:
    """The model's reading, keeping only values that appear in the document."""
    raw = ai_tools.read_rsu_grant(llm, text)
    if not raw:
        return None
    out = {"grant_number": None, "grant_date": None, "total": None, "vests": [], "company": None}
    if raw.get("grant_number") and _appears(raw["grant_number"], text):
        out["grant_number"] = raw["grant_number"]
    if raw.get("company") and _appears(raw["company"], text):
        out["company"] = raw["company"]
    if raw.get("grant_date_as_written") and _appears(raw["grant_date_as_written"], text):
        out["grant_date"] = parse_date(raw["grant_date_as_written"])
    if raw.get("total_units_as_written") and _appears(raw["total_units_as_written"], text):
        out["total"] = _milli(raw["total_units_as_written"])
    for v in raw.get("vests") or []:
        d, q = v.get("date_as_written"), v.get("units_as_written")
        if _appears(d, text) and _appears(q, text) and parse_date(d) and _milli(q):
            out["vests"].append({"date": parse_date(d), "shares": _milli(q)})
    out["vests"].sort(key=lambda v: v["date"])
    return out


def fmt_units(milli: int | None) -> str:
    if milli is None:
        return "?"
    units = milli / MILLI
    return f"{units:,.0f}" if units == int(units) else f"{units:,.3f}".rstrip("0")


def from_grant_notice(text: str, ctx: Ctx, existing_rules) -> list[Proposal]:
    if not is_grant_notice(text):
        raise ImportFailure(NOT_A_GRANT)
    rules = read_by_rules(text)
    found = dict(rules)
    source = {k: "rules" for k, v in rules.items() if v}
    if not (rules["grant_date"] and rules["total"] and rules["vests"]):
        ai = ctx.ask(read_by_ai, text, what="read the grant notice")
        if ai:
            for key in ("grant_number", "grant_date", "total", "company", "vests"):
                if not found.get(key) and ai.get(key):
                    found[key], source[key] = ai[key], "ai"
    if not found["vests"] and found["total"]:
        raise ImportFailure("The grant notice was found, but not its vest dates. Add the grant under Plan (New entry, "
                            "type RSU grant) and set the vesting there.")
    if not found["vests"]:
        raise ImportFailure(NOT_A_GRANT)

    vested_total = sum(v["shares"] for v in found["vests"])
    total = found["total"] or vested_total
    checks = []
    p = Proposal(target="rsu_grant", date=found["grant_date"] or found["vests"][0]["date"], amount=None)
    if found["total"] and vested_total != found["total"]:
        p.flag("check_vests", 0.6)
        checks.append(f"The vest quantities add up to {fmt_units(vested_total)} units, but the notice says "
                      f"{fmt_units(found['total'])} in total. Check the vest dates below.")
    else:
        checks.append(f"The vest quantities add up to the {fmt_units(total)} units granted.")
    if not found["grant_date"]:
        p.flag("missing_date", 0.6)
        checks.append("No grant date was found; the first vest date is used instead.")
    if "ai" in source.values():
        p.flag("from_ai", 0.8)

    label = found["company"] or "RSU"
    number = found["grant_number"]
    p.description = (f"{label} RSU grant {number}" if number else f"{label} RSU grant {p.date}")[:200]
    p.note = f"Grant {number}" if number else None
    p.raw = {"kind": "rsu_grant", "grant_number": number, "company": found["company"], "grant_date": found["grant_date"],
             "total_shares": total, "vests": found["vests"], "ticker": _known_ticker(found["company"], existing_rules),
             "sources": source}

    # The same grant number already in the Plan is flagged and unticked by matching.refresh_matches.
    ctx.extracted.update({"kind": "rsu_grant", "checks": checks})
    return [p]


def _known_ticker(company: str | None, existing_rules) -> str:
    """The ticker of an RSU grant already in the Plan from the same company, if there is exactly one."""
    if not company:
        return ""
    tickers = {(r.config or {}).get("ticker") for r in existing_rules
               if r.rule_type == "rsu" and (r.config or {}).get("company") == company and (r.config or {}).get("ticker")}
    return tickers.pop() if len(tickers) == 1 else ""
