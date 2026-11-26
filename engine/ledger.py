"""Account balances from recorded values plus the transactions since.

One rule, used by every page that shows a balance or net worth:

    balance on a date = the latest recorded balance on or before that date
                        + the account's transactions dated after it, up to that date

A recorded balance (a snapshot, or the value typed in when the account was added)
is the truth on its date; it is taken as the end-of-day balance, so transactions
on that same day are already in it. Between two recorded balances, transactions
explain the movement, and whatever they don't explain is the record's gap (see
balance_checks). Gaps are worked out afresh every time, never stored: import the
missing statement and the gap shrinks; undo an import and it comes back. Missing
data is normal, so a gap is something to look at or sign off, never an error.

Which entries move a balance: only what actually happened. Imported transactions
(and adjustment entries from older versions) do; one-off entries typed on the Plan page are the plan,
like rules, and never touch a balance. That split is also what keeps the plan and
the actuals from being counted twice anywhere else:

    plan    = rules + loan payments + one-off entries      (forecast, divergence, taxes)
    actual  = recorded balances + imported transactions    (balances, net worth, plan vs. actual)

Owed accounts (credit cards) hold what you owe, as a positive number: money in
lowers it and spending raises it, and net worth subtracts it.
"""

from __future__ import annotations

from bisect import bisect_right
from datetime import date, timedelta

ACTUAL_TYPES = frozenset({"imported", "adjustment"})
TRANSFER_CATEGORY = "transfer"
OWED_ACCOUNT_TYPES = frozenset({"credit_card"})

# Balance checks (see balance_checks)
GAP_ABS_CENTS = 500        # a difference this small counts as a match ($5) ...
GAP_BPS = 10               # ... or this share of the balance (0.1%), whichever is larger
TXN_REACH_DAYS = 3         # a transaction shows its days around it were imported
MISSING_MIN_DAYS = 10      # a stretch with nothing imported this long counts as missing data


def is_transfer(change: dict) -> bool:
    """Money moving between your own accounts, or paying a card: no net-worth change."""
    return (change.get("category") or "") == TRANSFER_CATEGORY


def is_actual(change: dict) -> bool:
    """Something that happened (an import or a reconcile), as opposed to a planned entry."""
    return change.get("change_type") in ACTUAL_TYPES


def is_owed(account_type: str | None) -> bool:
    return (account_type or "") in OWED_ACCOUNT_TYPES


def sign(owed: bool) -> int:
    """How a signed transaction (+ = money in) moves the stored balance."""
    return -1 if owed else 1


def account_txns(changes, today: str | None = None) -> dict:
    """{account_id: [(date, amount), ...]} oldest first: the entries that move balances."""
    out: dict = {}
    for c in changes:
        acct, d, amt = c.get("account_id"), c.get("date") or "", c.get("amount") or 0
        if not acct or not amt or not is_actual(c) or len(d) != 10:
            continue
        if today and d > today:
            continue
        out.setdefault(acct, []).append((d, amt))
    for t in out.values():
        t.sort(key=lambda x: x[0])
    return out


def value_at(points, txns, iso: str, owed: bool = False):
    """Balance on a date, or None when nothing anchors it.

    points  [(date, value)] recorded balances, oldest first
    txns    [(date, amount)] signed transactions, oldest first

    Before the first recorded balance, the value is worked back from it through
    the transactions in between, but only as far back as the first transaction.
    """
    s = sign(owed)
    anchor = None
    for p in points:
        if p[0] <= iso:
            anchor = p
    if anchor is not None:
        return anchor[1] + s * sum(a for d, a in txns if anchor[0] < d <= iso)
    if not points or not txns or iso < txns[0][0]:
        return None
    first_date, first_value = points[0]
    return first_value - s * sum(a for d, a in txns if iso < d <= first_date)


