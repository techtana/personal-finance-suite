"""Balances follow transactions: recorded balance + imported transactions since, balance checks, owed accounts."""

from engine import ledger
from engine.plan_actual import plan_vs_actual
from engine.projection import project_v2
from engine.tax import collect_tax_items
from models import Account, ChangeEvent, Rule, Snapshot, db
from tests.conftest import upload

TODAY = "2026-11-30"


def _txn(account, d, amount, desc="Coffee", category=None, change_type="imported"):
    c = ChangeEvent(date=d, description=desc, amount=amount, account_id=account.id, category=category,
                    change_type=change_type)
    db.session.add(c)
    return c


def _row(client, account):
    rows = client.get(f"/api/balances?today={TODAY}").get_json()["rows"]
    return next(r for r in rows if r["id"] == account.id)


# ── engine ────────────────────────────────────────────────────────────────────

def test_value_at_adds_transactions_after_the_latest_record():
    points = [("2026-10-31", 100000), ("2026-11-15", 90000)]
    txns = [("2026-11-05", -2000), ("2026-11-15", -500), ("2026-11-20", -3000), ("2026-11-25", 10000)]
    assert ledger.value_at(points, txns, "2026-11-10") == 98000
    assert ledger.value_at(points, txns, "2026-11-15") == 90000  # the record already includes its own day
    assert ledger.value_at(points, txns, "2026-11-22") == 87000
    assert ledger.value_at(points, txns, "2026-11-30") == 97000
    assert ledger.value_at(points, txns, "2026-10-01") is None  # before any record or transaction


def test_value_at_works_back_from_the_first_record_and_owed_accounts_flip():
    points = [("2026-11-30", 50000)]
    txns = [("2026-11-10", -1000), ("2026-11-20", -4000)]
    assert ledger.value_at(points, txns, "2026-11-15") == 54000
    assert ledger.value_at(points, txns, "2026-11-05") is None
    # A card: what you owe goes up with spending and down with a payment.
    card = [("2026-11-01", 20000)]
    spend = [("2026-11-03", -5000), ("2026-11-10", 20000)]
    assert ledger.value_at(card, spend, "2026-11-05", owed=True) == 25000
    assert ledger.value_at(card, spend, "2026-11-11", owed=True) == 5000


def test_ledger_shows_running_balance_and_the_gap_at_each_record():
    snaps = [{"id": "s1", "date": "2026-11-01", "value": 100000, "note": None},
             {"id": "s2", "date": "2026-11-30", "value": 94000, "note": None}]
    changes = [{"id": "a", "date": "2026-10-28", "amount": -1500}, {"id": "b", "date": "2026-11-10", "amount": -5000},
               {"id": "c", "date": "2026-11-30", "amount": -500}]
    entries = ledger.build_ledger(snaps, changes)
    by = {e.get("id"): e for e in entries}
    assert by["a"]["balance"] == 100000 and by["a"]["estimated"]
    assert by["b"]["balance"] == 95000 and by["c"]["balance"] == 94500
    assert (by["s2"]["expected"], by["s2"]["gap"]) == (94500, -500)
    assert by["s1"]["gap"] is None


def test_projection_and_divergence_ignore_actuals_and_transfers():
    changes = [{"id": "imp", "date": "2026-12-05", "amount": -10000, "change_type": "imported"},
               {"id": "adj", "date": "2026-12-05", "amount": 500, "change_type": "adjustment"},
               {"id": "xfer", "date": "2026-12-06", "amount": -20000, "change_type": "manual", "category": "transfer"},
               {"id": "plan", "date": "2026-12-07", "amount": -3000, "change_type": "manual"}]
    _, events = project_v2([], changes, [], 0, {}, "2026-12-01", "2026-12-31")
    assert [e.source_id for e in events] == ["plan"]


