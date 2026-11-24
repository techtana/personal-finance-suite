"""The AI toolset: small, single-purpose jobs for a local model.

Why a 9B local model is good enough here — every tool follows the same rules:

1. One narrow question per call. The answer's shape is fixed by a JSON schema,
   with enums for anything that must come from a list (categories, doc types).
2. The model points at evidence (column numbers, line numbers, values copied as
   printed). Code recomputes the stored values from that evidence; a number the
   model made up can't pass, because it won't be found in the document.
3. Every answer goes through a validator. Problems are sent back once as a
   correction; whatever still fails is dropped and flagged, never guessed.
4. No tool writes to the database. The pipeline stages proposals for review.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from importer.llm import LLMError, LLMUnavailable
from importer.parsing import amount_in_text, find_amounts, find_dates, parse_amount, parse_date


@dataclass
class ToolResult:
    data: Any
    problems: list
    ok: bool


def run_tool(llm, task: str, system: str, user: str, schema: dict,
             validate: Callable[[Any], tuple[Any, list]], attempts: int = 2, images=None) -> ToolResult:
    """Ask, validate, send problems back once, return the best validated answer."""
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    best, problems = None, []
    for _ in range(attempts):
        try:
            raw = llm.chat_json(messages, schema, task, images=images)
        except LLMUnavailable:
            raise
        except LLMError as e:
            problems = [f"model error: {e}"]
            continue
        clean, problems = validate(raw)
        best = clean
        if not problems:
            return ToolResult(clean, [], True)
        messages = messages + [
            {"role": "assistant", "content": json.dumps(raw)},
            {"role": "user", "content": "Some of that was rejected by the checker:\n- " + "\n- ".join(problems[:12])
             + "\nAnswer again in the same JSON shape with these fixed. Copy values exactly from the input."},
        ]
    return ToolResult(best, problems, False)


def _obj(props: dict, required=None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props)}


_STR = {"type": "string"}
_INT = {"type": "integer"}
_NUM = {"type": "number"}


# ── 1. transcribe a photo ──────────────────────────────────────────────────────

TRANSCRIBE_PROMPT = (
    "Transcribe all text in this image exactly, line by line, top to bottom. Keep numbers, dates and amounts "
    "exactly as printed, and keep each label on the same line as its value. Output only the text, no commentary."
)


def transcribe(llm, image: bytes) -> str:
    text = llm.chat_text([{"role": "user", "content": TRANSCRIBE_PROMPT}], "transcribe", images=[image])
    text = re.sub(r"^```\w*\s*|\s*```$", "", text.strip())
    if not re.search(r"\d", text):
        raise LLMError("no readable text was found in the photo")
    return text


# ── 2. what kind of document is this ───────────────────────────────────────────

DOC_TYPES = ["statement", "receipt", "payslip", "other"]
_CLASSIFY_SYSTEM = (
    "You sort financial documents into one type.\n"
    "statement: a bank, credit card or brokerage statement or export that lists many transactions.\n"
    "receipt: proof of one purchase or refund at a shop, restaurant, or online store.\n"
    "payslip: a pay stub or earnings statement from an employer with gross pay, deductions and net pay.\n"
    "other: anything else."
)


def classify_document(llm, text: str) -> tuple[str, float] | None:
    schema = _obj({"doc_type": {"type": "string", "enum": DOC_TYPES}, "confidence": _NUM})

    def validate(raw):
        if not isinstance(raw, dict) or raw.get("doc_type") not in DOC_TYPES:
            return None, ["doc_type must be one of " + ", ".join(DOC_TYPES)]
        return (raw["doc_type"], _conf(raw.get("confidence"))), []

    res = run_tool(llm, "classify", _CLASSIFY_SYSTEM, "Document:\n" + text[:3500], schema, validate)
    return res.data


def _conf(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.5


# ── 3. which column is which in a table export ─────────────────────────────────

SIGN_CONVENTIONS = ["negative_is_money_out", "positive_is_money_out", "unknown"]
_MAP_SYSTEM = (
    "You read the layout of a bank or credit card export. For each field give the column number from the list, "
    "or -1 if the file has no such column.\n"
    "amount_col: one column holding signed amounts. If money out and money in are in two separate columns, set "
    "amount_col to -1 and use debit_col (money out) and credit_col (money in).\n"
    "sign_convention: for a single amount column, whether negative numbers are money out (most bank accounts) or "
    "positive numbers are money out (many credit card exports, where purchases are positive and payments negative)."
)


def map_columns(llm, headers: list[str], profiles: list[dict], samples: list[list[str]]) -> ToolResult:
    ncols = len(headers)
    fields = ["date_col", "description_col", "amount_col", "debit_col", "credit_col", "balance_col", "category_col"]
    schema = _obj({**{f: _INT for f in fields}, "sign_convention": {"type": "string", "enum": SIGN_CONVENTIONS}})
    lines = []
    for i, (h, p) in enumerate(zip(headers, profiles)):
        lines.append(f"Column {i} {h!r}: {p['summary']}")
    user = ("Columns:\n" + "\n".join(lines) + "\n\nFirst rows:\n"
            + "\n".join(" | ".join(r[:ncols]) for r in samples[:6]))

    def looks(kind):
        return [f"{i} ({headers[i]!r})" for i, p in enumerate(profiles) if p[kind] >= 0.8] or ["none"]

    def validate(raw):
        if not isinstance(raw, dict):
            return None, ["answer must be a JSON object"]
        m, problems = {}, []
        for f in fields:
            try:
                v = int(raw.get(f, -1))
            except (TypeError, ValueError):
                v = -1
            if not -1 <= v < ncols:
                problems.append(f"{f}={v} is not a column number (0-{ncols - 1}) or -1")
                v = -1
            m[f] = None if v == -1 else v
        m["sign_convention"] = raw.get("sign_convention") if raw.get("sign_convention") in SIGN_CONVENTIONS else "unknown"
        d = m["date_col"]
        if d is None or profiles[d]["date_rate"] < 0.8:
            problems.append(f"date_col must be a column whose values are dates; columns that look like dates: "
                            f"{', '.join(looks('date_rate'))}")
        desc = m["description_col"]
        if desc is None or profiles[desc]["text_rate"] < 0.5:
            problems.append("description_col must be a text column with the payee or description")
        if m["amount_col"] is not None:
            if profiles[m["amount_col"]]["amount_rate"] < 0.8:
                problems.append(f"amount_col {m['amount_col']} doesn't hold amounts; columns that look like amounts: "
                                f"{', '.join(looks('amount_rate'))}")
        elif m["debit_col"] is None and m["credit_col"] is None:
            problems.append("give amount_col, or debit_col and credit_col")
        else:
            for f in ("debit_col", "credit_col"):
                c = m[f]
                if c is not None and profiles[c]["amount_rate_nonempty"] < 0.9:
                    problems.append(f"{f} {c} doesn't hold amounts")
        used = [m[f] for f in ("date_col", "description_col", "amount_col", "debit_col", "credit_col") if m[f] is not None]
        if len(used) != len(set(used)):
            problems.append("date, description and amount fields must be different columns")
        return m, problems

    return run_tool(llm, "map_columns", _MAP_SYSTEM, user, schema, validate)


# ── 4. transactions in free-text statement lines ───────────────────────────────

_LINES_SYSTEM = (
    "These are numbered lines from a bank or credit card statement. List every line that is one transaction: its "
    "line number, the date as printed, the description, the amount as printed, and whether money came in or went "
    "out. Use the section headings (Deposits, Withdrawals, Payments, Purchases, Credits, Debits) and minus signs to "
    "decide the direction. Skip headings, balances, totals and summaries."
)


def extract_statement_lines(llm, numbered: list[tuple[int, str]], prefer_dayfirst=False, year_for=None) -> ToolResult:
    by_no = dict(numbered)
    schema = _obj({"transactions": {"type": "array", "items": _obj({
        "line": _INT, "date": _STR, "description": _STR, "amount": _STR,
        "direction": {"type": "string", "enum": ["in", "out", "unknown"]}})}})
    user = "\n".join(f"{n}: {t}" for n, t in numbered)

    def validate(raw):
        items = (raw or {}).get("transactions") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            return [], ["answer must have a transactions list"]
        clean, problems, seen = [], [], set()
        for it in items:
            if not isinstance(it, dict):
                continue
            n = it.get("line")
            line = by_no.get(n)
            if line is None:
                problems.append(f"line {n} is not one of the numbered lines")
                continue
            if n in seen:
                continue
            cents = parse_amount(str(it.get("amount", "")), decimal_comma=False)
            if cents is None or not amount_in_text(cents, line):
                problems.append(f"line {n}: amount {it.get('amount')!r} is not on that line")
                continue
            dates = find_dates(line, prefer_dayfirst, year_for)
            if not dates:
                problems.append(f"line {n}: there is no date on that line, so it isn't a transaction")
                continue
            seen.add(n)
            clean.append({"line": n, "date": dates[0][1], "description": str(it.get("description") or ""),
                          "amount": abs(cents), "direction": it.get("direction") or "unknown",
                          "explicit_negative": cents < 0})
        return clean, problems

    return run_tool(llm, "statement_lines", _LINES_SYSTEM, user, schema, validate)


# ── 5. receipt ─────────────────────────────────────────────────────────────────

_RECEIPT_SYSTEM = (
    "Read this receipt and copy values exactly as printed. total is the final amount paid (after tax and tip), not "
    "the subtotal. merchant is the shop or restaurant name at the top. items: each purchased line with its price. "
    "card_last4: the last 4 digits of the card if shown. is_refund: true only for a refund or return. "
    "category: what most of the purchase is. Use \"\" only when a value really isn't on the receipt.\n"
    "Example: the line 'TOTAL   28.98' gives \"total\": \"28.98\"."
)


def read_receipt(llm, text: str, categories: dict) -> ToolResult:
    slugs = sorted(categories)
    schema = _obj({
        "merchant": _STR, "date": _STR, "total": _STR, "subtotal": _STR, "tax": _STR, "tip": _STR,
        "is_refund": {"type": "boolean"}, "card_last4": _STR,
        "category": {"type": "string", "enum": slugs},
        "items": {"type": "array", "items": _obj({"description": _STR, "amount": _STR})},
    })
    user = ("Categories: " + ", ".join(f"{s} ({categories[s]['label']})" for s in slugs)
            + "\n\nReceipt:\n" + text[:6000])
    text_dates = {iso for _, iso in find_dates(text)}

    def validate(raw):
        if not isinstance(raw, dict):
            return None, ["answer must be a JSON object"]
        out, problems = {"merchant": str(raw.get("merchant") or "").strip()[:100]}, []
        total = parse_amount(raw.get("total") or "", decimal_comma=False)
        if total is None or not amount_in_text(total, text):
            problems.append(f"total {raw.get('total')!r} isn't printed on the receipt; copy the amount next to TOTAL")
            total = None
        out["total"] = abs(total) if total is not None else None
        for f in ("subtotal", "tax", "tip"):
            v = parse_amount(raw.get(f) or "", decimal_comma=False)
            if v is not None and not amount_in_text(v, text):
                problems.append(f"{f} {raw.get(f)!r} isn't printed on the receipt; use \"\" if it isn't there")
                v = None
            out[f] = abs(v) if v is not None else None
        d = _ground_date(raw.get("date"), text_dates)
        if raw.get("date") and d is None:
            problems.append(f"date {raw.get('date')!r} isn't a date printed on the receipt")
        out["date"] = d
        out["is_refund"] = bool(raw.get("is_refund"))
        last4 = re.sub(r"\D", "", str(raw.get("card_last4") or ""))[-4:]
        out["card_last4"] = last4 if len(last4) == 4 and last4 in text else None
        out["category"] = raw.get("category") if raw.get("category") in categories else None
        items = []
        for it in raw.get("items") or []:
            if not isinstance(it, dict):
                continue
            a = parse_amount(it.get("amount") or "", decimal_comma=False)
            if a is not None and amount_in_text(a, text):
                items.append({"description": str(it.get("description") or "")[:80], "amount": a})
        out["items"] = items
        return out, problems

    return run_tool(llm, "read_receipt", _RECEIPT_SYSTEM, user, schema, validate)


def _ground_date(value, text_dates: set) -> str | None:
    """The model's date, only if it is one of the dates printed in the document."""
    if not value:
        return None
    candidates = {iso for _, iso in find_dates(str(value))}
    iso = parse_date(value)
    if iso:
        candidates.add(iso)
    hits = candidates & text_dates
    return sorted(hits)[0] if hits else None


