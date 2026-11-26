# Planning from scheduled events, and reconciling the plan with real balances

## 1. What this is and why the project needs it

Most money apps copy every transaction from your bank and sort it into budget categories. This project does something smaller. You tell it the few things that move your money on a schedule (a paycheck, the rent, a loan payment, a stock vest). You also tell it, now and then, what your accounts are really worth. From those two inputs it draws a line of your net worth into the future, and it warns you when reality and the plan drift apart. This note explains the ideas behind that design: net worth, recorded balances, recurring rules, the projection, what-if scenarios, and the checks that keep the plan honest. It also records two bugs in the date code, confirmed on 2026-11-24.

## 2. The ideas, built up from zero

### 2.1 Start with a checkbook

Picture a paper checkbook register. Each line says: date, what, amount, new balance. Every few weeks the bank sends a statement, and you compare its closing balance with the last number in your register. If they differ, you hunt for the missing line. The register is your plan. The bank statement is the truth. Everything in this project is a version of that habit.

A budgeting app automates the register. It pulls every line from the bank, so the register is always complete, and your job is to label lines. That works, but it is a lot of lines. Most months, a household has only a few dozen events that matter for the long view: a handful of paychecks, a mortgage, insurance, subscriptions, a tax payment. The rest is noise that averages out. This project plans from those scheduled events and ignores the noise. The noise does not vanish: it shows up as the gap between the plan and the next real balance, and the app reports that gap instead of hiding it.

The analogy stops working in one place. A checkbook register is exact, because you write down each check. A plan built from schedules is an estimate. It will always be a little wrong, and the design accepts that on purpose.

### 2.2 Net worth

Net worth is what you own minus what you owe. In symbols: net worth = cash + assets - liabilities.

- Cash is money in checking, savings and similar accounts, in dollars.
- Assets are things with a value: a brokerage account, a house, shares of company stock.
- Liabilities are debts: a mortgage, a car loan, a credit card balance.

Example. Checking holds $4,000. A brokerage account holds $20,000. A car is worth $9,000. A loan balance is $6,000. Net worth = 4,000 + 20,000 + 9,000 - 6,000 = $27,000.

Net worth is a better single number than "cash on hand" because buying a car does not change it much (cash falls, asset rises), while paying interest does. The limit of the number is that it hides liquidity: $27,000 in a house you cannot sell this month is not the same as $27,000 in a savings account.

### 2.3 Recorded balances (snapshots)

A recorded balance is a number you typed in, or imported from a statement, for one account on one date. The code calls it a snapshot (the `Snapshot` table in `models.py`). The key rule of the project is that a recorded balance is the truth on its date. If the plan said your checking account should hold $4,300 on the 1st and the bank statement says $4,120, the statement wins. The plan does not get to argue.

Between two recorded balances, the account's actual transactions explain the movement. Since 2026-11-24 (PR #13) one rule in `engine/ledger.py` gives every balance the app shows:

    balance on a date = latest recorded balance on or before that date + the account's transactions dated after it

A recorded balance counts as the end-of-day balance, so transactions on the same day are already in it. Only things that actually happened move a balance: imported transactions and reconcile adjustments. Plan rules and one-off entries typed on the Plan page never do. When a new recorded balance differs from the previous one plus the transactions in between, the difference is the gap that the Balances page offers to log as one adjustment.

This is how the project avoids the main weakness of planning from schedules, which is that errors pile up. Each fresh balance resets the starting point. The plan only has to be right between check-ins, not forever.

A snapshot always holds a positive number, even for a debt. The entity type (cash, asset or liability) says whether to add or subtract it. The newest value wins: `current_value` in `api/_data.py` picks the entity's own stored value or its latest snapshot, whichever carries the later date.

### 2.4 Recurring rules, and how dates repeat

A rule says "this amount, this often, starting on this date, optionally ending on this date." The project supports six frequencies: daily, weekly, biweekly, monthly, quarterly and annually. In `engine/recurrence.py` they become a repeat interval. Weekly is every 7 days. Biweekly is every 14 days. Monthly is every month. Quarterly is every 3 months. Annually is every year. The Plan page offers all of these except daily; the schema validator in `schemas.py` accepts daily too.

