"""Tests for the tax estimate engine and its API."""

import pytest

from engine.projection import project_v2
from engine.tax import collect_tax_items, compute_tax, estimate_taxes

D = 100


def item(treatment, dollars):
    return {"date": "2026-06-01", "label": treatment, "treatment": treatment, "amount": dollars * D,
            "source_type": "test", "source_id": "x", "assumed": False, "note": ""}


def rule(rule_type, name, dollars, treatment=None, frequency="monthly", **extra):
    return {"id": name, "name": name, "rule_type": rule_type, "amount": dollars * D,
            "frequency": frequency, "start_date": "2026-01-01", "end_date": None,
            "tax_treatment": treatment, "is_active": True, **extra}


# ── No input ──────────────────────────────────────────────────────────────────

def test_no_inputs_gives_zero_estimate_with_defaults_listed():
    r = estimate_taxes([], [], [], [], None, 2026)
    assert r["has_inputs"] is False and r["has_income"] is False
    assert r["summary"]["total_tax"] == 0
    assert r["summary"]["effective_rate"] == 0
    assert r["insights"] == []
    assert any("Filing status not set" in a for a in r["assumptions"])
    # Limits still show full room so the page has something to draw
    assert {l["key"]: l["remaining"] for l in r["limits"]}["k401"] == 24_500 * D


def test_untagged_income_rule_defaults_to_wages_and_is_flagged():
    items, assumptions = collect_tax_items([rule("income", "Salary", 10_000)], [], [], [], 2026)
    assert len(items) == 12
    assert all(i["treatment"] == "wages" and i["assumed"] for i in items)
    assert any("no tax treatment" in a for a in assumptions)


def test_unknown_year_falls_back_to_nearest_tables():
    r = compute_tax([item("wages", 50_000)], {}, 2031)
    assert r["table_year"] == 2026
    assert any("No tax tables for 2031" in a for a in r["assumptions"])


# ── Income tax and payroll ────────────────────────────────────────────────────

def test_single_wage_earner_matches_hand_calculation():
    s = compute_tax([item("wages", 120_000)], {"filing_status": "single"}, 2026)["summary"]
    assert s["taxable_income"] == 103_900 * D
    assert s["federal_income_tax"] == 17_570 * D   # 1,240 + 4,560 + 11,770
    assert s["social_security_tax"] == 7_440 * D
    assert s["medicare_tax"] == 1_740 * D
    assert s["marginal_rate"] == 0.22


def test_traditional_401k_lowers_income_tax_but_not_payroll_tax():
    base = compute_tax([item("wages", 120_000)], {}, 2026)["summary"]
    with_k = compute_tax([item("wages", 120_000), item("pretax_401k", 24_500)], {}, 2026)["summary"]
    assert base["federal_income_tax"] - with_k["federal_income_tax"] == 5_390 * D  # 24,500 × 22%
    assert with_k["payroll_tax"] == base["payroll_tax"]


def test_roth_401k_uses_the_limit_without_a_deduction():
    r = compute_tax([item("wages", 120_000), item("roth_401k", 10_000)], {}, 2026)
    assert r["summary"]["taxable_income"] == 103_900 * D
    assert {l["key"]: l["used"] for l in r["limits"]}["k401"] == 10_000 * D


def test_contributions_over_the_limit_are_capped_and_warned():
    r = compute_tax([item("wages", 200_000), item("pretax_401k", 30_000)], {}, 2026)
    assert r["summary"]["agi"] == (200_000 - 24_500) * D
    assert any(i["kind"] == "warning" and "over the limit" in i["title"] for i in r["insights"])


def test_catch_up_room_depends_on_age():
    limit = lambda age: {l["key"]: l["limit"] for l in compute_tax([], {"age": age}, 2026)["limits"]}
    assert limit(40)["k401"] == 24_500 * D
    assert limit(52)["k401"] == 32_500 * D
    assert limit(61)["k401"] == 35_750 * D
    assert limit(56)["hsa"] == 5_400 * D


def test_hsa_and_fsa_reduce_payroll_tax():
    base = compute_tax([item("wages", 100_000)], {}, 2026)["summary"]
    s = compute_tax([item("wages", 100_000), item("hsa", 4_400), item("fsa_limited", 3_400)], {}, 2026)["summary"]
    assert s["agi"] == (100_000 - 7_800) * D
    assert base["payroll_tax"] - s["payroll_tax"] == round(7_800 * D * 0.0765)


