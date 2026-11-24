"""Then vs. now: what each decision was worth when decided, when received, and today.

Every instrument is valued three times on the same units:

  decided   the day you said yes (grant accepted, ESPP offering started, purchase agreed)
  received  the day it landed (shares vested or bought, asset acquired)
  today     the latest known value

All money is in cents. Share counts are milli-shares (x1000), as in the rules engine.
Shares are counted gross: sell-to-cover and later sales are not tracked.
"""

from datetime import date as _date, timedelta

from engine.ledger import value_at

STALE_PRICE_DAYS = 7      # a "today" price older than this is reported as missing
MAX_HISTORY_YEARS = 20


def _d(iso: str) -> _date:
    return _date.fromisoformat(iso)


def _valid(iso) -> bool:
    try:
        _d(iso)
        return True
    except (TypeError, ValueError):
        return False


# ── Prices ────────────────────────────────────────────────────────────────────

def price_on(points: list, iso: str):
    """Price on a date from sorted (date, cents) points.

    Returns (price, exact). An exact point wins; between two points the price is
    interpolated by day; outside the range the nearest point is used. Anything
    that is not an exact point comes back with exact=False. No points → (None, False).
    """
    if not points:
        return None, False
    prev = nxt = None
    for p_date, p_val in points:
        if p_date == iso:
            return p_val, True
        if p_date < iso:
            prev = (p_date, p_val)
        elif nxt is None:
            nxt = (p_date, p_val)
            break
    if prev and nxt:
        span = (_d(nxt[0]) - _d(prev[0])).days
        done = (_d(iso) - _d(prev[0])).days
        return round(prev[1] + (nxt[1] - prev[1]) * done / span), False
    return (prev or nxt)[1], False


def latest_price(points: list, today: str):
    """Most recent point on or before today → (price, date), or (None, None)."""
    best = None
    for p_date, p_val in points:
        if p_date <= today:
            best = (p_val, p_date)
    return best or (None, None)


def _shares_text(millis: int) -> str:
    return f"{millis / 1000:g}"


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


# ── Instruments ───────────────────────────────────────────────────────────────

def _rsu(rule: dict, prices: dict, today: str, missing: list):
    cfg = rule.get("config") or {}
    ticker = (cfg.get("ticker") or "").upper()
    name = rule.get("name") or "RSU grant"
    grant_date = cfg.get("grant_date") or rule.get("start_date")
    if not _valid(grant_date):
        return None, "The grant has no grant date."
    vested = sorted(
        (v for v in (rule.get("schedule") or [])
         if _valid(v.get("date")) and v["date"] <= today and (v.get("shares") or 0) > 0),
        key=lambda v: v["date"],
    )
    if not vested:
        return None, "Nothing has vested yet."

    real = prices.get(ticker, [])
    if not real:
        missing.append({"ticker": ticker, "date": today, "reason": "Latest share price"})
        return None, f"Add a share price for {ticker or 'this grant'} to value it today."

    grant_price = cfg.get("price_at_grant") or None
    points = list(real)
    if grant_price and not any(p[0] == grant_date for p in points):
        points = sorted(points + [(grant_date, grant_price)])
    if not grant_price:
        grant_price, exact = price_on(points, grant_date)
        if not exact:
            missing.append({"ticker": ticker, "date": grant_date, "reason": f"{name}: grant date"})

    units = sum(v["shares"] for v in vested)
    total = cfg.get("total_shares") or sum((v.get("shares") or 0) for v in (rule.get("schedule") or []))
    receipts, estimated = [], False
    for v in vested:
        p, exact = price_on(points, v["date"])
        if not exact:
            estimated = True
            missing.append({"ticker": ticker, "date": v["date"], "reason": f"{name}: vest date"})
        receipts.append({
            "date": v["date"],
            "value": v["shares"] * p // 1000,
            "text": f"{_shares_text(v['shares'])} sh vested at {_money(p)}",
            "estimated": not exact,
        })

    now_price, now_date = latest_price(real, today)
    if now_price is None:
        now_price, now_date = real[0][1], real[0][0]
    if (_d(today) - _d(now_date)).days > STALE_PRICE_DAYS:
        missing.append({"ticker": ticker, "date": today, "reason": "Latest share price"})

    unvested = max(0, total - units)
    note = "Shares are counted before any were sold to cover tax or sold later."
    if unvested:
        note = f"{_shares_text(unvested)} sh are still unvested and not counted. " + note
    return {
        "id": "rule:" + rule["id"],
        "kind": "RSU",
        "name": name,
        "ticker": ticker,
        "units": f"{_shares_text(units)} of {_shares_text(total)} sh vested",
        "decided": {
            "date": grant_date,
            "value": units * grant_price // 1000,
            "text": f"Granted {_shares_text(total)} sh at {_money(grant_price)}. Counting the {_shares_text(units)} sh received so far.",
        },
        "receipts": receipts,
        "received_text": "Value on each vest date. This is the amount taxed as income.",
        "received_label": "vest",
        "today": {
            "value": units * now_price // 1000,
            "text": f"{_shares_text(units)} sh at {_money(now_price)} (price from {now_date}).",
        },
        "estimated": estimated,
        "note": note,
    }, None


