"""Read-only lookups the assistant may run, and the checks that keep it honest.

The model never does arithmetic and never writes data. It picks one tool and its
arguments; the tool computes `facts` (label/value pairs) from the user's own
records; the model may then word an answer using those facts only. An answer
that contains a number the facts don't is thrown away and the facts are shown
instead.
"""

import re
from datetime import date, timedelta

from engine.lookback import net_worth_at
from engine.projection import project_v2


def usd(cents: int) -> str:
    return f"-${abs(cents) / 100:,.0f}" if cents < 0 else f"${cents / 100:,.0f}"


def _fact(label, value):
    return {"label": label, "value": value}


def _valid_date(v) -> bool:
    try:
        date.fromisoformat(v)
        return True
    except (TypeError, ValueError):
        return False


def _match(needle, haystack) -> bool:
    return not needle or needle.strip().lower() in (haystack or "").lower()


class Context:
    """Everything a tool may read, loaded once per question."""

    def __init__(self, *, entities, snaps, rules, changes, loans, prices, today, insights=None, tax=None):
        self.entities, self.snaps, self.rules, self.changes = entities, snaps, rules, changes
        self.loans, self.prices, self.today = loans, prices, today
        self.insights, self.tax = insights or [], tax

    def net_worth(self) -> int:
        return sum(-e["current"] if e["type"] == "liability" else e["current"] for e in self.entities)

    def forecast(self, to_date):
        return project_v2(self.rules, self.changes, self.loans, self.net_worth(), self.prices, self.today, to_date,
                          fill_months=True)


# ── Tools ─────────────────────────────────────────────────────────────────────

def tool_balances(ctx: Context, args: dict):
    kind = args.get("type") if args.get("type") in ("cash", "asset", "liability") else None
    rows = [e for e in ctx.entities if (not kind or e["type"] == kind) and _match(args.get("name"), e["name"])]
    facts = [_fact(f"{e['name']} ({e['type']})", f"{usd(e['current'])} as of {e['current_date'] or 'unknown'}")
             for e in sorted(rows, key=lambda e: -e["current"])[:12]]
    if not args.get("name"):
        total = sum(-e["current"] if e["type"] == "liability" else e["current"] for e in rows)
        facts.insert(0, _fact("Total" if kind else "Net worth", usd(abs(total) if kind == "liability" else total)))
    href = "/balances" + (f"?type={kind}" if kind else "")
    return facts, href


def tool_net_worth_on(ctx: Context, args: dict):
    when = args.get("date") if _valid_date(args.get("date")) else ctx.today
    if when > ctx.today:
        buckets, _ = ctx.forecast(when)
        b = next((b for b in reversed(buckets) if b.month <= when[:7]), None)
        if not b:
            return [_fact("Forecast", "nothing planned that far out")], "/forecast"
        return [_fact(f"Forecast net worth at the end of {b.month}", usd(b.cumulative_net_worth)),
                _fact("Net worth today", usd(ctx.net_worth()))], f"/forecast?month={b.month}"
    value, partial = net_worth_at(ctx.entities, ctx.snaps, when)
    if value is None:
        return [_fact(f"Net worth on {when}", "not recorded yet")], "/balances"
    facts = [_fact(f"Recorded net worth on {when}", usd(value))]
    if partial:
        facts.append(_fact("Note", "some accounts had no record that early and are left out"))
    return facts, "/balances"


def tool_forecast_month(ctx: Context, args: dict):
    month = str(args.get("month") or "")[:7]
    if not re.fullmatch(r"\d{4}-\d{2}", month) or month < ctx.today[:7]:
        month = ctx.today[:7]
    end = f"{month}-28"
    buckets, _ = ctx.forecast(end)
    b = next((b for b in buckets if b.month == month), None)
    if not b:
        return [_fact(month, "outside the forecast")], "/forecast"
    facts = [_fact(f"Planned income in {month}", usd(b.income)), _fact(f"Planned expenses in {month}", usd(b.expenses)),
             _fact(f"Net cash flow in {month}", usd(b.net_cash_flow)),
             _fact(f"Forecast net worth at the end of {month}", usd(b.cumulative_net_worth))]
    for e in sorted(b.events, key=lambda e: -e.amount)[:5]:
        facts.append(_fact(f"{e.label or e.source_type} on {e.date}", usd(e.amount if e.type == "income" else -e.amount)))
    return facts, f"/forecast?month={month}"


