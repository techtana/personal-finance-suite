"""Statements: many transactions from a table export, an OFX file or statement text.

Order of trust for a table's layout: a layout saved from an earlier import of
the same header row, then header-name and content rules, then the AI (checked
against every row). The chosen layout is then applied to every row by code, so
the AI never touches individual amounts.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import date, timedelta
from statistics import median

from importer import ai_tools
from importer.core import Ctx, ImportFailure, Proposal
from importer.parsing import (
    clean_description, detect_date_format, detect_decimal_comma, find_amounts, find_dates, fmt_cents,
    merchant_key, parse_amount, parse_date, pretty_merchant, year_resolver, DATE_TOKEN_PATTERN, DATE_TOKEN_RE,
)
from importer.taxonomy import STARTER_CATEGORIES, keyword_category

# ── header vocabulary ──────────────────────────────────────────────────────────

DATE_HEADERS = ["transaction date", "trans date", "date", "posted date", "posting date", "post date", "value date",
                "booking date", "date posted", "effective date", "txn date", "settlement date"]
DESC_HEADERS = ["description", "transaction description", "original description", "payee", "merchant",
                "merchant name", "name", "narrative", "particulars", "details", "memo", "transaction", "reference"]
AMOUNT_HEADERS = ["amount", "transaction amount", "amt", "net amount", "value", "billing amount"]
DEBIT_HEADERS = ["debit", "debits", "withdrawal", "withdrawals", "money out", "paid out", "outflow", "charge",
                 "charges", "debit amount", "withdrawal amount", "spent", "out"]
CREDIT_HEADERS = ["credit", "credits", "deposit", "deposits", "money in", "paid in", "inflow", "credit amount",
                  "deposit amount", "received", "in"]
BALANCE_HEADERS = ["balance", "running bal", "running balance", "available balance", "ledger balance",
                   "closing balance", "account balance"]
CATEGORY_HEADERS = ["category", "transaction category", "merchant category"]
DIRECTION_HEADERS = ["details", "type", "transaction type", "dr/cr", "cr/dr", "debit/credit", "credit/debit",
                     "debit or credit", "indicator"]
ID_HEADERS = ["transaction id", "reference number", "reference no", "ref", "fitid", "id", "transaction reference"]
MEMO_HEADERS = ["memo", "notes", "note", "extended description"]
DIRECTION_VALUES = {"debit": -1, "dr": -1, "withdrawal": -1, "debit card": -1, "payment": -1, "out": -1,
                    "credit": 1, "cr": 1, "deposit": 1, "in": 1}
SUMMARY_WORDS = re.compile(
    r"(?i)^\s*(?:total|totals|subtotal|beginning balance|opening balance|ending balance|closing balance|"
    r"previous balance|new balance|balance forward|statement balance|pending)\b")


def _norm_header(h: str) -> str:
    h = re.sub(r"\(.*?\)", "", str(h or "").lower())
    h = re.sub(r"[^a-z/ ]+", " ", h)
    return re.sub(r"\s+", " ", h).strip()


def _header_rank(header: str, vocab: list[str]) -> int | None:
    h = _norm_header(header)
    if not h:
        return None
    if h in vocab:
        return vocab.index(h)
    for i, v in enumerate(vocab):
        if len(v) > 3 and re.search(rf"\b{re.escape(v)}\b", h):
            return 50 + i
    return None


def header_signature(headers: list[str]) -> str:
    return hashlib.sha256("|".join(_norm_header(h) for h in headers).encode()).hexdigest()[:32]


# ── table structure ────────────────────────────────────────────────────────────

def _is_value(cell: str) -> bool:
    return bool(cell) and (parse_amount(cell) is not None or parse_date(cell) is not None)


def detect_header(rows: list[list[str]]) -> tuple[list[str], list[list[str]], bool, list[list[str]]]:
    """(headers, data rows, has_header, preamble). Skips the lines banks put above the table."""
    useful = [r for r in rows if sum(1 for c in r if c) >= 2]
    if not useful:
        raise ImportFailure("The file has no rows with data.")
    width = Counter(len(r) for r in useful[:80]).most_common(1)[0][0]
    for idx, row in enumerate(rows[:40]):
        cells = [c for c in row if c]
        if len(row) < max(2, width - 1) or len(cells) < 2:
            continue
        if any(_is_value(c) for c in cells):
            continue  # a data row, not a header
        if sum(1 for c in cells if re.search(r"[A-Za-z]", c)) < 0.6 * len(cells):
            continue
        nxt = next((r for r in rows[idx + 1 : idx + 4] if sum(1 for c in r if c) >= 2), None)
        if nxt is None or not any(_is_value(c) for c in nxt):
            continue
        headers = [c.strip() or f"Column {i + 1}" for i, c in enumerate(row)]
        data = [r for r in rows[idx + 1 :] if sum(1 for c in r if c) >= 2]
        return headers, [_pad(r, len(headers)) for r in data], True, rows[:idx]
    headers = [f"Column {i + 1}" for i in range(width)]
    return headers, [_pad(r, width) for r in useful], False, []


def _pad(row, n):
    return (list(row) + [""] * n)[:n] if len(row) < n else list(row[:n])


def profile_columns(headers: list[str], data: list[list[str]], prefer_dayfirst=False) -> list[dict]:
    """What each column's values look like, for rules and for the AI prompt."""
    out = []
    for i, h in enumerate(headers):
        values = [r[i] if i < len(r) else "" for r in data]
        nonempty = [v for v in values if v.strip()]
        n, ne = max(len(values), 1), max(len(nonempty), 1)
        fmt, date_rate, _ = detect_date_format(nonempty[:300], prefer_dayfirst) if nonempty else (None, 0.0, False)
        amounts = [parse_amount(v) for v in nonempty]
        parsed = sum(1 for a in amounts if a is not None)
        if date_rate >= 0.8:
            parsed = 0
        decimals = sum(1 for v in nonempty if re.search(r"[.,]\d{2}\b", v))
        text = sum(1 for v in nonempty if len(re.findall(r"[A-Za-z]", v)) >= 3)
        distinct = len(set(nonempty)) / ne
        p = {
            "date_rate": date_rate if nonempty else 0.0, "date_format": fmt,
            "amount_rate": parsed / n, "amount_rate_nonempty": parsed / ne if nonempty else 0.0,
            "decimals_rate": decimals / ne if nonempty else 0.0,
            "text_rate": text / ne if nonempty else 0.0, "fill": len(nonempty) / n, "distinct": distinct,
            "avg_len": sum(len(v) for v in nonempty) / ne if nonempty else 0.0,
            "positive_share": (sum(1 for a in amounts if a is not None and a > 0) / max(parsed, 1)) if parsed else 0.0,
        }
        examples = ", ".join(repr(v[:40]) for v in nonempty[:3])
        kind = ("dates" if p["date_rate"] >= 0.8 else "amounts" if p["amount_rate_nonempty"] >= 0.8 else
                "text" if p["text_rate"] >= 0.5 else "mixed")
        p["summary"] = f"{int(p['fill'] * 100)}% filled, mostly {kind}, e.g. {examples or 'empty'}"
        out.append(p)
    return out


