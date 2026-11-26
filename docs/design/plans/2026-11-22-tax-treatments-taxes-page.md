# Tax treatments and a Taxes page

**Status:** done, PR #1 (merged 2026-11-23).

## Goal

Tag each income and expense with how it is taxed, and show an estimated US federal tax for a year. The owner wanted the charts first, then the analysis.

## Approach

- An optional `tax_treatment` on recurring rules and one-off entries (wages, 401(k), HSA, FSA, limited FSA, investment sale, charity and others).
- `engine/tax.py` computes the estimate; `engine/tax_tables.py` holds the 2026 brackets and limits.
- Capital losses net against gains, and up to $3,000 a year against other income; the rest carries forward.
- Asset sales with a cost basis, RSU vests and loan interest are found automatically.
- In the projection, 401(k), HSA and IRA contributions are transfers between your own accounts, not spending.
- The Taxes page lists every default it used, such as "untagged income counted as W-2 wages".

## Left out

Credits, AMT, income phase-outs, state-specific rules (a flat state rate is used instead), and filing. Amounts are taken as gross. Other years reuse the 2026 tables. The 2026 SALT cap was not checked against an IRS source.

Background: [docs/knowledge/us-income-tax.md](../../knowledge/us-income-tax.md).