def expected_at(points, txns, iso: str, owed: bool = False):
    """What the transactions say the balance should be on `iso`, ignoring any record on that day.

    Returns (expected, anchor_date, count) or None when there is no earlier record.
    """
    earlier = [p for p in points if p[0] < iso]
    if not earlier:
        return None
    anchor_date, anchor_value = earlier[-1]
    moving = [a for d, a in txns if anchor_date < d <= iso]
    return anchor_value + sign(owed) * sum(moving), anchor_date, len(moving)


def current(recorded: int, recorded_date: str | None, txns, today: str, owed: bool = False) -> dict:
    """Today's balance from the newest record and the transactions since it."""
    since = [(d, a) for d, a in txns if (not recorded_date or d > recorded_date) and d <= today]
    flow = sum(a for _, a in since)
    last_txn = since[-1][0] if since else None
    as_of = max(filter(None, [recorded_date, last_txn]), default=None)
    return {"value": (recorded or 0) + sign(owed) * flow, "as_of": as_of, "since_count": len(since),
            "since_flow": flow, "last_txn": last_txn}


def build_ledger(snapshots, changes, owed: bool = False) -> list[dict]:
    """Recorded balances and transactions of one account in date order, with a running balance.

    snapshots  [{id, date, value, note}]
    changes    [{id, date, description, amount, category, change_type, snapshot_id, note}]
               only the ones that move the balance (see is_actual)

    On a recorded balance, `expected` is what the transactions since the previous
    record add up to and `gap` is what they leave unexplained. Rows before the first
    record have their balance worked back from it and are marked estimated.
    Returned oldest first.
    """
    s = sign(owed)
    entries = ([{"kind": "txn", **c} for c in changes]
               + [{"kind": "recorded", **snap} for snap in snapshots])
    # Same day: transactions first, then the record, which already includes them.
    entries.sort(key=lambda e: (e["date"], 0 if e["kind"] == "txn" else 1))
    running = None
    for e in entries:
        if e["kind"] == "txn":
            if running is not None:
                running += s * e["amount"]
            e["balance"] = running
        else:
            e["expected"] = running
            e["gap"] = None if running is None else e["value"] - running
            running = e["value"]
            e["balance"] = running
    first = next((i for i, e in enumerate(entries) if e["kind"] == "recorded"), None)
    if first is not None:
        back = entries[first]["value"]
        for e in reversed(entries[:first]):
            e["balance"], e["estimated"] = back, True
            back -= s * e["amount"]
    return entries


# ── Balance checks ───────────────────────────────────────────────────────────