def heuristic_map(headers: list[str], profiles: list[dict]) -> dict:
    m = {"date_col": None, "description_col": None, "amount_col": None, "debit_col": None, "credit_col": None,
         "balance_col": None, "category_col": None, "direction_col": None, "id_col": None, "memo_col": None}
    by_header = 0
    taken: set[int] = set()

    def best(vocab, ok, exclude=()):
        ranked = []
        for i, h in enumerate(headers):
            if i in taken or i in exclude:
                continue
            r = _header_rank(h, vocab)
            if r is not None and ok(profiles[i]):
                ranked.append((r, i))
        return min(ranked)[1] if ranked else None

    m["date_col"] = best(DATE_HEADERS, lambda p: p["date_rate"] >= 0.8)
    if m["date_col"] is not None:
        by_header += 1
    else:
        cands = [(p["date_rate"], -i, i) for i, p in enumerate(profiles) if p["date_rate"] >= 0.9]
        m["date_col"] = max(cands)[2] if cands else None
    if m["date_col"] is not None:
        taken.add(m["date_col"])

    m["balance_col"] = best(BALANCE_HEADERS, lambda p: p["amount_rate_nonempty"] >= 0.8)
    if m["balance_col"] is not None:
        taken.add(m["balance_col"])

    m["amount_col"] = best(AMOUNT_HEADERS, lambda p: p["amount_rate"] >= 0.8)
    if m["amount_col"] is not None:
        by_header += 1
        taken.add(m["amount_col"])
    else:
        m["debit_col"] = best(DEBIT_HEADERS, lambda p: p["amount_rate_nonempty"] >= 0.9)
        if m["debit_col"] is not None:
            taken.add(m["debit_col"])
        m["credit_col"] = best(CREDIT_HEADERS, lambda p: p["amount_rate_nonempty"] >= 0.9)
        if m["credit_col"] is not None:
            taken.add(m["credit_col"])
        if m["debit_col"] is not None or m["credit_col"] is not None:
            by_header += 1
        else:
            cands = [i for i, p in enumerate(profiles) if i not in taken and p["amount_rate"] >= 0.9
                     and p["decimals_rate"] >= 0.5]
            if len(cands) == 1:
                m["amount_col"] = cands[0]
                taken.add(cands[0])

    m["description_col"] = best(DESC_HEADERS, lambda p: p["text_rate"] >= 0.5 and (p["distinct"] >= 0.2 or p["fill"] < 1))
    if m["description_col"] is not None:
        by_header += 1
    else:
        cands = [(p["text_rate"] * p["avg_len"] * p["distinct"], i) for i, p in enumerate(profiles)
                 if i not in taken and p["text_rate"] >= 0.5]
        m["description_col"] = max(cands)[1] if cands else None
    if m["description_col"] is not None:
        taken.add(m["description_col"])

    m["category_col"] = best(CATEGORY_HEADERS, lambda p: p["text_rate"] >= 0.5)
    m["id_col"] = best(ID_HEADERS, lambda p: p["fill"] >= 0.5)
    m["memo_col"] = best(MEMO_HEADERS, lambda p: p["text_rate"] >= 0.3, exclude=(m["description_col"],))
    m["direction_col"] = best(DIRECTION_HEADERS, lambda p: p["distinct"] <= 0.2 or p["fill"] < 0.5)

    complete = m["date_col"] is not None and m["description_col"] is not None and (
        m["amount_col"] is not None or m["debit_col"] is not None or m["credit_col"] is not None)
    m["confidence"] = 0.0 if not complete else (1.0 if by_header >= 3 else 0.7)
    return m