def test_social_security_stops_at_the_wage_base():
    s = compute_tax([item("wages", 300_000)], {}, 2026)["summary"]
    assert s["social_security_tax"] == round(184_500 * D * 0.062)
    # 1.45% on everything plus 0.9% above $200k
    assert s["medicare_tax"] == 4_350 * D + 900 * D


def test_self_employment_tax_and_half_deduction():
    r = compute_tax([item("self_employment", 100_000)], {}, 2026)
    se_tax = r["summary"]["self_employment_tax"]
    assert se_tax == round(92_350 * D * 0.124) + round(92_350 * D * 0.029)
    assert r["summary"]["agi"] == 100_000 * D - se_tax // 2


# ── Investments and losses ────────────────────────────────────────────────────

def test_long_term_gains_stack_into_the_zero_percent_band():
    r = compute_tax([item("wages", 60_000), item("capital_gain_long", 20_000)], {"filing_status": "mfj"}, 2026)
    assert r["summary"]["preferential_tax"] == 0
    assert r["preferential_bands"][0]["amount"] == 20_000 * D


def test_net_capital_loss_deducts_3000_and_carries_the_rest_forward():
    r = compute_tax([item("wages", 100_000), item("capital_gain_short", -10_000)], {}, 2026)
    assert r["capital"]["loss_deduction"] == 3_000 * D
    assert r["capital"]["carryover_out"] == 7_000 * D
    assert r["summary"]["agi"] == 97_000 * D


def test_carryover_and_untracked_sales_come_from_the_profile():
    profile = {"loss_carryover": 5_000 * D, "other_gain_long": 2_000 * D}
    c = compute_tax([item("wages", 100_000), item("capital_gain_long", 10_000)], profile, 2026)["capital"]
    assert c["taxable_long"] == 7_000 * D and c["carryover_out"] == 0


def test_short_term_loss_offsets_long_term_gain():
    c = compute_tax([item("capital_gain_short", -4_000), item("capital_gain_long", 10_000)], {}, 2026)["capital"]
    assert c["taxable_long"] == 6_000 * D and c["taxable_short"] == 0


def test_asset_sale_uses_proportional_basis_and_holding_period():
    asset = {"id": "a1", "name": "VTI", "category": "etf", "current_value": 100_000 * D,
             "cost_basis": 60_000 * D, "acquired_date": "2026-01-10",
             "scheduled_events": [{"id": "e1", "date": "2026-09-01", "type": "dispose", "value": 50_000 * D}]}
    items, _ = collect_tax_items([], [], [asset], [], 2026)
    assert items[0]["treatment"] == "capital_gain_short"   # held under a year
    assert items[0]["amount"] == 20_000 * D                # 50,000 − half of the 60,000 basis


def test_asset_sale_without_basis_is_left_out_and_explained():
    asset = {"id": "a1", "name": "Coins", "category": "crypto", "current_value": 10_000 * D, "cost_basis": None,
             "scheduled_events": [{"id": "e1", "date": "2026-09-01", "type": "dispose", "value": 10_000 * D}]}
    items, assumptions = collect_tax_items([], [], [asset], [], 2026)
    assert items == []
    assert any("no cost basis" in a for a in assumptions)


def test_niit_applies_above_the_threshold():
    s = compute_tax([item("wages", 250_000), item("interest", 20_000)], {}, 2026)["summary"]
    assert s["niit"] == round(20_000 * D * 0.038)


# ── Deductions ────────────────────────────────────────────────────────────────

def test_itemizing_wins_only_when_it_beats_the_standard_deduction():
    small = compute_tax([item("wages", 150_000), item("charity", 5_000)], {}, 2026)["deductions"]
    assert small["method"] == "standard"
    big = compute_tax([item("wages", 150_000), item("mortgage_interest", 18_000), item("property_tax", 9_000)], {}, 2026)["deductions"]
    assert big["method"] == "itemized" and big["used"] == 27_000 * D


def test_salt_is_capped():
    d = compute_tax([item("wages", 300_000), item("property_tax", 60_000)], {}, 2026)["deductions"]
    assert d["parts"][1]["amount"] == 40_400 * D


