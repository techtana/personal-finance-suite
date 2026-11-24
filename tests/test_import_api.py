"""End to end through the API: drop -> review -> edit -> import -> undo."""

import io
import os

from engine.projection import project_v2
from models import Category, ChangeEvent, ImportMerchantRule, ImportProfile, Rule, Snapshot, db
from tests.conftest import sample_bytes, upload


def rows_by_desc(batch):
    return {r["description"]: r for r in batch["rows"] if r["target"] == "change_event"}


def test_statement_csv_full_cycle(client, accounts):
    b = upload(client, "checking-activity.csv")
    assert b["status"] == "review" and b["doc_type"] == "statement"
    assert b["account_id"] == accounts["chk"].id  # from "...1234" above the table
    rows = rows_by_desc(b)
    assert rows["ACME CORP PAYROLL PPD ID: 9876543210"]["amount"] == 325000
    transfer = rows["ONLINE TRANSFER TO SAV XXXXXX5678 REF #IB0QWE"]
    assert transfer["action"] == "import" and "transfer" in transfer["flags"]  # kept so the balance adds up
    zelle = rows["ZELLE TO JORDAN SAMPLE"]
    assert zelle["category"] is None and "uncategorized" in zelle["flags"]  # AI is off in tests
    snap = [r for r in b["rows"] if r["target"] == "snapshot"][0]
    assert snap["action"] == "import" and snap["amount"] == 412055
    suggestions = [r for r in b["rows"] if r["target"] == "rule"]
    assert {(r["description"], r["frequency"]) for r in suggestions} == {("Netflix", "monthly"), ("Acme Corp Payroll", "biweekly")}
    assert all(r["action"] == "skip" for r in suggestions)

    # pick a category for the Zelle payment and accept the payroll rule
    res = client.patch(f"/api/imports/{b['id']}/rows/{zelle['id']}", json={"category": "gifts"})
    assert res.status_code == 200
    payroll_rule = next(r for r in suggestions if r["frequency"] == "biweekly")
    client.patch(f"/api/imports/{b['id']}/rows/{payroll_rule['id']}", json={"action": "import"})

    res = client.post(f"/api/imports/{b['id']}/commit", json={})
    assert res.status_code == 200, res.get_json()
    created = res.get_json()["created"]
    assert len(created["change_events"]) == 15 and len(created["snapshots"]) == 1 and len(created["rules"]) == 1
    assert ChangeEvent.query.filter_by(change_type="imported").count() == 15
    assert ChangeEvent.query.filter_by(description="ONLINE TRANSFER TO SAV XXXXXX5678 REF #IB0QWE").one().category == "transfer"
    assert ChangeEvent.query.filter_by(description="ZELLE TO JORDAN SAMPLE").one().category == "gifts"
    assert db.session.get(Category, "gifts") is not None  # starter category created on first use
    assert ImportMerchantRule.query.filter_by(merchant_key="ZELLE JORDAN SAMPLE").one().category == "gifts"
    assert ImportProfile.query.count() == 1
    rule = Rule.query.one()
    assert (rule.rule_type, rule.amount, rule.frequency, rule.start_date) == ("income", 325000, "biweekly", "2026-11-28")
    assert Snapshot.query.one().value == 412055

    # the same file again: everything is a duplicate and the saved layout is used
    b2 = upload(client, "checking-activity.csv")
    assert b2["mapping"]["source"] == "saved"
    txns = [r for r in b2["rows"] if r["target"] == "change_event" and "transfer" not in r["flags"]]
    assert txns and all("duplicate" in r["flags"] and r["action"] == "skip" for r in txns)
    assert rows_by_desc(b2)["ZELLE TO JORDAN SAMPLE"]["category"] == "gifts"  # learned
    assert any("already imported" in w["text"] for w in b2["warnings"])

    # undo the first import
    res = client.post(f"/api/imports/{b['id']}/undo")
    assert res.status_code == 200 and res.get_json()["removed"] == 17
    assert ChangeEvent.query.count() == 0 and Rule.query.count() == 0 and Snapshot.query.count() == 0
    assert res.get_json()["import"]["status"] == "review"


def test_statement_needs_an_account_before_import(client, accounts):
    b = upload(client, "card-activity.csv")
    assert b["account_id"] is None
    res = client.post(f"/api/imports/{b['id']}/commit", json={})
    assert res.status_code == 400 and "account" in res.get_json()["error"]
    client.patch(f"/api/imports/{b['id']}", json={"account_id": accounts["card"].id})
    assert client.post(f"/api/imports/{b['id']}/commit", json={}).status_code == 200