Two kinds of repeat behave differently. Day-based repeats (weekly, biweekly, daily) count a fixed number of days, so they drift against the calendar: a biweekly paycheck lands on 26 dates a year, and twice a year a month holds three of them. Month-based repeats (monthly, quarterly, annually) keep the day number, so they stay on "the 15th" but the gap between dates varies from 28 to 31 days.

What should happen when the day number does not exist? A rule that starts on January 31 has no February 31. Calendar programs usually either clamp (use February 28) or skip (no February event). The design document says clamp (`docs/SRD.md` section 9.4). The code skips. Section 6 shows the run.

### 2.5 The projection

The projection answers: "If nothing surprising happens, what will my net worth be at the end of each month?" The method has four steps.

1. Take today's recorded net worth. This is the starting point (`starting_net_worth`).
2. List every dated event inside the window: each date a rule fires, each one-off change you logged, each loan payment, each RSU vest or ESPP purchase.
3. Add up the events by calendar month. Income events add, expense events subtract. The sum for a month is its net flow.
4. Walk forward month by month: net worth at the end of a month = net worth at the end of the previous month + that month's net flow.

Working example. Starting net worth is $10,000. Salary is $5,000 a month in, rent is $2,000 a month out. Net flow is +$3,000 each month. End of month 1: 10,000 + 3,000 = $13,000. Month 2: $16,000. Month 3: $19,000. The code is `project_v2` in `engine/projection.py`; the numbers above are 1,000,000 cents starting and 300,000 cents a month, and the run in section 6 returns exactly that.

Notice what the method leaves out. It does not grow your investments, it does not raise prices with inflation, and it does not split a loan payment into principal and interest. A loan payment is an expense of the full payment amount, and the loan balance is not reduced in the projection. That sounds wrong, and it is worth thinking through. Paying $1,500 on a mortgage lowers your cash by $1,500 and lowers the debt by the principal part, perhaps $500. Net worth falls only by the interest part, perhaps $1,000. The projection charges the full $1,500, so it understates net worth for loans. The project accepts that because the correct split needs an amortization schedule per loan, and the next recorded balance corrects the error. `engine/amortization.py` exists, and the tax estimate uses it for loan interest, but the projection does not.

### 2.6 What-if: leave an item out

A scenario is the same projection with some items switched off. The Forecast page lists every rule, change and loan with a tick box. Unticking one passes its id in `disabled_ids`. The API then runs the projection twice, once with the items left out and once with nothing left out (the `baseline`), so the page can print the difference at the end of the window. This is the cheapest useful what-if: "What if I did not buy the car?" "What if the bonus never comes?" It cannot answer "what if I earned 10% more", because that needs a changed amount, not a removed item.

### 2.7 Transfers between your own accounts are not spending

When you move $500 from checking into a 401(k), you are not poorer. Cash fell by $500, and the retirement account rose by $500. If the projection counted the $500 as an expense, net worth would fall each month for no reason. So rules and changes whose tax treatment marks them as a transfer (pre-tax 401(k), Roth 401(k), HSA, traditional IRA, Roth IRA) are skipped in the projection. The list lives in `engine/tax_tables.py` as `TRANSFER_KEYS`. The same idea applies to paying a credit card from checking: one account falls, a debt falls by the same amount, net worth is unchanged. In that case the importer marks the row as a transfer (see `file-import-and-matching.md`).

One limit: the projection does not grow the retirement account by the skipped contribution, because it never models growth. So the money simply vanishes from the picture until your next recorded balance for that account brings it back.

### 2.8 Plan versus actual, and double counting

Divergence is the difference between what the plan predicted and what the balances say. The app measures it like this: find an earlier recorded net worth (the anchor), run the projection from the day after the anchor up to today, and compare the predicted total with today's recorded net worth. The gap, in basis points of the predicted value, is the divergence. A basis point is one hundredth of one percent, so 500 basis points is 5%.

Example. Anchor net worth was $100,000 on September 30. The plan expects +$2,000 of net flow by today, so it predicts $102,000. Today's recorded net worth is $98,000. Gap = 98,000 - 102,000 = -$4,000. Divided by $102,000 that is -3.9%, or -392 basis points. With a 5% threshold this is "on track". At -6% it would raise an attention item.