def _espp(rule: dict, prices: dict, today: str, missing: list):
    cfg = rule.get("config") or {}
    ticker = (cfg.get("ticker") or "").upper()
    name = rule.get("name") or "ESPP"
    done = sorted(
        (p for p in (rule.get("schedule") or [])
         if _valid(p.get("end_date")) and p["end_date"] <= today and (p.get("estimated_purchase_amount") or 0) > 0),
        key=lambda p: p["end_date"],
    )
    if not done:
        return None, "No purchase period has finished yet."
    if not ticker:
        return None, "Add a ticker to this ESPP plan so its shares can be valued today."
    points = prices.get(ticker, [])
    if not points:
        missing.append({"ticker": ticker, "date": today, "reason": "Latest share price"})
        return None, f"Add a share price for {ticker} to value it today."

    discount = (cfg.get("discount_rate") or 0) / 10000
    offer_start = cfg.get("offering_start_date") or rule.get("start_date")
    lookback = cfg.get("has_lookback", True) and _valid(offer_start)
    start_price = None
    if lookback:
        start_price, exact = price_on(points, offer_start)
        if not exact:
            missing.append({"ticker": ticker, "date": offer_start, "reason": f"{name}: offering start"})

    now_price, now_date = latest_price(points, today)
    if now_price is None:
        now_price, now_date = points[0][1], points[0][0]
    if (_d(today) - _d(now_date)).days > STALE_PRICE_DAYS:
        missing.append({"ticker": ticker, "date": today, "reason": "Latest share price"})

    paid = today_value = shares_m = 0
    receipts, estimated = [], False
    for p in done:
        fmv = p["estimated_purchase_amount"]
        end_price, exact = price_on(points, p["end_date"])
        if not exact:
            estimated = True
            missing.append({"ticker": ticker, "date": p["end_date"], "reason": f"{name}: purchase date"})
        base = min(start_price, end_price) if start_price else end_price
        paid += round(fmv * base / end_price * (1 - discount))
        today_value += round(fmv * now_price / end_price)
        shares_m += round(fmv * 1000 / end_price)
        receipts.append({
            "date": p["end_date"],
            "value": fmv,
            "text": f"Shares bought, market price {_money(end_price)}",
            "estimated": not exact,
        })

    decided_date = offer_start if _valid(offer_start) else done[0].get("start_date") or done[0]["end_date"]
    pct = f"{discount * 100:g}%"
    return {
        "id": "rule:" + rule["id"],
        "kind": "ESPP",
        "name": name,
        "ticker": ticker,
        "units": f"about {_shares_text(shares_m)} sh from {len(done)} purchase{'s' if len(done) != 1 else ''}",
        "decided": {
            "date": decided_date,
            "value": paid,
            "text": "What you paid for the shares bought so far.",
        },
        "receipts": receipts,
        "received_text": "Market value on each purchase date.",
        "received_label": "purchase",
        "today": {
            "value": today_value,
            "text": f"About {_shares_text(shares_m)} sh at {_money(now_price)} (price from {now_date}).",
        },
        "estimated": estimated,
        "note": f"Your price is {pct} off the "
                + ("lower of the offering-start and purchase-day prices." if lookback else "purchase-day price.")
                + " Share counts are worked out from the purchase value, so they are approximate.",
    }, None


