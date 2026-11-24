"""The role-based pages and the read models behind them: balances, insights, what-if, backup, assistant."""

from datetime import date, timedelta

import pytest

from engine import assistant as A
from engine.projection import project_v2
from tests.sample_data import load_sample_data
from models import Account, ChangeEvent, Loan, OneTimeTxn, RecurringTxn, Rule, Snapshot, db

TODAY = date.today().isoformat()


def days_ago(n):
    return (date.today() - timedelta(days=n)).isoformat()


@pytest.fixture
def seeded(client):
    load_sample_data()
    return client


# ── Pages ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path,chip", [
    ("/overview", "View only"), ("/forecast", "View only"), ("/then-vs-now", "View only"), ("/taxes", "View + inputs"),
    ("/plan", "You manage"), ("/balances", "You manage"), ("/import", "You manage"), ("/insights", "Guidance"),
    ("/settings", None),
])
def test_every_page_renders_with_its_role(client, path, chip):
    res = client.get(path)
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    for group in ("Your picture", "Your inputs", "Guidance"):
        assert group in html
    if chip:
        assert f'">{chip}</span>' in html


@pytest.mark.parametrize("old,new", [
    ("/", "/overview"), ("/dashboard", "/overview"), ("/timeline", "/forecast"), ("/transactions", "/plan"),
    ("/accounts", "/balances?type=cash"), ("/equity", "/balances?type=asset"), ("/loans", "/balances?type=liability"),
])
def test_old_addresses_redirect(client, old, new):
    res = client.get(old)
    assert res.status_code == 302 and res.headers["Location"].endswith(new)


def test_old_endpoints_are_gone(client):
    for path in ("/api/transactions/one-time", "/api/equity/rsu", "/api/projection/legacy"):
        assert client.get(path).status_code == 404


# ── Balances ──────────────────────────────────────────────────────────────────

def test_balances_lists_all_three_kinds_with_freshness(app, client):
    db.session.add_all([
        Account(name="Checking", type="checking", institution="Bank", current_balance=100000, last_updated_date=TODAY),
        Account(name="Old savings", type="savings", institution="Bank", current_balance=500000,
                last_updated_date=days_ago(90)),
        Loan(name="Car", type="auto", institution="CU", original_balance=900000, current_balance=400000,
             interest_rate=500, monthly_payment=20000, start_date=days_ago(400), payoff_date="2030-01-01",
             last_updated_date=TODAY),
    ])
    db.session.commit()
    body = client.get("/api/balances").get_json()
    assert body["totals"] == {"cash": 600000, "assets": 0, "liabilities": 400000, "net_worth": 200000}
    by_name = {r["name"]: r for r in body["rows"]}
    assert by_name["Old savings"]["stale"] and by_name["Old savings"]["days_since"] == 90
    assert not by_name["Checking"]["stale"]
    assert by_name["Car"]["signed_value"] == -400000
    assert body["stale_count"] == 1


def test_record_balance_updates_entity_and_history(app, client):
    acct = Account(name="Checking", type="checking", institution="Bank", current_balance=100000,
                   last_updated_date=days_ago(40))
    db.session.add(acct)
    db.session.commit()

    res = client.post("/api/balances/record", json={"entity_type": "cash", "entity_id": acct.id, "value": 123400})
    assert res.status_code == 201
    assert acct.current_balance == 123400 and acct.last_updated_date == TODAY
    # Same day again replaces rather than duplicating.
    client.post("/api/balances/record", json={"entity_type": "cash", "entity_id": acct.id, "value": 125000})
    assert Snapshot.query.filter_by(entity_id=acct.id).count() == 1 and acct.current_balance == 125000
    # A back-dated record is kept in history but does not overwrite the current value.
    client.post("/api/balances/record", json={"entity_type": "cash", "entity_id": acct.id, "value": 90000,
                                              "date": days_ago(60)})
    assert acct.current_balance == 125000 and Snapshot.query.filter_by(entity_id=acct.id).count() == 2