# ── sign convention ────────────────────────────────────────────────────────────

_IN_HINT = re.compile(r"(?i)\bpayroll\b|\bdir(?:ect)? ?dep|\bsalary\b|\binterest (?:paid|earned)\b|\brefund\b|"
                      r"\bpayment,? thank you\b|\bpayment received\b|\bthank you\b|\bcash ?back\b|\bdeposit\b")
_OUT_HINT = re.compile(r"(?i)\bpurchase\b|\bpos\b|\bdebit card\b|\batm withdrawal\b|\bwithdrawal\b|\bfee\b|\bcheck #?\d")
_STARTER_TYPES = {slug: typ for slug, _, typ, _ in STARTER_CATEGORIES}


def _direction_hint(desc: str) -> str | None:
    if _IN_HINT.search(desc):
        return "in"
    if _OUT_HINT.search(desc):
        return "out"
    cat = keyword_category(desc, None)
    if cat and _STARTER_TYPES.get(cat) == "expense" and cat != "refund":
        return "out"
    if cat in ("salary", "interest"):
        return "in"
    return None


def detect_sign(amounts: list[int], descriptions: list[str], account=None) -> tuple[str, str, bool]:
    """(convention, explanation, confident) for a single signed amount column."""
    normal = flipped = 0
    for a, d in zip(amounts, descriptions):
        if not a:
            continue
        hint = _direction_hint(d)
        if hint == "in":
            normal, flipped = (normal + 1, flipped) if a > 0 else (normal, flipped + 1)
        elif hint == "out":
            normal, flipped = (normal + 1, flipped) if a < 0 else (normal, flipped + 1)
    if normal + flipped >= 2:
        if flipped > 2 * normal:
            return "positive_is_money_out", f"{flipped} of {normal + flipped} recognisable rows (shops, payments) " \
                                            "only make sense if positive amounts are money out", True
        if normal > 2 * flipped:
            return "negative_is_money_out", "recognisable rows agree that negative amounts are money out", True
    nonzero = [a for a in amounts if a]
    pos_share = sum(1 for a in nonzero if a > 0) / max(len(nonzero), 1)
    is_card = bool(account) and re.search(r"credit|card", f"{account.type} {account.name}", re.I)
    if pos_share >= 0.85 and is_card:
        return "positive_is_money_out", "almost every amount is positive and the account is a card", False
    if pos_share >= 0.85:
        return "negative_is_money_out", "almost every amount is positive, which is unusual for a bank account", False
    return "negative_is_money_out", "negative amounts are money out", True