def test_taxes_skip_imported_deposits_and_transfers_unless_given_a_treatment():
    changes = [{"id": "pay", "date": "2026-11-14", "amount": 325000, "change_type": "imported", "category": "salary"},
               {"id": "xfer", "date": "2026-11-15", "amount": 50000, "change_type": "imported", "category": "transfer"},
               {"id": "bonus", "date": "2026-11-16", "amount": 100000, "change_type": "imported",
                "tax_treatment": "other_income"},
               {"id": "gift", "date": "2026-11-17", "amount": 20000, "change_type": "manual"}]
    items, assumptions = collect_tax_items([], changes, [], [], 2026)
    assert sorted(i["source_id"] for i in items) == ["bonus", "gift"]
    assert any("imported deposit" in a for a in assumptions)


def test_plan_vs_actual_by_category_leaves_transfers_out():
    rules = [{"id": "r", "name": "Groceries", "rule_type": "expense", "amount": 40000, "frequency": "monthly",
              "start_date": "2026-01-01", "category": "groceries", "is_active": True}]
    changes = [{"id": "a", "date": "2026-10-04", "amount": -25000, "change_type": "imported", "category": "groceries"},
               {"id": "b", "date": "2026-10-18", "amount": -21000, "change_type": "imported", "category": "groceries"},
               {"id": "c", "date": "2026-10-20", "amount": -90000, "change_type": "imported", "category": "transfer"},
               {"id": "d", "date": "2026-10-31", "amount": -700, "change_type": "adjustment"}]
    out = plan_vs_actual(rules, changes, [], {}, ["2026-10", "2026-11"], {"groceries": "Groceries"})
    rows = {r["category"]: r for r in out["rows"]}
    oct_ = rows["groceries"]["months"][0]
    assert (oct_["planned"], oct_["actual"], oct_["diff"]) == (-40000, -46000, -6000)
    assert rows["_unexplained"]["months"][0]["actual"] == -700
    assert "transfer" not in rows
    assert rows["groceries"]["months"][1]["actual"] is None  # nothing imported in November
    assert out["totals"][0]["actual_spending"] == 46700 and out["totals"][1]["has_actuals"] is False


# ── API ───────────────────────────────────────────────────────────────────────

def test_balance_moves_with_imported_transactions_but_not_planned_entries(app, client, accounts):
    chk = accounts["chk"]  # 4,000.00 recorded on 2026-11-01
    _txn(chk, "2026-10-20", -99999)  # before the record: already in it
    _txn(chk, "2026-11-05", -2500)
    _txn(chk, "2026-11-12", 100000, desc="Payroll")
    _txn(chk, "2026-11-13", -30000, desc="To savings", category="transfer")
    _txn(chk, "2026-11-14", -77700, change_type="manual")  # a planned entry: never moves a balance
    _txn(chk, "2026-12-05", -1000)  # after today
    db.session.commit()
    r = _row(client, chk)
    assert r["value"] == 400000 - 2500 + 100000 - 30000
    assert (r["recorded"], r["recorded_date"], r["since_count"]) == (400000, "2026-11-01", 3)
    assert r["last_updated"] == "2026-11-13" and r["needs_start"] is True
    body = client.get(f"/api/balances?today={TODAY}").get_json()
    assert body["totals"]["cash"] == sum(x["value"] for x in body["rows"] if x["bucket"] == "cash")

    hist = client.get(f"/api/net-worth/history?months=2&types=cash&ids={chk.id}&today={TODAY}").get_json()["series"]
    assert hist[0]["date"] == "2026-10-31" and hist[0]["cash"] == 400000
    assert hist[-1]["cash"] == r["value"]


def test_credit_card_is_owed_and_subtracted(app, client, accounts):
    card = accounts["card"]
    client.post("/api/balances/record", json={"entity_type": "cash", "entity_id": card.id, "value": 20000,
                                              "date": "2026-11-01"})
    _txn(card, "2026-11-03", -5000, desc="Groceries")
    _txn(card, "2026-11-10", 15000, desc="PAYMENT THANK YOU", category="transfer")
    db.session.commit()
    r = _row(client, card)
    assert r["owed"] and r["bucket"] == "liability" and r["value"] == 10000 and r["signed_value"] == -10000
    totals = client.get(f"/api/balances?today={TODAY}").get_json()["totals"]
    assert totals["liabilities"] == 10000
    assert totals["net_worth"] == totals["cash"] + totals["assets"] - totals["liabilities"]


