"""Tax estimate engine: classify cash-flow inputs, then estimate US federal tax.

Two steps, both pure functions:
  collect_tax_items()  turns rules, changes, asset sales and loans into tax items
  compute_tax()        turns tax items + a tax profile into an estimate

Every input is optional. Where something is missing the engine picks a default
and records it in `assumptions`, so the result always says what it guessed.
All money is in cents.
"""

from datetime import date

from engine.amortization import amortize_loan
from engine.recurrence import expand_recurring_dates
from engine.tax_tables import (
    D, EXPENSE_KEYS, FILING_STATUSES, INCOME_KEYS, TREATMENT_LABELS, tables_for,
)

DEFAULT_PROFILE = {
    "filing_status": "single",
    "state_rate": 0,            # flat effective state income tax rate, percent × 100
    "age": None,                # for catch-up contributions
    "hsa_coverage": "self",     # self | family | none
    "loss_carryover": 0,        # capital loss carried in from earlier years (positive)
    "other_gain_short": 0,      # realized gain (+) / loss (−) from sales not tracked in the app
    "other_gain_long": 0,
}

# Asset categories where a loss on sale is personal and not deductible
PERSONAL_USE_CATEGORIES = {"vehicle", "property"}


def normalize_profile(raw: dict | None) -> tuple[dict, list[str]]:
    """Fill a possibly empty tax profile with defaults; report what was assumed."""
    raw = raw or {}
    profile = dict(DEFAULT_PROFILE)
    assumptions = []

    status = raw.get("filing_status")
    if status in FILING_STATUSES:
        profile["filing_status"] = status
    else:
        assumptions.append("Filing status not set — assumed Single.")

    if raw.get("state_rate") is None:
        assumptions.append("State income tax rate not set — assumed 0%.")
    else:
        profile["state_rate"] = max(0, int(raw["state_rate"]))

    if raw.get("age"):
        profile["age"] = int(raw["age"])
    else:
        assumptions.append("Age not set — catch-up contribution room (50+) not included.")

    coverage = raw.get("hsa_coverage")
    if coverage in ("self", "family", "none"):
        profile["hsa_coverage"] = coverage
    else:
        assumptions.append("HSA coverage not set — assumed self-only coverage for the limit.")

    for key in ("loss_carryover", "other_gain_short", "other_gain_long"):
        if raw.get(key) is not None:
            profile[key] = int(raw[key])
    profile["loss_carryover"] = abs(profile["loss_carryover"])
    return profile, assumptions


def _item(date_str, label, treatment, amount, source_type, source_id, assumed=False, note=""):
    return {
        "date": date_str,
        "label": label,
        "treatment": treatment,
        "treatment_label": TREATMENT_LABELS.get(treatment, treatment),
        "amount": amount,
        "source_type": source_type,
        "source_id": source_id,
        "assumed": assumed,
        "note": note,
    }


