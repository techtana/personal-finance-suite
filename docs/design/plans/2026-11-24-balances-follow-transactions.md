# Account balances follow imported transactions

**Status:** done, PR #13 (merged 2026-11-24).

## Goal

Make an imported transaction move its account's balance, and stop imported history from being counted on top of the plan. Before, Balances read only recorded values, so importing did nothing to a balance. Meanwhile the "net worth vs. plan" insight and Taxes counted imported history in addition to the plan.

## Approach

- One rule for every balance, in `engine/ledger.py`: balance on a date = the latest recorded balance on or before it, plus the account's transactions dated after it. A recorded balance is the end-of-day truth on its date. Balances, Overview, the forecast's starting point, net-worth history and Then vs. Now all use it.
- Plan and actual are kept apart. Only imported transactions and reconcile adjustments move a balance. One-off entries typed on Plan are plan, like rules. The forecast, the divergence insight and Taxes use only the plan, so nothing is counted twice. Imported deposits count toward taxes only once you give them a tax treatment.
- **Balances**: each account shows how its value was reached. A **Transactions** view lists records and transactions with a running balance and the gap at each record. When a new recorded balance isn't explained by the transactions, **Log the difference** adds one adjustment entry.
- Credit card accounts hold the amount owed and are subtracted from net worth.
- **Import**: transfers and card payments are now imported (category `transfer`, ticked by default) instead of skipped, so balances add up without counting as spending. The review checks a statement's closing balance against the account's earlier balance plus the transactions in between.
- **Insights**: a plan vs. actual table by category and month, and a spending-vs-plan insight for months the imports fully cover.

## Behaviour changes on existing data

- Imported transactions dated after an account's latest recorded balance now move that balance.
- Recording a new balance keeps the value typed in with the account as an earlier record.
- Imported deposits without a tax treatment are left out of Taxes, with an assumption line.
