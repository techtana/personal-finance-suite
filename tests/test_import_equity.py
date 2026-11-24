"""Stock-plan documents (RSU, ESPP) are recognised and turned away with a useful message,
instead of being mistaken for a receipt."""

import pytest

from importer import documents
from importer.core import Ctx
from importer.extract import load_document
from tests.conftest import sample_bytes, upload

RSU = sample_bytes("rsu-release.txt").decode()


class NoAI:
    """classify() with the model switched off: rules only."""

    def __init__(self):
        self.notes = []

    def stage(self, text):
        pass

    def ask(self, *args, **kwargs):
        return None

    def info(self, text):
        self.notes.append(text)


def classify(text, name="doc.txt"):
    return documents.classify(load_document(text.encode(), name), NoAI())


def test_the_rsu_sample_would_have_looked_like_a_receipt():
    """Why this needed fixing: 'total' and 'tax' lines score as a receipt."""
    assert documents.score_document(RSU)["receipt"] >= 2
    assert documents.equity_score(RSU) >= 4


def test_stock_plan_documents_are_recognised_without_ai():
    assert classify(RSU) == "equity"
    espp = ("Employee Stock Purchase Plan - Purchase Confirmation\nOffering period 01/01/2025 - 06/30/2025\n"
            "Purchase price $61.20  Fair market value $72.00\nShares purchased 41\nTotal contributions $2,509.20")
    assert classify(espp) == "equity"


@pytest.mark.parametrize("name,expected", [("receipt.txt", "receipt"), ("paystub.txt", "payslip"),
                                           ("card-statement.txt", "statement")])
def test_the_other_samples_are_still_read_as_before(name, expected):
    assert classify(sample_bytes(name).decode(), name) == expected


def test_a_pay_stub_that_lists_rsu_income_is_still_a_pay_stub():
    stub = sample_bytes("paystub.txt").decode() + "\nRSU vest income 1,200.00\nShares withheld for tax 4\nESPP 150.00\n"
    assert documents.equity_score(stub) >= 3
    assert classify(stub, "paystub.txt") == "payslip"


def test_a_stock_plan_file_that_is_not_a_grant_notice_says_what_to_do(client, accounts):
    batch = upload(client, "rsu-release.txt")      # a vest summary, not a notice of grant
    assert batch["status"] == "failed" and batch["doc_type"] == "equity"
    assert "stock-plan document" in batch["error"] and "Plan" in batch["error"]
    assert "receipt" in batch["error"] and "No total" not in batch["error"]


def test_the_model_can_also_say_it_is_a_stock_plan_document(client, accounts, fake_llm):
    # Too little for the rules to be sure (one signal), so the model is asked.
    fake_llm({"classify": {"doc_type": "equity", "confidence": 0.9}})
    batch = upload(client, "award.txt", b"Notice of award\nYour RSUs: 300 units\nThank you\n")
    assert batch["status"] == "failed" and batch["doc_type"] == "equity"


def test_the_owner_can_overrule_it(client, accounts):
    batch = upload(client, "rsu-release.txt", doc_type="receipt")
    assert batch["doc_type"] == "receipt"            # read as asked, whatever comes of it
    assert "stock-plan" not in (batch.get("error") or "")


def test_a_receipt_without_a_total_points_at_the_document_type(client, accounts):
    batch = upload(client, "note.txt", b"Corner Shop\nVisa approved\nThank you, come again\nSubtotal\nSales tax\n",
                   doc_type="receipt")
    assert batch["status"] == "failed"
    assert "may not be a receipt" in batch["error"] and "Cash Flow" not in batch["error"]


# ── RSU grant notices are read into a Plan entry ──────────────────────────────

from models import Rule, db  # noqa: E402

NOTICE = sample_bytes("rsu-grant-notice.txt").decode()


def grant_row(batch):
    rows = [r for r in batch["rows"] if r["target"] == "rsu_grant"]
    assert len(rows) == 1, batch
    return rows[0]


def test_a_grant_notice_is_read_by_rules_alone():
    from importer.equity import read_by_rules
    got = read_by_rules(NOTICE)
    assert got["grant_number"] == "US00012345" and got["grant_date"] == "2025-09-15"
    assert got["total"] == 40_000 and got["vests"] == [{"date": "2026-09-15", "shares": 40_000}]
    assert got["company"] == "EXAMPLE CORPORATION, INC."


