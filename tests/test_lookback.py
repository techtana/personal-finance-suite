"""Tests for the Then vs. Now engine and API."""

import pytest

from app import create_app
from config import TestingConfig
from engine.lookback import build_lookback, net_worth_at, price_on
from models import db
from tests import lookback_sample as sample


def _with_ids(rows, prefix):
    return [dict(r, id=f"{prefix}{i}") for i, r in enumerate(rows)]


def _build(**overrides):
    args = dict(
        rules=_with_ids(sample.rules(), "r"), assets=_with_ids(sample.assets(), "a"),
        accounts=_with_ids(sample.accounts(), "c"), loans=_with_ids(sample.loans(), "l"),
        snapshots=[], prices=sample.prices(), today=sample.TODAY,
    )
    args.update(overrides)
    return build_lookback(**args)


def _by_name(result, name):
    return next(i for i in result["instruments"] if i["name"] == name)


# ── price_on ──────────────────────────────────────────────────────────────────

def test_price_on_exact_interpolated_and_outside():
    points = [("2024-01-01", 10000), ("2024-01-11", 20000)]
    assert price_on(points, "2024-01-11") == (20000, True)
    assert price_on(points, "2024-01-06") == (15000, False)
    assert price_on(points, "2023-06-01") == (10000, False)
    assert price_on(points, "2025-06-01") == (20000, False)
    assert price_on([], "2024-01-01") == (None, False)


# ── Instruments ───────────────────────────────────────────────────────────────

def test_rsu_three_moments_use_the_same_shares():
    grant = _by_name(_build(), "2023 annual RSU grant")
    # 50 + 11 x 12.5 = 187.5 sh vested by 2026-11-22
    assert grant["units"] == "187.5 of 200 sh vested"
    assert grant["decided"]["date"] == "2023-01-15"
    assert grant["decided"]["value"] == 1668750          # 187.5 x $89.00
    assert len(grant["receipts"]) == 12
    assert grant["received"]["value"] == 3391875         # sum of vest-date values
    assert grant["today"]["value"] == 4650000            # 187.5 x $248.00
    assert grant["estimated"] is False


def test_rsu_without_any_price_is_skipped_and_asks_for_one():
    result = _build(prices=[])
    assert all(i["kind"] != "RSU" for i in result["instruments"])
    assert {"ticker": "GOOG", "date": sample.TODAY, "reason": "Latest share price"} in result["missing_prices"]
    assert any("Add a share price for GOOG" in s["reason"] for s in result["skipped"])


def test_rsu_missing_vest_price_is_interpolated_and_reported():
    prices = [p for p in sample.prices() if p["date"] != "2024-04-15"]
    result = _build(prices=prices)
    grant = _by_name(result, "2023 annual RSU grant")
    assert grant["estimated"] is True
    assert [r["date"] for r in grant["receipts"] if r["estimated"]] == ["2024-04-15"]
    assert any(m["date"] == "2024-04-15" for m in result["missing_prices"])


def test_stale_latest_price_is_reported():
    prices = [p for p in sample.prices() if p["date"] != sample.TODAY]
    result = _build(prices=prices)
    assert any(m["date"] == sample.TODAY and m["reason"] == "Latest share price" for m in result["missing_prices"])
    # still valued, from the most recent price on file ($262.00)
    assert _by_name(result, "2023 annual RSU grant")["today"]["value"] == 187500 * 26200 // 1000


def test_espp_paid_received_today():
    espp = _by_name(_build(), "Employer ESPP")
    # three finished periods; the fourth ends after today
    assert [r["value"] for r in espp["receipts"]] == [402500, 441600, 520260]
    assert espp["received"]["value"] == 1364360
    # paid = 15% off the $162.00 offering-start price, for 23 sh each period
    assert espp["decided"]["value"] == pytest.approx(3 * 23 * 13770, abs=3)
    assert espp["today"]["value"] == pytest.approx(69 * 24800, abs=3)
    assert espp["decided"]["date"] == "2024-12-01"


def test_espp_without_ticker_is_skipped():
    rules = _with_ids(sample.rules(), "r")
    del rules[3]["config"]["ticker"]
    result = _build(rules=rules)
    assert all(i["kind"] != "ESPP" for i in result["instruments"])
    assert any("ticker" in s["reason"] for s in result["skipped"])


def test_asset_uses_decided_date_and_latest_snapshot():
    snaps = [{"entity_type": "asset", "entity_id": "a0", "date": "2026-01-15", "value": 44200000}]
    home = _by_name(_build(snapshots=snaps), "Home")
    assert home["decided"]["date"] == "2023-07-02"
    assert home["receipts"][0]["date"] == "2023-08-18"
    assert home["decided"]["value"] == home["received"]["value"] == 39500000
    assert home["today"]["value"] == 44200000