def test_mortgage_interest_is_derived_from_the_loan_when_not_entered():
    loan = {"id": "l1", "name": "Home", "type": "mortgage", "original_balance": 400_000 * D,
            "interest_rate": 600, "monthly_payment": 2_400 * D, "start_date": "2025-01-01"}
    items, assumptions = collect_tax_items([], [], [], [loan], 2026)
    assert len(items) == 1 and items[0]["treatment"] == "mortgage_interest"
    assert 23_000 * D < items[0]["amount"] < 24_000 * D   # about 6% of ~$395k
    entered = rule("expense", "Mortgage interest", 2_000, "mortgage_interest")
    items, _ = collect_tax_items([entered], [], [], [loan], 2026)
    assert all(i["source_type"] != "loan" for i in items)


# ── Payments and insights ─────────────────────────────────────────────────────

def test_withholding_counts_against_the_federal_bill():
    s = compute_tax([item("wages", 120_000), item("tax_payment", 20_000)], {}, 2026)["summary"]
    assert s["federal_balance_due"] == (17_570 - 20_000) * D


def test_no_contributions_surfaces_the_unused_401k_room():
    r = compute_tax([item("wages", 120_000)], {}, 2026)
    top = [i for i in r["insights"] if i["kind"] == "opportunity"][0]
    assert "No 401(k) contributions entered" in top["title"]
    assert top["value"] == 5_390 * D


def test_rsu_vest_is_wages_with_withholding_as_a_payment():
    rsu = {"id": "r1", "name": "GOOG grant", "rule_type": "rsu", "is_active": True, "start_date": "2025-01-01",
           "schedule": [{"date": "2026-03-01", "shares": 10_000}],
           "config": {"ticker": "GOOG", "price_at_grant": 150 * D, "withholding_rate": 2200}}
    items, assumptions = collect_tax_items([rsu], [], [], [], 2026)
    assert [(i["treatment"], i["amount"]) for i in items] == [("wages", 1_500 * D), ("tax_payment", 330 * D)]
    assert any("grant price" in a for a in assumptions)


def test_adjustments_and_exempt_income_are_not_taxed():
    changes = [
        {"id": "c1", "date": "2026-02-01", "description": "Reconcile", "amount": 5_000 * D, "change_type": "adjustment"},
        {"id": "c2", "date": "2026-02-01", "description": "Gift", "amount": 5_000 * D, "change_type": "manual", "tax_treatment": "tax_exempt"},
    ]
    r = estimate_taxes([], changes, [], [], None, 2026)
    assert r["summary"]["gross_income"] == 0 and r["summary"]["tax_exempt_income"] == 5_000 * D


# ── Projection ────────────────────────────────────────────────────────────────

def test_retirement_contributions_are_not_projected_as_spending():
    rules = [rule("income", "Salary", 10_000, "wages"),
             rule("expense", "401k", 2_000, "pretax_401k"),
             rule("expense", "Rent", 3_000)]
    buckets, _ = project_v2(rules, [], [], 0, {}, "2026-01-01", "2026-01-31")
    assert buckets[0].income == 10_000 * D and buckets[0].expenses == 3_000 * D


# ── API ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from app import create_app
    from config import TestingConfig
    from models import db

    app = create_app(TestingConfig)
    with app.app_context():
        yield app.test_client()
        db.drop_all()


def test_api_round_trip(client):
    assert client.get("/api/taxes/summary?year=2026").get_json()["has_inputs"] is False
    client.post("/api/rules", json={"name": "Salary", "rule_type": "income", "amount": 1_000_000,
                                    "frequency": "monthly", "start_date": "2026-01-01", "tax_treatment": "wages"})
    client.post("/api/changes", json={"date": "2026-04-01", "description": "Donation", "amount": -200_000,
                                      "tax_treatment": "charity"})
    assert client.patch("/api/taxes/profile", json={"filing_status": "mfj", "state_rate": 500}).status_code == 200
    r = client.get("/api/taxes/summary?year=2026").get_json()
    assert r["summary"]["gross_income"] == 12_000_000
    assert r["filing_status_label"] == "Married filing jointly"
    assert r["summary"]["state_tax"] == 600_000
    assert r["deductions"]["parts"][2]["amount"] == 200_000
    assert client.get("/taxes").status_code == 200