def test_receipt_then_card_export_is_caught_as_duplicate(client, accounts, fake_llm):
    fake_llm({"read_receipt": [{"merchant": "GREEN LEAF GROCERY", "date": "11/17/2026", "total": "28.98",
                                "subtotal": "28.11", "tax": "0.87", "tip": "", "is_refund": False, "card_last4": "4821",
                                "category": "groceries", "items": []}]})
    text = b"GREEN LEAF GROCERY\n11/17/2026\nSUBTOTAL 28.11\nTAX 0.87\nTOTAL 28.98\nVISA ****4821 28.98\nTHANK YOU\n"
    r = upload(client, "receipt.txt", text)
    assert r["doc_type"] == "receipt" and r["account_id"] == accounts["card"].id
    assert client.post(f"/api/imports/{r['id']}/commit", json={}).status_code == 200

    s = upload(client, "rewards-card.csv")
    assert s["account_id"] == accounts["card"].id  # from the Card No. column
    green = rows_by_desc(s)["GREEN LEAF GROCERY"]
    assert green["action"] == "skip" and ({"duplicate", "possible_duplicate"} & set(green["flags"]))
    assert green["match"]["file"] == "receipt.txt"


def test_payslip_then_statement_flags_the_paycheck(client, accounts, fake_llm):
    fake_llm({})  # AI "available" but every call fails -> rules only
    p = upload(client, "paystub.txt", doc_type="payslip")
    net = rows_by_desc(p)["Paycheck"] if "Paycheck" in rows_by_desc(p) else next(iter(rows_by_desc(p).values()))
    assert net["amount"] == 325000 and p["account_id"] == accounts["chk"].id
    assert client.post(f"/api/imports/{p['id']}/commit", json={}).status_code == 200
    s = upload(client, "checking-activity.csv")
    payroll = [r for r in s["rows"] if r["description"].startswith("ACME CORP PAYROLL") and r["date"] == "2026-11-14"][0]
    assert "possible_duplicate" in payroll["flags"] and payroll["action"] == "skip"


def test_reopening_a_review_shows_duplicates_committed_meanwhile(client, accounts):
    a = upload(client, "rewards-card.csv")
    b = upload(client, "rewards-card.csv")  # both in review at once
    assert client.post(f"/api/imports/{a['id']}/commit", json={}).status_code == 200
    again = client.get(f"/api/imports/{b['id']}").get_json()
    txns = [r for r in again["rows"] if "transfer" not in r["flags"]]
    assert all("duplicate" in r["flags"] and r["action"] == "skip" for r in txns)


def test_commit_rechecks_duplicates_added_meanwhile(client, accounts):
    a = upload(client, "rewards-card.csv")
    b = upload(client, "rewards-card.csv")  # both in review at once
    assert client.post(f"/api/imports/{a['id']}/commit", json={}).status_code == 200
    res = client.post(f"/api/imports/{b['id']}/commit", json={})
    assert res.status_code == 409 and "now match" in res.get_json()["error"]
    again = client.get(f"/api/imports/{b['id']}").get_json()
    assert all(r["action"] == "skip" for r in again["rows"])


def test_photo_needs_the_ai(client, accounts):
    jpg = sample_bytes("receipt-photo.jpg")
    b = upload(client, "receipt-photo.jpg", jpg)
    assert b["status"] == "failed" and "needs the local AI" in b["error"]


def test_photo_is_transcribed_then_read(client, accounts, fake_llm):
    transcript = "GREEN LEAF GROCERY\n11/17/2026 3:42 PM\nSUBTOTAL 28.11\nTAX 0.87\nTOTAL 28.98\nVISA ****4821 28.98"
    fake = fake_llm({"transcribe": [transcript], "classify": [{"doc_type": "receipt", "confidence": 0.9}],
                     "read_receipt": [{"merchant": "GREEN LEAF GROCERY", "date": "11/17/2026", "total": "28.98",
                                       "subtotal": "28.11", "tax": "0.87", "tip": "", "is_refund": False,
                                       "card_last4": "4821", "category": "groceries", "items": []}]})
    b = upload(client, "receipt-photo.jpg", sample_bytes("receipt-photo.jpg"))
    assert b["status"] == "review" and b["doc_type"] == "receipt"
    [row] = b["rows"]
    assert row["amount"] == -2898 and "from_photo" in row["flags"] and row["needs_review"]
    assert fake.seen[0][0] == "transcribe" and fake.seen[0][2]  # the image was sent
    assert b["extracted"]["transcript"].startswith("GREEN LEAF")
    assert client.get(f"/api/imports/{b['id']}/file").status_code == 200