def collect_tax_items(
    rules: list,
    changes: list,
    assets: list,
    loans: list,
    year: int,
    stock_prices: dict | None = None,
) -> tuple[list[dict], list[str]]:
    """Expand every input into dated tax items for one calendar year."""
    stock_prices = stock_prices or {}
    start, end = f"{year}-01-01", f"{year}-12-31"
    items: list[dict] = []
    assumptions: list[str] = []
    defaulted_income = 0
    defaulted_change = 0

    for rule in rules:
        if not rule.get("is_active", True):
            continue
        rt = rule.get("rule_type", "income")
        name = rule.get("name") or "Unnamed rule"

        if rt in ("income", "expense"):
            freq = rule.get("frequency")
            amount = rule.get("amount") or 0
            if not freq or amount <= 0:
                continue
            valid = INCOME_KEYS if rt == "income" else EXPENSE_KEYS
            treatment = rule.get("tax_treatment")
            assumed = treatment not in valid
            if assumed:
                treatment = "wages" if rt == "income" else "none"
                if rt == "income":
                    defaulted_income += 1
            for d in expand_recurring_dates(rule["start_date"], rule.get("end_date"), freq, start, end):
                items.append(_item(d, name, treatment, amount, "rule", rule["id"], assumed and rt == "income"))

        elif rt == "rsu":
            cfg = rule.get("config") or {}
            ticker = cfg.get("ticker", "")
            price = stock_prices.get(ticker) or 0
            price_assumed = False
            if not price:
                price = cfg.get("price_at_grant") or 0
                price_assumed = bool(price)
            vests = [v for v in (rule.get("schedule") or []) if start <= v.get("date", "") <= end]
            if vests and not price:
                assumptions.append(f"RSU “{name}” has no share price — its vests are left out of income.")
                continue
            if vests and price_assumed:
                assumptions.append(f"RSU “{name}” valued at the grant price (no current price given).")
            rate = cfg.get("withholding_rate", 0) or 0
            for v in vests:
                gross = (v.get("shares", 0) * price) // 1000
                if gross <= 0:
                    continue
                items.append(_item(v["date"], f"{name} vest", "wages", gross, "rsu", rule["id"], price_assumed))
                withheld = (gross * rate) // 10000
                if withheld > 0:
                    items.append(_item(v["date"], f"{name} vest withholding", "tax_payment", withheld, "rsu", rule["id"]))

        elif rt == "espp":
            if any(start <= p.get("end_date", "") <= end for p in (rule.get("schedule") or [])):
                assumptions.append(f"ESPP “{name}”: the discount is taxed when shares are sold, so purchases add no tax here.")

    for change in changes:
        amt = change.get("amount", 0)
        d = change.get("date", "")
        if amt == 0 or not (start <= d <= end):
            continue
        if change.get("change_type") == "adjustment":
            continue  # balance corrections are not taxable events
        treatment = change.get("tax_treatment")
        label = change.get("description") or "Change"
        if amt > 0:
            assumed = treatment not in INCOME_KEYS
            if assumed:
                treatment = "other_income"
                defaulted_change += 1
            items.append(_item(d, label, treatment, amt, "change", change["id"], assumed))
        else:
            if treatment not in EXPENSE_KEYS:
                treatment = "none"
            items.append(_item(d, label, treatment, -amt, "change", change["id"]))

    for asset in assets:
        for ev in asset.get("scheduled_events") or []:
            d = ev.get("date", "")
            if ev.get("type") != "dispose" or not (start <= d <= end):
                continue
            name = asset.get("name") or "Asset"
            proceeds = ev.get("value", 0) or 0
            basis_total = asset.get("cost_basis")
            if basis_total is None:
                assumptions.append(f"Sale of “{name}” has no cost basis — gain or loss can't be computed, so it is left out.")
                continue
            value = asset.get("current_value") or 0
            share = min(1.0, proceeds / value) if value > 0 else 1.0
            gain = proceeds - round(basis_total * share)
            if gain < 0 and asset.get("category") in PERSONAL_USE_CATEGORIES:
                assumptions.append(f"Loss on “{name}” treated as personal-use — not deductible.")
                continue
            if gain > 0 and asset.get("category") == "property":
                assumptions.append(f"Sale of “{name}”: the home-sale exclusion ($250k / $500k) is not applied.")
            acquired = asset.get("acquired_date")
            assumed = False
            if acquired:
                try:
                    long_term = (date.fromisoformat(d) - date.fromisoformat(acquired)).days > 365
                except ValueError:
                    long_term, assumed = True, True
            else:
                long_term, assumed = True, True
            if assumed:
                assumptions.append(f"Sale of “{name}” has no purchase date — assumed held over a year (long-term).")
            treatment = "capital_gain_long" if long_term else "capital_gain_short"
            items.append(_item(d, f"Sell {name}", treatment, gain, "asset_sale", asset.get("id", ""), assumed,
                               note=f"proceeds {proceeds / D:,.0f} − basis {round(basis_total * share) / D:,.0f}"))

    # Loan interest, derived from the loan itself unless the user entered it
    entered = {i["treatment"] for i in items}
    for loan in loans:
        treatment = {"mortgage": "mortgage_interest", "heloc": "mortgage_interest",
                     "student": "student_loan_interest"}.get(loan.get("type"))
        if not treatment or treatment in entered:
            continue
        schedule = amortize_loan(
            loan.get("start_date", ""), loan.get("original_balance", 0),
            loan.get("interest_rate", 0), loan.get("monthly_payment", 0), 600,
        )
        interest = sum(r["interest"] for r in schedule if start <= r["date"] <= end)
        if interest > 0:
            name = loan.get("name") or "Loan"
            items.append(_item(end, f"{name} interest", treatment, interest, "loan", loan["id"], True,
                               note="estimated from the loan's rate and payment"))
            assumptions.append(f"Interest on “{name}” estimated from its amortization schedule.")

    if defaulted_income:
        assumptions.append(f"{defaulted_income} income rule(s) have no tax treatment — assumed W-2 wages entered before tax.")
    if defaulted_change:
        assumptions.append(f"{defaulted_change} one-time gain(s) have no tax treatment — assumed other taxable income.")

    items.sort(key=lambda i: i["date"])
    return items, assumptions