def tool_net_worth_crosses(ctx: Context, args: dict):
    try:
        target = int(round(float(args.get("amount_dollars")) * 100))
    except (TypeError, ValueError):
        return [_fact("Amount", "not understood")], "/forecast"
    below = args.get("direction") == "below"
    horizon = (date.fromisoformat(ctx.today) + timedelta(days=3653)).isoformat()
    buckets, _ = ctx.forecast(horizon)
    now = ctx.net_worth()
    facts = [_fact("Net worth today", usd(now))]
    hit = next((b for b in buckets if (b.cumulative_net_worth <= target if below else b.cumulative_net_worth >= target)), None)
    word = "falls to" if below else "reaches"
    if hit:
        facts.append(_fact(f"Forecast net worth first {word} {usd(target)}", f"in {hit.month} ({usd(hit.cumulative_net_worth)})"))
    else:
        facts.append(_fact(f"Forecast net worth {word} {usd(target)}", "not within the next 10 years on the current plan"))
    return facts, "/forecast" + (f"?month={hit.month}" if hit else "")


def _planned(ctx: Context, args: dict, kind: str):
    start = args.get("from") if _valid_date(args.get("from")) else ctx.today
    end = args.get("to") if _valid_date(args.get("to")) else (date.fromisoformat(start) + timedelta(days=365)).isoformat()
    start = max(start, ctx.today)
    _, events = ctx.forecast(end)
    rows = [e for e in events if e.type == kind and start <= e.date <= end
            and _match(args.get("category"), e.category) and _match(args.get("search"), e.label)]
    what = "expenses" if kind == "expense" else "income"
    scope = " ".join(x for x in [args.get("category") or "", f'matching "{args["search"]}"' if args.get("search") else ""] if x)
    facts = [_fact(f"Planned {scope + ' ' if scope else ''}{what} from {start} to {end}", usd(sum(e.amount for e in rows))),
             _fact("Planned events counted", str(len(rows)))]
    by_label: dict = {}
    for e in rows:
        by_label[e.label or e.source_type] = by_label.get(e.label or e.source_type, 0) + e.amount
    for label, amount in sorted(by_label.items(), key=lambda kv: -kv[1])[:5]:
        facts.append(_fact(label, usd(amount)))
    href = f"/forecast?type={kind}"
    if args.get("category") and any(e.category == args["category"] for e in rows):
        href += f"&category={args['category']}"
    if args.get("search"):
        href += f"&q={args['search']}"
    return facts, href


def tool_planned_spending(ctx, args):
    return _planned(ctx, args, "expense")


def tool_planned_income(ctx, args):
    return _planned(ctx, args, "income")


def tool_loan(ctx: Context, args: dict):
    loans = [l for l in ctx.loans if _match(args.get("name"), l.get("name"))] or ctx.loans
    facts = []
    for l in loans[:6]:
        current = next((e["current"] for e in ctx.entities if e["type"] == "liability" and e["id"] == l["id"]),
                       l.get("current_balance", 0))
        facts.append(_fact(l["name"], f"{usd(current)} owed, {usd(l.get('monthly_payment', 0))} a month, "
                                      f"paid off {l.get('payoff_date') or 'date not set'}"))
    return facts or [_fact("Liabilities", "none recorded")], "/balances?type=liability"


def tool_insights(ctx: Context, args: dict):
    items = [i for i in ctx.insights if i["severity"] != "good"][:8] or ctx.insights[:8]
    return [_fact(i["title"], i["detail"]) for i in items] or [_fact("Insights", "nothing stands out right now")], "/insights"