@pytest.mark.parametrize("payload,status", [
    ({"entity_type": "bogus", "entity_id": "x", "value": 1}, 422),
    ({"entity_type": "cash", "entity_id": "missing", "value": 1}, 404),
])
def test_record_balance_rejects_bad_input(client, payload, status):
    assert client.post("/api/balances/record", json=payload).status_code == status


def test_record_balance_rejects_negative_and_bad_date(app, client):
    acct = Account(name="Checking", type="checking", institution="Bank", current_balance=1, last_updated_date=TODAY)
    db.session.add(acct)
    db.session.commit()
    base = {"entity_type": "cash", "entity_id": acct.id}
    assert client.post("/api/balances/record", json={**base, "value": -5}).status_code == 422
    assert client.post("/api/balances/record", json={**base, "value": 5, "date": "soon"}).status_code == 422


def test_net_worth_history_splits_and_filters_by_type(seeded):
    full = seeded.get("/api/net-worth/history?months=6").get_json()["series"]
    assert full and full[-1]["date"] == TODAY
    last = full[-1]
    assert last["net_worth"] == last["cash"] + last["assets"] - last["liabilities"]
    cash_only = seeded.get("/api/net-worth/history?months=6&types=cash").get_json()["series"][-1]
    assert cash_only["assets"] == 0 and cash_only["liabilities"] == 0 and cash_only["net_worth"] == last["cash"]


# ── Forecast ──────────────────────────────────────────────────────────────────

RULES = [{"id": "sal", "name": "Salary", "rule_type": "income", "amount": 500000, "frequency": "monthly",
          "start_date": "2026-01-01"},
         {"id": "rent", "name": "Rent", "rule_type": "expense", "amount": 200000, "frequency": "monthly",
          "start_date": "2026-01-01"}]


def test_project_v2_can_leave_items_out_and_fill_empty_months():
    base, _ = project_v2(RULES, [], [], 0, {}, "2027-01-01", "2027-06-30")
    without_rent, events = project_v2(RULES, [], [], 0, {}, "2027-01-01", "2027-06-30", disabled_ids={"rent"})
    assert base[-1].cumulative_net_worth == 6 * 300000
    assert without_rent[-1].cumulative_net_worth == 6 * 500000
    assert all(e.source_id != "rent" for e in events)

    sparse, _ = project_v2([], [{"id": "c", "date": "2027-03-10", "description": "x", "amount": 100}], [], 1000, {},
                           "2027-01-01", "2027-06-30", fill_months=True)
    assert [b.month for b in sparse] == ["2027-01", "2027-02", "2027-03", "2027-04", "2027-05", "2027-06"]
    assert [b.cumulative_net_worth for b in sparse] == [1000, 1000, 1100, 1100, 1100, 1100]


def test_projection_api_what_if_returns_baseline_and_history(seeded):
    rent = Rule.query.filter_by(name="Rent").first()
    plain = seeded.get("/api/projection?history=6").get_json()
    assert plain["baseline"] is None and plain["actuals"]
    assert plain["starting_net_worth"] == seeded.get("/api/balances").get_json()["totals"]["net_worth"]
    assert all(b["events"] is not None for b in plain["buckets"]) and len(plain["buckets"]) >= 12

    what_if = seeded.get(f"/api/projection?disable={rent.id}").get_json()
    assert what_if["disabled"] == [rent.id]
    assert what_if["buckets"][-1]["cumulative_net_worth"] > what_if["baseline"][-1]["cumulative_net_worth"]
    assert what_if["baseline"][-1]["cumulative_net_worth"] == plain["buckets"][-1]["cumulative_net_worth"]


def test_projection_values_rsu_vests_with_stored_prices(seeded):
    body = seeded.get("/api/projection").get_json()
    assert body["prices_used"] == {"EXMP": 10450}
    assert any(e["source_type"] == "rsu" and e["amount"] > 0 for e in body["events"])


# ── Insights ──────────────────────────────────────────────────────────────────

def test_insights_on_empty_database_are_empty(client):
    body = client.get("/api/insights").get_json()
    assert body["insights"] == [] and body["counts"]["attention"] == 0


