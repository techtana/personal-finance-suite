"""Account balances from recorded values plus the transactions since.

One rule, used by every page that shows a balance or net worth:

    balance on a date = the latest recorded balance on or before that date
                        + the account's transactions dated after it, up to that date

A recorded balance (a snapshot, or the value typed in when the account was added)
is the truth on its date; it is taken as the end-of-day balance, so transactions
on that same day are already in it. Between two recorded balances, transactions
explain the movement, and whatever they don't explain is the gap a reconcile
shows.

Which entries move a balance: only what actually happened. Imported transactions
and reconcile adjustments do; one-off entries typed on the Plan page are the plan,
like rules, and never touch a balance. That split is also what keeps the plan and
the actuals from being counted twice anywhere else:

    plan    = rules + loan payments + one-off entries      (forecast, divergence, taxes)
    actual  = recorded balances + imported transactions    (balances, net worth, plan vs. actual)

Owed accounts (credit cards) hold what you owe, as a positive number: money in
lowers it and spending raises it, and net worth subtracts it.
"""

from __future__ import annotations

ACTUAL_TYPES = frozenset({"imported", "adjustment"})
TRANSFER_CATEGORY = "transfer"
OWED_ACCOUNT_TYPES = frozenset({"credit_card"})


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