# ── table → proposals ──────────────────────────────────────────────────────────

def from_table(rows: list[list[str]], ctx: Ctx) -> list[Proposal]:
    from models import ImportProfile

    headers, data, has_header, preamble = detect_header(rows)
    if not data:
        raise ImportFailure("The table has a header but no rows.")
    # Hints for which account this is: "Account: Everyday Checking ...1234" above the table, or a card-number column.
    pre = " ".join(c for r in preamble for c in r if c)
    if pre:
        ctx.extracted["account_text"] = pre[:400]
        m = re.search(r"(?i)(?:\.{2,}|…|x{2,}|\*{2,}|ending in\s*|#)\s*(\d{4})\b", pre)
        if m:
            ctx.extracted["account_hint"] = m.group(1)
    for i, h in enumerate(headers):
        if re.search(r"(?i)card|account", h):
            vals = {r[i].strip() for r in data if r[i].strip()}
            if len(vals) == 1 and re.fullmatch(r"\d{4}", next(iter(vals))):
                ctx.extracted["account_hint"] = next(iter(vals))
    profiles = profile_columns(headers, data, ctx.prefer_dayfirst)
    signature = header_signature(headers) if has_header else None
    override = ctx.overrides.get("mapping")
    # Kept even if reading fails, so the review screen can offer the columns to pick from.
    ctx.mapping = {"headers": headers, "has_header": has_header, "signature": signature,
                   "sample": [r[:len(headers)] for r in data[:5]], "columns": [p["summary"] for p in profiles]}

    mapping, source = None, None
    if override:
        mapping, source = dict(override), "user"
    if mapping is None and signature:
        prof = ImportProfile.query.filter_by(signature=signature).first()
        if prof:
            mapping, source = dict(prof.mapping), "saved"
            if prof.account_id and not ctx.account:
                ctx.suggested_account_id = prof.account_id
            ctx.info("Read with the column layout saved from your last import of this kind of file.")
    if mapping is None:
        mapping = heuristic_map(headers, profiles)
        source = "rules"
        if mapping["confidence"] < 1.0:
            ctx.stage("Asking the local AI which column is which")
            res = ctx.ask(ai_tools.map_columns, headers, profiles, data[:6], what="work out the columns")
            if res is not None and res.ok:
                ai = res.data
                for k in ("date_col", "description_col", "amount_col", "debit_col", "credit_col", "balance_col",
                          "category_col"):
                    mapping[k] = ai[k]
                if ai["sign_convention"] != "unknown":
                    mapping["ai_sign"] = ai["sign_convention"]
                source = "ai"
                ctx.info("The local AI worked out which column is which; check the layout below.")
            elif mapping["confidence"] == 0.0:
                why = "; ".join(res.problems[:3]) if res is not None else "the local AI is unavailable"
                raise ImportFailure(
                    "Couldn't tell which columns hold the date, description and amount "
                    f"({why}). Pick them under 'How this file was read' and re-read.")
    for k in ("date_col", "description_col", "amount_col", "debit_col", "credit_col", "balance_col", "category_col",
              "direction_col", "id_col", "memo_col"):
        v = mapping.get(k)
        mapping[k] = v if isinstance(v, int) and 0 <= v < len(headers) else None
    if mapping["date_col"] is None or mapping["description_col"] is None or (
            mapping["amount_col"] is None and mapping["debit_col"] is None and mapping["credit_col"] is None):
        raise ImportFailure("The column layout is incomplete: it needs a date, a description and an amount column.")

    date_values = [r[mapping["date_col"]] for r in data]
    fmt, rate, ambiguous = detect_date_format([v for v in date_values if v.strip()], ctx.prefer_dayfirst)
    if mapping.get("date_format") and source in ("user", "saved"):
        fmt = mapping["date_format"]
    elif ambiguous:
        ctx.warn("Every date in this file works both as month/day and day/month. Read as "
                 f"{'day/month' if ctx.prefer_dayfirst else 'month/day'} from your locale setting; switch it under "
                 "'How this file was read' if that's wrong.")
    mapping["date_format"] = fmt
    year_for = year_resolver()

    amount_cols = [c for c in (mapping["amount_col"], mapping["debit_col"], mapping["credit_col"]) if c is not None]
    dc = detect_decimal_comma([r[c] for r in data for c in amount_cols])
    mapping["decimal_comma"] = dc

    parsed = []
    for r in data:
        iso = parse_date(r[mapping["date_col"]], fmt, year_for) if fmt else None
        desc = clean_description(r[mapping["description_col"]])
        if mapping.get("memo_col") is not None and r[mapping["memo_col"]].strip() and r[mapping["memo_col"]] not in desc:
            desc = clean_description(f"{desc} {r[mapping['memo_col']]}")
        if mapping["amount_col"] is not None:
            amt = parse_amount(r[mapping["amount_col"]], dc)
            if amt is not None and mapping.get("direction_col") is not None:
                d = DIRECTION_VALUES.get(r[mapping["direction_col"]].strip().lower())
                if d is not None:
                    amt = abs(amt) * d
        else:
            deb = parse_amount(r[mapping["debit_col"]], dc) if mapping["debit_col"] is not None else None
            cre = parse_amount(r[mapping["credit_col"]], dc) if mapping["credit_col"] is not None else None
            amt = None if deb is None and cre is None else abs(cre or 0) - abs(deb or 0)
        bal = parse_amount(r[mapping["balance_col"]], dc) if mapping["balance_col"] is not None else None
        parsed.append((r, iso, desc, amt, bal))

    single = mapping["amount_col"] is not None and mapping.get("direction_col") is None
    if single:
        if mapping.get("sign_convention") and source in ("user", "saved"):
            sign = mapping["sign_convention"]
        else:
            sign, why, confident = detect_sign([p[3] for p in parsed], [p[2] for p in parsed], ctx.account)
            if not confident and mapping.get("ai_sign") in ("negative_is_money_out", "positive_is_money_out"):
                sign, why = mapping["ai_sign"], "the local AI's reading of the rows"
            if not confident:
                ctx.warn(f"Guessed which amounts are money out ({why}). If incomes show as spending, use "
                         "'Flip signs'.")
                mapping["sign_guessed"] = True
        mapping["sign_convention"] = sign
        if sign == "positive_is_money_out":
            parsed = [(r, iso, desc, -amt if amt is not None else None, bal) for r, iso, desc, amt, bal in parsed]
    mapping.update({**ctx.mapping, "source": source})
    ctx.mapping = mapping

    proposals, ignored = [], 0
    for r, iso, desc, amt, bal in parsed:
        if iso is None and (SUMMARY_WORDS.search(desc) or not desc):
            ignored += 1
            continue
        p = Proposal(date=iso, description=desc or "(no description)", amount=amt, merchant_key=merchant_key(desc),
                     raw={"cells": r}, confidence=0.95 if source in ("rules", "saved", "user") else 0.85)
        if mapping.get("category_col") is not None:
            p.hint = r[mapping["category_col"]] or None
        if mapping.get("id_col") is not None:
            p.external_id = r[mapping["id_col"]][:100] or None
        if iso is None:
            p.flag("unparsed_date", 0.2)
        if amt is None:
            p.flag("unparsed_amount", 0.2)
        elif amt == 0:
            p.flag("zero_amount")
        if mapping.get("sign_guessed"):
            p.flag("sign_guessed", 0.7)
        if ambiguous and not (source in ("user", "saved")):
            p.flag("ambiguous_date", 0.8)
        proposals.append(p)
    if ignored:
        ctx.info(f"Left out {ignored} summary or blank line(s) such as totals and balances.")

    # Closing balance -> balance snapshot proposal
    with_bal = [(iso, bal, i) for i, (_, iso, _, _, bal) in enumerate(parsed) if iso and bal is not None]
    if with_bal:
        dates = [d for d, _, _ in with_bal]
        newest = max(dates)
        descending = dates[0] >= dates[-1]
        same_day = [x for x in with_bal if x[0] == newest]
        iso, bal, _ = same_day[0] if descending else same_day[-1]
        proposals.append(balance_proposal(iso, bal, "running balance column"))
    return proposals