def test_insights_flag_stale_balances_and_stay_quiet_when_fresh(seeded):
    items = {i["id"]: i for i in seeded.get("/api/insights").get_json()["insights"]}
    stale = items["stale-balances"]
    assert stale["severity"] == "attention" and stale["action"]["href"] == "/balances?stale=1"
    assert "High Yield Savings" in stale["detail"] and stale["basis"]
    assert "net-worth-on-track" in items or "net-worth-divergence" in items

    for row in seeded.get("/api/balances").get_json()["rows"]:
        seeded.post("/api/balances/record", json={"entity_type": row["entity_type"], "entity_id": row["id"],
                                                  "value": row["value"]})
    items = {i["id"] for i in seeded.get("/api/insights").get_json()["insights"]}
    assert "stale-balances" not in items and "balances-fresh" in items


def test_insights_report_divergence_beyond_the_limit(app, client):
    acct = Account(name="Checking", type="checking", institution="Bank", current_balance=1000000,
                   last_updated_date=days_ago(70))
    db.session.add(acct)
    db.session.flush()
    db.session.add(Snapshot(entity_type="cash", entity_id=acct.id, date=days_ago(70), value=1000000))
    db.session.commit()
    client.post("/api/balances/record", json={"entity_type": "cash", "entity_id": acct.id, "value": 1300000})

    items = {i["id"]: i for i in client.get("/api/insights").get_json()["insights"]}
    div = items["net-worth-divergence"]
    assert div["severity"] == "attention" and div["value"] == 300000 and "above" in div["title"]

    client.patch("/api/settings", json={"divergence_thresholds": {"net_worth_bps": 5000}})
    items = {i["id"] for i in client.get("/api/insights").get_json()["insights"]}
    assert "net-worth-on-track" in items and "net-worth-divergence" not in items


def test_insights_point_out_missing_share_prices(app, client):
    db.session.add(Account(name="Checking", type="checking", institution="Bank", current_balance=1,
                           last_updated_date=TODAY))
    db.session.add(Rule(name="Grant", rule_type="rsu", start_date="2026-01-01", schedule=[],
                        config={"ticker": "zzzz"}))
    db.session.commit()
    items = {i["id"]: i for i in client.get("/api/insights").get_json()["insights"]}
    assert "ZZZZ" in items["missing-prices"]["title"]
    assert items["missing-prices"]["action"]["href"] == "/balances?tab=prices"


# ── Backup, restore, old-format data ──────────────────────────────────────────

def test_export_then_import_round_trips_everything(seeded):
    before = seeded.get("/api/export").get_json()
    assert before["meta"]["version"] == 2
    for key in ("accounts", "loans", "assets", "rules", "change_events", "snapshots", "price_points", "categories"):
        assert before[key], key

    db.session.query(Rule).delete()
    db.session.query(Snapshot).delete()
    db.session.commit()
    assert seeded.post("/api/import", json=before).status_code == 200
    after = seeded.get("/api/export").get_json()
    for key in ("accounts", "loans", "assets", "rules", "change_events", "snapshots", "price_points", "categories"):
        assert sorted(r.get("id") or r.get("slug") for r in after[key]) == \
               sorted(r.get("id") or r.get("slug") for r in before[key]), key