def _bracket_tax(taxable: int, brackets: list) -> tuple[int, list[dict], float]:
    """Tax on ordinary income. Returns (tax, per-bracket fill, marginal rate)."""
    tax = 0
    fill = []
    lower = 0
    marginal = brackets[0][0] if taxable > 0 else 0.0
    for rate, upper_dollars in brackets:
        upper = upper_dollars * D if upper_dollars is not None else None
        in_band = max(0, (taxable if upper is None else min(taxable, upper)) - lower)
        band_tax = round(in_band * rate)
        tax += band_tax
        if in_band > 0:
            marginal = rate
        fill.append({"rate": rate, "from": lower, "to": upper, "amount": in_band, "tax": band_tax})
        if upper is None:
            break
        lower = upper
    return tax, fill, marginal


def _preferential_tax(ordinary_taxable: int, pref: int, thresholds: tuple) -> tuple[int, list[dict]]:
    """Tax on long-term gains / qualified dividends, stacked on top of ordinary income."""
    t0, t15 = thresholds[0] * D, thresholds[1] * D
    at0 = max(0, min(ordinary_taxable + pref, t0) - ordinary_taxable)
    at15 = max(0, min(ordinary_taxable + pref, t15) - max(ordinary_taxable, t0))
    at20 = pref - at0 - at15
    bands = [
        {"rate": 0.0, "amount": at0, "tax": 0},
        {"rate": 0.15, "amount": at15, "tax": round(at15 * 0.15)},
        {"rate": 0.20, "amount": at20, "tax": round(at20 * 0.20)},
    ]
    return sum(b["tax"] for b in bands), bands


def _limit(key, label, used, limit, note=""):
    return {"key": key, "label": label, "used": used, "limit": limit,
            "remaining": max(0, limit - used), "over": max(0, used - limit), "note": note}


