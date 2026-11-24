"""Live checks against the real local model. Skipped unless RUN_LOCAL_LLM_TESTS=1.

Run these after changing a prompt, the model (LLM_MODEL) or the agent stack:
    RUN_LOCAL_LLM_TESTS=1 pytest tests/test_import_live.py -v
Each case is a sample file in docs/sample-data/imports with the values a correct reading must produce.
"""

import os

import pytest

from importer.llm import build_client
from tests.conftest import upload

pytestmark = pytest.mark.skipif(os.environ.get("RUN_LOCAL_LLM_TESTS") != "1", reason="set RUN_LOCAL_LLM_TESTS=1")


@pytest.fixture
def live(app):
    app.config["LLM_PROVIDER"] = os.environ.get("LLM_PROVIDER", "ollama")
    status = build_client(app.config).status()
    if not status["ok"]:
        pytest.skip(f"local AI not ready: {status['error']}")
    return status


def by_desc(b):
    return {r["description"]: r for r in b["rows"] if r["target"] == "change_event"}


def test_receipt_photo(client, accounts, live):
    b = upload(client, "receipt-photo.jpg")
    assert b["status"] == "review" and b["doc_type"] == "receipt", b.get("error")
    [row] = b["rows"]
    assert (row["amount"], row["date"], row["category"]) == (-2898, "2026-11-17", "groceries")
    assert b["extracted"]["adds_up"] is True


def test_receipt_text(client, accounts, live):
    b = upload(client, "receipt.txt")
    [row] = b["rows"]
    assert (row["amount"], row["date"], row["category"]) == (-7870, "2026-11-15", "dining")
    assert b["extracted"]["tip"] == 1200


@pytest.mark.parametrize("name,date", [("paystub.txt", "2026-11-14"), ("paystub-photo.jpg", "2026-11-28")])
def test_payslips(client, accounts, live, name, date):
    b = upload(client, name)
    assert b["doc_type"] == "payslip", b.get("error")
    ex = b["extracted"]
    assert (ex["gross_pay"], ex["net_pay"], ex["pay_date"]) == (500000, 325000, date)
    assert any("✓" in c for c in ex["checks"]), ex["checks"]
    net = [r for r in b["rows"] if r["category"] == "salary" and r["target"] == "change_event"][0]
    assert net["amount"] == 325000
    retire = [r for r in b["rows"] if r["category"] == "investment"][0]
    assert retire["amount"] == 60000 and retire["account_id"] == accounts["k401"].id


def test_headerless_csv_columns(client, accounts, live):
    b = upload(client, "headerless.csv")
    assert b["mapping"]["source"] == "ai"
    assert (b["mapping"]["date_col"], b["mapping"]["amount_col"], b["mapping"]["description_col"]) == (0, 1, 4)
    assert by_desc(b)["SAFEWAY #1555 SEATTLE WA"]["amount"] == -4210


def test_unknown_merchants_get_a_sensible_category(client, accounts, live):
    csv = (b"Date,Description,Amount\n11/02/2026,BLUE APRON MEAL KIT,-59.99\n11/03/2026,PETCO 1234,-42.10\n"
           b"11/04/2026,MAJESTIC BAY THEATRES,-28.00\n11/05/2026,KING COUNTY LIBRARY FINE,-2.50\n")
    b = upload(client, "misc.csv", csv, account_id=accounts["chk"].id)
    cats = {d: r["category"] for d, r in by_desc(b).items()}
    assert all(cats.values()), cats
    assert cats["MAJESTIC BAY THEATRES"] in ("entertainment", "misc")
    assert all(r["category_source"] == "ai" for r in by_desc(b).values())