def _asset(asset: dict, snaps: dict, today: str):
    received_date = asset.get("acquired_date")
    if not asset.get("cost_basis") or not _valid(received_date):
        return None, "Add a cost basis and an acquired date to include it."
    if received_date > today:
        return None, "Not acquired yet."
    decided_date = asset.get("decided_date")
    if not _valid(decided_date) or decided_date > received_date:
        decided_date = received_date
    history = [s for s in snaps.get(("asset", asset["id"]), []) if s[0] <= today]
    if history:
        now_date, now_value = history[-1]
    else:
        now_date, now_value = asset.get("last_updated_date") or today, asset.get("current_value") or 0
    qty = asset.get("quantity")
    return {
        "id": "asset:" + asset["id"],
        "kind": (asset.get("category") or "asset").replace("_", " ").capitalize(),
        "name": asset.get("name") or "Asset",
        "ticker": asset.get("ticker") or "",
        "units": f"{qty:g} units" if qty else "1 asset",
        "decided": {"date": decided_date, "value": asset["cost_basis"], "text": "What you agreed to pay."},
        "receipts": [{"date": received_date, "value": asset["cost_basis"], "text": "Acquired at cost.", "estimated": False}],
        "received_text": "Acquired at cost.",
        "received_label": "",
        "today": {"value": now_value, "text": f"Latest recorded value, from {now_date}."},
        "estimated": False,
        "note": asset.get("note") or "",
    }, None


# ── Net worth history ─────────────────────────────────────────────────────────

def _entity_value(entity: dict, history: list, iso: str):
    """Value of one account, asset or loan on a date. None = not recorded yet.

    The latest snapshot on or before the date wins. The entity's own recorded
    value counts as a snapshot on its last-updated date. Cash accounts that carry
    `txns` add the transactions since that record (engine.ledger.value_at).
    Before any snapshot, assets fall back to cost basis and loans to their
    starting balance from the day they began, and are worth nothing before that.
    """
    points = list(history)
    cur_date = entity.get("recorded_date", entity.get("current_date"))
    cur_value = entity.get("recorded", entity.get("current"))
    if _valid(cur_date) and not any(p[0] >= cur_date for p in points):
        points.append((cur_date, cur_value or 0))
    if entity.get("txns"):
        v = value_at(points, entity["txns"], iso, bool(entity.get("owed")))
        if v is not None:
            return v
    best = None
    for p_date, p_val in points:
        if p_date <= iso:
            best = p_val
    if best is not None:
        return best
    first = entity.get("first_date")
    if _valid(first):
        if iso < first:
            return 0
        if entity.get("first_value") is not None:
            return entity["first_value"]
    return None


def net_worth_at(entities: list, snaps: dict, iso: str):
    """(net worth, partial) on a date; (None, True) when nothing is recorded yet.

    partial=True means at least one account, asset or loan had no record that
    early and was left out.
    """
    total, known, partial = 0, 0, False
    for e in entities:
        v = _entity_value(e, snaps.get((e["type"], e["id"]), []), iso)
        if v is None:
            partial = True
            continue
        known += 1
        total += -v if e.get("negative", e["type"] == "liability") else v
    if not known:
        return None, True
    return total, partial


def _month_ends(start: str, end: str):
    y, m = _d(start).year, _d(start).month
    last = _d(end)
    while True:
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        month_end = _date(ny, nm, 1) - timedelta(days=1)
        if month_end >= last:
            return
        yield month_end.isoformat()
        y, m = ny, nm


def net_worth_series(entities: list, snaps: dict, start: str, today: str) -> list:
    """Month-end net worth from start to today, ending on today itself."""
    floor = _date(_d(today).year - MAX_HISTORY_YEARS, 1, 1).isoformat()
    start = max(start, floor)
    out = []
    for iso in list(_month_ends(start, today)) + [today]:
        if iso < start:
            continue
        value, partial = net_worth_at(entities, snaps, iso)
        if value is not None:
            out.append({"date": iso, "value": value, "partial": partial})
    return out