def test_import_converts_a_version_1_file(client):
    v1 = {
        "categories": [{"slug": "salary", "label": "Salary", "type": "income", "color": "#10b981"}],
        "accounts": [{"id": "a1", "name": "Checking", "type": "checking", "institution": "Bank", "currency": "USD",
                      "current_balance": 5000, "last_updated_date": "2026-05-10", "is_active": True, "note": None}],
        "loans": [],
        "recurring_transactions": [{"id": "r1", "type": "income", "amount": 1000000, "frequency": "monthly",
                                    "start_date": "2026-01-01", "end_date": None, "category": "salary",
                                    "account_id": "a1", "note": "Monthly salary"}],
        "blanket_expenses": [{"id": "b1", "label": "Misc", "amount": 50000, "frequency": "monthly",
                              "start_date": "2026-01-01", "end_date": None, "category": "salary", "note": None}],
        "one_time_transactions": [{"id": "o1", "type": "expense", "amount": 30000, "date": "2026-03-01",
                                   "category": "salary", "account_id": "a1", "note": "Laptop"}],
        "account_snapshots": [{"id": "s1", "account_id": "a1", "date": "2026-04-01", "actual_balance": 4200,
                               "predicted_balance": 4000, "delta": 200, "resolution": "accepted", "note": None}],
    }
    res = client.post("/api/import", json=v1)
    assert res.status_code == 200 and res.get_json()["converted"] == {"rules": 2, "change_events": 1, "snapshots": 1}
    assert {r.name: (r.rule_type, r.amount) for r in Rule.query.all()} == \
           {"Monthly salary": ("income", 1000000), "Misc": ("expense", 50000)}
    change = ChangeEvent.query.one()
    assert (change.description, change.amount) == ("Laptop", -30000)
    assert Snapshot.query.one().value == 4200


def test_import_rejects_non_backup_payloads(client):
    assert client.post("/api/import", json=[1, 2]).status_code == 400


def test_old_format_rows_in_the_database_can_be_converted(app, client):
    acct = Account(name="Checking", type="checking", institution="Bank", current_balance=1, last_updated_date=TODAY)
    db.session.add(acct)
    db.session.flush()
    db.session.add_all([
        RecurringTxn(type="expense", amount=120000, frequency="monthly", start_date="2026-01-01", category="rent",
                     account_id=acct.id, note="Rent"),
        OneTimeTxn(type="income", amount=250000, date="2026-02-02", category="bonus", account_id=acct.id,
                   note="Bonus"),
    ])
    db.session.commit()
    assert client.get("/api/legacy").get_json()["total"] == 2
    assert client.post("/api/legacy/convert").get_json()["converted"] == {"rules": 1, "change_events": 1,
                                                                          "snapshots": 0}
    assert client.get("/api/legacy").get_json()["total"] == 0
    assert Rule.query.one().name == "Rent" and ChangeEvent.query.one().amount == 250000


# ── Assistant ─────────────────────────────────────────────────────────────────

def test_assistant_is_off_without_a_model_and_says_so(seeded):
    status = seeded.get("/api/assistant/status").get_json()
    assert status["enabled"] is False and status["ok"] is False
    res = seeded.post("/api/assistant/ask", json={"question": "What is my net worth?"})
    assert res.status_code == 503 and res.get_json()["unavailable"] is True


def test_ask_runs_the_chosen_lookup_and_keeps_grounded_wording(seeded, fake_llm):
    net_worth = seeded.get("/api/balances").get_json()["totals"]["net_worth"]
    figure = A.usd(net_worth)
    fake_llm({"assistant_route": {"tool": "balances", "args": {}},
              "assistant_answer": f"Your net worth today is {figure}."})
    body = seeded.post("/api/assistant/ask", json={"question": "What is my net worth?"}).get_json()
    assert body["tool"] == "balances" and body["worded_by_ai"] is True
    assert body["answer"] == f"Your net worth today is {figure}."
    assert body["facts"][0] == {"label": "Net worth", "value": figure}


def test_ask_discards_wording_that_invents_a_number(seeded, fake_llm):
    fake_llm({"assistant_route": {"tool": "balances", "args": {}},
              "assistant_answer": "Your net worth today is $999,999,999."})
    body = seeded.post("/api/assistant/ask", json={"question": "What is my net worth?"}).get_json()
    assert body["worded_by_ai"] is False
    assert "999,999,999" not in body["answer"] and "Net worth" in body["answer"]


def test_ask_rejects_an_unknown_lookup(seeded, fake_llm):
    fake_llm({"assistant_route": {"tool": "delete_everything", "args": {}}})
    assert seeded.post("/api/assistant/ask", json={"question": "Wipe my data"}).status_code == 422
    assert Account.query.count() > 0


def test_ask_requires_a_question(seeded, fake_llm):
    fake_llm({})
    assert seeded.post("/api/assistant/ask", json={"question": "  "}).status_code == 422