def test_review_then_import_adds_one_rsu_grant_with_the_documents_dates(client, accounts):
    batch = upload(client, "rsu-grant-notice.txt")
    assert batch["status"] == "review" and batch["doc_type"] == "equity"
    row = grant_row(batch)
    assert row["grant"]["ticker"] == "" and row["action"] == "import"

    res = client.post(f"/api/imports/{batch['id']}/commit")
    assert res.status_code == 400 and "ticker" in res.get_json()["error"]

    url = f"/api/imports/{batch['id']}/rows/{row['id']}"
    assert client.patch(url, json={"ticker": " exmp! "}).status_code == 200
    res = client.post(f"/api/imports/{batch['id']}/commit")
    assert res.status_code == 200, res.get_json()
    rule = Rule.query.filter_by(rule_type="rsu").one()
    assert rule.config["ticker"] == "EXMP" and rule.config["grant_number"] == "US00012345"
    assert rule.config["schedule_source"] == "document" and rule.config["total_shares"] == 40_000
    assert rule.schedule == [{"date": "2026-09-15", "shares": 40_000}] and rule.start_date == "2025-09-15"

    assert client.post(f"/api/imports/{batch['id']}/undo").status_code == 200
    assert Rule.query.filter_by(rule_type="rsu").count() == 0


def test_the_same_grant_number_is_not_added_twice(client, accounts):
    first = upload(client, "rsu-grant-notice.txt")
    client.patch(f"/api/imports/{first['id']}/rows/{grant_row(first)['id']}", json={"ticker": "EXMP"})
    client.post(f"/api/imports/{first['id']}/commit")
    again = upload(client, "copy.txt", NOTICE.encode())
    row = grant_row(again)
    assert "duplicate" in row["flags"] and row["action"] == "skip"
    assert row["grant"]["ticker"] == "EXMP"          # known from the earlier grant by the same company


def test_a_vest_table_is_read_and_a_mismatch_is_flagged(client, accounts):
    text = ("NOTICE OF RESTRICTED STOCK UNIT GRANT\nGrant Number: G-7781\nGrant Date: 03/01/2025\n"
            "Number of RSUs granted: 100\nVesting schedule\n03/01/2026     25\n03/01/2027     25\n03/01/2028     25\n")
    batch = upload(client, "grant.txt", text.encode())
    row = grant_row(batch)
    assert [v["date"] for v in row["grant"]["vests"]] == ["2026-03-01", "2027-03-01", "2028-03-01"]
    assert "check_vests" in row["flags"] and row["needs_review"]
    assert any("add up to 75" in c for c in batch["extracted"]["checks"])


def test_the_model_fills_gaps_but_only_with_values_in_the_document(client, accounts, fake_llm):
    text = ("Restricted Stock Unit Award Agreement\nNotice of Grant\nAward ID 55-1\nDate of Grant: 2025-02-01\n"
            "You were granted 60 units. Half vest on 1 Feb 2026 (30 units) and half on 1 Feb 2027 (30 units).\n")
    fake_llm({"read_rsu_grant": {"company": "", "grant_number": "55-1", "grant_date_as_written": "2025-02-01",
                                 "total_units_as_written": "60",
                                 "vests": [{"date_as_written": "1 Feb 2026", "units_as_written": "30"},
                                           {"date_as_written": "1 Feb 2027", "units_as_written": "30"},
                                           {"date_as_written": "1 Feb 2028", "units_as_written": "30"}]}})
    batch = upload(client, "award.txt", text.encode(), doc_type="equity")
    row = grant_row(batch)
    assert [v["date"] for v in row["grant"]["vests"]] == ["2026-02-01", "2027-02-01"]   # 2028 isn't in the text
    assert row["grant"]["total_shares"] == 60_000 and "from_ai" in row["flags"]


def test_editing_an_imported_grant_in_plan_keeps_the_documents_dates(client, accounts):
    batch = upload(client, "rsu-grant-notice.txt")
    client.patch(f"/api/imports/{batch['id']}/rows/{grant_row(batch)['id']}", json={"ticker": "EXMP"})
    client.post(f"/api/imports/{batch['id']}/commit")
    rule = Rule.query.filter_by(rule_type="rsu").one()
    res = client.patch(f"/api/rules/{rule.id}", json={"config": {
        "ticker": "EXMP", "total_shares": 40_000, "withholding_rate": 3000, "cliff_months": 12, "cliff_percent": 2500,
        "subsequent_frequency": "monthly", "subsequent_percent": 208, "schedule_source": "document"}})
    assert res.status_code == 200
    db.session.refresh(rule)
    assert rule.schedule == [{"date": "2026-09-15", "shares": 40_000}]
    assert rule.config["withholding_rate"] == 3000 and rule.config["grant_number"] == "US00012345"


def test_the_ticker_is_saved_to_the_database(client, accounts):
    """Checked from a fresh session, so a missing commit can't hide behind the test's shared session."""
    batch = upload(client, "rsu-grant-notice.txt")
    row = grant_row(batch)
    client.patch(f"/api/imports/{batch['id']}/rows/{row['id']}", json={"ticker": "EXMP"})
    db.session.remove()
    from models import ImportRow
    assert db.session.get(ImportRow, row["id"]).raw["ticker"] == "EXMP"