def balance_proposal(iso: str, cents: int, source: str) -> Proposal:
    p = Proposal(target="snapshot", date=iso, amount=cents, description=f"Balance on {iso}",
                 note=f"Statement balance ({source})", confidence=0.95)
    if cents < 0:
        p.flag("negative_balance")
    return p


# ── OFX → proposals ────────────────────────────────────────────────────────────

def from_ofx(ofx: dict, ctx: Ctx) -> list[Proposal]:
    proposals = []
    for t in ofx["transactions"]:
        name, memo = clean_description(t["name"]), clean_description(t["memo"])
        desc = name or memo or t["trntype"] or "(no description)"
        p = Proposal(date=t["date"], description=desc, amount=t["amount"], merchant_key=merchant_key(desc),
                     external_id=(t["fitid"] or None), raw=t, confidence=0.97,
                     note=memo if memo and memo.lower() not in desc.lower() else None)
        if t["date"] is None:
            p.flag("unparsed_date", 0.2)
        if t["amount"] is None:
            p.flag("unparsed_amount", 0.2)
        elif t["amount"] == 0:
            p.flag("zero_amount")
        proposals.append(p)
    bal = ofx.get("balance")
    if bal and bal.get("amount") is not None:
        iso = bal.get("date") or max((t["date"] for t in ofx["transactions"] if t["date"]), default=None)
        if iso:
            proposals.append(balance_proposal(iso, bal["amount"], "OFX ledger balance"))
    ctx.mapping = {"source": "ofx", "ofx_account": _mask(ofx.get("account_id")), "account_type": ofx.get("account_type")}
    return proposals