def tolerance(value: int, abs_cents: int = GAP_ABS_CENTS, bps: int = GAP_BPS) -> int:
    """How far a record may be from what the transactions say and still count as a match."""
    return max(abs_cents, abs(value or 0) * bps // 10_000)


def uncovered(after: str, until: str, spans=(), txn_dates=(), min_days: int = MISSING_MIN_DAYS):
    """The stretches of (after, until] with nothing imported, and how many days were covered.

    spans      [(from, to)] date ranges an import covered, such as a statement's period
    txn_dates  the account's transaction dates; each one covers TXN_REACH_DAYS either side
    Returns ([(from, to, days)], covered_days); only stretches of min_days or more count.
    """
    start, end = date.fromisoformat(after) + timedelta(days=1), date.fromisoformat(until)
    if end < start:
        return [], 0
    reach = timedelta(days=TXN_REACH_DAYS)
    cover = [(date.fromisoformat(a), date.fromisoformat(b)) for a, b in spans if a and b]
    cover += [(date.fromisoformat(d) - reach, date.fromisoformat(d) + reach) for d in txn_dates]
    cover = sorted((max(a, start), min(b, end)) for a, b in cover if b >= start and a <= end)
    merged: list = []
    for a, b in cover:
        if merged and a <= merged[-1][1] + timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    covered = sum((b - a).days + 1 for a, b in merged)
    holes, cursor = [], start
    for a, b in merged + [(end + timedelta(days=1), end + timedelta(days=1))]:
        if a > cursor:
            days = (a - cursor).days
            if days >= min_days:
                holes.append((cursor.isoformat(), (a - timedelta(days=1)).isoformat(), days))
        cursor = max(cursor, b + timedelta(days=1))
    return holes, covered


def balance_checks(records, txns, owed: bool = False, spans=(), abs_cents: int = GAP_ABS_CENTS,
                   bps: int = GAP_BPS) -> list[dict]:
    """Each recorded balance against the one before it plus the transactions in between.

    records  [{id, date, value, source, gap_ok, gap_ok_at, gap_note}] one per date, oldest first
    txns     [(date, amount)] the account's transactions that move its balance, oldest first
    spans    [(from, to)] the dates the account's imports cover

    One check per record after the first, oldest first. An account with no
    transactions has nothing to check against, so it gets none.

    gap = recorded - expected, in the account's own terms (for an owed account, a
    positive gap means you owe more than the transactions say).

    status
      matches     the transactions explain the record, within the tolerance
      open        a difference no one has looked at yet
      signed_off  a difference you accepted; it stays accepted while imports only shrink it
      changed     you accepted a difference, but it has grown or flipped since
      untracked   nothing was imported for the period, so there is nothing to check it with
    """
    if not txns:
        return []
    s = sign(owed)
    txns = sorted(txns)
    dates = [d for d, _ in txns]
    running = [0]  # running[i] = sum of the first i amounts
    for _, a in txns:
        running.append(running[-1] + a)
    out = []
    for prev, rec in zip(records, records[1:]):
        lo, hi = bisect_right(dates, prev["date"]), bisect_right(dates, rec["date"])
        flow, count = running[hi] - running[lo], hi - lo
        expected = prev["value"] + s * flow
        gap = rec["value"] - expected
        missing, covered = uncovered(prev["date"], rec["date"], spans, dates[lo:hi])
        tol = tolerance(rec["value"], abs_cents, bps)
        ok = rec.get("gap_ok")
        if abs(gap) <= tol:
            status = "matches"
        elif ok is not None:
            status = "signed_off" if ok and gap * ok > 0 and abs(gap) <= abs(ok) else "changed"
        elif not count and not covered:
            status = "untracked"
        else:
            status = "open"
        out.append({
            "id": rec.get("id"), "date": rec["date"], "value": rec["value"], "source": rec.get("source"),
            "since_date": prev["date"], "since_value": prev["value"], "since_source": prev.get("source"),
            "expected": expected, "gap": gap, "count": count, "flow": flow, "owed": owed,
            "missing": missing, "covered_days": covered,
            "period_days": (date.fromisoformat(rec["date"]) - date.fromisoformat(prev["date"])).days,
            "tolerance": tol, "status": status, "gap_ok": ok, "gap_ok_at": rec.get("gap_ok_at"),
            "gap_note": rec.get("gap_note"), "explained_since": abs(ok) - abs(gap) if status == "signed_off" else None,
        })
    return out


NEEDS_LOOK = frozenset({"open", "changed"})
HAS_GAP = frozenset({"open", "changed", "signed_off"})


def unexplained_flows(checks) -> list[tuple[str, str, int]]:
    """Where each record's gap most likely happened, as money in (+) or out (-).

    [(from, to, amount)]: spread over the stretches with nothing imported, or over
    the whole period between the two records when the imports cover all of it.
    """
    out = []
    for c in checks:
        if c["status"] not in HAS_GAP:
            continue
        flow = sign(c["owed"]) * c["gap"]
        ranges = [(a, b, n) for a, b, n in c["missing"]] or [
            ((date.fromisoformat(c["since_date"]) + timedelta(days=1)).isoformat(), c["date"], c["period_days"])]
        total_days = sum(n for _, _, n in ranges) or 1
        left = flow
        for i, (a, b, n) in enumerate(ranges):
            part = left if i == len(ranges) - 1 else round(flow * n / total_days)
            left -= part
            out.append((a, b, part))
    return out
