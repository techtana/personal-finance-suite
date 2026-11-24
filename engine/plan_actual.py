"""Plan vs. actual: what the plan expected each month, next to what was imported.

Plan   = rules, loan payments and planned one-off entries (the Plan page), expanded
         for the month exactly as the forecast does.
Actual = imported transactions and reconcile adjustments dated in the month.
Transfers between your own accounts are in neither: they don't change net worth.

A month with no imported transaction has no actuals (None), so it isn't shown as
"you spent nothing". A month the imported history only partly covers (it starts
or stops inside the month) is marked complete=False.
"""

from __future__ import annotations

from datetime import date, timedelta

from engine.ledger import is_actual, is_transfer
from engine.projection import project_v2

UNEXPLAINED = "_unexplained"
UNCATEGORIZED = "_uncategorized"
COVERAGE_SLACK_DAYS = 4


def _shift(iso: str, days: int) -> str:
    return (date.fromisoformat(iso) + timedelta(days=days)).isoformat()


def _month_bounds(month: str) -> tuple[str, str]:
    y, m = int(month[:4]), int(month[5:7])
    first = date(y, m, 1)
    nxt = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
    return first.isoformat(), (nxt - timedelta(days=1)).isoformat()


def recent_months(today: str, count: int) -> list[str]:
    """The last `count` months, oldest first, ending with today's month."""
    y, m = int(today[:4]), int(today[5:7])
    out = []
    for _ in range(count):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return out[::-1]


def plan_vs_actual(rules, changes, loans, prices, months: list[str], labels: dict | None = None) -> dict:
    """Per category and month: planned and actual amounts (signed: + money in, - money out)."""
    labels = labels or {}
    planned: dict = {}
    actual: dict = {}
    has_actuals = {m: False for m in months}
    plan_changes = [c for c in changes if not is_actual(c)]
    for month in months:
        start, end = _month_bounds(month)
        _, events = project_v2(rules, plan_changes, loans, 0, prices, start, end)
        for e in events:
            cat = e.category or UNCATEGORIZED
            amt = e.amount if e.type == "income" else -e.amount
            planned.setdefault(cat, {}).setdefault(month, 0)
            planned[cat][month] += amt
    imported_dates = sorted(c["date"] for c in changes
                            if c.get("change_type") == "imported" and len(c.get("date") or "") == 10)
    for c in changes:
        d, amt = c.get("date") or "", c.get("amount") or 0
        month = d[:7]
        if month not in has_actuals or not amt or not is_actual(c):
            continue
        if c.get("change_type") == "imported":
            has_actuals[month] = True
        if is_transfer(c):
            continue
        cat = UNEXPLAINED if c.get("change_type") == "adjustment" else (c.get("category") or UNCATEGORIZED)
        actual.setdefault(cat, {}).setdefault(month, 0)
        actual[cat][month] += amt

    def label(cat):
        if cat == UNEXPLAINED:
            return "Unexplained (balance corrections)"
        if cat == UNCATEGORIZED:
            return "No category"
        if cat == "debt":
            return labels.get(cat, "Loan payments")
        return labels.get(cat) or cat.replace("_", " ").capitalize()

    rows = []
    for cat in sorted(set(planned) | set(actual)):
        cells = []
        for month in months:
            p = planned.get(cat, {}).get(month, 0)
            a = actual.get(cat, {}).get(month, 0) if has_actuals[month] else None
            cells.append({"month": month, "planned": p, "actual": a, "diff": None if a is None else a - p})
        rows.append({"category": cat, "label": label(cat), "months": cells,
                     "direction": "income" if sum(c["planned"] + (c["actual"] or 0) for c in cells) > 0 else "spending"})
    rows.sort(key=lambda r: (r["direction"] != "income", -max(abs(c["planned"]) + abs(c["actual"] or 0)
                                                               for c in r["months"])))

    totals = []
    for i, month in enumerate(months):
        start, end = _month_bounds(month)
        # Complete: the imported history runs from before the month starts to after it ends
        # (a few days' slack for posting delays), so the actuals aren't just part of the month.
        complete = bool(imported_dates) and has_actuals[month] and \
            imported_dates[0] <= _shift(start, COVERAGE_SLACK_DAYS) and imported_dates[-1] >= _shift(end, -COVERAGE_SLACK_DAYS)
        t = {"month": month, "has_actuals": has_actuals[month], "complete": complete,
             "covered_from": max(start, imported_dates[0]) if has_actuals[month] else None,
             "covered_to": min(end, imported_dates[-1]) if has_actuals[month] else None}
        for side in ("planned", "actual"):
            vals = [r["months"][i][side] for r in rows]
            if side == "actual" and not has_actuals[month]:
                t.update({"actual_income": None, "actual_spending": None, "actual_net": None})
                continue
            vals = [v or 0 for v in vals]
            t[f"{side}_income"] = sum(v for v in vals if v > 0)
            t[f"{side}_spending"] = -sum(v for v in vals if v < 0)
            t[f"{side}_net"] = sum(vals)
        totals.append(t)
    return {"months": months, "rows": rows, "totals": totals}