def _mask(acct: str | None) -> str | None:
    return f"…{acct[-4:]}" if acct and len(acct) >= 4 else None


# ── statement text (PDF or pasted) → proposals ─────────────────────────────────

_IN_SECTION = re.compile(r"(?i)\b(deposits?|credits?|additions|payments(?: and| &) (?:other )?credits|money in|paid in|"
                         r"interest (?:paid|earned))\b")
_OUT_SECTION = re.compile(r"(?i)\b(withdrawals?|debits?|purchases?|checks? paid|fees|charges|money out|paid out|"
                          r"card transactions|subtractions|atm (?:&|and) debit|electronic payments)\b")
_PERIOD = re.compile(
    r"(?:statement period|period|for the period|from|billing cycle|opening/closing date)\s*:?\s*"
    rf"({DATE_TOKEN_PATTERN})\s*(?:-|–|to|through|thru)\s*({DATE_TOKEN_PATTERN})", re.I)
_CLOSING = re.compile(r"(?i)\b(?:ending|closing|new) balance\b")
CARD_STATEMENT = re.compile(r"(?i)\bminimum payment\b|\bpayment due date\b|\bcredit limit\b|\bavailable credit\b")


def statement_period(text: str, prefer_dayfirst=False) -> tuple[str | None, str | None]:
    m = _PERIOD.search(text)
    if not m:
        return None, None
    a = find_dates(m.group(1), prefer_dayfirst)
    b = find_dates(m.group(2), prefer_dayfirst)
    if a and b and a[0][1] <= b[0][1]:
        return a[0][1], b[0][1]
    return None, None


