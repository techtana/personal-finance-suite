# Sample Data — Personal Finance Suite

Sample JSON files representing the Google Drive storage layout for a fictional user.
These mirror the wireframe v3 UI mockups exactly.

## File Layout

```
Personal Finance Suite/     ← Drive folder created on first run
├── meta.json
├── settings.json
├── accounts.json
├── transactions.json
├── blanket-expenses.json
├── equity.json
├── snapshots.json
└── (settings.json already listed above)
```

## Units & Conventions

| Thing | Convention | Example |
|---|---|---|
| Money | Integer cents (minor units) | `$12,400 → 1240000` |
| Shares | Integer milliShares (×1000) | `25.0 shares → 25000` |
| Interest rate | Integer basis points × 10 | `6.875% → 68750` |
| Percent (withholding, discount) | Integer percent × 100 | `22% → 2200` |
| Dates | ISO 8601 string `YYYY-MM-DD` | `"2026-05-09"` |
| IDs | Readable slug for sample data | `"acc_chase_checking_001"` (prod: nanoid 21-char) |

## Sample User Profile

- **Gross salary:** ~$195k/yr · biweekly net ~$7,500/paycheck
- **401k:** $1,154/paycheck pre-tax (employee) + 4% employer match
- **GOOG RSU grants:** 3 active (2023 / 2024 / 2025 annual), 200 shares each
- **ESPP:** 10% salary, 15% discount, lookback, 6-month periods
- **Home:** bought Mar 2022 for $430k, 30yr fixed 6.875%
- **Net worth May 2026:** ~$482k

## Key Relationships

```
acc_chase_checking_001
  ← rec_salary_001             (income lands here)
  ← rec_mortgage_001           (payment leaves here)
  ← txn_annual_bonus_2026      (one-time income)
  ← blk_misc_spending_001      (blanket expense)

acc_fidelity_brokerage_001
  ← rsu_goog_2023_annual       (vest events deposit here)
  ← espp_goog_2025             (ESPP purchases deposit here)
  ← snap_fidelity_brok_may26   (reconciliation: −$11,600)
  ← txn_adj_fidelity_may26     (adjustment transaction from reconcile)

acc_home_001
  → linkedLoanId: loan_chase_mortgage_001
loan_chase_mortgage_001
  → linkedAccountId: acc_home_001
```