def tool_taxes(ctx: Context, args: dict):
    s = (ctx.tax or {}).get("summary") or {}
    if not s:
        return [_fact("Tax estimate", "not available")], "/taxes"
    facts = []
    for key, label in (("gross_income", "Gross income"), ("taxable_income", "Taxable income"),
                       ("federal_income_tax", "Estimated federal income tax"), ("total_tax", "Estimated total tax"),
                       ("tax_paid", "Withheld or paid so far"), ("federal_balance_due", "Federal balance still owed at filing")):
        if isinstance(s.get(key), int):
            facts.append(_fact(f"{label} ({(ctx.tax or {}).get('year', '')})".replace(" ()", ""), usd(s[key])))
    return facts or [_fact("Tax estimate", "not available")], "/taxes"


TOOLS = {
    "balances": (tool_balances, "Current recorded values of accounts, assets and liabilities, and net worth today. "
                                "args: type (cash|asset|liability, optional), name (optional)"),
    "net_worth_on": (tool_net_worth_on, "Net worth on one date, past (recorded) or future (forecast). args: date YYYY-MM-DD"),
    "forecast_month": (tool_forecast_month, "Planned income, expenses and net worth for one future month. args: month YYYY-MM"),
    "net_worth_crosses": (tool_net_worth_crosses, "When forecast net worth first reaches or falls to an amount. "
                                                  "args: amount_dollars (number), direction (above|below)"),
    "planned_spending": (tool_planned_spending, "Total planned expenses in a date range. "
                                                "args: from, to (YYYY-MM-DD, optional), category (optional), search (optional words in the name)"),
    "planned_income": (tool_planned_income, "Total planned income in a date range. args: from, to, category, search (all optional)"),
    "loan": (tool_loan, "Balance, payment and payoff date of loans. args: name (optional)"),
    "insights": (tool_insights, "What currently needs attention or stands out. no args"),
    "taxes": (tool_taxes, "This year's tax estimate. no args"),
}

ASK_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string", "enum": list(TOOLS)},
        "args": {"type": "object", "properties": {
            "type": {"type": "string"}, "name": {"type": "string"}, "date": {"type": "string"},
            "month": {"type": "string"}, "amount_dollars": {"type": "number"}, "direction": {"type": "string"},
            "from": {"type": "string"}, "to": {"type": "string"}, "category": {"type": "string"},
            "search": {"type": "string"}}},
    },
    "required": ["tool"],
}


def run_tool(ctx: Context, choice) -> dict:
    if not isinstance(choice, dict) or choice.get("tool") not in TOOLS:
        raise ValueError("the model did not pick a known lookup")
    args = choice.get("args") if isinstance(choice.get("args"), dict) else {}
    args = {k: v for k, v in args.items() if v not in (None, "")}
    facts, href = TOOLS[choice["tool"]][0](ctx, args)
    return {"tool": choice["tool"], "args": args, "facts": facts, "href": href}


# ── Guardrail ─────────────────────────────────────────────────────────────────

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set:
    out = set()
    for raw in _NUM.findall(text or ""):
        n = raw.replace(",", "")
        if "." in n:
            n = n.rstrip("0").rstrip(".")
        out.add(n.lstrip("0") or "0")
    return out


def numbers_grounded(answer: str, *sources: str) -> bool:
    """True when every number in the answer also appears in one of the sources."""
    allowed = set()
    for s in sources:
        allowed |= _numbers(s)
    return all(n in allowed or len(n) == 1 for n in _numbers(answer))


def facts_text(facts: list[dict]) -> str:
    return "\n".join(f"- {f['label']}: {f['value']}" for f in facts)


# ── Natural-language filter and drafts ────────────────────────────────────────