def from_text(text: str, ctx: Ctx) -> list[Proposal]:
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    start, end = statement_period(text, ctx.prefer_dayfirst)
    year_for = year_resolver(start, end)
    proposals, section, closing = [], None, None
    for n, line in enumerate(lines):
        amounts = find_amounts(line)
        if _CLOSING.search(line) and amounts:
            closing = amounts[-1][1]
        head = DATE_TOKEN_RE.match(line.strip())
        if not head:
            if not amounts or len(line) < 60:
                if _IN_SECTION.search(line) and not _OUT_SECTION.search(line):
                    section = "in"
                elif _OUT_SECTION.search(line) and not _IN_SECTION.search(line):
                    section = "out"
            continue
        if not amounts or SUMMARY_WORDS.search(line[head.end():]):
            continue
        dates = find_dates(head.group(0), ctx.prefer_dayfirst, year_for)
        if not dates:
            continue
        tok, cents = amounts[0]
        desc = line.strip()[head.end():]
        for t, _ in amounts:
            desc = desc.replace(t, " ")
        desc = re.sub(rf"^\s*(?:{DATE_TOKEN_PATTERN}\s*)+", "", desc, flags=re.I)  # a second (posting) date
        desc = clean_description(re.sub(r"\s(?:CR|DR)\b", " ", desc))
        p = Proposal(date=dates[0][1], description=desc or "(no description)", merchant_key=merchant_key(desc),
                     raw={"line": line, "n": n}, confidence=0.85)
        if cents < 0:
            p.amount = cents
        elif section == "in":
            p.amount = cents
        elif section == "out":
            p.amount = -cents
        else:
            p.amount = -cents
            p.flag("direction_unknown", 0.5)
        proposals.append(p)

    if len(proposals) < 2 and ctx.ai_ok:
        ctx.stage("Asking the local AI to find the transactions in the text")
        ai_props = []
        numbered = list(enumerate(lines))
        for i in range(0, len(numbered), 80):
            res = ctx.ask(ai_tools.extract_statement_lines, numbered[i:i + 80], ctx.prefer_dayfirst, year_for,
                          what="find the transactions")
            if res is None:
                break
            for t in res.data or []:
                desc = clean_description(t["description"]) or clean_description(lines[t["line"]])
                amt = t["amount"]
                signed = -amt if (t["explicit_negative"] or t["direction"] == "out") else amt
                p = Proposal(date=t["date"], description=desc, amount=signed, merchant_key=merchant_key(desc),
                             raw={"line": lines[t["line"]], "n": t["line"]}, confidence=0.7)
                p.flag("ai_extracted", 0.7)
                if t["direction"] == "unknown" and not t["explicit_negative"]:
                    p.flag("direction_unknown", 0.5)
                ai_props.append(p)
            if res.problems:
                ctx.info(f"The AI's answer for some lines didn't match the text and was dropped "
                         f"({len(res.problems)} line(s)).")
        if len(ai_props) > len(proposals):
            proposals = ai_props
    if not proposals:
        raise ImportFailure("No transactions were found in this statement. If it's a scan, try a clearer copy; if "
                            "your bank offers a CSV or OFX download, that's the most reliable option.")
    if closing is not None and CARD_STATEMENT.search(text):
        ctx.info("This looks like a credit card statement. Its balance is money you owe, so it isn't offered as an "
                 "account balance.")
    elif closing is not None:
        iso = end or max(p.date for p in proposals if p.date)
        proposals.append(balance_proposal(iso, closing, "statement closing balance"))
    last4 = re.search(r"(?i)(?:ending in|account (?:number|no\.?|#)?[:\s]*(?:\*+|x+|\.{2,})?)\s*(\d{4})\b", text)
    if last4:
        ctx.extracted["account_hint"] = last4.group(1)
    ctx.extracted["account_text"] = " ".join(lines[:6])[:400]
    ctx.mapping = {"source": "text", "period": {"start": start, "end": end}}
    return proposals


