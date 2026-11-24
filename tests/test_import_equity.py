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


def test_upload_says_what_it_is_and_what_to_do(client, accounts):
    batch = upload(client, "rsu-release.txt")
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