def test_mapping_override_and_flip(client, accounts):
    csv = b"A,B,C\n11/02/2026,COFFEE SHOP,4.50\n11/03/2026,LANDLORD,1850.00\n11/04/2026,EMPLOYER PAYROLL,-3000.00\n"
    b = upload(client, "odd.csv", csv, account_id=accounts["chk"].id)
    before = {r["description"]: r["amount"] for r in b["rows"]}
    res = client.patch(f"/api/imports/{b['id']}", json={"flip_signs": True})
    after = {r["description"]: r["amount"] for r in res.get_json()["rows"]}
    assert all(after[k] == -before[k] for k in before)
    res = client.patch(f"/api/imports/{b['id']}", json={"mapping": {"date_col": 0, "description_col": 1, "amount_col": 2,
                                                                    "date_format": "%m/%d/%Y",
                                                                    "sign_convention": "positive_is_money_out"}})
    body = res.get_json()
    assert body["mapping"]["source"] == "user"
    amounts = {r["description"]: r["amount"] for r in body["rows"]}
    assert amounts["EMPLOYER PAYROLL"] == -300000  # user mapping applied, and the earlier flip still applies


def test_row_edits_validate(client, accounts):
    b = upload(client, "card-activity.csv", account_id=accounts["card"].id)
    shell = rows_by_desc(b)["SHELL OIL 57444 SEATTLE WA"]
    url = f"/api/imports/{b['id']}/rows/{shell['id']}"
    assert client.patch(url, json={"category": "salary"}).status_code == 400  # income category on spending
    assert client.patch(url, json={"category": "nope"}).status_code == 400
    assert client.patch(url, json={"date": "30/11/2026"}).status_code == 400
    body = client.patch(url, json={"amount": -5000, "date": "2026-11-17", "category": "transport"}).get_json()
    edited = rows_by_desc(body)["SHELL OIL 57444 SEATTLE WA"]
    assert (edited["amount"], edited["date"], edited["category_source"]) == (-5000, "2026-11-17", "user")


def test_upload_rejections_and_delete(client, app, accounts):
    res = client.post("/api/imports", data={"files": (io.BytesIO(b"MZ"), "tool.exe")}, content_type="multipart/form-data")
    assert res.status_code == 400 and "aren't supported" in res.get_json()["rejected"][0]["error"]
    b = upload(client, "card-activity.csv")
    path = os.path.join(app.config["IMPORT_STORAGE_DIR"], os.listdir(app.config["IMPORT_STORAGE_DIR"])[0])
    assert client.delete(f"/api/imports/{b['id']}").status_code == 204
    assert not os.path.exists(path)


def test_ofx_import_picks_account_and_balance(client, accounts):
    b = upload(client, "bank-statement.ofx")
    assert b["account_id"] == accounts["sav"].id
    rows = rows_by_desc(b)
    assert rows["INTEREST PAYMENT"]["category"] == "interest"
    assert rows["ONLINE TRANSFER FROM CHK 1234"]["action"] == "import"
    assert "transfer" in rows["ONLINE TRANSFER FROM CHK 1234"]["flags"]
    snap = [r for r in b["rows"] if r["target"] == "snapshot"][0]
    assert snap["amount"] == 1850741 and snap["action"] == "import"


def test_projection_ignores_past_changes():
    changes = [{"id": "a", "date": "2026-01-05", "description": "old", "amount": -10000},
               {"id": "b", "date": "2026-12-05", "description": "future", "amount": 5000}]
    buckets, events = project_v2([], changes, [], 100000, {}, "2026-11-22", "2027-11-22")
    assert [e.source_id for e in events] == ["b"]
    assert buckets[0].cumulative_net_worth == 105000


def test_ai_status_endpoint(client, fake_llm):
    assert client.get("/api/imports/ai-status").get_json()["ok"] is False  # provider off in tests
    fake_llm({})
    assert client.get("/api/imports/ai-status").get_json()["ok"] is True


def test_ai_category_is_a_suggestion_until_kept(client, accounts, fake_llm):
    fake_llm({"categorize": [{"items": [{"i": 0, "category": "gifts", "confidence": 0.8}]}]})
    csv = b"Date,Description,Amount\n11/02/2026,FLOWER CART MARKET,-35.00\n"
    b = upload(client, "odd.csv", csv, account_id=accounts["chk"].id)
    [row] = b["rows"]
    assert (row["category"], row["category_source"]) == ("gifts", "ai")
    kept = client.patch(f"/api/imports/{b['id']}/rows/{row['id']}", json={"category": "gifts"}).get_json()
    assert kept["rows"][0]["category_source"] == "user"
    assert client.post(f"/api/imports/{b['id']}/commit", json={}).status_code == 200
    assert ImportMerchantRule.query.filter_by(merchant_key="FLOWER CART MARKET").one().category == "gifts"


def big_statement(n=230):
    """A bank export large enough to need several pages: n distinct money-out rows."""
    lines = ["Date,Description,Amount"]
    for i in range(n):
        shop = "CORNER GROCER" if i % 2 == 0 else "CITY HARDWARE"
        lines.append(f"11/{i % 28 + 1:02d}/2026,{shop} STORE {i:04d},-{10 + i}.25")
    return ("\n".join(lines) + "\n").encode()