Double counting is the main trap. A real paycheck can be described twice: once as a rule ("salary, monthly") and once as a logged change or an imported bank line ("Payroll, +$5,000"). If both feed the same window, the plan counts the paycheck twice. The project avoids it by keeping two worlds apart (PR #13, 2026-11-24). The plan is rules, loan payments and one-off Plan entries; the forecast, the divergence check and Taxes use only the plan. The actuals are recorded balances and imported transactions; Balances and net worth use only those. So an imported paycheck never adds to a salary rule.

### 2.9 Staleness and the monthly check-in

A recorded balance goes stale. Any balance older than a limit (35 days by default) is flagged. The check-in on the Balances page walks you through each stale account, asks for today's value, and offers an "Unchanged" button. It takes a few minutes and is the habit that keeps the whole method honest. No one wants to do it daily, so the limit sits just over a month.

### 2.10 Money as whole numbers

Every amount in the project is an integer count of the smallest currency unit (cents for dollars). $19.99 is stored as 1999. The reason is that computers store ordinary decimal numbers in binary, and many decimal fractions (0.1, 0.2) have no exact binary form. Adding them gives results like 0.30000000000000004. Over thousands of additions, tiny errors can make two totals that should match differ by a cent, and then a duplicate check or a "does it add up" check fails. Whole numbers add exactly. Percentages follow the same idea: the withholding rate and loan rates are whole numbers of basis points (2200 means 22%). The cost is conversion at the edges: the display layer divides by 100, and importers parse text into cents with the `Decimal` type rather than a float.

## 3. Rules of thumb and typical numbers

| Item | Value | Source |
|---|---|---|
| Stale balance limit | 35 days | project choice, `api/_data.py` (`DEFAULT_STALE_DAYS`) |
| Divergence threshold | 500 basis points (5%) | project choice, `api/_data.py` (`DEFAULT_DIVERGENCE_BPS`) |
| Both limits editable | Settings page, stored in `divergence_thresholds` | `models.py`, `api/_data.py:thresholds` |
| Anchor must be at least this old | 25 days | project choice, `engine/insights.py:divergence` |
| How far back an anchor is searched | 400 days | project choice, `engine/insights.py:divergence` |
| Default forecast window | today to today + 365 days | project choice, `api/projection.py` |
| Largest history returned | 120 months | project choice, `api/projection.py` |
| Net worth history limit | 20 years | project choice, `engine/lookback.py` (`MAX_HISTORY_YEARS`) |
| "Large event" alert | $1,000 or more, next 30 days | project choice, `engine/insights.py` (`LARGE_EVENT_CENTS`) |
| Months with a shortfall | attention at 3 or more, else info | project choice, `engine/insights.py` |
| Biweekly pay dates in a year | 26 | arithmetic: 365 / 14 = 26.07 |
| Weekly pay dates in a year | 52 | arithmetic |
| Monthly equivalent of weekly / biweekly | x 52/12 and x 26/12 | project choice, `templates/plan.html` (`PER_MONTH`) |

A rough check on any forecast: income minus expenses times the number of months should be close to the end-point minus the start-point. If they differ, an event is missing from a bucket, or a rule starts or ends inside the window. Source for this check: source not recorded (it is plain arithmetic).

How often to check in: the project says monthly. Source not recorded.

## 4. Common misconceptions and edge cases

- "The forecast predicts my future." It extrapolates the schedules you entered. It has no view on markets, raises or surprises.
- "Net worth should rise when I pay down a loan." In this projection it falls by the whole payment (section 2.5). The next recorded balance of the loan corrects it.
- "A logged change and a rule for the same thing are harmless." They are not: both count (section 2.8).
- "The first month is a full month." It holds only the dates from today forward. An event dated today counts, even though today's balance may already include it.
- "Daily frequency is available in the app." The schema accepts it. The Plan form does not offer it.
- "An unknown frequency raises an error." It returns no dates, silently, so the rule vanishes from the forecast. A misspelling such as "yearly" gives an empty list (checked today).
- "A rule that starts in the past keeps its original day." It does not in the current code. See section 6.
- RSU and ESPP rules carry their own date schedules; they do not use the frequency logic.
- A share price of zero (no price entered) makes an RSU vest worth $0. The Insights page warns about this.
- A snapshot dated before the entity's own last-updated date is kept in history but does not become "current".

## 5. How the project uses it

Files and functions:

- `engine/recurrence.py:expand_recurring_dates` turns one rule into dates inside a window.
- `engine/projection.py:project_v2` is the engine used by the pages (the older `project` function still exists). `fill_months=True` returns months with no events so charts have no gaps.
- `api/_data.py` loads the database into plain dicts. `load_entities` builds the cash, asset and liability list; `totals` computes net worth; `thresholds` reads the two limits.
- `api/projection.py:get_projection` serves `GET /projection` with `from`, `to`, `prices`, `disable` and `history` parameters.
- `engine/insights.py` holds the rules listed below.
- `templates/forecast.html` draws the chart and the what-if list. `templates/balances.html` holds the check-in dialog.

Insights rules (all in `engine/insights.py:build_insights`; each says what it is based on):

1. Stale balances: attention when any balance is older than the limit; a "good" note when all are fresh.
2. Divergence: attention when the gap is at or above the threshold, "good" otherwise.
3. No recurring income or expense rules while accounts exist.
4. Missing share price for a ticker used by an RSU rule.
5. Months in the next 12 whose expenses exceed income (attention if 3 or more).
6. One-off or equity events of $1,000 or more in the next 30 days (at most three shown).
7. A loan whose payoff date falls inside the next 12 months.
8. Imported files waiting for review.
9. Tax items passed in from the tax estimate.

The module states that it reports facts and gives no advice on what to do with money.

Left out, and why: growth and inflation (they need assumptions that no one can verify, and a wrong default looks like a fact); principal and interest split (needs per-loan schedules; the check-in resets the error); automatic share prices (prices are typed in, see `docs/design/plans/2026-11-22-then-vs-now.md`); tracking every transaction (the product's whole premise; see `docs/PRD.md` sections 1 and 3).

Design record: [DECISIONS](../design/DECISIONS.md), [first plan and SRD](../design/plans/2026-05-09-prd-srd-v1-flask-sqlite.md), [tax treatments and transfers](../design/plans/2026-11-22-tax-treatments-taxes-page.md), [Insights and role-based pages](../design/plans/2026-11-23-role-ui-insights-assistant-pwa.md).

## 6. What we found

All commands were run on 2026-11-24 from the repository root of this worktree.

**Finding 1: a rule on the 31st skips short months. The SRD says it should clamp.**

```
python -c "from engine.recurrence import expand_recurring_dates as e; print(e('2026-01-31',None,'monthly','2026-01-01','2026-08-31'))"
```

Output: `['2026-01-31', '2026-03-31', '2026-05-31', '2026-07-31', '2026-08-31']`. February, April and June have no event. `docs/SRD.md` section 9.4 says "clamped to last day of month for short months". The cause is that the `dateutil` repeat rule skips impossible dates. The same happens on the 29th and 30th for February, quarterly rules from January 31 (`2026-01-31`, `2026-07-31`, `2026-10-31`, `2027-01-31`) and annual rules on February 29 (only leap years, 2024 then 2028).

**Finding 2: a rule that started before the window is re-anchored to the window's first day.**

```
python -c "from engine.recurrence import expand_recurring_dates as e; print(e('2026-01-05',None,'monthly','2026-02-01','2026-03-15'))"
```

Output: `['2026-02-01', '2026-03-01']`. The rule starts on the 5th, so the dates should be February 5 and March 5. The code sets the start of the repeat to the later of the rule start and the window start, so the pattern restarts at the window edge. A biweekly rule from 2026-01-05 with a window from 2026-02-01 returns 02-01, 02-15, 03-01, 03-15 instead of 02-02, 02-16, 03-02, 03-16.

Effect in the app: the Forecast, Insights and divergence calls use today as the window start. So every monthly rule that began earlier fires on today's day number. A full run (rules on the 15th and the 1st, window from 2026-11-24):

```
python - <<'EOF'
from engine.projection import project_v2
rules=[{"id":"sal","rule_type":"income","amount":500000,"frequency":"monthly","start_date":"2026-01-15","name":"Salary"},
{"id":"rent","rule_type":"expense","amount":200000,"frequency":"monthly","start_date":"2026-01-01","name":"Rent"},
{"id":"k","rule_type":"expense","amount":50000,"frequency":"monthly","start_date":"2026-01-01","name":"401k","tax_treatment":"pretax_401k"}]
b,e=project_v2(rules,[],[],1000000,{},"2026-11-24","2027-02-28",fill_months=True)
print([(x.month,x.net_cash_flow,x.cumulative_net_worth) for x in b]); print(sorted({v.date for v in e}))
EOF
```

Output: net flow 300000 in each of four months, cumulative 1300000, 1600000, 1900000, 2200000 (so the transfer rule was skipped, as designed). The event dates are `2026-11-24`, `2026-12-24`, `2027-01-24`, `2027-02-24`: salary and rent, which belong on the 15th and the 1st, all sit on the 24th. Monthly totals stay right, but the date inside a month is wrong, so the first month also gets a full set of events that may already be in today's balance. If today is the 31st, every rule inherits the skip-short-months behavior of finding 1 (checked with window start 2026-12-31: `['2026-12-31', '2027-01-31', '2027-03-31', '2027-05-31']`). `engine/tax.py` calls the same function with the tax year as the window, so it carries the same issue.

No test covers `engine/recurrence.py` (`grep -rn expand_recurring tests` finds nothing).

**Finding 3 (fixed 2026-11-24 by PR #13): the divergence check double counted a rule and an imported change.**

```
python - <<'EOF'
from engine.insights import divergence
ents=[{"type":"cash","id":"a","name":"Chk","current":1200000,"current_date":"2026-11-24","first_date":None,"first_value":None}]
snaps={("cash","a"):[("2026-09-30",1000000),("2026-11-24",1200000)]}
rules=[{"id":"s","rule_type":"income","amount":100000,"frequency":"monthly","start_date":"2026-01-15","name":"Salary"}]
ch=[{"id":"c%d"%i,"date":d,"amount":100000,"description":"Payroll","change_type":"imported"} for i,d in enumerate(["2026-10-15","2026-11-15"])]
print(divergence(ents,snaps,rules,[],[],{},"2026-11-24")["bps"], divergence(ents,snaps,rules,ch,[],{},"2026-11-24")["bps"])
EOF
```

Output: `0 -1429`. With the rule alone the plan is exact. With the same two paychecks also logged as imported changes, the plan predicts $14,000 instead of $12,000 and reports 14.3% below plan, which is above the 5% threshold and raises an "attention" item. A user who imported bank statements and also kept a salary rule would have seen a false alarm. Rerun on `main` after PR #13 merged, the same script prints `0 0`: imported changes no longer feed the plan.

**Finding 4: the Rule model comment and the Plan form omit "daily".** `models.py` (comment on `Rule.frequency`) lists five values and the Plan form offers five; `schemas.py` and `docs/SRD.md` allow six. This is a documentation gap, not a failure.

## 7. Open questions

- Should month-end rules clamp, as the SRD says, or skip, as the code does? Clamping matches how rent and bills behave. Skipping is dangerous for a rule that starts on the 31st.
- Should a rule keep its own start date as the anchor when the window starts later? This is almost certainly the intended behavior.
- Is the whole-payment treatment of loans acceptable once a user has a large mortgage? A principal-and-interest split would need the loan rate (stored in basis points) and `engine/amortization.py`.
- Should the check-in limit and the divergence limit have different defaults per account type? No evidence either way.

## 8. Sources and further reading

- Project files: `engine/projection.py`, `engine/recurrence.py`, `engine/insights.py`, `engine/lookback.py`, `api/_data.py`, `api/projection.py`, `models.py`, `templates/forecast.html`, `templates/balances.html`.
- Project documents: `docs/PRD.md` (section 5.2 scheduled versus actual; features F4 accounts and net worth, F5 timeline, F6 reconciliation), `docs/SRD.md` (section 5 projection engine, section 9.4 recurring dates, the minor-units rule), `BUILD_SUMMARY.md` (decision: amounts as integers in minor units).
- Python `decimal` module and `dateutil` `rrule` documentation, from the Python and dateutil projects. Search by those names; no address is given here.
- The IEEE 754 floating-point standard explains why 0.1 + 0.2 is not exactly 0.3. A readable account is the essay "What Every Computer Scientist Should Know About Floating-Point Arithmetic", published in ACM Computing Surveys in 1991.

## Changes

2026-11-25: added the balance rule from `engine/ledger.py` and the plan/actual split (PR #13); finding 3 marked fixed.

2026-11-24: first version.