# ── 6. pay stub ────────────────────────────────────────────────────────────────

_PAYSLIP_SYSTEM = (
    "Read this pay stub and copy values exactly as printed. Pay stubs have a CURRENT column (this pay period) and "
    "a YTD column (year to date). Always take the CURRENT amount: the first amount after the label.\n"
    "gross_pay: Gross Pay or Total Earnings for this period. net_pay: Net Pay (take-home) for this period.\n"
    "deductions: every line taken out of gross pay (taxes, 401k, ESPP, insurance), each with its amount; not the "
    "'Total Deductions' line.\n"
    "employer_contributions: money the employer adds that isn't in the paycheck, such as a 401k match or HSA.\n"
    "Dates as printed. Use \"\" only when a value really isn't on the pay stub.\n"
    "Example: the line 'Federal Income Tax   640.00   13,440.00' becomes "
    "{\"name\": \"Federal Income Tax\", \"amount\": \"640.00\", \"kind\": \"tax\"}."
)


def read_payslip(llm, text: str) -> ToolResult:
    schema = _obj({
        "employer": _STR, "pay_date": _STR, "period_start": _STR, "period_end": _STR,
        "gross_pay": _STR, "net_pay": _STR,
        "deductions": {"type": "array", "items": _obj({
            "name": _STR, "amount": _STR,
            "kind": {"type": "string", "enum": ["tax", "retirement", "stock_plan", "health", "other"]}})},
        "employer_contributions": {"type": "array", "items": _obj({
            "name": _STR, "amount": _STR, "kind": {"type": "string", "enum": ["retirement", "health", "other"]}})},
    })
    text_dates = {iso for _, iso in find_dates(text)}

    def validate(raw):
        if not isinstance(raw, dict):
            return None, ["answer must be a JSON object"]
        out, problems = {"employer": str(raw.get("employer") or "").strip()[:100]}, []
        for f in ("gross_pay", "net_pay"):
            v = parse_amount(raw.get(f) or "", decimal_comma=False)
            if v is not None and not amount_in_text(v, text):
                problems.append(f"{f} {raw.get(f)!r} isn't printed on the pay stub")
                v = None
            out[f] = abs(v) if v is not None else None
        if out["net_pay"] is None:
            problems.append("net_pay is required: the take-home amount for this period")
        for f in ("pay_date", "period_start", "period_end"):
            d = _ground_date(raw.get(f), text_dates)
            if raw.get(f) and d is None:
                problems.append(f"{f} {raw.get(f)!r} isn't a date printed on the pay stub")
            out[f] = d
        for group in ("deductions", "employer_contributions"):
            kept = []
            for it in raw.get(group) or []:
                if not isinstance(it, dict) or re.search(r"(?i)\btotal\b", str(it.get("name") or "")):
                    continue  # "Total Deductions" would double count
                a = parse_amount(it.get("amount") or "", decimal_comma=False)
                if a is None:
                    if it.get("name"):
                        problems.append(f"{group}: {it.get('name')!r} has no amount; copy its CURRENT amount")
                    continue
                if a == 0:
                    continue
                if not amount_in_text(a, text):
                    problems.append(f"{group}: {it.get('name')!r} amount {it.get('amount')!r} isn't on the pay stub")
                    continue
                kept.append({"name": str(it.get("name") or "")[:60], "amount": abs(a), "kind": it.get("kind") or "other"})
            out[group] = kept
        return out, problems

    return run_tool(llm, "read_payslip", _PAYSLIP_SYSTEM, "Pay stub:\n" + text[:7000], schema, validate)