def test_recording_a_balance_reports_the_gap_and_sign_off_keeps_it_live(app, client, accounts):
    chk = accounts["chk"]  # 4,000.00 entered on 2026-11-01
    _txn(chk, "2026-11-05", -2500)
    _txn(chk, "2026-11-12", -7500)
    db.session.commit()
    res = client.post("/api/balances/record", json={"entity_type": "cash", "entity_id": chk.id, "value": 388000,
                                                    "date": "2026-11-20"}).get_json()
    c = res["check"]
    assert (c["expected"], c["value"], c["gap"], c["since_date"], c["count"], c["status"]) == \
        (390000, 388000, -2000, "2026-11-01", 2, "open")
    assert _row(client, chk)["value"] == 388000 and _row(client, chk)["gaps_open"] == 1
    body = client.get(f"/api/balances?today={TODAY}").get_json()
    assert [g["date"] for g in body["gaps"]] == ["2026-11-20"]

    snap_id = res["id"]
    ok = client.post("/api/balances/signoff", json={"snapshot_id": snap_id, "note": "cash spending"})
    assert ok.status_code == 201 and ok.get_json()["check"]["status"] == "signed_off"
    assert ChangeEvent.query.filter_by(change_type="adjustment").count() == 0  # nothing is added to the history
    assert _row(client, chk)["value"] == 388000 and _row(client, chk)["gaps_signed"] == 1
    assert client.get(f"/api/balances?today={TODAY}").get_json()["gaps"] == []

    # importing part of what was missing shrinks the gap: it stays signed off
    _txn(chk, "2026-11-15", -1000)
    db.session.commit()
    led = client.get(f"/api/balances/{chk.id}/ledger?today={TODAY}").get_json()
    rec = next(e for e in led["entries"] if e["kind"] == "recorded" and e["id"] == snap_id)
    assert (rec["check"]["gap"], rec["check"]["status"], rec["check"]["explained_since"]) == (-1000, "signed_off", 1000)
    _txn(chk, "2026-11-16", -600)
    db.session.commit()
    assert _row(client, chk)["check"]["status"] == "matches"  # -400: within the $5 tolerance

    # a difference that grows past what was signed off asks for a look again
    _txn(chk, "2026-11-18", 9000)
    db.session.commit()
    row = _row(client, chk)
    assert row["check"]["status"] == "changed" and row["gaps_open"] == 1
    assert client.delete(f"/api/balances/signoff/{snap_id}").get_json()["check"]["status"] == "open"


def test_sign_off_the_value_entered_with_the_account(app, client, accounts):
    chk = accounts["chk"]
    db.session.add(Snapshot(entity_type="cash", entity_id=chk.id, date="2026-10-01", value=300000))
    _txn(chk, "2026-10-10", 50000)
    db.session.commit()
    c = _row(client, chk)["check"]
    assert (c["id"], c["date"], c["gap"], c["status"]) == (None, "2026-11-01", 50000, "open")
    res = client.post("/api/balances/signoff", json={"account_id": chk.id, "date": "2026-11-01"})
    assert res.status_code == 201 and res.get_json()["check"]["status"] == "signed_off"
    assert Snapshot.query.filter_by(entity_id=chk.id, date="2026-11-01").one().gap_ok == 50000