def test_net_worth_crosses_lookup_reads_the_forecast():
    ctx = A.Context(entities=[{"type": "cash", "id": "a", "name": "A", "current": 100000, "current_date": TODAY}],
                    snaps={}, rules=[{"id": "s", "name": "Salary", "rule_type": "income", "amount": 100000,
                                      "frequency": "monthly", "start_date": TODAY}],
                    changes=[], loans=[], prices={}, today=TODAY)
    result = A.run_tool(ctx, {"tool": "net_worth_crosses", "args": {"amount_dollars": 5000, "direction": "above"}})
    assert result["facts"][0] == {"label": "Net worth today", "value": "$1,000"}
    assert "first reaches $5,000" in result["facts"][1]["label"] and result["href"].startswith("/forecast?month=")


def test_filter_keeps_only_values_the_list_offers(seeded, fake_llm):
    fake_llm({"assistant_filter": {"filter_type": "expense", "filter_category": "yachts", "date_from": "2027-01-01",
                                   "date_to": "not a date", "min_amount_dollars": 1000, "max_amount_dollars": None,
                                   "sort": "amount", "direction": "desc", "search": "over 1000"}})
    body = seeded.post("/api/assistant/filter", json={
        "text": "expenses over $1000 in January", "filters": {"type": ["income", "expense"], "category": ["rent"]},
        "sorts": ["date", "amount"]}).get_json()
    assert body["filter"] == {"filters": {"type": "expense"}, "date_from": "2027-01-01", "min_amount": 1000.0,
                              "sort": "amount", "dir": "desc"}


def test_filter_schema_limits_dropdowns_to_real_values():
    schema = A.filter_schema({"type": ["income", "expense"]}, ["date"])
    assert schema["properties"]["filter_type"]["enum"] == ["", "income", "expense"]
    assert schema["properties"]["sort"]["enum"] == ["", "date"]
    assert set(schema["required"]) == set(schema["properties"])


def test_explain_discards_text_with_new_figures(seeded, fake_llm):
    note = {"title": "2 balances not updated in 35+ days", "detail": "The oldest was recorded 68 days ago.",
            "basis": "Last-updated dates."}
    fake_llm({"assistant_explain": "Two balances are over 35 days old; the oldest is 68 days old."})
    assert "68 days" in seeded.post("/api/assistant/explain", json=note).get_json()["explanation"]
    fake_llm({"assistant_explain": "You are losing about $4,321 a year because of this."})
    body = seeded.post("/api/assistant/explain", json=note).get_json()
    assert body["explanation"] is None and "discarded" in body["error"]


def test_draft_prefills_a_form_and_saves_nothing(seeded, fake_llm):
    rules_before = Rule.query.count()
    fake_llm({"assistant_draft": {"kind": "rule", "direction": "expense", "name": "Gym", "amount_dollars": 120,
                                  "frequency": "monthly", "start_date": "2027-01-01"}})
    body = seeded.post("/api/assistant/draft", json={"text": "gym $120 monthly from January 2027"}).get_json()
    assert body["draft"] == {"kind": "rule", "rule_type": "expense", "name": "Gym", "amount_dollars": "120.00",
                             "frequency": "monthly", "start_date": "2027-01-01", "end_date": ""}
    assert Rule.query.count() == rules_before


def test_draft_rejects_an_amount_the_user_never_typed(seeded, fake_llm):
    fake_llm({"assistant_draft": {"kind": "change", "direction": "expense", "name": "Laptop", "amount_dollars": 2500,
                                  "date": "2027-03-03"}})
    assert seeded.post("/api/assistant/draft", json={"text": "new laptop $1800 on March 3"}).status_code == 422


@pytest.mark.parametrize("answer,ok", [
    ("Net worth is $617,200.", True), ("Net worth is $617,200.00.", True), ("It reaches that in 2028-02.", True),
    ("Net worth is $617,201.", False), ("Roughly 12 percent more.", False),
])
def test_numbers_grounded(answer, ok):
    assert A.numbers_grounded(answer, "- Net worth today: $617,200\n- reaches: in 2028-02 ($701,156)") is ok