# ── recurring patterns → rule suggestions ─────────────────────────────────────

_FREQS = [("weekly", 7, 1), ("biweekly", 14, 2), ("monthly", 30.4, 4), ("quarterly", 91, 8), ("annually", 365, 20)]


def suggest_rules(proposals: list[Proposal], existing_rules, account_id) -> list[Proposal]:
    """Same merchant, similar amount, regular gaps -> suggest a recurring rule (opt-in)."""
    groups: dict = {}
    for p in proposals:
        if p.target != "change_event" or not p.date or not p.amount or p.category == "transfer":
            continue
        groups.setdefault((p.merchant_key, p.amount > 0), []).append(p)
    out = []
    for (key, is_in), ps in groups.items():
        if len(ps) < 2 or not key:
            continue
        ps = sorted(ps, key=lambda p: p.date)
        days = [date.fromisoformat(p.date) for p in ps]
        gaps = [(b - a).days for a, b in zip(days, days[1:])]
        amts = [abs(p.amount) for p in ps]
        med_amt, med_gap = int(median(amts)), median(gaps)
        if med_amt == 0 or any(abs(a - med_amt) > 0.15 * med_amt for a in amts):
            continue
        freq = next((f for f, d, tol in _FREQS if abs(med_gap - d) <= tol and all(abs(g - d) <= tol + 1 for g in gaps)), None)
        if not freq or (len(ps) == 2 and not (freq == "monthly" and amts[0] == amts[1])):
            continue
        if any(_rule_similar(r, key, med_amt, is_in) for r in existing_rules):
            continue
        step = {"weekly": timedelta(days=7), "biweekly": timedelta(days=14)}.get(freq)
        last = days[-1]
        if step:
            nxt = last + step
        else:
            months = {"monthly": 1, "quarterly": 3, "annually": 12}[freq]
            y, m = divmod(last.month - 1 + months, 12)
            nxt = _safe_date(last.year + y, m + 1, last.day)
        signed = med_amt if is_in else -med_amt
        name = pretty_merchant(key)
        p = Proposal(target="rule", date=nxt.isoformat(), description=name, amount=signed, frequency=freq,
                     category=ps[-1].category, category_source=ps[-1].category_source, merchant_key=key,
                     note=f"Seen {len(ps)} times, about {fmt_cents(med_amt)} {freq}", confidence=0.8)
        p.flag("suggestion")
        out.append(p)
    return out


def _safe_date(y, m, d):
    while d > 28:
        try:
            return date(y, m, d)
        except ValueError:
            d -= 1
    return date(y, m, d)


def _rule_similar(rule, key, amount, is_in) -> bool:
    if (rule.rule_type == "income") != is_in or rule.rule_type not in ("income", "expense"):
        return False
    return bool({t for t in merchant_key(rule.name).split() if len(t) >= 3} & set(key.split()))