# ── 7. categories ──────────────────────────────────────────────────────────────

_CATEGORIZE_SYSTEM = (
    "You categorize bank transactions for a personal budget. Pick one category slug for each item from the list. "
    "Money in usually gets an income category; a refund from a shop may keep the shop's category. Moving money "
    "between the person's own accounts, and paying off a credit card, is 'transfer'. If unsure, use 'misc' with a "
    "low confidence. confidence is 0 to 1."
)
BATCH = 25


def categorize(llm, items: list[dict], categories: dict) -> dict[int, tuple[str, float]]:
    """items: [{i, description, amount (cents), hint}] -> {i: (slug, confidence)}"""
    from importer.taxonomy import fits_direction

    slugs = sorted(categories)
    schema = _obj({"items": {"type": "array", "items": _obj({
        "i": _INT, "category": {"type": "string", "enum": slugs}, "confidence": _NUM})}})
    cat_lines = "\n".join(
        f"{s}: {categories[s]['label']} ({ {'income': 'money in', 'expense': 'money out', 'both': 'either'}.get(categories[s]['type'], 'either') })"
        for s in slugs)
    result: dict[int, tuple[str, float]] = {}
    for start in range(0, len(items), BATCH):
        chunk = items[start : start + BATCH]
        by_i = {it["i"]: it for it in chunk}
        user = "Categories:\n" + cat_lines + "\n\nTransactions:\n" + "\n".join(
            f"{it['i']}: {it['description']} | {'money in' if it['amount'] > 0 else 'money out'} "
            f"{abs(it['amount']) / 100:.2f}" + (f" | hint: {it['hint']}" if it.get("hint") else "")
            for it in chunk)

        def validate(raw, by_i=by_i):
            answers = raw.get("items") if isinstance(raw, dict) else None
            if not isinstance(answers, list):
                return {}, ["answer must have an items list"]
            clean, problems = {}, []
            for a in answers:
                if not isinstance(a, dict) or a.get("i") not in by_i:
                    continue
                cat = a.get("category")
                if cat not in categories:
                    problems.append(f"i={a.get('i')}: {cat!r} is not in the category list")
                    continue
                if not fits_direction(cat, by_i[a["i"]]["amount"], categories):
                    problems.append(f"i={a['i']}: {cat!r} is an income category but this is money out")
                    continue
                clean[a["i"]] = (cat, _conf(a.get("confidence")))
            missing = [i for i in by_i if i not in clean]
            if missing and not problems:
                problems.append("no valid answer for i=" + ", ".join(map(str, missing)))
            return clean, problems

        res = run_tool(llm, "categorize", _CATEGORIZE_SYSTEM, user, schema, validate)
        result.update(res.data or {})
    return result


__all__ = [
    "ToolResult", "run_tool", "transcribe", "classify_document", "map_columns", "extract_statement_lines",
    "read_receipt", "read_payslip", "categorize", "find_amounts", "DOC_TYPES",
]
