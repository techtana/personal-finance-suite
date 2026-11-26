"""File readers and rule-based statement reading (no AI)."""

import pytest

from importer.core import Ctx, ImportFailure
from importer.documents import classify, payslip_heuristics, receipt_heuristics, score_document
from importer.extract import Document, UnsupportedFile, load_document, parse_ofx, read_delimited
from importer.llm import LLMClient
from importer.statements import detect_header, detect_sign, from_table, from_text, heuristic_map, profile_columns
from tests.conftest import sample_bytes


def ctx(**kw):
    return Ctx(llm=LLMClient(provider="off"), ai_ok=False, **kw)


def table(name):
    return load_document(sample_bytes(name), name).tables[0]


def test_preamble_is_skipped_and_kept_for_account_hints():
    headers, data, has_header, preamble = detect_header(table("checking-activity.csv"))
    assert has_header and headers[:4] == ["Details", "Posting Date", "Description", "Amount"]
    assert len(data) == 15
    assert "1234" in " ".join(c for r in preamble for c in r)


def test_headerless_file_gets_numbered_columns():
    headers, data, has_header, _ = detect_header(table("headerless.csv"))
    assert not has_header and headers[0] == "Column 1" and len(data) == 5


def test_heuristic_map_single_amount_with_direction_column():
    headers, data, _, _ = detect_header(table("checking-activity.csv"))
    m = heuristic_map(headers, profile_columns(headers, data))
    assert (m["date_col"], m["description_col"], m["amount_col"], m["balance_col"]) == (1, 2, 3, 5)
    assert m["direction_col"] == 0 and m["confidence"] == 1.0


def test_heuristic_map_debit_credit_columns():
    headers, data, _, _ = detect_header(table("rewards-card.csv"))
    m = heuristic_map(headers, profile_columns(headers, data))
    assert (m["date_col"], m["description_col"], m["debit_col"], m["credit_col"], m["amount_col"]) == (0, 3, 5, 6, None)
    assert m["category_col"] == 4


def test_card_export_sign_is_detected_from_the_rows():
    sign, _, confident = detect_sign([3499, 5210, 2340, -61240, 6125], [
        "AMAZON.COM", "SHELL OIL", "MOD PIZZA", "AUTOPAY PAYMENT - THANK YOU", "TRADER JOE'S"])
    assert sign == "positive_is_money_out" and confident


def test_card_export_rows_come_out_as_spending(app):
    c = ctx()
    props = from_table(table("card-activity.csv"), c)
    by_desc = {p.description: p.amount for p in props}
    assert by_desc["SHELL OIL 57444 SEATTLE WA"] == -5210
    assert by_desc["AUTOPAY PAYMENT - THANK YOU"] == 61240
    assert by_desc["AMAZON.COM REFUND AMZN.COM/BILL WA"] == 1999
    assert c.mapping["sign_convention"] == "positive_is_money_out"


def test_checking_export_rows_and_balance(app):
    c = ctx()
    props = from_table(table("checking-activity.csv"), c)
    txns = [p for p in props if p.target == "change_event"]
    snaps = [p for p in props if p.target == "snapshot"]
    assert len(txns) == 15 and txns[0].date == "2026-11-20" and txns[0].amount == -8217
    assert txns[2].amount == 325000
    assert len(snaps) == 1 and snaps[0].date == "2026-11-20" and snaps[0].amount == 412055
    assert c.extracted["account_hint"] == "1234"


def test_european_csv_without_ai_uses_content_rules(app):
    text = "Datum;Empfänger;Betrag\n30.10.2026;REWE Markt GmbH;-45,20\n31.10.2026;Gehalt ACME GmbH;2.850,00\n" \
           "02.11.2026;Deutsche Bahn;-29,90\n"
    c = ctx(prefer_dayfirst=True)
    props = from_table(read_delimited(text), c)
    assert [(p.date, p.amount) for p in props] == [("2026-10-30", -4520), ("2026-10-31", 285000), ("2026-11-02", -2990)]
    assert c.mapping["source"] == "rules"


def test_unreadable_layout_without_ai_fails_with_a_way_out(app):
    rows = [["a", "b"], ["x", "y"], ["z", "w"]]
    with pytest.raises(ImportFailure, match="Pick them"):
        from_table(rows, ctx())


def test_ofx_parse():
    ofx = parse_ofx(sample_bytes("bank-statement.ofx").decode())
    assert [t["amount"] for t in ofx["transactions"]] == [50000, 1241, -500]
    assert ofx["transactions"][0]["fitid"] == "202611140001"
    assert ofx["balance"] == {"amount": 1850741, "date": "2026-11-21"}
    assert ofx["account_id"].endswith("5678")


def test_card_statement_text_uses_sections_and_offers_amount_owed(app):
    c = ctx()
    props = from_text(sample_bytes("card-statement.txt").decode(), c)
    amounts = {p.description: p.amount for p in props}
    assert amounts["PAYMENT THANK YOU"] == 65000
    assert amounts["SAFEWAY #1555 SEATTLE WA"] == -9412
    owed = [p for p in props if p.target == "snapshot"]  # a card's New Balance is what you owe
    assert len(owed) == 1 and owed[0].amount > 0 and owed[0].raw == {"card": True}
    assert {p.date for p in props} >= {"2026-10-05", "2026-11-02"}
    assert c.extracted["account_hint"] == "4821"


def test_receipt_and_payslip_rules():
    r = receipt_heuristics(sample_bytes("receipt.txt").decode())
    assert (r["merchant"], r["total"], r["subtotal"], r["tax"], r["tip"], r["date"], r["card_last4"]) == (
        "CEDAR & SALT KITCHEN", 7870, 6050, 620, 1200, "2026-11-15", "4821")
    p = payslip_heuristics(sample_bytes("paystub.txt").decode())
    assert (p["net_pay"], p["gross_pay"], p["pay_date"], p["period_start"], p["period_end"]) == (
        325000, 500000, "2026-11-14", "2026-10-26", "2026-11-08")


@pytest.mark.parametrize("name,kind", [("receipt.txt", "receipt"), ("paystub.txt", "payslip"),
                                       ("card-statement.txt", "statement")])
def test_classify_text_documents_without_ai(name, kind):
    text = sample_bytes(name).decode()
    assert classify(Document("text", name, text=text), ctx()) == kind, score_document(text)


def test_unsupported_files():
    with pytest.raises(UnsupportedFile, match="xlsx or .csv"):
        load_document(b"\xd0\xcf\x11\xe0", "old.xls")
    with pytest.raises(UnsupportedFile, match="HEIC"):
        load_document(b"....", "IMG_0001.heic")