def compute_tax(items: list[dict], raw_profile: dict | None, year: int) -> dict:
    """Estimate federal (and flat-rate state) tax for one year from tax items."""
    profile, assumptions = normalize_profile(raw_profile)
    t, table_year = tables_for(year)
    if table_year != year:
        assumptions.append(f"No tax tables for {year} — using {table_year} brackets and limits.")
    status = profile["filing_status"]
    age = profile["age"] or 0

    totals: dict[str, int] = {}
    for it in items:
        totals[it["treatment"]] = totals.get(it["treatment"], 0) + it["amount"]
    g = lambda key: totals.get(key, 0)

    # ── Contribution limits ──────────────────────────────────────────────────
    k401_limit = t["k401_limit"]
    if 60 <= age <= 63:
        k401_limit += t["k401_catchup_60_63"]
    elif age >= 50:
        k401_limit += t["k401_catchup_50"]
    ira_limit = t["ira_limit"] + (t["ira_catchup_50"] if age >= 50 else 0)
    coverage = profile["hsa_coverage"]
    hsa_limit = t["hsa_limit"][coverage] + (t["hsa_catchup_55"] if age >= 55 and coverage != "none" else 0)

    k401_trad = min(g("pretax_401k"), k401_limit)
    hsa = min(g("hsa"), hsa_limit)
    fsa_used = g("fsa_health") + g("fsa_limited")
    fsa = min(fsa_used, t["fsa_health_limit"])
    dcfsa = min(g("fsa_dependent_care"), t["fsa_dependent_care_limit"])
    ira_trad = min(g("ira_traditional"), ira_limit)

    limits = [
        _limit("k401", "401(k)", g("pretax_401k") + g("roth_401k"), k401_limit,
               "Traditional + Roth share one limit"),
        _limit("hsa", "HSA", g("hsa"), hsa_limit,
               {"self": "Self-only coverage", "family": "Family coverage",
                "none": "No HSA-eligible health plan"}[coverage]),
        _limit("fsa", "Health FSA / limited FSA", fsa_used, t["fsa_health_limit"],
               "Unspent balance is mostly forfeited at year end"),
        _limit("dcfsa", "Dependent-care FSA", g("fsa_dependent_care"), t["fsa_dependent_care_limit"],
               "Per household"),
        _limit("ira", "IRA", g("ira_traditional") + g("ira_roth"), ira_limit,
               "Traditional + Roth share one limit"),
    ]

    # ── Income ───────────────────────────────────────────────────────────────
    wages = g("wages")
    se = g("self_employment")
    interest, div_ord, div_q = g("interest"), g("dividend_ordinary"), g("dividend_qualified")
    rental, other = g("rental"), g("other_income")
    exempt = g("tax_exempt")

    taxable_wages = max(0, wages - k401_trad - fsa - dcfsa - min(hsa, wages))
    fica_wages = max(0, wages - fsa - dcfsa - min(hsa, wages))

    # ── Payroll and self-employment tax ──────────────────────────────────────
    ss_tax = round(min(fica_wages, t["ss_wage_base"]) * t["ss_rate"])
    medicare_tax = round(fica_wages * t["medicare_rate"])
    se_net = round(max(0, se) * 0.9235)
    se_ss = round(min(se_net, max(0, t["ss_wage_base"] - fica_wages)) * t["ss_rate"] * 2)
    se_medicare = round(se_net * t["medicare_rate"] * 2)
    se_tax = se_ss + se_medicare
    addl_medicare = round(max(0, fica_wages + se_net - t["addl_medicare_threshold"][status]) * t["addl_medicare_rate"])

    # ── Capital gains and losses ─────────────────────────────────────────────
    st = g("capital_gain_short") + profile["other_gain_short"]
    lt = g("capital_gain_long") + profile["other_gain_long"]
    carry_in = profile["loss_carryover"]
    lt_after = lt - carry_in  # carryover treated as long-term
    net_capital = st + lt_after
    loss_deduction = carry_out = st_taxable = lt_taxable = 0
    if net_capital <= 0:
        loss_deduction = min(-net_capital, t["capital_loss_limit"])
        carry_out = -net_capital - loss_deduction
    elif st < 0:
        lt_taxable = net_capital
    elif lt_after < 0:
        st_taxable = net_capital
    else:
        st_taxable, lt_taxable = st, lt_after
    capital = {
        "short_term": st, "long_term": lt, "carryover_in": carry_in, "net": net_capital,
        "taxable_short": st_taxable, "taxable_long": lt_taxable,
        "loss_deduction": loss_deduction, "carryover_out": carry_out,
        "has_activity": bool(st or lt or carry_in),
    }

    # ── AGI ──────────────────────────────────────────────────────────────────
    ordinary_income = taxable_wages + se + interest + div_ord + rental + other + st_taxable - loss_deduction
    preferential = div_q + lt_taxable
    student_interest = min(g("student_loan_interest"), t["student_loan_interest_limit"])
    hsa_outside_payroll = hsa - min(hsa, wages)
    half_se = se_tax // 2
    adjustments = ira_trad + student_interest + half_se + hsa_outside_payroll
    agi = max(0, ordinary_income + preferential - adjustments)

    state_tax = round(agi * profile["state_rate"] / 10000)

    # ── Deductions ───────────────────────────────────────────────────────────
    standard = t["standard_deduction"][status]
    salt_cap = max(t["salt_floor"], t["salt_cap"] - round(max(0, agi - t["salt_phase_start"]) * 0.30))
    salt_paid = state_tax + g("property_tax")
    medical_deductible = max(0, g("medical") - round(agi * t["medical_floor_rate"]))
    itemized_parts = [
        {"label": "Mortgage interest", "amount": g("mortgage_interest")},
        {"label": "State & local taxes (capped)", "amount": min(salt_paid, salt_cap)},
        {"label": "Charitable donations", "amount": g("charity")},
        {"label": "Medical above 7.5% of AGI", "amount": medical_deductible},
    ]
    itemized = sum(p["amount"] for p in itemized_parts)
    deduction = max(standard, itemized)
    deductions = {
        "standard": standard, "itemized": itemized, "used": deduction,
        "method": "itemized" if itemized > standard else "standard",
        "parts": itemized_parts, "salt_cap": salt_cap, "salt_paid": salt_paid,
    }

    # ── Income tax ───────────────────────────────────────────────────────────
    taxable_income = max(0, agi - deduction)
    pref_taxable = min(preferential, taxable_income)
    ordinary_taxable = taxable_income - pref_taxable
    ordinary_tax, bracket_fill, marginal = _bracket_tax(ordinary_taxable, t["brackets"][status])
    pref_tax, pref_bands = _preferential_tax(ordinary_taxable, pref_taxable, t["ltcg"][status])

    investment_income = interest + div_ord + div_q + rental + max(0, net_capital)
    niit = round(min(investment_income, max(0, agi - t["niit_threshold"][status])) * t["niit_rate"])

    federal_income_tax = ordinary_tax + pref_tax + niit
    payroll_tax = ss_tax + medicare_tax + addl_medicare + se_tax
    total_tax = federal_income_tax + payroll_tax + state_tax

    gross_income = wages + se + interest + div_ord + div_q + rental + other + max(0, net_capital)
    sheltered = (g("pretax_401k") + g("roth_401k") + g("hsa") + fsa_used
                 + g("fsa_dependent_care") + g("ira_traditional") + g("ira_roth"))
    paid = g("tax_payment")
    federal_due = federal_income_tax + addl_medicare + se_tax - paid

    # Next ordinary bracket
    next_bracket = None
    for band in bracket_fill:
        if band["to"] is not None and ordinary_taxable < band["to"]:
            idx = bracket_fill.index(band)
            next_rate = t["brackets"][status][idx + 1][0]
            next_bracket = {"room": band["to"] - ordinary_taxable, "rate": next_rate}
            break

    result = {
        "year": year,
        "table_year": table_year,
        "has_income": gross_income > 0,
        "profile": profile,
        "filing_status_label": FILING_STATUSES[status],
        "summary": {
            "gross_income": gross_income,
            "tax_exempt_income": exempt,
            "agi": agi,
            "taxable_income": taxable_income,
            "federal_income_tax": federal_income_tax,
            "ordinary_tax": ordinary_tax,
            "preferential_tax": pref_tax,
            "niit": niit,
            "payroll_tax": payroll_tax,
            "social_security_tax": ss_tax,
            "medicare_tax": medicare_tax + addl_medicare,
            "self_employment_tax": se_tax,
            "state_tax": state_tax,
            "total_tax": total_tax,
            "effective_rate": total_tax / gross_income if gross_income > 0 else 0,
            "marginal_rate": marginal,
            "sheltered": sheltered,
            "take_home": gross_income - total_tax - sheltered,
            "tax_paid": paid,
            "federal_balance_due": federal_due,
        },
        "income_sources": [
            {"key": k, "label": TREATMENT_LABELS[k], "amount": v}
            for k, v in [
                ("wages", wages), ("self_employment", se), ("interest", interest),
                ("dividend_ordinary", div_ord), ("dividend_qualified", div_q),
                ("capital_gain_short", st_taxable), ("capital_gain_long", lt_taxable),
                ("rental", rental), ("other_income", other),
            ] if v > 0
        ],
        # Gross income → taxable income, step by step
        "waterfall": [
            {"label": "Gross income", "amount": gross_income, "kind": "total"},
            {"label": "Pre-tax payroll (401(k), HSA, FSA)", "amount": -(wages - taxable_wages), "kind": "minus"},
            {"label": "Capital loss deduction", "amount": -loss_deduction, "kind": "minus"},
            {"label": "Adjustments (IRA, student loan, SE tax)", "amount": -min(adjustments, ordinary_income + preferential), "kind": "minus"},
            {"label": "Adjusted gross income", "amount": agi, "kind": "total"},
            {"label": ("Itemized" if itemized > standard else "Standard") + " deduction", "amount": -min(deduction, agi), "kind": "minus"},
            {"label": "Taxable income", "amount": taxable_income, "kind": "total"},
        ],
        # Where each gross dollar goes
        "allocation": [
            {"key": "federal", "label": "Federal income tax", "amount": federal_income_tax},
            {"key": "payroll", "label": "Social Security & Medicare", "amount": payroll_tax},
            {"key": "state", "label": "State income tax", "amount": state_tax},
            {"key": "sheltered", "label": "Tax-advantaged savings", "amount": sheltered},
            {"key": "take_home", "label": "Left to spend or save", "amount": max(0, gross_income - total_tax - sheltered)},
        ],
        "brackets": bracket_fill,
        "preferential_bands": pref_bands,
        "next_bracket": next_bracket,
        "limits": limits,
        "capital": capital,
        "deductions": deductions,
        "assumptions": assumptions,
    }
    result["insights"] = build_insights(result, totals, t)
    return result