def test_balance_checks_find_missing_data_and_spread_the_gap():
    records = [{"id": "a", "date": "2026-09-30", "value": 100000},
               {"id": "b", "date": "2026-10-31", "value": 93000},
               {"id": "c", "date": "2026-11-30", "value": 80000}]
    txns = [("2026-10-05", -5000), ("2026-10-20", -2000), ("2026-11-03", -1000)]
    checks = ledger.balance_checks(records, txns, spans=[("2026-10-01", "2026-11-03")])
    oct_, nov = checks
    assert (oct_["gap"], oct_["status"], oct_["missing"]) == (0, "matches", [])
    assert (nov["expected"], nov["gap"], nov["status"]) == (92000, -12000, "open")
    assert nov["missing"] == [("2026-11-07", "2026-11-30", 24)]  # the 3rd's transaction covers a few days
    assert ledger.unexplained_flows(checks) == [("2026-11-07", "2026-11-30", -12000)]
    assert ledger.balance_checks(records, []) == []  # no transactions: nothing to check against
    quiet = ledger.balance_checks(records[:2], [("2026-12-15", -10)])
    assert quiet[0]["status"] == "untracked"  # nothing imported between the two records
    owed = ledger.balance_checks([{"date": "2026-11-01", "value": 20000}, {"date": "2026-11-30", "value": 30000}],
                                 [("2026-11-10", -5000)], owed=True)
    assert (owed[0]["expected"], owed[0]["gap"]) == (25000, 5000)
    assert ledger.unexplained_flows(owed) == [("2026-11-14", "2026-11-30", -5000)]  # owing more = money out


def test_plan_vs_actual_counts_balance_gaps_as_not_imported():
    changes = [{"id": "a", "date": "2026-10-04", "amount": -25000, "change_type": "imported", "category": "groceries"}]
    out = plan_vs_actual([], changes, [], {}, ["2026-10"], unexplained=[("2026-10-17", "2026-11-15", -30000)])
    rows = {r["category"]: r for r in out["rows"]}
    assert rows["_unexplained"]["months"][0]["actual"] == -15000  # 15 of the 30 days are in October
    assert out["totals"][0]["actual_spending"] == 40000


def test_old_reconcile_adjustments_become_sign_offs(app, accounts):
    from app import _convert_reconcile_adjustments

    card = accounts["card"]
    snap = Snapshot(entity_type="cash", entity_id=card.id, date="2026-11-20", value=30000)
    db.session.add(snap)
    db.session.flush()
    db.session.add(ChangeEvent(date="2026-11-20", description="Unexplained difference", amount=-4000,
                               account_id=card.id, change_type="adjustment", snapshot_id=snap.id))
    db.session.commit()
    _convert_reconcile_adjustments()
    assert ChangeEvent.query.filter_by(change_type="adjustment").count() == 0
    assert snap.gap_ok == 4000 and snap.gap_note == "Logged as an adjustment"  # owed: money out = owing more


def test_insight_points_at_differences_to_look_at(app, client, accounts):
    chk = accounts["chk"]
    _txn(chk, "2026-11-05", -2500)
    db.session.commit()
    client.post("/api/balances/record", json={"entity_type": "cash", "entity_id": chk.id, "value": 350000,
                                              "date": "2026-11-28"})
    items = client.get(f"/api/insights?today={TODAY}").get_json()["insights"]
    gap = next(i for i in items if i["id"] == "balance-gaps")
    assert gap["severity"] == "info" and "Nothing was imported for 2026-11-09 to 2026-11-28" in gap["detail"]


def test_no_check_without_transactions_in_between(app, client, accounts):
    res = client.post("/api/balances/record", json={"entity_type": "cash", "entity_id": accounts["sav"].id,
                                                    "value": 1810000, "date": "2026-11-20"}).get_json()
    assert res["check"] is None


