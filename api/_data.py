"""Shared loaders that turn database rows into the plain dicts the engines take.

Every page that shows a balance, a forecast or an insight goes through these, so
"current value" and "net worth" mean the same thing everywhere.
"""

from datetime import date

from models import Account, Asset, ChangeEvent, Loan, PricePoint, Rule, Settings, Snapshot

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


def load_entities(snaps=None) -> list[dict]:
    """Every tracked cash account, asset and liability in one shape.

    type: cash | asset | liability. `current` is always positive; liabilities are
    subtracted by the caller. first_date / first_value let history start before the
    first recorded balance (cost basis for assets, original balance for loans).
    """
    snaps = snapshot_history() if snaps is None else snaps
    out = []
    for a in Account.query.filter_by(is_active=True).all():
        value, as_of = current_value(a.current_balance, a.last_updated_date, snaps.get(("cash", a.id)))
        out.append({"type": "cash", "id": a.id, "name": a.name, "kind": a.type, "institution": a.institution or "",
                    "current": value, "current_date": as_of, "first_date": None, "first_value": None,
                    "note": a.note})
    for a in Asset.query.all():
        value, as_of = current_value(a.current_value, a.last_updated_date, snaps.get(("asset", a.id)))
        out.append({"type": "asset", "id": a.id, "name": a.name, "kind": a.category, "institution": a.ticker or "",
                    "current": value, "current_date": as_of, "first_date": a.acquired_date,
                    "first_value": a.cost_basis, "note": a.note})
    for l in Loan.query.all():
        value, as_of = current_value(l.current_balance, l.last_updated_date, snaps.get(("liability", l.id)))
        out.append({"type": "liability", "id": l.id, "name": l.name, "kind": l.type,
                    "institution": l.institution or "", "current": value, "current_date": as_of,
                    "first_date": l.start_date, "first_value": l.original_balance, "note": l.note})
    return out


def totals(entities: list[dict]) -> dict:
    t = {"cash": 0, "asset": 0, "liability": 0}
    for e in entities:
        t[e["type"]] += e["current"]
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


def change_dicts() -> list[dict]:
    return [
        {"id": c.id, "date": c.date, "description": c.description, "amount": c.amount, "category": c.category,
         "account_id": c.account_id, "change_type": c.change_type, "tax_treatment": c.tax_treatment}
        for c in ChangeEvent.query.all()
    ]


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