def filter_schema(filters: dict, sorts: list) -> dict:
    """JSON schema for one list's filter. Dropdown values are enums, so the model can only pick real ones.

    Every field is required: an empty string or null means "not mentioned". That makes a small
    model consider each field instead of answering with only the first one it notices.
    """
    props = {
        "search": {"type": "string"},
        "date_from": {"type": "string"}, "date_to": {"type": "string"},
        "min_amount_dollars": {"type": ["number", "null"]}, "max_amount_dollars": {"type": ["number", "null"]},
        "sort": {"type": "string", "enum": [""] + [str(x) for x in sorts]},
        "direction": {"type": "string", "enum": ["asc", "desc"]},
    }
    for name, values in filters.items():
        props["filter_" + name] = {"type": "string", "enum": [""] + [str(v) for v in values]}
    return {"type": "object", "properties": props, "required": list(props)}


def clean_filter(raw, filters: dict, sorts: list) -> dict:
    """Keep only filter values the page actually offers; anything else is dropped, not guessed."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    chosen = {}
    for name, values in filters.items():
        allowed = {str(v).lower(): str(v) for v in values}
        value = str(raw.get("filter_" + name) or "").strip().lower()
        if value in allowed:
            chosen[name] = allowed[value]
    if chosen:
        out["filters"] = chosen
    for key in ("date_from", "date_to"):
        if _valid_date(raw.get(key)):
            out[key] = raw[key]
    for key in ("min_amount_dollars", "max_amount_dollars"):
        try:
            if raw.get(key) is not None and float(raw[key]) > 0:
                out[key.replace("_dollars", "")] = abs(float(raw[key]))
        except (TypeError, ValueError):
            pass
    if str(raw.get("sort") or "") in [str(x) for x in sorts]:
        out["sort"] = str(raw["sort"])
        out["dir"] = raw.get("direction") if raw.get("direction") in ("asc", "desc") else "asc"
    # Search text is only kept when it is not just a repeat of something already captured.
    taken = " ".join(chosen.values()).lower()
    text = str(raw.get("search") or "").strip()
    if text and text.lower() not in taken and not any(ch.isdigit() for ch in text):
        out["q"] = text[:60]
    return out


DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["rule", "change"]},
        "direction": {"type": "string", "enum": ["income", "expense"]},
        "name": {"type": "string"}, "amount_dollars": {"type": "number"},
        "frequency": {"type": "string", "enum": ["weekly", "biweekly", "monthly", "quarterly", "annually"]},
        "start_date": {"type": "string"}, "end_date": {"type": "string"}, "date": {"type": "string"},
    },
    "required": ["kind", "direction", "name", "amount_dollars"],
}


def clean_draft(raw, today: str, source_text: str):
    """A form prefill from the model's draft, or None. The amount must appear in what the user typed."""
    if not isinstance(raw, dict) or raw.get("kind") not in ("rule", "change"):
        return None
    try:
        amount = abs(float(raw.get("amount_dollars")))
    except (TypeError, ValueError):
        return None
    if amount <= 0 or not numbers_grounded(f"{amount:.2f}".rstrip("0").rstrip("."), source_text):
        return None
    direction = raw.get("direction") if raw.get("direction") in ("income", "expense") else "expense"
    name = str(raw.get("name") or "").strip()[:100] or "Untitled"
    if raw["kind"] == "rule":
        freq = raw.get("frequency") if raw.get("frequency") in DRAFT_SCHEMA["properties"]["frequency"]["enum"] else "monthly"
        return {"kind": "rule", "rule_type": direction, "name": name, "amount_dollars": f"{amount:.2f}",
                "frequency": freq, "start_date": raw["start_date"] if _valid_date(raw.get("start_date")) else today,
                "end_date": raw["end_date"] if _valid_date(raw.get("end_date")) else ""}
    signed = amount if direction == "income" else -amount
    return {"kind": "change", "description": name, "amount_dollars": f"{signed:.2f}",
            "date": raw["date"] if _valid_date(raw.get("date")) else today}
