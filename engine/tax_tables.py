"""US federal tax parameters and the tax-treatment registry.

All money values are in cents. Parameters are estimates for planning, not filing.
Sources: IRS Rev. Proc. 2025-32 (brackets, standard deduction, capital gains
thresholds, health FSA), IRS Notice 2025-67 (401(k)/IRA limits),
Rev. Proc. 2025-19 (HSA limits), SSA 2026 wage base.
"""

D = 100  # cents per dollar

# ── Treatments ────────────────────────────────────────────────────────────────
# kind: which side of the ledger the treatment applies to.
# transfer: money moved into the user's own tax-advantaged account, so it is
#           not a net-worth loss and the projection engine skips it.

INCOME_TREATMENTS = [
    {"key": "wages", "label": "Wages / salary (W-2)", "hint": "Income tax + Social Security + Medicare"},
    {"key": "self_employment", "label": "Self-employment / 1099", "hint": "Income tax + 15.3% self-employment tax"},
    {"key": "interest", "label": "Interest", "hint": "Ordinary income"},
    {"key": "dividend_ordinary", "label": "Dividends – ordinary", "hint": "Ordinary income"},
    {"key": "dividend_qualified", "label": "Dividends – qualified", "hint": "0 / 15 / 20% rates"},
    {"key": "capital_gain_short", "label": "Investment sale – short-term gain", "hint": "Held 1 year or less; ordinary rates"},
    {"key": "capital_gain_long", "label": "Investment sale – long-term gain", "hint": "Held over 1 year; 0 / 15 / 20% rates"},
    {"key": "rental", "label": "Rental income (net)", "hint": "Ordinary income"},
    {"key": "other_income", "label": "Other taxable income", "hint": "Ordinary income, no payroll tax"},
    {"key": "tax_exempt", "label": "Not taxable (gift, refund, transfer)", "hint": "Left out of the tax estimate"},
]

EXPENSE_TREATMENTS = [
    {"key": "none", "label": "Not deductible (personal spending)", "hint": "No tax effect"},
    {"key": "pretax_401k", "label": "401(k) – traditional (pre-tax)", "hint": "Lowers taxable wages", "transfer": True},
    {"key": "roth_401k", "label": "401(k) – Roth", "hint": "No deduction; shares the 401(k) limit", "transfer": True},
    {"key": "hsa", "label": "HSA contribution", "hint": "Deductible; skips payroll tax via payroll", "transfer": True},
    {"key": "fsa_health", "label": "Health FSA", "hint": "Pre-tax; use it or lose it"},
    {"key": "fsa_limited", "label": "Limited-purpose FSA (dental / vision)", "hint": "Pre-tax; can pair with an HSA"},
    {"key": "fsa_dependent_care", "label": "Dependent-care FSA", "hint": "Pre-tax"},
    {"key": "ira_traditional", "label": "IRA – traditional", "hint": "Deductible (income limits not modelled)", "transfer": True},
    {"key": "ira_roth", "label": "IRA – Roth", "hint": "No deduction; shares the IRA limit", "transfer": True},
    {"key": "mortgage_interest", "label": "Mortgage interest", "hint": "Itemized deduction"},
    {"key": "property_tax", "label": "Property / other state & local tax", "hint": "Itemized, under the SALT cap"},
    {"key": "charity", "label": "Charitable donation", "hint": "Itemized deduction"},
    {"key": "medical", "label": "Medical expense (out of pocket)", "hint": "Itemized above 7.5% of AGI"},
    {"key": "student_loan_interest", "label": "Student loan interest", "hint": "Deductible up to $2,500"},
    {"key": "tax_payment", "label": "Federal tax withheld / estimated payment", "hint": "Counts as tax already paid"},
]

TREATMENT_LABELS = {t["key"]: t["label"] for t in INCOME_TREATMENTS + EXPENSE_TREATMENTS}
INCOME_KEYS = {t["key"] for t in INCOME_TREATMENTS}
EXPENSE_KEYS = {t["key"] for t in EXPENSE_TREATMENTS}
TRANSFER_KEYS = {t["key"] for t in EXPENSE_TREATMENTS if t.get("transfer")}

FILING_STATUSES = {
    "single": "Single",
    "mfj": "Married filing jointly",
    "hoh": "Head of household",
}

# ── Yearly parameters ─────────────────────────────────────────────────────────
# brackets: list of (rate, upper bound of taxable income in dollars or None)

TAX_YEARS = {
    2026: {
        "standard_deduction": {"single": 16_100 * D, "mfj": 32_200 * D, "hoh": 24_150 * D},
        "brackets": {
            "single": [(0.10, 12_400), (0.12, 50_400), (0.22, 105_700), (0.24, 201_775),
                       (0.32, 256_225), (0.35, 640_600), (0.37, None)],
            "mfj": [(0.10, 24_800), (0.12, 100_800), (0.22, 211_400), (0.24, 403_550),
                    (0.32, 512_450), (0.35, 768_700), (0.37, None)],
            "hoh": [(0.10, 17_700), (0.12, 67_450), (0.22, 105_700), (0.24, 201_750),
                    (0.32, 256_200), (0.35, 640_600), (0.37, None)],
        },
        # long-term gains / qualified dividends: (top of 0% band, top of 15% band)
        "ltcg": {"single": (49_450, 545_500), "mfj": (98_900, 613_700), "hoh": (66_200, 579_600)},
        "ss_wage_base": 184_500 * D,
        "ss_rate": 0.062,
        "medicare_rate": 0.0145,
        "addl_medicare_rate": 0.009,
        "addl_medicare_threshold": {"single": 200_000 * D, "mfj": 250_000 * D, "hoh": 200_000 * D},
        "niit_rate": 0.038,
        "niit_threshold": {"single": 200_000 * D, "mfj": 250_000 * D, "hoh": 200_000 * D},
        "k401_limit": 24_500 * D,
        "k401_catchup_50": 8_000 * D,
        "k401_catchup_60_63": 11_250 * D,
        "ira_limit": 7_500 * D,
        "ira_catchup_50": 1_100 * D,
        "hsa_limit": {"self": 4_400 * D, "family": 8_750 * D, "none": 0},
        "hsa_catchup_55": 1_000 * D,
        "fsa_health_limit": 3_400 * D,
        "fsa_dependent_care_limit": 7_500 * D,
        "salt_cap": 40_400 * D,
        "salt_phase_start": 505_000 * D,
        "salt_floor": 10_000 * D,
        "capital_loss_limit": 3_000 * D,
        "student_loan_interest_limit": 2_500 * D,
        "medical_floor_rate": 0.075,
    },
}


def tables_for(year: int) -> tuple[dict, int]:
    """Return (parameters, year the parameters were written for)."""
    if year in TAX_YEARS:
        return TAX_YEARS[year], year
    nearest = min(TAX_YEARS, key=lambda y: abs(y - year))
    return TAX_YEARS[nearest], nearest
