# Knowledge base

What you need to understand about the subject itself to work on this project, explained from zero. For setup and use, see [../manuals/](../manuals/installation.md). For what was decided and why, see [../design/DECISIONS.md](../design/DECISIONS.md).

These pages explain how the app treats money. They are not financial or tax advice.

## Reading order

**Start here**

1. [planning-and-reconciliation.md](planning-and-reconciliation.md): the core idea of the app. Plan from scheduled events, treat recorded balances as the truth, and watch the gap. Net worth, recurring rules, the forecast, what-if, transfers, divergence, check-ins, money as whole cents. Everyone should read this.

**Foundations**

2. [us-income-tax.md](us-income-tax.md): how the Taxes page gets from gross pay to a tax estimate. Filing status, deductions, brackets, payroll tax, pre-tax accounts, capital gains, with one worked example. For anyone touching `engine/tax*.py` or the Taxes page.
3. [equity-compensation.md](equity-compensation.md): RSU vesting and withholding, ESPP discounts and lookbacks, grant notices, and how Then vs. Now values a decision. For anyone touching Plan's RSU and ESPP forms, the forecast or Then vs. Now.
4. [loans-and-amortization.md](loans-and-amortization.md): principal, APR, the level-payment formula, amortization schedules, payoff, extra payments, and which interest lowers tax. For anyone touching liabilities, the forecast or loan interest in tax.

**Specialised topics**

5. [file-import-and-matching.md](file-import-and-matching.md): what bank, card, OFX, receipt and pay stub files look like, sign conventions, duplicates, transfers, categorization and suggested rules. For anyone touching `importer/`.
6. [small-local-models.md](small-local-models.md): what a small local language model can and can't be trusted with, and how the app keeps it honest (schemas, grounding, sums, retries, read-only lookups), where it runs and what it costs. For anyone touching AI features.
7. [private-network-access.md](private-network-access.md): why an app without sign-in sits behind Tailscale, how Serve, identity headers, HTTPS and installable web apps fit together, and how the server is locked down. For whoever deploys or changes access.

Each page ends with **Open questions**. Several of them describe possible code bugs found on 2026-11-24 while writing these pages. They are not yet confirmed or fixed.

## Glossary

| Term | Meaning |
|---|---|
| AGI (adjusted gross income) | Income after pre-tax savings and a few adjustments; many tax rules use it as the yardstick |
| Amortization | Paying a loan off with level payments, so the interest share falls each month |
| APR | A loan's yearly interest rate. The monthly rate is APR ÷ 12 |
| Basis (cost basis) | What you paid for an investment; the gain is the sale price minus the basis |
| Basis points (bps) | Hundredths of a percent. 500 bps = 5 %. The app stores rates this way |
| Cliff | The first RSU vest date, before which nothing vests |
| Constrained decoding | Forcing a model's output to fit a JSON schema, so it is always well formed |
| Divergence | The gap between what the plan predicted and what the recorded balances say |
| ESPP | Employee stock purchase plan: buying company shares at a discount from payroll savings |
| FITID | The unique id a bank gives each transaction in an OFX file; used to catch duplicates |
| Grounding check | Accepting a model's value only if it appears in the source document |
| Home runner | `home_runner.py`: a program on a home PC that collects the server's AI work and answers it with a local model |
| Liability | Something you owe: a loan, a card balance |
| Lookback | ESPP feature: the discount applies to the lower of the offering-start and purchase-day prices |
| Marginal rate | The tax rate on your next dollar of income |
| Minor units | The smallest unit of a currency (cents). All money in the app is an integer count of them |
| Net worth | Cash + assets − liabilities |
| OFX / QFX / QBO | A standard bank export format that carries signed amounts and transaction ids |
| Ollama | A program that runs language models on your own computer |
| Recurring rule | A Plan entry that repeats: an amount, a frequency, a start and an optional end |
| RSU | Restricted stock unit: a promise of a company share that turns into a real share when it vests |
| Sell-to-cover | Selling some vested shares to pay the tax withheld on the vest |
| Snapshot (recorded balance) | A value for one account on one date; the truth on that date. Later imported transactions move the balance from there |
| Reconcile adjustment | One entry that logs the gap between a recorded balance and the previous one plus the transactions since |
| Stale | A balance not updated within the limit (35 days by default) |
| Tailnet | Your private Tailscale network: the devices signed in to your Tailscale account |
| Tailscale Serve / Funnel | Serve publishes a local port to your tailnet only, over HTTPS. Funnel publishes it to the internet; never used here |
| Tax treatment | A tag on an income or expense saying how it is taxed (wages, 401(k), HSA, investment sale…) |
| Transfer | Money moved between your own accounts; not income or spending |
| Vest | The date a promised share becomes yours, and taxable |
| Withholding | Tax your employer pays on your behalf from your pay or vested shares; a prepayment, not the final bill |