def test_asset_decided_date_falls_back_to_acquired_date():
    assets = _with_ids(sample.assets(), "a")
    assets[1]["decided_date"] = None
    assert _by_name(_build(assets=assets), "Car")["decided"]["date"] == "2024-06-22"


def test_instruments_sorted_by_decision_date():
    dates = [i["decided"]["date"] for i in _build()["instruments"]]
    assert dates == sorted(dates) and len(dates) == 6


# ── Net worth history ─────────────────────────────────────────────────────────

def test_net_worth_carries_snapshots_forward_and_flags_gaps():
    entities = [
        {"type": "cash", "id": "c", "current": 500, "current_date": "2026-01-01"},
        {"type": "asset", "id": "a", "current": 900, "current_date": "2026-01-01", "first_date": "2024-06-01", "first_value": 800},
        {"type": "liability", "id": "l", "current": 300, "current_date": "2026-01-01", "first_date": "2024-06-01", "first_value": 600},
    ]
    snaps = {("cash", "c"): [("2025-01-01", 100), ("2025-07-01", 200)], ("liability", "l"): [("2025-03-01", 450)]}
    assert net_worth_at(entities, snaps, "2024-01-01") == (0, True)           # asset and loan not started, cash unknown
    assert net_worth_at(entities, snaps, "2024-07-01") == (200, True)         # 800 - 600, cash still unknown
    assert net_worth_at(entities, snaps, "2025-02-01") == (100 + 800 - 600, False)
    assert net_worth_at(entities, snaps, "2025-08-01") == (200 + 800 - 450, False)
    assert net_worth_at(entities, snaps, "2026-02-01") == (500 + 900 - 300, False)
    assert net_worth_at([entities[0]], {}, "2020-01-01") == (None, True)


def test_series_ends_today_and_events_carry_net_worth():
    result = _build()
    series = result["net_worth"]["series"]
    assert series[-1]["date"] == sample.TODAY
    assert series[-1]["value"] == result["net_worth"]["now"]
    assert [p["date"] for p in series] == sorted(p["date"] for p in series)
    assert "net_worth" in _by_name(result, "Home")["decided"]


# ── API ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    app = create_app(TestingConfig)
    with app.app_context():
        yield app.test_client()
        db.drop_all()


def test_prices_api_upserts_and_validates(client):
    assert client.post("/api/prices", json={"ticker": "goog", "date": "2026-01-15", "price": 20500}).status_code == 201
    assert client.post("/api/prices", json={"prices": [{"ticker": "GOOG", "date": "2026-01-15", "price": 20600}]}).status_code == 201
    rows = client.get("/api/prices?ticker=GOOG").get_json()
    assert [(r["ticker"], r["date"], r["price"]) for r in rows] == [("GOOG", "2026-01-15", 20600)]
    assert client.post("/api/prices", json={"ticker": "GOOG", "date": "nope", "price": 1}).status_code == 422
    assert client.post("/api/prices", json={"ticker": "GOOG", "date": "2026-01-15", "price": 0}).status_code == 422
    assert client.delete("/api/prices/" + rows[0]["id"]).status_code == 204
    assert client.get("/api/prices").get_json() == []


def test_then_vs_now_api_end_to_end(client):
    for rule in sample.rules():
        payload = dict(rule)
        if rule["rule_type"] == "rsu":   # the rules API rebuilds RSU schedules from these
            payload["config"] = dict(rule["config"], cliff_months=12, cliff_percent=2500,
                                     subsequent_frequency="quarterly", subsequent_percent=625)
        assert client.post("/api/rules", json=payload).status_code == 201
    for asset in sample.assets():
        assert client.post("/api/assets", json=asset).status_code == 201
    assert client.post("/api/prices", json={"prices": sample.prices()}).status_code == 201

    data = client.get("/api/then-vs-now?today=" + sample.TODAY).get_json()
    assert data["today"] == sample.TODAY
    assert len(data["instruments"]) == 6
    assert data["missing_prices"] == []
    grant = next(i for i in data["instruments"] if i["name"] == "2023 annual RSU grant")
    assert (grant["decided"]["value"], grant["received"]["value"], grant["today"]["value"]) == (1668750, 3391875, 4650000)
    car = next(i for i in data["instruments"] if i["name"] == "Car")
    assert car["decided"]["date"] == "2024-06-10"


def test_then_vs_now_api_empty(client):
    data = client.get("/api/then-vs-now").get_json()
    assert data["instruments"] == [] and data["net_worth"]["series"] == []