def test_imported_statement_moves_the_balance_and_checks_its_closing_balance(app, client, accounts):
    chk = accounts["chk"]
    b = upload(client, "checking-activity.csv")
    check = b["balance_check"]
    assert check["status"] in ("ok", "gap") and check["actual"] == 412055
    assert check["since_date"] == "2026-11-01" and check["count_here"] > 0
    assert client.post(f"/api/imports/{b['id']}/commit", json={}).status_code == 200
    r = _row(client, chk)
    snap = Snapshot.query.filter_by(entity_id=chk.id, date="2026-11-20").one()
    later = sum(c.amount for c in ChangeEvent.query.filter_by(account_id=chk.id).all() if c.date > snap.date)
    assert r["value"] == snap.value + later and r["recorded"] == snap.value
    effect = client.get(f"/api/imports/{b['id']}").get_json()["gap_effect"]
    assert effect and all("before_gap" in c for c in effect)
    assert "2026-11-20" in {c["date"] for c in effect}
    led = client.get(f"/api/balances/{chk.id}/ledger?today={TODAY}").get_json()
    assert any(e["kind"] == "txn" and e["transfer"] for e in led["entries"])
    assert all(e["file"] == "checking-activity.csv" for e in led["entries"] if e["kind"] == "txn")


def test_card_statement_balance_is_recorded_only_on_a_card_account(app, client, accounts):
    b = upload(client, "card-statement.txt", account_id=accounts["card"].id)
    owed = [r for r in b["rows"] if r["target"] == "snapshot"]
    assert len(owed) == 1 and owed[0]["action"] == "import" and "card_balance" not in owed[0]["flags"]
    assert b["balance_check"]["owed"] is True
    other = client.patch(f"/api/imports/{b['id']}", json={"account_id": accounts["chk"].id}).get_json()
    snap = next(r for r in other["rows"] if r["target"] == "snapshot")
    assert "card_balance" in snap["flags"] and snap["action"] == "skip"


def test_divergence_does_not_count_imported_spending_as_planned(app, client, accounts):
    chk = accounts["chk"]
    chk.last_updated_date = "2026-09-30"  # the fixture's own value would otherwise count as a 2026-11-01 record
    for a in accounts.values():
        if a.id != chk.id:
            a.is_active = False
    db.session.add(Snapshot(entity_type="cash", entity_id=chk.id, date="2026-09-30", value=400000))
    db.session.add(Rule(name="Salary", rule_type="income", account_id=chk.id, amount=300000, frequency="monthly",
                        start_date="2026-01-25"))
    _txn(chk, "2026-10-25", 300000, desc="Payroll", category="salary")
    _txn(chk, "2026-11-25", 300000, desc="Payroll", category="salary")
    db.session.commit()
    items = client.get(f"/api/insights?today={TODAY}").get_json()["insights"]
    on_track = next(i for i in items if i["id"] in ("net-worth-on-track", "net-worth-divergence"))
    assert on_track["id"] == "net-worth-on-track" and on_track["value"] == 0, on_track


def test_plan_vs_actual_api_and_insight(app, client, accounts):
    chk = accounts["chk"]
    db.session.add(Rule(name="Groceries", rule_type="expense", account_id=chk.id, amount=40000, frequency="monthly",
                        start_date="2026-01-01", category="groceries"))
    _txn(chk, "2026-10-04", -60000, category="groceries")
    db.session.commit()
    body = client.get(f"/api/plan-vs-actual?months=2&today={TODAY}").get_json()
    assert body["months"] == ["2026-10", "2026-11"]
    groceries = next(r for r in body["rows"] if r["category"] == "groceries")
    assert groceries["months"][0]["diff"] == -20000
    assert body["totals"][0]["complete"] is False  # one transaction on the 4th doesn't cover the month
    items = client.get(f"/api/insights?today={TODAY}").get_json()["insights"]
    assert not any(i["id"].startswith("spending-") for i in items)

    _txn(chk, "2026-09-29", -1000, category="dining")
    _txn(chk, "2026-11-03", -1000, category="dining")
    db.session.commit()
    assert client.get(f"/api/plan-vs-actual?months=2&today={TODAY}").get_json()["totals"][0]["complete"] is True
    items = client.get(f"/api/insights?today={TODAY}").get_json()["insights"]
    assert any(i["id"] == "spending-vs-plan" and "over plan" in i["title"] for i in items)