def _usd(cents: int) -> str:
    return f"${abs(cents) / D:,.0f}"


def build_insights(r: dict, totals: dict, t: dict) -> list[dict]:
    """Analysis: turn the estimate into plain-language findings, most valuable first."""
    s, profile = r["summary"], r["profile"]
    out: list[dict] = []
    if not r["has_income"]:
        return out
    combined = s["marginal_rate"] + profile["state_rate"] / 10000
    limits = {l["key"]: l for l in r["limits"]}

    def add(kind, title, detail, value=0):
        out.append({"kind": kind, "title": title, "detail": detail, "value": value})

    for l in r["limits"]:
        if l["over"] > 0:
            add("warning", f"{l['label']} is over the limit by {_usd(l['over'])}",
                f"You entered {_usd(l['used'])} against a {_usd(l['limit'])} limit. The excess is not deductible and may be penalized.")

    wages = totals.get("wages", 0)
    k = limits["k401"]
    if wages > 0 and k["remaining"] > 0 and combined > 0:
        room = min(k["remaining"], max(0, wages - k["used"]))
        saving = round(room * combined)
        if saving > 0:
            lead = "No 401(k) contributions entered" if k["used"] == 0 else f"{_usd(k['remaining'])} of 401(k) room unused"
            add("opportunity", f"{lead} — up to {_usd(saving)} less tax",
                f"Putting {_usd(room)} more into a traditional 401(k) would cut this year's income tax by about {_usd(saving)} at your {combined:.0%} marginal rate.",
                saving)

    h = limits["hsa"]
    if profile["hsa_coverage"] != "none" and h["remaining"] > 0 and combined > 0:
        saving = round(h["remaining"] * (combined + (0.0765 if wages > 0 else 0)))
        lead = "No HSA contributions entered" if h["used"] == 0 else f"{_usd(h['remaining'])} of HSA room unused"
        add("opportunity", f"{lead} — up to {_usd(saving)} less tax",
            f"If you have an HSA-eligible health plan, {_usd(h['remaining'])} more would save about {_usd(saving)} in income and payroll tax. Set HSA coverage to “none” in the tax profile if you aren't eligible.",
            saving)

    if totals.get("hsa", 0) > 0 and totals.get("fsa_health", 0) > 0:
        add("warning", "HSA and a general health FSA in the same year",
            "A general-purpose health FSA normally makes you ineligible to contribute to an HSA. A limited-purpose FSA (dental and vision) can be paired with an HSA.")

    if profile["hsa_coverage"] == "none" and totals.get("hsa", 0) > 0:
        add("warning", "HSA contributions without HSA-eligible coverage",
            "The tax profile says you have no HSA-eligible health plan, so these contributions are not deducted here.")

    f = limits["fsa"]
    if f["used"] == 0 and limits["dcfsa"]["used"] == 0 and wages > 0 and combined > 0:
        add("info", "No FSA elections entered",
            f"A health FSA allows up to {_usd(f['limit'])} pre-tax (worth about {_usd(round(f['limit'] * (combined + 0.0765)))}), but unspent money is mostly forfeited — only elect what you expect to spend.")

    d = r["deductions"]
    if d["method"] == "standard":
        gap = d["standard"] - d["itemized"]
        if d["itemized"] > 0:
            add("info", f"Standard deduction wins by {_usd(gap)}",
                f"Your itemized deductions total {_usd(d['itemized'])} against a {_usd(d['standard'])} standard deduction. Mortgage interest, donations and state taxes change nothing until they pass that gap.")
        else:
            add("info", f"Using the {_usd(d['standard'])} standard deduction",
                "No itemizable expenses are tagged. Tag mortgage interest, property tax, donations or medical costs on your expenses to see whether itemizing would beat it.")
    else:
        extra = d["itemized"] - d["standard"]
        add("opportunity", f"Itemizing beats the standard deduction by {_usd(extra)}",
            f"Itemized deductions of {_usd(d['itemized'])} save about {_usd(round(extra * s['marginal_rate']))} more than the standard deduction.",
            round(extra * s["marginal_rate"]))
    if d["salt_paid"] > d["salt_cap"]:
        add("info", f"{_usd(d['salt_paid'] - d['salt_cap'])} of state and local tax is over the SALT cap",
            f"Only {_usd(d['salt_cap'])} of state income and property tax is deductible.")

    c = r["capital"]
    if c["loss_deduction"] > 0:
        detail = f"Net capital losses offset {_usd(c['loss_deduction'])} of ordinary income this year, saving about {_usd(round(c['loss_deduction'] * combined))}."
        if c["carryover_out"] > 0:
            detail += f" The remaining {_usd(c['carryover_out'])} carries forward to future years."
        add("opportunity", f"Capital loss deduction: {_usd(c['loss_deduction'])}", detail, round(c["loss_deduction"] * combined))
    elif c["carryover_out"] == 0 and c["net"] > 0 and (c["short_term"] < 0 or c["long_term"] < 0 or c["carryover_in"] > 0):
        add("info", "Losses offset part of your gains",
            f"Realized losses and carryovers reduced your taxable gains to {_usd(c['net'])}.")
    if c["taxable_short"] > 0:
        add("info", f"{_usd(c['taxable_short'])} of short-term gains taxed at ordinary rates",
            f"Holding an investment over a year before selling moves the gain to the 0 / 15 / 20% long-term rates instead of your {s['marginal_rate']:.0%} bracket.")
    zero_band = r["preferential_bands"][0]["amount"]
    if zero_band > 0:
        add("opportunity", f"{_usd(zero_band)} of long-term gains and qualified dividends taxed at 0%",
            "This income falls inside the 0% long-term capital gains band.")

    nb = r["next_bracket"]
    if nb and s["taxable_income"] > 0:
        add("info", f"{_usd(nb['room'])} of room before the {nb['rate']:.0%} bracket",
            f"Each extra dollar of ordinary income is taxed at {s['marginal_rate']:.0%} federally until taxable income rises another {_usd(nb['room'])}.")

    if s["niit"] > 0:
        add("info", f"Net investment income tax: {_usd(s['niit'])}",
            "Investment income above the income threshold carries an extra 3.8% tax, included in federal income tax here.")

    due = s["federal_balance_due"]
    if s["tax_paid"] == 0 and due > 0:
        add("info", "No tax payments entered",
            f"No withholding or estimated payments are tagged, so the full {_usd(due)} federal bill shows as still owed. Tag withholding as “Federal tax withheld” to see what's left at filing.")
    elif due > 0:
        add("warning", f"About {_usd(due)} federal tax still owed at filing",
            f"Withholding and estimated payments of {_usd(s['tax_paid'])} fall short of the estimated federal bill.")
    elif due < 0:
        add("info", f"About {_usd(due)} federal refund expected",
            f"Withholding and estimated payments of {_usd(s['tax_paid'])} exceed the estimated federal bill.")

    order = {"warning": 0, "opportunity": 1, "info": 2}
    out.sort(key=lambda i: (order[i["kind"]], -i["value"]))
    return out


def estimate_taxes(rules, changes, assets, loans, profile, year, stock_prices=None) -> dict:
    """Collect tax items for the year and compute the estimate."""
    items, item_assumptions = collect_tax_items(rules, changes, assets, loans, year, stock_prices)
    result = compute_tax(items, profile, year)
    result["assumptions"] = result["assumptions"] + item_assumptions
    result["items"] = items
    result["has_inputs"] = bool(items)
    return result
