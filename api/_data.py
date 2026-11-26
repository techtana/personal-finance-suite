"""Shared loaders that turn database rows into the plain dicts the engines take.

Every page that shows a balance, a forecast or an insight goes through these, so
"current value" and "net worth" mean the same thing everywhere.
"""

from datetime import date

from flask import has_request_context, request

from engine import ledger
from models import Account, Asset, ChangeEvent, Loan, PricePoint, Rule, Settings, Snapshot, db

DEFAULT_STALE_DAYS = 35
DEFAULT_DIVERGENCE_BPS = 500  # 5%


def today_iso(value=None) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        return date.today().isoformat()


def snapshot_history() -> dict:
    """{(entity_type, entity_id): [(date, value), ...]} oldest first."""
    snaps: dict = {}
    for s in Snapshot.query.order_by(Snapshot.date.asc(), Snapshot.created_at.asc()).all():
        snaps.setdefault((s.entity_type, s.entity_id), []).append((s.date, s.value))
    return snaps


def current_value(field_value, field_date, history) -> tuple[int, str | None]:
    """(value, as-of date). The newer of the entity's own field and its last snapshot wins."""
    if history:
        snap_date, snap_value = history[-1]
        if not field_date or snap_date >= field_date:
            return snap_value, snap_date
    return field_value or 0, field_date


def account_points(account, before: str | None = None) -> list:
    """[(date, value)] recorded balances of one cash account, oldest first.

    The value typed in with the account counts as a record on its date when no
    snapshot is as new. `before` keeps only records dated before that day.
    """
    points = [(s.date, s.value) for s in Snapshot.query.filter_by(entity_type="cash", entity_id=account.id)
              .order_by(Snapshot.date.asc(), Snapshot.created_at.asc()).all()]
    if account.last_updated_date and not any(p[0] >= account.last_updated_date for p in points):
        points.append((account.last_updated_date, account.current_balance or 0))
        points.sort(key=lambda p: p[0])
    return [p for p in points if before is None or p[0] < before]


def balance_txns(today: str | None = None) -> dict:
    """{account_id: [(date, amount)]}: the imported transactions and adjustments that move balances."""
    return ledger.account_txns(change_dicts(), today or date.today().isoformat())


def load_entities(snaps=None, txns=None, today: str | None = None) -> list[dict]:
    """Every tracked cash account, asset and liability in one shape.

    type: cash | asset | liability. `current` is always positive; `negative` says
    whether net worth subtracts it (liabilities, and owed accounts such as credit
    cards). first_date / first_value let history start before the first recorded
    balance (cost basis for assets, original balance for loans).

    For cash accounts `current` is the newest recorded balance (`recorded`, on
    `recorded_date`) plus the transactions since (see engine.ledger), and
    `current_date` is the newer of that record and the last transaction.
    """
    today = today or date.today().isoformat()
    snaps = snapshot_history() if snaps is None else snaps
    txns = balance_txns(today) if txns is None else txns
    out = []
    for a in Account.query.filter_by(is_active=True).all():
        history = snaps.get(("cash", a.id))
        recorded, rec_date = current_value(a.current_balance, a.last_updated_date, history)
        owed = ledger.is_owed(a.type)
        t = txns.get(a.id, [])
        now = ledger.current(recorded, rec_date, t, today, owed)
        out.append({"type": "cash", "id": a.id, "name": a.name, "kind": a.type, "institution": a.institution or "",
                    "current": now["value"], "current_date": now["as_of"], "first_date": None, "first_value": None,
                    "recorded": recorded, "recorded_date": rec_date, "txns": t, "owed": owed, "negative": owed,
                    "since_count": now["since_count"], "since_flow": now["since_flow"], "txn_count": len(t),
                    "has_snapshots": bool(history), "note": a.note})
    for a in Asset.query.all():
        value, as_of = current_value(a.current_value, a.last_updated_date, snaps.get(("asset", a.id)))
        out.append({"type": "asset", "id": a.id, "name": a.name, "kind": a.category, "institution": a.ticker or "",
                    "current": value, "current_date": as_of, "first_date": a.acquired_date,
                    "first_value": a.cost_basis, "negative": False, "note": a.note})
    for l in Loan.query.all():
        value, as_of = current_value(l.current_balance, l.last_updated_date, snaps.get(("liability", l.id)))
        out.append({"type": "liability", "id": l.id, "name": l.name, "kind": l.type,
                    "institution": l.institution or "", "current": value, "current_date": as_of,
                    "first_date": l.start_date, "first_value": l.original_balance, "negative": True, "note": l.note})
    return out


