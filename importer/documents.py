"""Single documents: what kind of file is this, and receipts and pay stubs.

Each document is read twice, by rules and by the AI. Values are trusted when
both agree or when the arithmetic works out (subtotal + tax + tip = total;
gross - deductions = net). Disagreements are flagged for review, never hidden.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from importer import ai_tools
from importer.core import Ctx, ImportFailure, Proposal
from importer.parsing import (
    find_amounts, find_dates, fmt_cents, merchant_key, pretty_merchant,
)

# ── what is this document ──────────────────────────────────────────────────────

_SIGNALS = {
    "payslip": [r"\bnet pay\b|\bnet amount\b|\btake home\b", r"\bgross (?:pay|earnings|wages)\b|\btotal earnings\b",
                r"\bdeductions?\b", r"\bytd\b|\byear to date\b", r"\bpay (?:period|date)\b|\bcheck date\b|\bperiod (?:ending|beginning)\b",
                r"\bfederal (?:income )?tax\b|\bfed(?:eral)? withholding\b|\bfica\b|\bsocial security\b|\bmedicare\b|\boasdi\b",
                r"\bearnings statement\b|\bpay ?stub\b|\bpay ?slip\b|\bpay statement\b|\bremittance advice\b",
                r"\bemployee (?:id|no|number|name)\b|\bemployer\b|\bregular (?:pay|hours|earnings)\b"],
    "receipt": [r"\bsub ?-?total\b", r"\btotal\b", r"\b(?:sales )?tax\b", r"\bchange(?: due)?\b|\btendered\b|\bcash\b",
                r"\bvisa\b|\bmastercard\b|\bamex\b|\bapproved\b|\bauth(?:orization)? ?(?:code|#)\b|\bcard ?#",
                r"\bthank you\b|\bcome again\b|\bcustomer copy\b", r"\breceipt\b|\border (?:#|number|no)\b|\binvoice\b",
                r"\bqty\b|\btip\b|\bgratuity\b|\bcashier\b|\bregister\b"],
    "statement": [r"\bstatement (?:period|date)\b|\bfor the period\b|\bbilling cycle\b",
                  r"\b(?:beginning|opening|previous) balance\b", r"\b(?:ending|closing|new) balance\b",
                  r"\baccount (?:number|summary)\b", r"\bdeposits\b|\bwithdrawals\b|\bpayments and (?:other )?credits\b",
                  r"\bdaily (?:ending )?balance\b|\bminimum payment\b|\bpayment due date\b"],
}


# Stock-plan paperwork (RSU grants and releases, ESPP purchases, option statements). The importer
# can't read these yet, but it has to recognise them: they carry "total" and "tax" lines, so
# without this they were taken for receipts and failed with a message about a missing total.
_EQUITY_SIGNALS = [
    r"\brsus?\b|\brestricted stock\b|\bstock units?\b",
    r"\bespp\b|\bemployee stock purchase\b|\bstock plan\b|\bequity award\b",
    r"\bvest(?:s|ed|ing)?\b|\brelease date\b|\bshares released\b",
    r"\bgrant (?:date|id|number|price)\b|\baward (?:date|id|number|price)\b|\bgrant(?:ed)?\b",
    r"\bfair market value\b|\bfmv\b|\bmarket value per share\b",
    r"\bshares? (?:withheld|sold|issued|traded|deposited|purchased|granted)\b|\bnet shares\b|\bsell to cover\b",
    r"\bstock options?\b|\bexercise price\b|\bstrike price\b|\bpurchase period\b|\boffering period\b",
]
EQUITY_MESSAGE = (
    "This looks like a stock-plan document (an RSU, ESPP or option statement). Import reads statements, "
    "receipts and pay stubs; it can't read stock-plan documents yet. Add or update the grant by hand under "
    "Plan (New entry, type RSU grant or ESPP). If this is really a statement, a receipt or a pay stub, pick "
    "that type above and click Re-read."
)


def equity_score(text: str) -> int:
    low = text.lower()
    return sum(1 for rx in _EQUITY_SIGNALS if re.search(rx, low))


def score_document(text: str) -> dict[str, int]:
    low = text.lower()
    scores = {k: sum(1 for rx in v if re.search(rx, low)) for k, v in _SIGNALS.items()}
    txn_lines = sum(1 for ln in text.splitlines() if find_dates(ln[:14]) and find_amounts(ln))
    if txn_lines >= 6:
        scores["statement"] += 2 + min(txn_lines // 10, 3)
    elif txn_lines <= 1:
        scores["statement"] = max(0, scores["statement"] - 1)
    return scores


def classify(doc, ctx: Ctx) -> str:
    if doc.kind in ("csv", "xlsx", "ofx", "json") and (doc.tables or doc.ofx):
        return "statement"
    text = doc.text or ""
    scores = score_document(text)
    equity = equity_score(text)
    # A pay stub can list RSU income and a brokerage statement can list share sales; those stay what
    # they are. Anything else that talks this much about grants, vesting and shares is stock-plan paperwork.
    if equity >= 3 and scores["payslip"] < 3 and scores["statement"] < 4:
        return "equity"
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    (top, s1), (_, s2) = ranked[0], ranked[1]
    if s1 >= 3 and s1 - s2 >= 2:
        return top
    ctx.stage("Asking the local AI what kind of document this is")
    ai = ctx.ask(ai_tools.classify_document, text, what="tell what kind of document this is")
    if ai:
        kind, conf = ai
        if kind == "equity":
            if equity >= 1:
                ctx.info("The local AI read this as a stock-plan document.")
                return "equity"
        elif kind != "other" and (scores.get(kind, 0) >= 1 or s1 == 0):
            ctx.info(f"The local AI read this as a {LABELS[kind]}.")
            return kind
    if s1 >= 2 and s1 > s2:
        return top
    return "unknown"


LABELS = {"statement": "statement", "receipt": "receipt", "payslip": "pay stub", "equity": "stock-plan document",
          "unknown": "document"}


# ── receipts ───────────────────────────────────────────────────────────────────

_TOTAL_LINE = re.compile(r"(?i)\b(grand total|total due|amount due|balance due|total paid|total|amount paid)\b")
_NOT_TOTAL = re.compile(r"(?i)sub ?-?total|total (?:tax|savings|discount|items?|qty|saved)|tax total|items? total|# items")
_GENERIC_TOP = re.compile(r"(?i)^(?:receipt|sales receipt|welcome|customer copy|merchant copy|store|thank you|order)\b")


def receipt_heuristics(text: str, prefer_dayfirst=False) -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    merchant = next((ln for ln in lines[:6] if len(re.findall(r"[A-Za-z]", ln)) >= 3 and not _GENERIC_TOP.match(ln)
                     and not find_amounts(ln)), "")
    best = None
    for ln in lines:
        m = _TOTAL_LINE.search(ln)
        if not m or _NOT_TOTAL.search(ln):
            continue
        amts = find_amounts(ln)
        if not amts or amts[-1][1] == 0:  # "Balance due 0.00" on a paid receipt
            continue
        rank = 0 if m.group(1).lower() in ("grand total", "total due", "amount due", "balance due", "total paid") else 1
        cand = (rank, -abs(amts[-1][1]), abs(amts[-1][1]))
        best = min(best, cand) if best else cand

    def last_amount(rx, allow_total_words=False):
        for ln in lines:
            if re.search(rx, ln, re.I) and (allow_total_words or not _NOT_TOTAL.search(ln)):
                amts = find_amounts(ln)
                if amts:
                    return abs(amts[-1][1])
        return None

    subtotal = last_amount(r"sub ?-?total", allow_total_words=True)
    tax = None
    for ln in lines:
        if re.search(r"(?i)\btax\b", ln) and not re.search(r"(?i)pre-?tax|tax ?id|tax ?#|total", ln):
            amts = find_amounts(ln)
            if amts:
                tax = (tax or 0) + abs(amts[-1][1])
    tip = last_amount(r"\b(?:tip|gratuity)\b")
    dates = find_dates(text, prefer_dayfirst)
    card = re.search(r"(?i)(?:\*{2,}|x{2,}|#{2,}|ending in\s*|card ?#?\s*\**)(\d{4})\b", text)
    return {
        "merchant": merchant[:100], "total": best[2] if best else None, "subtotal": subtotal, "tax": tax, "tip": tip,
        "date": dates[0][1] if dates else None, "card_last4": card.group(1) if card else None,
        "is_refund": bool(re.search(r"(?i)\brefund\b|\breturn(?:ed)?\b", text)),
    }


def from_receipt(text: str, ctx: Ctx, categories: dict) -> list[Proposal]:
    h = receipt_heuristics(text, ctx.prefer_dayfirst)
    ctx.stage("Reading the receipt with the local AI")
    res = ctx.ask(ai_tools.read_receipt, text, categories, what="read the receipt")
    ai = res.data if res else None
    flags, conf, checks = [], 0.7, []

    total, total_src = h["total"], "rules"
    if ai and ai.get("total") is not None:
        if h["total"] is None:
            total, total_src, conf = ai["total"], "ai", 0.75
        elif ai["total"] == h["total"]:
            total_src, conf = "both", 0.95
        else:
            flags.append("ai_disagrees")
            checks.append(f"Total: the AI read {fmt_cents(ai['total'])}, the rules read {fmt_cents(h['total'])} "
                          "from the TOTAL line; using the TOTAL line.")
            conf = 0.55
    if total is None:
        raise ImportFailure("No total was found, so this may not be a receipt. If it is another kind of document, "
                            "pick the type above and click Re-read. If it is a receipt, check that the total is "
                            "readable and in frame, or add it by hand on the Plan page.")

    sub = (ai or {}).get("subtotal") or h["subtotal"]
    tax = (ai or {}).get("tax") if (ai or {}).get("tax") is not None else h["tax"]
    tip = (ai or {}).get("tip") if (ai or {}).get("tip") is not None else h["tip"]
    adds_up = None
    if sub is not None:
        adds_up = abs(sub + (tax or 0) + (tip or 0) - total) <= 2
        if adds_up:
            conf = min(0.97, conf + 0.1)
            checks.append(f"Subtotal {fmt_cents(sub)} + tax {fmt_cents(tax or 0)}"
                          + (f" + tip {fmt_cents(tip)}" if tip else "") + f" = total {fmt_cents(total)} ✓")
        else:
            flags.append("doesnt_add_up")
            conf = min(conf, 0.55)
            checks.append(f"Subtotal {fmt_cents(sub)} + tax {fmt_cents(tax or 0)}"
                          + (f" + tip {fmt_cents(tip)}" if tip else "") + f" ≠ total {fmt_cents(total)}")
    items = (ai or {}).get("items") or []
    if items and sub is not None:
        s = sum(i["amount"] for i in items)
        checks.append(f"Items add up to {fmt_cents(s)}" + (" = subtotal ✓" if abs(s - sub) <= 2 else
                                                           f", subtotal is {fmt_cents(sub)} (some items may be missed)"))

    when = (ai or {}).get("date") or h["date"]
    if (ai or {}).get("date") and h["date"] and ai["date"] != h["date"]:
        when = h["date"] if h["date"] in {iso for _, iso in find_dates(text)} else ai["date"]
    merchant = ((ai or {}).get("merchant") or h["merchant"] or "Receipt").strip()
    refund = bool((ai or {}).get("is_refund")) or (h["is_refund"] and not ai)
    last4 = (ai or {}).get("card_last4") or h["card_last4"]

    p = Proposal(date=when, description=merchant[:200], amount=total if refund else -total,
                 merchant_key=merchant_key(merchant), confidence=conf,
                 note=_receipt_note(items, sub, tax, tip), raw={"text": text[:4000]})
    for f in flags:
        p.flag(f)
    if ai and ai.get("category") and ai["category"] in categories:
        p.category, p.category_source = ai["category"], "ai"  # a suggestion until you confirm it
        p.hint = ", ".join(i["description"] for i in items[:8]) or None
    if when is None:
        p.flag("missing_date", 0.4)
    ctx.extracted.update({
        "kind": "receipt", "merchant": merchant, "date": when, "total": total, "total_source": total_src,
        "subtotal": sub, "tax": tax, "tip": tip, "items": items, "card_last4": last4, "is_refund": refund,
        "adds_up": adds_up, "checks": checks, "ai_problems": (res.problems if res else None),
    })
    if last4:
        ctx.extracted["account_hint"] = last4
    return [p]


def _receipt_note(items, sub, tax, tip) -> str | None:
    parts = []
    if items:
        names = ", ".join(i["description"] for i in items[:6] if i["description"])
        parts.append(f"{len(items)} item(s): {names}" + ("…" if len(items) > 6 else ""))
    if tax:
        parts.append(f"tax {fmt_cents(tax)}")
    if tip:
        parts.append(f"tip {fmt_cents(tip)}")
    return "; ".join(parts)[:500] or None


# ── pay stubs ──────────────────────────────────────────────────────────────────

_NET = re.compile(r"(?i)\bnet (?:pay|amount|earnings|check)\b|\btake ?home\b")
_GROSS = re.compile(r"(?i)\bgross (?:pay|earnings|wages)\b|\btotal (?:gross|earnings)\b|^\s*gross\b")
_PAYDATE = re.compile(r"(?i)\b(?:pay|check|payment|advice|deposit) date\b")
_PERIOD = re.compile(r"(?i)\b(?:pay )?period\b|\bperiod (?:beginning|ending|start|end)\b")
_RETIREMENT = re.compile(r"(?i)401 ?\(?k\)?|403 ?\(?b\)?|\b457\b|\bretirement\b|\bpension\b|\broth\b|\btsp\b")


def payslip_heuristics(text: str, prefer_dayfirst=False) -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out = {"net_pay": None, "gross_pay": None, "pay_date": None, "period_start": None, "period_end": None}
    for ln in lines:
        amts = find_amounts(ln)
        if out["net_pay"] is None and _NET.search(ln) and amts:
            out["net_pay"] = abs(amts[0][1])   # first column is this period, later ones are YTD
        if out["gross_pay"] is None and _GROSS.search(ln) and amts:
            out["gross_pay"] = abs(amts[0][1])
        if out["pay_date"] is None and _PAYDATE.search(ln):
            d = find_dates(ln, prefer_dayfirst)
            if d:
                out["pay_date"] = d[0][1]
        if out["period_start"] is None and _PERIOD.search(ln):
            d = find_dates(ln, prefer_dayfirst)
            if len(d) >= 2:
                out["period_start"], out["period_end"] = sorted([d[0][1], d[1][1]])
    return out


def pay_frequency(start: str | None, end: str | None) -> str | None:
    if not start or not end:
        return None
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    if 6 <= days <= 8:
        return "weekly"
    if 13 <= days <= 15:
        return "biweekly"
    if 27 <= days <= 32:
        return "monthly"
    return None  # semi-monthly (15-16 days) has no matching rule frequency


def from_payslip(text: str, ctx: Ctx, existing_rules) -> list[Proposal]:
    h = payslip_heuristics(text, ctx.prefer_dayfirst)
    ctx.stage("Reading the pay stub with the local AI")
    res = ctx.ask(ai_tools.read_payslip, text, what="read the pay stub")
    ai = res.data if res else {}
    ai = ai or {}
    checks, flags = [], []
    deductions = ai.get("deductions") or []
    contributions = ai.get("employer_contributions") or []
    gross = ai.get("gross_pay") or h["gross_pay"]
    if ai.get("gross_pay") and h["gross_pay"] and ai["gross_pay"] != h["gross_pay"]:
        gross = h["gross_pay"]
        flags.append("ai_disagrees")
        checks.append(f"Gross pay: the AI read {fmt_cents(ai['gross_pay'])}, the rules read {fmt_cents(h['gross_pay'])}.")

    def reconciles(net):
        return gross is not None and deductions and net is not None and abs(gross - sum(d["amount"] for d in deductions) - net) <= 100

    candidates = [c for c in (ai.get("net_pay"), h["net_pay"]) if c is not None]
    net = next((c for c in candidates if reconciles(c)), None)
    if net is None:
        net = h["net_pay"] if h["net_pay"] is not None else ai.get("net_pay")
        if ai.get("net_pay") and h["net_pay"] and ai["net_pay"] != h["net_pay"]:
            flags.append("ai_disagrees")
            checks.append(f"Net pay: the AI read {fmt_cents(ai['net_pay'])}, the rules read {fmt_cents(h['net_pay'])} "
                          "(the first amount on the Net Pay line); using the rules' value.")
    if net is None:
        raise ImportFailure("No net pay was found on this pay stub. Check the photo shows the Net Pay line.")
    if gross is not None and net > gross:
        flags.append("doesnt_add_up")
        checks.append(f"Net pay {fmt_cents(net)} is more than gross {fmt_cents(gross)}; one of them may be a "
                      "year-to-date figure.")
    elif reconciles(net):
        checks.append(f"Gross {fmt_cents(gross)} − deductions {fmt_cents(sum(d['amount'] for d in deductions))} "
                      f"= net {fmt_cents(net)} ✓")
    elif gross is not None and deductions:
        flags.append("doesnt_add_up")
        checks.append(f"Gross {fmt_cents(gross)} − deductions {fmt_cents(sum(d['amount'] for d in deductions))} "
                      f"≠ net {fmt_cents(net)}; some deductions may have been missed.")
    conf = 0.95 if reconciles(net) and "ai_disagrees" not in flags else (0.7 if not flags else 0.5)

    pay_date = ai.get("pay_date") or h["pay_date"] or ai.get("period_end") or h["period_end"]
    start = ai.get("period_start") or h["period_start"]
    end = ai.get("period_end") or h["period_end"]
    employer = (ai.get("employer") or "").strip() or _employer_guess(text)
    freq = pay_frequency(start, end)

    note_bits = [f"gross {fmt_cents(gross)}" if gross else None]
    taxes = sum(d["amount"] for d in deductions if d["kind"] == "tax")
    if taxes:
        note_bits.append(f"taxes {fmt_cents(taxes)}")
    for d in deductions:
        if d["kind"] != "tax":
            note_bits.append(f"{d['name']} {fmt_cents(d['amount'])}")
    note = "Pay stub: " + "; ".join(b for b in note_bits if b) if any(note_bits) else None
    desc = f"Pay — {employer}" if employer else "Paycheck"

    net_row = Proposal(date=pay_date, description=desc[:200], amount=net, category="salary",
                       category_source="document", merchant_key=merchant_key(employer or "PAYROLL"),
                       confidence=conf, note=note[:500] if note else None, raw={"text": text[:4000]})
    for f in flags:
        net_row.flag(f)
    if pay_date is None:
        net_row.flag("missing_date", 0.4)
    rows = [net_row]

    retire = [d for d in deductions if d["kind"] == "retirement" or _RETIREMENT.search(d["name"])]
    retire += [c for c in contributions if c["kind"] == "retirement" or _RETIREMENT.search(c["name"])]
    if retire and pay_date:
        total = sum(r["amount"] for r in retire)
        acct = _retirement_account(ctx.accounts)
        r = Proposal(date=pay_date, description=f"Retirement contributions — {employer or 'payroll'}"[:200],
                     amount=total, category="investment", category_source="document",
                     merchant_key=merchant_key(f"{employer} RETIREMENT"), confidence=min(conf, 0.9),
                     note="; ".join(f"{x['name']} {fmt_cents(x['amount'])}" for x in retire)[:500],
                     account_id=acct.id if acct else None, explicit_account=True)
        if not acct:
            r.flag("pick_account")
        rows.append(r)

    salary_rules = [x for x in existing_rules if x.rule_type == "income" and
                    (x.category == "salary" or re.search(r"(?i)salary|payroll|pay\b|wage", x.name or ""))]
    if salary_rules:
        rule = salary_rules[0]
        if rule.amount and abs(rule.amount - net) > max(100, rule.amount // 100):
            ctx.warn(f"Your rule '{rule.name}' expects {fmt_cents(rule.amount)} per {rule.frequency or 'period'}; "
                     f"this pay stub's net pay is {fmt_cents(net)}. Update the rule on the Plan page if your pay "
                     "changed.")
    elif freq and pay_date:
        step = {"weekly": 7, "biweekly": 14}.get(freq)
        nxt = (date.fromisoformat(pay_date) + timedelta(days=step)) if step else _next_month(date.fromisoformat(pay_date))
        sug = Proposal(target="rule", date=nxt.isoformat(), description=f"Salary — {employer}" if employer else "Salary",
                       amount=net, frequency=freq, category="salary", category_source="document",
                       merchant_key=net_row.merchant_key, note=f"From the pay stub dated {pay_date}", confidence=conf)
        sug.flag("suggestion")
        rows.append(sug)

    deposit = re.search(r"(?i)(?:direct )?deposit[^\n]*?(?:\*{2,}|x{2,}|ending in\s*|#)\s*(\d{4})\b", text)
    if deposit:
        ctx.extracted["account_hint"] = deposit.group(1)
    ctx.extracted.update({
        "kind": "payslip", "employer": employer, "pay_date": pay_date, "period_start": start, "period_end": end,
        "frequency": freq, "gross_pay": gross, "net_pay": net, "deductions": deductions,
        "employer_contributions": contributions, "checks": checks, "ai_problems": (res.problems if res else None),
    })
    return rows


def _employer_guess(text: str) -> str:
    for ln in text.splitlines()[:5]:
        ln = ln.strip()
        if len(re.findall(r"[A-Za-z]", ln)) >= 3 and not re.search(r"(?i)pay|earnings|statement|stub|slip", ln):
            return pretty_merchant(merchant_key(ln))
    return ""


def _retirement_account(accounts):
    found = [a for a in accounts if (a.type or "").startswith("retirement") or re.search(r"(?i)401|403|ira\b", a.name or "")]
    return found[0] if len(found) == 1 else None


def _next_month(d: date) -> date:
    y, m = divmod(d.month, 12)
    for day in (d.day, 30, 29, 28):
        try:
            return date(d.year + y, m + 1, day)
        except ValueError:
            continue
    return d + timedelta(days=30)
