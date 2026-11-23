"""The AI layer with a scripted model: wrong answers must be caught, not stored."""

from importer import ai_tools
from importer.core import Ctx
from importer.documents import from_payslip, from_receipt
from importer.llm import LLMUnavailable
from importer.statements import detect_header, from_table, profile_columns
from importer.taxonomy import allowed_categories
from tests.conftest import FakeLLM, sample_bytes, upload

CATS = allowed_categories([])
RECEIPT = sample_bytes("receipt.txt").decode()
PAYSTUB = sample_bytes("paystub.txt").decode()


def receipt_answer(**over):
    base = {"merchant": "CEDAR & SALT KITCHEN", "date": "11/15/2026", "total": "78.70", "subtotal": "60.50",
            "tax": "6.20", "tip": "12.00", "is_refund": False, "card_last4": "4821", "category": "dining",
            "items": [{"description": "Margherita Pizza", "amount": "32.00"}, {"description": "Caesar Salad", "amount": "12.50"},
                      {"description": "Sparkling Water", "amount": "7.00"}, {"description": "Tiramisu", "amount": "9.00"}]}
    return {**base, **over}


def test_map_columns_rejects_wrong_columns_then_accepts_the_fix():
    rows = [["When", "What", "How much"], ["11/02/2026", "COFFEE", "-4.50"], ["11/03/2026", "RENT", "-1,850.00"]]
    headers, data, _, _ = detect_header(rows)
    good = {"date_col": 0, "description_col": 1, "amount_col": 2, "debit_col": -1, "credit_col": -1,
            "balance_col": -1, "category_col": -1, "sign_convention": "negative_is_money_out"}
    bad = {**good, "date_col": 1, "description_col": 0}
    llm = FakeLLM({"map_columns": [bad, good]})
    res = ai_tools.map_columns(llm, headers, profile_columns(headers, data), data)
    assert res.ok and res.data["date_col"] == 0 and llm.calls == 2
    correction = llm.seen[1][1][-1]["content"]
    assert "date_col must be a column whose values are dates" in correction and "0 ('When')" in correction


def test_receipt_total_not_on_the_receipt_is_rejected(app):
    llm = FakeLLM({"read_receipt": [receipt_answer(total="80.00"), receipt_answer(total="80.00")]})
    c = Ctx(llm=llm, ai_ok=True)
    [p] = from_receipt(RECEIPT, c, CATS)
    assert p.amount == -7870  # the TOTAL line, not the invented 80.00
    assert any("isn't printed on the receipt" in x for x in c.extracted["ai_problems"])


def test_receipt_subtotal_read_as_total_is_caught_by_the_rules(app):
    llm = FakeLLM({"read_receipt": [receipt_answer(total="60.50")]})
    c = Ctx(llm=llm, ai_ok=True)
    [p] = from_receipt(RECEIPT, c, CATS)
    assert p.amount == -7870 and "ai_disagrees" in p.flags and p.confidence <= 0.7  # arithmetic backs the rules


def test_receipt_that_adds_up_is_trusted(app):
    c = Ctx(llm=FakeLLM({"read_receipt": [receipt_answer()]}), ai_ok=True)
    [p] = from_receipt(RECEIPT, c, CATS)
    assert p.amount == -7870 and p.date == "2026-11-15" and p.category == "dining" and p.confidence >= 0.95
    assert any("= total 78.70 ✓" in x for x in c.extracted["checks"])


def test_receipt_date_must_be_printed_on_it(app):
    c = Ctx(llm=FakeLLM({"read_receipt": [receipt_answer(date="2026-12-25")] * 2}), ai_ok=True)
    [p] = from_receipt(RECEIPT, c, CATS)
    assert p.date == "2026-11-15"


def payslip_answer(**over):
    base = {"employer": "ACME CORP", "pay_date": "11/14/2026", "period_start": "10/26/2026", "period_end": "11/08/2026",
            "gross_pay": "5,000.00", "net_pay": "3,250.00",
            "deductions": [{"name": "Federal Income Tax", "amount": "640.00", "kind": "tax"},
                           {"name": "Social Security", "amount": "310.00", "kind": "tax"},
                           {"name": "Medicare", "amount": "72.50", "kind": "tax"},
                           {"name": "WA PFML", "amount": "14.50", "kind": "tax"},
                           {"name": "401(k)", "amount": "400.00", "kind": "retirement"},
                           {"name": "Medical Insurance", "amount": "163.00", "kind": "health"},
                           {"name": "ESPP", "amount": "150.00", "kind": "stock_plan"},
                           {"name": "Total Deductions", "amount": "1,750.00", "kind": "other"}],
            "employer_contributions": [{"name": "401(k) Match", "amount": "200.00", "kind": "retirement"}]}
    return {**base, **over}


