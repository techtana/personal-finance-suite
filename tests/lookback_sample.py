"""Sample data for the Then vs. Now page, shared by the tests and the demo loader.

Money is in cents, shares in milli-shares. "Today" for this data set is 2026-11-22.
"""

TODAY = "2026-11-22"

PRICES = [  # GOOG, dollars
    ("2023-01-15", 89), ("2024-01-15", 140.5), ("2024-04-15", 156), ("2024-07-15", 182),
    ("2024-10-15", 165), ("2024-12-01", 162), ("2025-01-15", 192.5), ("2025-04-15", 158),
    ("2025-05-31", 175), ("2025-07-15", 183), ("2025-10-15", 196), ("2025-11-30", 192),
    ("2026-01-15", 205), ("2026-04-15", 214), ("2026-05-31", 226.2), ("2026-07-15", 238),
    ("2026-10-15", 262), (TODAY, 248),
]


def prices():
    return [{"ticker": "GOOG", "date": d, "price": round(p * 100)} for d, p in PRICES]


def _vests(cliff_year):
    """50 sh at the one-year cliff, then 12.5 sh a quarter for three years."""
    out, y, m = [{"date": f"{cliff_year}-01-15", "shares": 50000}], cliff_year, 1
    for _ in range(12):
        m += 3
        if m > 12:
            m, y = m - 12, y + 1
        out.append({"date": f"{y}-{m:02d}-15", "shares": 12500})
    return out


def rules():
    def rsu(name, grant_date, price):
        return {
            "name": name, "rule_type": "rsu", "start_date": grant_date, "schedule": _vests(int(grant_date[:4]) + 1),
            "config": {"ticker": "GOOG", "total_shares": 200000, "grant_date": grant_date,
                       "price_at_grant": round(price * 100), "withholding_rate": 2200},
        }
    return [
        rsu("2023 annual RSU grant", "2023-01-15", 89),
        rsu("2024 refresh RSU grant", "2024-01-15", 140.5),
        rsu("2025 annual RSU grant", "2025-01-15", 192.5),
        {
            "name": "Employer ESPP", "rule_type": "espp", "start_date": "2024-12-01", "end_date": "2026-11-30",
            "config": {"ticker": "GOOG", "offering_start_date": "2024-12-01", "offering_end_date": "2026-11-30",
                       "contribution_mode": "fixed", "contribution_value": 25000, "discount_rate": 1500,
                       "has_lookback": True},
            "schedule": [
                {"start_date": "2024-12-01", "end_date": "2025-05-31", "estimated_purchase_amount": 402500},
                {"start_date": "2025-06-01", "end_date": "2025-11-30", "estimated_purchase_amount": 441600},
                {"start_date": "2025-12-01", "end_date": "2026-05-31", "estimated_purchase_amount": 520260},
                {"start_date": "2026-06-01", "end_date": "2026-11-30", "estimated_purchase_amount": 520260},
            ],
        },
    ]


def loans():
    return [{
        "name": "Home mortgage", "type": "mortgage", "institution": "Chase", "original_balance": 31600000,
        "current_balance": 28940000, "interest_rate": 625, "monthly_payment": 194500,
        "start_date": "2023-08-18", "payoff_date": "2053-08-18", "last_updated_date": TODAY,
    }]


def assets():
    return [
        {"name": "Home", "category": "property", "current_value": 44600000, "cost_basis": 39500000,
         "decided_date": "2023-07-02", "acquired_date": "2023-08-18", "last_updated_date": TODAY},
        {"name": "Car", "category": "vehicle", "current_value": 3150000, "cost_basis": 4820000,
         "decided_date": "2024-06-10", "acquired_date": "2024-06-22", "last_updated_date": TODAY},
    ]


def accounts():
    return [
        {"name": "Checking", "type": "checking", "institution": "Chase", "current_balance": 1240000, "last_updated_date": TODAY},
        {"name": "Brokerage", "type": "brokerage", "institution": "Fidelity", "current_balance": 15300000, "last_updated_date": TODAY},
        {"name": "401k", "type": "retirement_401k", "institution": "Fidelity", "current_balance": 20300000, "last_updated_date": TODAY},
    ]


# Quarter-end balances in dollars: (date, checking, brokerage, 401k)
ACCOUNT_HISTORY = [
    ("2022-12-31", 9000, 118000, 84000), ("2023-03-31", 9500, 122000, 88000), ("2023-06-30", 10500, 128000, 93000),
    ("2023-08-18", 9500, 50000, 95000), ("2023-09-30", 9000, 52000, 97000), ("2023-12-31", 10000, 60000, 103000), ("2024-03-31", 11000, 72000, 110000),
    ("2024-06-22", 8000, 38000, 117000), ("2024-06-30", 8000, 40000, 118000), ("2024-09-30", 9500, 52000, 125000), ("2024-12-31", 11000, 66000, 133000),
    ("2025-03-31", 10500, 70000, 138000), ("2025-06-30", 11500, 84000, 148000), ("2025-09-30", 12000, 98000, 160000),
    ("2025-12-31", 12500, 110000, 170000), ("2026-03-31", 12000, 124000, 182000), ("2026-06-30", 12800, 136000, 190000),
    ("2026-09-30", 12500, 148000, 198000),
]

ASSET_HISTORY = {  # asset name -> [(date, dollars)]
    "Home": [("2024-06-30", 410000), ("2025-06-30", 428000), ("2026-01-15", 442000), (TODAY, 446000)],
    "Car": [("2025-06-30", 39000), (TODAY, 31500)],
}

LOAN_HISTORY = {  # loan name -> [(date, dollars)]
    "Home mortgage": [("2024-06-30", 311000), ("2025-06-30", 304000), ("2026-06-30", 293000), (TODAY, 289400)],
}