def test_rows_come_a_page_at_a_time(client, accounts):
    b = upload(client, "big.csv", big_statement(), account_id=accounts["chk"].id)
    bid = b["id"]
    lean = client.get(f"/api/imports/{bid}?rows=0").get_json()
    assert "rows" not in lean and lean["counts"]["rows"] == len(b["rows"])
    n = lean["row_counts"]["targets"]["change_event"]
    assert n == 230 and lean["row_counts"]["filters"]["all"] == len(b["rows"])

    first = client.get(f"/api/imports/{bid}/rows?target=change_event&limit=50").get_json()
    assert (len(first["rows"]), first["total"], first["offset"]) == (50, 230, 0)
    last = client.get(f"/api/imports/{bid}/rows?target=change_event&limit=50&offset=200").get_json()
    assert len(last["rows"]) == 30
    assert not {r["id"] for r in first["rows"]} & {r["id"] for r in last["rows"]}
    # never more than 200 at once, and an offset past the end lands on the last page
    assert len(client.get(f"/api/imports/{bid}/rows?limit=100000").get_json()["rows"]) == 200
    assert client.get(f"/api/imports/{bid}/rows?target=change_event&limit=50&offset=9999").get_json()["offset"] == 200

    found = client.get(f"/api/imports/{bid}/rows?target=change_event&q=hardware").get_json()
    assert found["total"] == 115 and all("HARDWARE" in r["description"] for r in found["rows"])
    one = client.get(f"/api/imports/{bid}/rows?q=grocer+0004").get_json()
    assert [r["description"] for r in one["rows"]] == ["CORNER GROCER STORE 0004"]
    assert client.get(f"/api/imports/{bid}/rows?filter=nope").status_code == 400

    # an edit can answer without the rows too
    res = client.patch(f"/api/imports/{bid}/rows/{first['rows'][0]['id']}?rows=0", json={"action": "skip"}).get_json()
    assert "rows" not in res and res["row_counts"]["filters"]["skip"] >= 1


def test_bulk_change(client, accounts):
    b = upload(client, "big.csv", big_statement(), account_id=accounts["chk"].id)
    bid = b["id"]
    url = f"/api/imports/{bid}/rows/bulk?rows=0"

    # everything matching a search, on screen or not
    res = client.post(url, json={"q": "hardware", "target": "change_event", "set": {"category": "housing"}})
    body = res.get_json()
    assert res.status_code == 200, body
    assert (body["changed"], body["skipped"]) == (115, 0) and "rows" not in body
    rows = client.get(f"/api/imports/{bid}").get_json()["rows"]
    hardware = [r for r in rows if "HARDWARE" in r["description"]]
    assert all((r["category"], r["category_source"]) == ("housing", "user") for r in hardware)
    assert not any(r["category"] == "housing" for r in rows if "GROCER" in r["description"])

    # hand-picked rows: date, account and untick in one go
    ids = [r["id"] for r in hardware[:3]]
    body = client.post(url, json={"ids": ids, "set": {"date": "2026-10-31", "account_id": accounts["card"].id,
                                                      "action": "skip"}}).get_json()
    assert body["changed"] == 3
    picked = [r for r in client.get(f"/api/imports/{bid}").get_json()["rows"] if r["id"] in ids]
    assert all((r["date"], r["account_id"], r["action"]) == ("2026-10-31", accounts["card"].id, "skip") for r in picked)

    # an income category doesn't fit money out: those rows are left alone and counted
    body = client.post(url, json={"ids": ids, "set": {"category": "salary"}}).get_json()
    assert (body["changed"], body["skipped"]) == (0, 3)
    # flipping the sign turns them into money in, and then it fits
    assert client.post(url, json={"ids": ids, "set": {"flip_sign": True}}).get_json()["changed"] == 3
    assert client.post(url, json={"ids": ids, "set": {"category": "salary"}}).get_json()["changed"] == 3
    picked = [r for r in client.get(f"/api/imports/{bid}").get_json()["rows"] if r["id"] in ids]
    assert all(r["amount"] > 0 and r["category"] == "salary" for r in picked)

    # the older shape still works; bad requests are refused
    assert client.post(url, json={"ids": ids, "action": "import"}).get_json()["changed"] == 3
    assert client.post(url, json={"ids": ids, "set": {}}).status_code == 400
    assert client.post(url, json={"ids": ids, "set": {"category": "no_such"}}).status_code == 400
    assert client.post(url, json={"ids": ids, "set": {"date": "31/10/2026"}}).status_code == 400
    assert client.post(url, json={"filter": "skip", "set": {"action": "import"}}).status_code == 200