# ── Assembly ──────────────────────────────────────────────────────────────────

def build_lookback(rules, assets, accounts, loans, snapshots, prices, today: str) -> dict:
    """Build the whole then-vs-now payload from plain dicts.

    rules      [{id, name, rule_type, start_date, schedule, config}]
    assets     [{id, name, category, ticker, quantity, current_value, cost_basis,
                 acquired_date, decided_date, last_updated_date, note}]
    accounts   [{id, current_balance, last_updated_date}]
    loans      [{id, current_balance, original_balance, start_date, last_updated_date}]
    snapshots  [{entity_type, entity_id, date, value}]
    prices     [{ticker, date, price}]
    """
    snaps: dict = {}
    for s in snapshots:
        if _valid(s.get("date")):
            snaps.setdefault((s["entity_type"], s["entity_id"]), []).append((s["date"], s["value"]))
    for history in snaps.values():
        history.sort()

    by_ticker: dict = {}
    for p in prices:
        if _valid(p.get("date")) and (p.get("price") or 0) > 0:
            by_ticker.setdefault((p.get("ticker") or "").upper(), []).append((p["date"], p["price"]))
    for points in by_ticker.values():
        points.sort()

    instruments, skipped, missing = [], [], []
    for rule in rules:
        builder = {"rsu": _rsu, "espp": _espp}.get(rule.get("rule_type"))
        if not builder:
            continue
        inst, why = builder(rule, by_ticker, today, missing)
        if inst:
            instruments.append(inst)
        else:
            skipped.append({"name": rule.get("name") or rule.get("rule_type"), "reason": why})
    for asset in assets:
        inst, why = _asset(asset, snaps, today)
        if inst:
            instruments.append(inst)
        elif asset.get("cost_basis") or asset.get("acquired_date"):
            skipped.append({"name": asset.get("name") or "Asset", "reason": why})

    entities = (
        [{"type": "cash", "id": a["id"], "current": a.get("current_balance") or 0,
          "current_date": a.get("last_updated_date"), "txns": a.get("txns") or [],
          "owed": bool(a.get("owed")), "negative": bool(a.get("owed"))} for a in accounts]
        + [{"type": "asset", "id": a["id"], "current": a.get("current_value") or 0,
            "current_date": a.get("last_updated_date"),
            "first_date": a.get("acquired_date"), "first_value": a.get("cost_basis")} for a in assets]
        + [{"type": "liability", "id": l["id"], "current": l.get("current_balance") or 0,
            "current_date": l.get("last_updated_date"),
            "first_date": l.get("start_date"), "first_value": l.get("original_balance")} for l in loans]
    )

    def with_nw(event: dict) -> dict:
        value, partial = net_worth_at(entities, snaps, event["date"])
        event["net_worth"] = value
        event["net_worth_partial"] = partial
        return event

    for inst in instruments:
        with_nw(inst["decided"])
        for r in inst["receipts"]:
            with_nw(r)
        inst["received"] = {"value": sum(r["value"] for r in inst["receipts"])}
    instruments.sort(key=lambda i: i["decided"]["date"])

    # Start the line at the first record of anything, or the first decision if that is later.
    recorded = [h[0][0] for h in snaps.values() if h]
    recorded += [e["first_date"] for e in entities if _valid(e.get("first_date"))]
    recorded += [e["current_date"] for e in entities if _valid(e.get("current_date"))]
    recorded += [e["txns"][0][0] for e in entities if e.get("txns")]
    series = net_worth_series(entities, snaps, min(recorded), today) if recorded else []
    now_value, _ = net_worth_at(entities, snaps, today)

    seen, missing_unique = set(), []
    for m in sorted(missing, key=lambda m: (m["ticker"], m["date"])):
        key = (m["ticker"], m["date"])
        if key not in seen and m["ticker"]:
            seen.add(key)
            missing_unique.append(m)

    return {
        "today": today,
        "instruments": instruments,
        "skipped": skipped,
        "missing_prices": missing_unique,
        "net_worth": {"series": series, "now": now_value},
    }