def test_payslip_ytd_net_is_replaced_by_the_amount_that_reconciles(app, accounts):
    c = Ctx(llm=FakeLLM({"read_payslip": [payslip_answer(net_pay="68,250.00")]}), ai_ok=True,
            accounts=list(accounts.values()))
    rows = from_payslip(PAYSTUB, c, [])
    net, retire, rule = rows
    assert net.amount == 325000 and net.category == "salary" and net.date == "2026-11-14"
    assert retire.amount == 60000 and retire.account_id == accounts["k401"].id  # 401k 400 + match 200
    assert rule.target == "rule" and rule.frequency == "biweekly" and rule.date == "2026-11-28"
    assert any("= net 3,250.00 ✓" in x for x in c.extracted["checks"])  # "Total Deductions" wasn't double counted


def test_payslip_empty_amounts_are_sent_back():
    empty = payslip_answer(net_pay="", deductions=[{"name": "Federal Income Tax", "amount": "", "kind": "tax"}])
    llm = FakeLLM({"read_payslip": [empty, payslip_answer()]})
    res = ai_tools.read_payslip(llm, PAYSTUB)
    assert res.ok and llm.calls == 2
    assert "copy its CURRENT amount" in llm.seen[1][1][-1]["content"]


def test_statement_lines_must_be_grounded_in_their_line():
    lines = [(0, "PURCHASES"), (1, "10/05 SAFEWAY #1555 SEATTLE WA 94.12"), (2, "10/09 CHEVRON 0091234 48.30")]
    answer = {"transactions": [
        {"line": 1, "date": "10/05", "description": "SAFEWAY", "amount": "94.12", "direction": "out"},
        {"line": 2, "date": "10/09", "description": "CHEVRON", "amount": "84.30", "direction": "out"},  # digits swapped
        {"line": 0, "date": "10/01", "description": "PURCHASES", "amount": "1.00", "direction": "out"},
    ]}
    res = ai_tools.extract_statement_lines(FakeLLM({"statement_lines": [answer]}), lines)
    assert [t["line"] for t in res.data] == [1]
    assert any("84.30" in p for p in res.problems)


def test_categorize_rejects_income_category_on_spending():
    items = [{"i": 0, "description": "MYSTERY SHOP", "amount": -1000, "hint": None}]
    bad = {"items": [{"i": 0, "category": "salary", "confidence": 0.9}]}
    llm = FakeLLM({"categorize": [bad, bad]})
    assert ai_tools.categorize(llm, items, CATS) == {}
    good = {"items": [{"i": 0, "category": "shopping", "confidence": 0.7}]}
    assert ai_tools.categorize(FakeLLM({"categorize": [bad, good]}), items, CATS) == {0: ("shopping", 0.7)}


def test_ai_going_offline_mid_file_falls_back_to_rules(app, client, accounts, fake_llm):
    def offline(messages, images):
        raise LLMUnavailable("connection refused")

    fake_llm({"categorize": offline})
    csv = b"Date,Description,Amount\n11/02/2026,MYSTERY VENDOR 1,-10.00\n11/03/2026,SAFEWAY #12,-20.00\n"
    b = upload(client, "odd.csv", csv, account_id=accounts["chk"].id)
    assert b["status"] == "review"
    rows = {r["description"]: r for r in b["rows"]}
    assert rows["SAFEWAY #12"]["category"] == "groceries"
    assert "uncategorized" in rows["MYSTERY VENDOR 1"]["flags"]
    assert any("stopped responding" in w["text"] for w in b["warnings"])


def test_ai_mapped_layout_is_flagged_for_a_look(app):
    rows = [["11/02/2026", "-4.50", "COFFEE SHOP"], ["11/03/2026", "-1,850.00", "LANDLORD LLC"],
            ["11/04/2026", "3,000.00", "EMPLOYER INC"]]
    ai_map = {"date_col": 0, "description_col": 2, "amount_col": 1, "debit_col": -1, "credit_col": -1,
              "balance_col": -1, "category_col": -1, "sign_convention": "negative_is_money_out"}
    c = Ctx(llm=FakeLLM({"map_columns": [ai_map]}), ai_ok=True)
    props = from_table(rows, c)
    assert [p.amount for p in props] == [-450, -185000, 300000]
    assert c.mapping["source"] == "ai" and all(p.confidence <= 0.85 for p in props)