def bucket(entity: dict) -> str:
    """Which total an entity adds to: cash, asset or liability (owed accounts count as liabilities)."""
    return "liability" if entity.get("owed") else entity["type"]


def signed(entity: dict) -> int:
    return -entity["current"] if entity.get("negative", entity["type"] == "liability") else entity["current"]


def totals(entities: list[dict]) -> dict:
    t = {"cash": 0, "asset": 0, "liability": 0}
    for e in entities:
        t[bucket(e)] += e["current"]
    return {"cash": t["cash"], "assets": t["asset"], "liabilities": t["liability"],
            "net_worth": t["cash"] + t["asset"] - t["liability"]}


def rule_dicts(active_only=True) -> list[dict]:
    q = Rule.query.filter_by(is_active=True) if active_only else Rule.query
    return [
        {"id": r.id, "name": r.name, "rule_type": r.rule_type, "account_id": r.account_id, "amount": r.amount,
         "frequency": r.frequency, "start_date": r.start_date, "end_date": r.end_date, "category": r.category,
         "schedule": r.schedule, "config": r.config, "is_active": r.is_active, "tax_treatment": r.tax_treatment}
        for r in q.all()
    ]


_CHANGE_COLUMNS = ("id", "date", "description", "amount", "category", "account_id", "change_type",
                   "tax_treatment", "snapshot_id")


def change_dicts() -> list[dict]:
    """Every one-off entry and imported transaction as a plain dict.

    This is the biggest table (years of imported transactions), so it is read as
    plain columns rather than ORM objects, and read once per GET request however
    many engines ask for it. Callers get their own list but share the dicts:
    treat them as read-only.
    """
    memo = _request_memo()
    if memo is not None and "changes" in memo:
        return list(memo["changes"])
    cols = [getattr(ChangeEvent, c) for c in _CHANGE_COLUMNS]
    rows = [dict(zip(_CHANGE_COLUMNS, r)) for r in db.session.query(*cols).all()]
    if memo is not None:
        memo["changes"] = rows
    return list(rows)


def _request_memo():
    """A per-request cache, only for reads: a GET never writes, so nothing it loaded goes stale."""
    if not has_request_context() or request.method != "GET":
        return None
    # Kept on the request itself (not flask.g, which can outlive one request).
    return request.environ.setdefault("finance.data_memo", {})


def loan_dicts() -> list[dict]:
    return [
        {"id": l.id, "name": l.name, "type": l.type, "current_balance": l.current_balance,
         "original_balance": l.original_balance, "interest_rate": l.interest_rate,
         "monthly_payment": l.monthly_payment, "start_date": l.start_date, "payoff_date": l.payoff_date}
        for l in Loan.query.all()
    ]


def latest_prices(today: str | None = None) -> dict:
    """{ticker: cents per share}, the most recent hand-entered price on or before today."""
    today = today or date.today().isoformat()
    out: dict = {}
    for p in PricePoint.query.order_by(PricePoint.date.asc()).all():
        if p.date <= today:
            out[p.ticker.upper()] = p.price
    return out


def thresholds() -> dict:
    # Read-only on purpose: several requests arrive at once on a fresh database,
    # and creating the settings row here would race.
    settings = Settings.query.first()
    raw = (settings.divergence_thresholds if settings else None) or {}

    def _int(key, default):
        try:
            return max(1, int(raw.get(key, default)))
        except (TypeError, ValueError):
            return default

    return {"stale_days": _int("stale_days", DEFAULT_STALE_DAYS),
            "net_worth_bps": _int("net_worth_bps", DEFAULT_DIVERGENCE_BPS)}
