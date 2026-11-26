"""Long lists are filtered, sorted and paged on the server, so no page downloads everything."""

from models import ChangeEvent, PricePoint, db


def _seed(accounts, n=120):
    chk, card = accounts["chk"], accounts["card"]
    for i in range(n):
        db.session.add(ChangeEvent(date=f"2026-{1 + i % 10:02d}-{1 + i % 28:02d}", description=f"Shop {i}",
                                   amount=-(i + 1) * 100, account_id=(chk if i % 2 else card).id,
                                   category="groceries" if i % 3 else "dining", change_type="import"))
    db.session.add(ChangeEvent(date="2027-03-01", description="Planned trip", amount=-500000, change_type="manual"))
    db.session.commit()


def test_changes_pages_and_counts(client, accounts):
    _seed(accounts)
    r = client.get("/api/changes?limit=50&today=2026-11-25").get_json()
    assert len(r["items"]) == 50 and r["matched"] == r["total"] == 121 and r["offset"] == 0
    assert r["items"][0]["description"] == "Planned trip"  # newest first by default
    dates = [c["date"] for c in r["items"]]
    assert dates == sorted(dates, reverse=True)
    nxt = client.get("/api/changes?limit=50&offset=50&options=0").get_json()
    assert nxt["options"] is None and not {c["id"] for c in nxt["items"]} & {c["id"] for c in r["items"]}
    assert r["sum"] == sum(c.amount for c in ChangeEvent.query.all())


def test_changes_filters_sort_and_options(client, accounts):
    _seed(accounts)
    chk = accounts["chk"]
    r = client.get(f"/api/changes?limit=500&account={chk.id}&category=groceries&sort=amount&dir=asc").get_json()
    assert r["matched"] == len(r["items"]) > 0
    assert all(c["account_id"] == chk.id and c["category"] == "groceries" for c in r["items"])
    assert [c["amount"] for c in r["items"]] == sorted(c["amount"] for c in r["items"])
    # Each dropdown lists what the other filters leave, accounts by name.
    assert {o["label"] for o in r["options"]["account"]} == {"Everyday Checking", "Rewards Visa 4821"}
    assert set(r["options"]["category"]) == {"groceries", "dining"}

    planned = client.get("/api/changes?limit=10&when=planned&today=2026-11-25").get_json()
    assert [c["description"] for c in planned["items"]] == ["Planned trip"]
    assert client.get("/api/changes?limit=10&q=shop 11").get_json()["matched"] == 11  # 11, 110-119
    ranged = client.get("/api/changes?limit=500&min=50&max=60&from=2026-01-01&to=2026-12-31").get_json()
    assert ranged["items"] and all(5000 <= abs(c["amount"]) <= 6000 for c in ranged["items"])
    assert client.get("/api/changes?limit=nope").status_code == 422


def test_changes_without_limit_still_returns_the_whole_list(client, accounts):
    _seed(accounts, n=5)
    assert len(client.get("/api/changes").get_json()) == 6


def test_price_count(client):
    db.session.add_all([PricePoint(ticker="GOOG", date=f"2026-01-{d:02d}", price=100) for d in range(1, 11)])
    db.session.commit()
    assert client.get("/api/prices?count=1").get_json() == {"count": 10}


def test_tax_summary_sends_grouped_entries(client, accounts):
    _seed(accounts, n=30)
    body = client.get("/api/taxes/summary?year=2026").get_json()
    assert "items" not in body and body["item_count"] >= len(body["item_groups"]) > 0
    totals = [abs(g["total"]) for g in body["item_groups"]]
    assert totals == sorted(totals, reverse=True)
