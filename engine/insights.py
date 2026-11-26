"""Factual observations the app can make from the user's own inputs.

Pure functions over plain dicts. Every insight says what it is based on and links
to the page where the user can act on it. Nothing here gives advice on what to
do with money; it reports where inputs and reality disagree or need attention.

Insight shape:
  {id, source, severity, title, detail, basis, value, action: {label, href}}
  source:   balances | forecast | plan | import | tax
  severity: attention | info | good
"""

from datetime import date, timedelta

from engine.lookback import _month_ends, net_worth_at
from engine.projection import project_v2

LARGE_EVENT_CENTS = 100_000  # $1,000


def _usd(cents: int) -> str:
    return f"-${abs(cents) / 100:,.0f}" if cents < 0 else f"${cents / 100:,.0f}"


def _days_between(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _insight(id, source, severity, title, detail, basis, href, label, value=None):
    return {"id": id, "source": source, "severity": severity, "title": title, "detail": detail,
            "basis": basis, "value": value, "action": {"label": label, "href": href}}


def days_since(entity: dict, today: str):
    d = entity.get("current_date")
    try:
        return max(0, _days_between(d, today))
    except (TypeError, ValueError):
        return None


def stale_entities(entities: list[dict], today: str, stale_days: int) -> list[dict]:
    out = []
    for e in entities:
        n = days_since(e, today)
        if n is None or n >= stale_days:
            out.append({**e, "days_since": n})
    out.sort(key=lambda e: -(e["days_since"] if e["days_since"] is not None else 10**6))
    return out


def divergence(entities, snaps, rules, changes, loans, prices, today: str, min_days: int = 25):
    """Compare today's recorded net worth with what the plan predicted from an earlier recorded point.

    Returns None when there is no earlier complete record to start from.
    """
    earliest = (date.fromisoformat(today) - timedelta(days=400)).isoformat()
    cutoff = (date.fromisoformat(today) - timedelta(days=min_days)).isoformat()
    anchor = None
    for iso in _month_ends(earliest, today):
        if iso > cutoff:
            break
        value, partial = net_worth_at(entities, snaps, iso)
        if value is not None and not partial:
            anchor = (iso, value)
    if not anchor:
        return None
    anchor_date, then_value = anchor
    now_value, _ = net_worth_at(entities, snaps, today)
    if now_value is None:
        return None
    start = (date.fromisoformat(anchor_date) + timedelta(days=1)).isoformat()
    _, events = project_v2(rules, changes, loans, then_value, prices, start, today)
    flow = sum(e.amount if e.type == "income" else -e.amount for e in events)
    predicted = then_value + flow
    delta = now_value - predicted
    base = abs(predicted) or abs(now_value) or 1
    return {"anchor_date": anchor_date, "anchor_value": then_value, "predicted": predicted,
            "actual": now_value, "delta": delta, "bps": round(delta * 10000 / base), "planned_flow": flow}


def build_insights(*, entities, snaps, rules, changes, loans, prices, today: str, stale_days: int,
                   net_worth_bps: int, pending_imports: int = 0, tax_insights=None, tax_year=None,
                   plan_actual=None, balance_checks=None) -> list[dict]:
    out = []

    # ── Balances: stale records ───────────────────────────────────────────
    stale = stale_entities(entities, today, stale_days)
    if stale:
        names = ", ".join(e["name"] for e in stale[:4]) + (f" and {len(stale) - 4} more" if len(stale) > 4 else "")
        oldest = stale[0]["days_since"]
        out.append(_insight(
            "stale-balances", "balances", "attention",
            f"{len(stale)} balance{'s' if len(stale) != 1 else ''} not updated in {stale_days}+ days",
            f"{names}. The oldest was last recorded {oldest} days ago." if oldest is not None
            else f"{names}. At least one has never been recorded.",
            f"Last-updated dates on the Balances page; the limit of {stale_days} days is set in Settings.",
            "/balances?stale=1", "Update balances", value=len(stale)))
    elif entities:
        out.append(_insight(
            "balances-fresh", "balances", "good", "All balances are up to date",
            f"Every account, asset and liability was recorded within the last {stale_days} days.",
            "Last-updated dates on the Balances page.", "/balances", "View balances"))

    # ── Balances vs. imports: differences no one has looked at ────────────
    look = sorted((c for c in balance_checks or [] if c["status"] in ("open", "changed")),
                  key=lambda c: c["date"], reverse=True)
    if look:
        c = look[0]
        n = len(look)
        detail = (f"{c['account']} on {c['date']}: {_usd(abs(c['gap']))} isn't explained by the transactions "
                  f"since {c['since_date']}.")
        if c["missing"]:
            a, b, _ = c["missing"][0]
            detail += f" Nothing was imported for {a} to {b}."
        detail += " Import what's missing, or sign it off: some details are always missing, and that's fine."
        out.append(_insight(
            "balance-gaps", "balances", "info",
            f"{n} recorded balance{'s' if n != 1 else ''} {'differ' if n != 1 else 'differs'} from your imports",
            detail, "Each recorded balance against the balance before it plus the imported transactions in between.",
            "/balances?gaps=1", "Review the differences", value=c["gap"]))

    # ── Balances vs. plan: divergence ─────────────────────────────────────
    div = divergence(entities, snaps, rules, changes, loans, prices, today)
    if div:
        pct = abs(div["bps"]) / 100
        direction = "above" if div["delta"] >= 0 else "below"
        detail = (f"From {_usd(div['anchor_value'])} on {div['anchor_date']}, your plan expected "
                  f"{_usd(div['predicted'])} today. Recorded net worth is {_usd(div['actual'])}, "
                  f"a difference of {_usd(div['delta'])}.")
        basis = ("Recorded balances on both dates, plus every rule, logged change and loan payment in between. "
                 "Market moves on investments are not planned, so they show up here.")
        if abs(div["bps"]) >= net_worth_bps:
            out.append(_insight(
                "net-worth-divergence", "balances", "attention",
                f"Net worth is {pct:.1f}% {direction} what your plan predicted",
                detail, basis, "/forecast", "Open forecast", value=div["delta"]))
        else:
            out.append(_insight(
                "net-worth-on-track", "balances", "good",
                f"Net worth is within {pct:.1f}% of what your plan predicted",
                detail, basis, "/forecast", "Open forecast", value=div["delta"]))

    # ── Plan: missing inputs ──────────────────────────────────────────────
    recurring = [r for r in rules if r.get("rule_type") in ("income", "expense")]
    if entities and not recurring:
        out.append(_insight(
            "no-rules", "plan", "attention", "No recurring income or expenses in your plan",
            "Without them the forecast only moves on loan payments and one-off entries.",
            "Rules on the Plan page.", "/plan", "Add a rule"))
    missing = sorted({(r.get("config") or {}).get("ticker", "").upper() for r in rules if r.get("rule_type") == "rsu"}
                     - set(prices) - {""})
    if missing:
        out.append(_insight(
            "missing-prices", "plan", "attention",
            f"No share price for {', '.join(missing)}",
            "RSU vests for these tickers count as $0 in the forecast until a price is entered.",
            "RSU rules on the Plan page and stored share prices.", "/balances?tab=prices", "Enter a price",
            value=len(missing)))

    # ── Forecast: next 12 months ──────────────────────────────────────────
    horizon = (date.fromisoformat(today) + timedelta(days=365)).isoformat()
    buckets, events = project_v2(rules, changes, loans, 0, prices, today, horizon, fill_months=True)
    negative = [b for b in buckets if b.net_cash_flow < 0]
    if negative and (rules or changes or loans):
        worst = min(negative, key=lambda b: b.net_cash_flow)
        out.append(_insight(
            "negative-months", "forecast", "attention" if len(negative) >= 3 else "info",
            f"{len(negative)} of the next {len(buckets)} months spend more than they bring in",
            f"The largest shortfall is {_usd(worst.net_cash_flow)} in {worst.month}.",
            "Planned income and expenses per month on the Forecast page.",
            f"/forecast?month={worst.month}", "See that month", value=worst.net_cash_flow))

    soon = (date.fromisoformat(today) + timedelta(days=30)).isoformat()
    upcoming = [e for e in events if today <= e.date <= soon
                and e.source_type in ("rsu", "espp", "change") and e.amount >= LARGE_EVENT_CENTS]
    upcoming.sort(key=lambda e: -e.amount)
    for e in upcoming[:3]:
        signed = e.amount if e.type == "income" else -e.amount
        out.append(_insight(
            f"upcoming:{e.source_id}:{e.date}", "forecast", "info",
            f"{e.label or 'Planned event'}: {'+' if signed >= 0 else ''}{_usd(signed)} on {e.date}",
            "A one-off or equity event of $1,000 or more in the next 30 days.",
            "Rules and logged changes on the Plan page.", f"/forecast?month={e.date[:7]}", "See that month",
            value=signed))

    for loan in loans:
        payoff = loan.get("payoff_date") or ""
        if today <= payoff <= horizon:
            out.append(_insight(
                f"payoff:{loan['id']}", "forecast", "info",
                f"{loan.get('name', 'Loan')} is paid off in {payoff[:7]}",
                f"That ends a payment of {_usd(loan.get('monthly_payment', 0))} a month.",
                "The payoff date and monthly payment on the Balances page.", "/balances?type=liability",
                "View liabilities", value=loan.get("monthly_payment", 0)))

    # ── Plan vs. actual: last full month ──────────────────────────────────
    last = (plan_actual or {}).get("totals", [None])[0] if plan_actual else None
    if last and last.get("complete") and last.get("planned_spending"):
        planned, spent = last["planned_spending"], last["actual_spending"]
        diff = spent - planned
        month = last["month"]
        pct = abs(diff) * 100 / planned
        basis = ("Imported transactions dated in the month, against the rules, loan payments and one-off entries "
                 "planned for it. Transfers between your accounts are left out.")
        if pct >= 10 and abs(diff) >= 10_000:
            out.append(_insight(
                "spending-vs-plan", "plan", "attention" if diff > 0 else "info",
                f"Spending in {month} was {_usd(abs(diff))} {'over' if diff > 0 else 'under'} plan",
                f"You planned {_usd(planned)} and the imported transactions add up to {_usd(spent)}.",
                basis, "/insights#plan-vs-actual", "Compare by category", value=-diff))
        else:
            out.append(_insight(
                "spending-on-plan", "plan", "good", f"Spending in {month} was close to plan",
                f"You planned {_usd(planned)} and the imported transactions add up to {_usd(spent)}.",
                basis, "/insights#plan-vs-actual", "Compare by category", value=-diff))

    # ── Import ────────────────────────────────────────────────────────────
    if pending_imports:
        out.append(_insight(
            "imports-pending", "import", "attention",
            f"{pending_imports} imported file{'s' if pending_imports != 1 else ''} waiting for review",
            "Nothing from an import reaches your records until you review and accept it.",
            "Imports in review on the Import page.", "/import", "Review imports", value=pending_imports))

    # ── Tax ───────────────────────────────────────────────────────────────
    severity = {"warning": "attention", "opportunity": "info", "info": "info"}
    for i, t in enumerate(tax_insights or []):
        out.append(_insight(
            f"tax:{i}", "tax", severity.get(t.get("kind"), "info"), t.get("title", ""), t.get("detail", ""),
            f"The {tax_year} estimate on the Taxes page, including its listed assumptions.",
            "/taxes", "Open taxes", value=t.get("value")))

    order = {"attention": 0, "info": 1, "good": 2}
    out.sort(key=lambda i: order[i["severity"]])
    return out
