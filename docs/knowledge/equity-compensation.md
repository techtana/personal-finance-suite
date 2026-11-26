# Equity compensation: RSUs and ESPPs

General explanation of how the app treats employer stock. It is not financial or tax advice.

## 1. What this is and why the project needs it

Many employers pay part of a person's salary in company stock. Two common forms are restricted stock units (RSUs) and the employee stock purchase plan (ESPP). Both put real money into the owner's net worth, but on dates and in amounts that ordinary pay does not follow. A forecast that ignores them is wrong by thousands of dollars in the months they land, and a tax estimate that ignores them misses a large slice of income. The app therefore has a small model for each: what arrives, when, how much tax is taken at the door, and what it was worth on the day the owner decided, the day it arrived and today. This note explains the ideas first, then shows where the code uses them and where it deliberately stops.

## 2. The ideas, built up from zero

### 2.1 A promise of shares: the RSU

Start with an everyday picture. A new employer says: "If you stay, we will give you 48 shares of our company, but not all at once." That promise is a restricted stock unit grant. A **share** is one small slice of ownership in a company. A **unit** is the promise of one share. The **grant date** is the day the promise is made. Until a unit **vests**, it is only a promise and the employee cannot sell or keep it. When it vests, the unit turns into a real share in the employee's brokerage account.

Vesting follows a **schedule**. The most common shape has two parts. First comes a **cliff**: nothing vests until some time has passed, often 12 months, and then a larger block vests at once, often 25 percent. After the cliff, the rest vests in equal slices at regular dates. That is **graded vesting**. The slices can come monthly or quarterly. The cliff protects the employer, because a person who leaves in month 11 gets nothing. After the cliff the person gains a little more each period.

Here is a worked example with numbers the code reproduces. A grant of 48 shares has a 12-month cliff of 25 percent, then vests 6.25 percent every quarter. The cliff block is 25 percent of 48, which is 12 shares. Each quarterly slice is 6.25 percent of 48, which is 3 shares. Twelve quarterly slices of 3 shares make 36 shares. Twelve plus 36 is the full 48. In total there are 13 vest events over four years. The cliff and the twelve slices together add up to exactly 100 percent. That equality matters later.

The analogy is a layaway plan run backwards: the store holds the goods and hands over a piece each time you hit a date. It stops working because the employee pays nothing in cash for the shares and the employer can usually cancel unvested units if the person leaves.

### 2.2 What happens at a vest

A vest is a taxable event. On the vest date the shares are worth some price on the stock market. The tax authority treats that value as pay, the same as a bonus. In the United States this is ordinary income, reported with wages. The amount is the number of shares times the **fair market value** (FMV), which for a listed company is the market price on the vest date. The employer must also send tax to the government on the employee's behalf. This is called **withholding**.

Here is how it works in words before any equation. The employer holds back part of the shares, or sells them for cash, and sends the cash to the tax authority. Selling just enough shares to pay the tax is called **sell-to-cover**. The employee keeps the remaining shares. The employer picks a flat withholding rate for this kind of extra pay. For United States federal tax the flat rate on supplemental wages is 22 percent up to one million dollars in a year, and higher above that (IRS Publication 15). The app defaults its RSU withholding to 22 percent for that reason.

The equation, in plain symbols:

    gross = shares x price
    withheld = gross x withholding_rate
    net = gross - withheld

Here `shares` is the number of shares that vest (a count), `price` is the market price per share on the vest date (dollars), `gross` and `withheld` and `net` are dollar amounts, and `withholding_rate` is a fraction such as 0.22. Example: the 12-share cliff block vests when the price is 100.00 dollars. Gross is 12 x 100.00 = 1,200.00 dollars. Withheld at 22 percent is 264.00 dollars. Net is 936.00 dollars, which in shares is 9.36 shares kept and 2.64 shares sold to cover.

The 22 percent flat rate is a prepayment, not the final bill. The final bill depends on the owner's whole year of income and the tax brackets it falls in. Someone whose total income places them in a higher bracket owes more than 22 percent on the vest and settles the difference when they file. Someone in a lower bracket gets the difference back. Social Security and Medicare taxes also apply to the vest, and many states add their own tax. The single withholding rate in the app is a rough stand-in for all of that. So 22 percent withheld is not the same as 22 percent owed.

### 2.3 Buying at a discount: the ESPP

The ESPP works the other way around. Instead of being given shares, the employee opts in to save part of each paycheck. The employer uses the savings to buy company stock at a discount. A few terms:

- The **offering period** is the whole window in which the plan watches the stock price and collects contributions. It can last from 6 months to two years.
- A **purchase period** is a shorter slice inside it. At the end of each purchase period, the money saved so far buys shares. A 12-month offering often has two purchase periods of six months.
- The **contribution** is the share of pay the employee puts in. It is usually a percentage of salary, such as 10 percent, taken after other deductions.
- The **discount** is how far below the market price the employee pays. The usual figure is 15 percent.
- The **lookback** is a feature that makes the discount more generous. The price used is the lower of the price on the first day of the offering and the price on the purchase day. The discount is then taken off that lower price.

Here is an example the code reproduces. The stock is 50.00 dollars on the first day of the offering and 60.00 dollars on the purchase day. With a lookback, the base price is the lower of the two, 50.00. A 15 percent discount gives a purchase price of 42.50. Without the lookback the base would be 60.00 and the purchase price 51.00. Now suppose the owner earns 120,000 dollars a year and saves 10 percent. That is 1,000.00 dollars a month. Over six months it is 6,000.00 dollars. At 42.50 dollars a share, it buys 141.176 shares. Those shares are worth 141.176 x 60.00 = 8,470.56 dollars at the purchase-day price. The owner paid 6,000.00 dollars. The paper gain on day one is about 2,470 dollars, which is 41 percent of the money put in. Without the lookback the same saving at 51.00 buys 117.647 shares worth 7,058.82 dollars, a gain of about 1,059 dollars, which is 17.6 percent.

If the price falls instead, the lookback picks the purchase-day price. Say the stock is 50.00 at the start and 40.00 at the purchase. The base is 40.00, and the price after discount is 34.00. The discount can never be worse than 15 percent off the purchase-day price. That is the sense in which a lookback is a one-way bet in the employee's favor.

The analogy is a store with a coupon and a price-match guarantee. It stops working because the stock price can fall between purchase and sale, so a day-one paper gain is not cash until the shares are sold.

### 2.4 General background the code does not model

Everything in this subsection is general background. The code does not model any of it, and the Taxes page says so by listing an assumption (see section 5).

When an ESPP discount is taxed depends on how long the shares are held. A **qualifying disposition** is a sale made more than two years after the offering start and more than one year after the purchase. In general, the part of the gain up to the discount is ordinary income, and the rest is a long-term capital gain. A **disqualifying disposition** is a sale before those dates. In general, the gap between the market price at purchase and the price paid is ordinary income, and any further gain or loss is a capital gain or loss. Under the usual United States rules for qualified plans, an employee can buy at most 25,000 dollars of stock a year, measured by the market price at the start of the offering, and the discount cannot exceed 15 percent. IRS Topic 427 and the IRS guidance on employee stock purchase plans give the precise rules.

The app does not know any of these dates, so it cannot tell which kind of sale happened.

### 2.5 Grant notices

A **grant notice** is the document the employer sends when it makes an RSU grant. It is also called a notice of grant or an award agreement. In general it carries a grant number, the grant date, the total number of units, the company name and a table of vest dates with the number of units on each. It does not print the stock ticker. A ticker is the short code the market uses, such as a few capital letters. The ticker matters because the app needs it to find a price. So the owner types it during import.

### 2.6 Then vs. now

Equity makes it easy to ask "was that a good deal?" The Then vs. Now page answers by valuing each instrument three times:

- **Decided**: the day the owner said yes. For an RSU it is the grant date. For an ESPP it is the start of the offering.
- **Received**: the day the thing landed. For an RSU it is each vest date. For an ESPP it is each purchase date.
- **Today**: the latest known price times the same number of shares.

The share prices come from a table the owner fills in by hand, one price per ticker per date. Real prices are not available for every date, so the page fills the gaps. It uses an exact entry when one exists. It draws a straight line between the two nearest entries when the date falls between them. It uses the nearest entry when the date is outside the range. Anything that is not an exact entry is marked as estimated and listed in a "missing prices" box so the owner can type the real number.

Example: the price was 100.00 on 1 January and 120.00 on 1 March. For 1 February, 31 of the 59 days have passed. The straight-line price is 100.00 + 20.00 x 31 / 59 = 110.51 dollars, which the code returns as 11051 cents. For a date before 1 January the page uses 100.00, the nearest entry.

## 3. Rules of thumb and typical numbers

| Item | Typical value | Source |
| --- | --- | --- |
| RSU schedule length | Four years | source not recorded |
| RSU cliff | 12 months, 25 percent of the grant | source not recorded |
| After the cliff | Monthly or quarterly slices | source not recorded |
| US federal flat withholding on supplemental wages | 22 percent up to 1 million dollars a year | IRS Publication 15 |
| ESPP discount | Up to 15 percent by law for qualified plans | IRS Topic 427 and Internal Revenue Code section 423 |
| ESPP offering period | 6 to 24 months | source not recorded |
| ESPP contribution | Plan-specific, often 1 to 15 percent of pay | source not recorded |
| ESPP purchase limit | 25,000 dollars a year at the offering-start price | IRS Topic 427 |

One more rule of thumb: the 22 percent flat rate is below the marginal rate of anyone whose top bracket is 24 percent or more. Those owners usually owe extra at filing. The app does not warn about this.

## 4. Common misconceptions and edge cases

**"Withholding 22 percent means my tax is 22 percent."** It does not. See section 2.2. The Taxes page treats the withheld amount as a payment against the estimated federal bill, not as the bill itself.

**"The vest is a gain only when I sell."** For RSUs the vest is the taxable income. A later sale creates a second, separate gain or loss measured from the price at vest.

**"The ESPP discount is taxed when I buy."** Under the general rules the discount is taxed when the shares are sold (section 2.4). The Taxes page leaves purchases out for this reason.

**"A lookback is free money."** It raises the paper gain but not the tax or the risk. The shares still move with the market after purchase.

**Unvested units are not wealth.** A grant of 48 shares on day one is worth nothing today in cash. The Then vs. Now page counts only the shares that have vested and says how many remain unvested.

**Shares are counted gross.** Then vs. Now counts shares before sell-to-cover and before any later sale, because the app does not track either. The page notes this on every RSU card.

**A ticker can be missing.** If an RSU grant or an ESPP plan has no ticker, or no price entered for it, the instrument cannot be valued. The page lists it as skipped with a reason.

**Vest dates that fall on the 29th to 31st.** Adding months to such a date clamps it to the end of a shorter month. The builder then adds the next month to the clamped date, so the day stays at the lower value for the rest of the schedule. Example: a grant dated 2026-01-31 with a one-month cliff gets a cliff date of 2026-02-28, and the next vest is on 2026-03-28, not 2026-03-31.

**The vest builder returns an empty list when the numbers do not add up.** Details in section 6.

## 5. How the project uses it

### 5.1 Units

Money is stored in cents. Shares are stored in milli-shares, which are thousandths of a share, so 48 shares is 48000. Rates and percents are stored in basis points, which are hundredths of a percent, so 22 percent is 2200 and 15 percent is 1500. The code comments often say "percent x 100", which means the same thing. The Plan form hides the conversion. The owner types 48, 22 and 15. The page multiplies by 1000 or 100 and rounds. This is in `templates/plan.html`, where the form builds the rule's `config` object. Price at grant is typed in dollars and saved in cents.

For the full reasoning behind these choices, see [the design decision record](../design/DECISIONS.md).

### 5.2 Where the data lives

Both RSU grants and ESPP plans are stored as a single `Rule` row (`models.py`) with `rule_type` of `rsu` or `espp`. Two JSON fields hold the detail. `schedule` is the list of events. For an RSU it is a list of `{date, shares}` with shares in milli-shares. For an ESPP it is a list of `{start_date, end_date, estimated_purchase_amount}` with the amount in cents. `config` holds the parameters:

- RSU: ticker, total shares, price at grant, withholding rate, cliff months, cliff percent, later frequency, later percent, and `schedule_source`.
- ESPP: ticker, offering start and end, contribution mode and value, base salary, discount rate and the lookback flag.

The older tables `RSUGrant` and `ESPPPlan` still exist in `models.py` and in the first design in `docs/SRD.md` sections 4.7 and 4.8, but the Plan page and the API now use `Rule`.

### 5.3 Vest schedule builder

`engine/vest_builder.py` has `build_vest_schedule`. It takes the grant date, total shares in milli-shares, cliff months, cliff percent in basis points, the frequency (`monthly` or `quarterly`) and the percent per later vest in basis points. It works out how many later vests fit by dividing the leftover percent by the percent per vest and rounding down. It then checks that the cliff plus the later vests add up to 100 percent with a tolerance of 0.1 percentage point. If they do not, it returns an empty list. Otherwise it returns the cliff vest plus the later vests, with share counts rounded down to a whole milli-share. `api/rules.py` calls it when a rule is created, when its config is edited, and in the preview endpoint. It skips the call when the dates came from a grant document.

### 5.4 Forecast

`engine/projection.py` turns each RSU vest into an income event on the vest date. The amount is the net value after withholding: shares times the latest hand-entered price for that ticker, minus the withholding share, all in integer cents. An ESPP purchase becomes an income event on each period's end date with the amount the owner typed as "Est. $". The label is the rule name plus "vest" or "purchase". If no price is stored for the ticker, the price is 0 and the vest produces no event at all, with no warning.

### 5.5 Taxes

`engine/tax.py` turns a vest into two tax items. The gross value counts as `wages`. The withheld amount counts as a `tax_payment`, which the tax calculation subtracts from the federal bill. For the price it uses the passed-in price for the ticker, then falls back to `price_at_grant`. If neither exists, the vest is left out and an assumption says so. For an ESPP it adds no tax item and records an assumption that the discount is taxed on sale. The test `test_rsu_vest_is_wages_with_withholding_as_a_payment` in `tests/test_tax.py` covers the RSU case.

### 5.6 Then vs. Now

`engine/lookback.py` holds `price_on` (exact, interpolated or nearest price), `latest_price`, and the builders `_rsu` and `_espp`. An RSU is valued at the grant price when decided (typed, or looked up from the price table), at the price on each vest date when received, and at the latest price today. An ESPP uses the typed purchase value as the market value on each purchase date, works out the price paid as that value times the base price over the purchase-day price times one minus the discount, and counts shares as value divided by purchase-day price. A "today" price older than 7 days is reported as missing. See [the plan for Then vs. Now](../design/plans/2026-11-22-then-vs-now.md). Tests are in `tests/test_lookback.py`, for example `test_rsu_three_moments_use_the_same_shares` and `test_espp_paid_received_today`.

### 5.7 Grant notice import

`importer/equity.py` reads an RSU grant notice. Rules read the labelled fields first. If the grant date, the total or the vests are missing, the model is asked. A value from the model is kept only when it appears in the document text. The review card checks that the vest quantities add up to the granted total and flags a mismatch. The ticker is left for the owner to fill in, or is copied from an existing grant of the same company if there is exactly one. The saved rule has `schedule_source` set to `document`, so the Plan page and the API keep the dates from the notice and never rebuild them from the cliff fields. See [the grant notice plan](../design/plans/2026-11-24-rsu-grant-notice-import.md) and the tests in `tests/test_import_equity.py`.

### 5.8 What was left out, and why

The project left out several things. This list is as of 2026-11-24.

- ESPP contribution math is not applied. The form stores contribution mode, value and base salary, but nothing turns them into period amounts. The owner types the estimate for each period.
- Qualifying and disqualifying dispositions, the 25,000 dollar limit and the 15 percent cap (section 2.4). The plan treats the discount as taxed on sale and does not track sales.
- Sell-to-cover and later sales. Shares are counted gross.
- Actual share prices from a market feed. Prices are typed by hand (PRD section 8 lists a feed as future work).
- Social Security, Medicare and state tax on a vest as part of the withholding. One rate is used.
- Other grant document types. ESPP statements and vest confirmations are not read.

## 6. What we found

Checks run on 2026-11-24 from the worktree root. The first group relates to the Plan form defaults and the second to the ESPP code.

**Does the Plan form's default RSU schedule produce a vest list?** The form defaults are a 12-month cliff, 25 percent at the cliff, then 2.0833 percent per month. The page sends each percent as `round(percent x 100)`, so the later slice becomes 208 basis points, not 208.33. The API fallback is also 208. Command:

    PYTHONPATH=. python -c "from engine.vest_builder import build_vest_schedule as b; print(b('2026-01-15', 48000, 12, 2500, 'monthly', 208))"

Result: `[]`. The schedule is empty. The cause is not a crash. The builder works out `int(0.75 / 0.0208)` as 36 later vests. Then 25 percent plus 36 x 2.08 percent is 99.88 percent (the check printed `0.9987999999999999`). That is 0.12 percentage points short of 100, and the builder only allows 0.1. So it gives up and returns nothing. The cause is the rounding of 2.0833 to 208 basis points, which loses 0.0033 percent per vest and 0.12 percent over 36 vests. Rounding up to 209 does not help: 35 later vests then reach only 98.15 percent, and the builder again returns nothing. The same call with 625 and `quarterly` works:

    PYTHONPATH=. python -c "from engine.vest_builder import build_vest_schedule as b; r=b('2026-01-15', 48000, 12, 2500, 'quarterly', 625); print(r[:2], len(r))"

Result: `[{'date': '2027-01-15', 'shares': 12000}, {'date': '2027-04-15', 'shares': 3000}] 13`.

What this means for the owner: on the Plan page, "Preview schedule" shows nothing for the default numbers. In `api/rules.py`, `create_rule` saves the empty list as the rule's schedule without any error. The grant then produces no forecast, tax or Then vs. Now events. A schedule of 25 percent plus 6.25 percent quarterly, or 25 percent plus 18.75 percent monthly or quarterly, works. A monthly 1/48 schedule with no cliff (208 basis points, 0 months and 0 percent) also returns an empty list.

**Rounding loses milli-shares.** Share counts are rounded down per vest.

    PYTHONPATH=. python -c "from engine.vest_builder import build_vest_schedule as b; print(sum(x['shares'] for x in b('2026-01-15', 100001, 12, 2500, 'quarterly', 625)))"

Result: `100000`. A grant of 100.001 shares schedules 100.000 shares, a loss of one milli-share. The amount is small, but the total of the schedule does not equal the grant.

**Day-of-month drift and a zero-share vest.**

    PYTHONPATH=. python -c "from engine.vest_builder import build_vest_schedule as b; print(b('2026-01-31', 48000, 1, 0, 'monthly', 10000))"

Result: `[{'date': '2026-02-28', 'shares': 0}, {'date': '2026-03-28', 'shares': 48000}]`. A 0 percent cliff makes a vest event with zero shares, and the month clamp drifts the day to the 28th.

**Is `engine/espp.py` called anywhere?** Command:

    grep -rn "engine.espp\|calculate_espp_purchase\|calculate_purchase_price" --include=*.py --include=*.html . | grep -v "^./engine/espp.py"

Result: no output. Nothing in the app or the tests calls `calculate_espp_purchase` or `calculate_purchase_price`. They are dead code. The ESPP forecast, tax and Then vs. Now parts all work from the typed purchase amounts.

**Do the ESPP functions agree with the worked example and with the SRD?**

    PYTHONPATH=. python -c "from engine.espp import calculate_purchase_price as p, calculate_espp_purchase as c; x=p(5000,6000,1500,True); print(x, c(12000000,1000,6,5000,x))"

Result: `4250 {'contribution_per_period': 100000, 'total_contribution': 600000, 'shares_purchased': 141176, 'immediate_gain': 2}`. The price (42.50) and shares (141.176) match section 2.3. The `immediate_gain` is 2 cents. It is only the rounding left over, because the function subtracts the cost of the shares from the contribution, and the shares were bought with that same contribution. The SRD (section 9.2) says the gain is the contribution times the discount rate, which would be 900.00 dollars here. The docstring says "discount amount". Neither describes what the code returns. Also, the `base_price` argument of `calculate_espp_purchase` is never used.

**Tests.** `PYTHONPATH=. python -m pytest tests/test_tax.py tests/test_lookback.py tests/test_import_equity.py -q` gave 59 passed. No test calls `build_vest_schedule` directly. It is only used to make sample data (`tests/sample_data.py`, with the working 625 quarterly case).

**Price interpolation.** `price_on([('2026-01-01',10000),('2026-03-01',12000)], '2026-02-01')` returns `(11051, False)`, and for `'2025-06-01'` returns `(10000, False)`. An empty list returns `(None, False)`.

## 7. Open questions

- Should the vest builder accept a small rounding gap, or let the last vest absorb the remainder, so the default 2.0833 percent monthly schedule produces 48 months of vests? As written, the default produces an empty schedule without telling the owner.
- Should the forecast fall back to the grant price when no market price exists, as the tax code does? Today the forecast drops the vest silently and the tax estimate values it at the grant price.
- The Taxes page asks for `/taxes/summary?year=...` with no prices, and the API reads prices only from a query parameter. So the Taxes page values RSU vests at the grant price, while the Overview insights use the latest stored prices. This is from reading `templates/taxes.html` and `api/taxes.py`, not from running the page. Is that intended?
- When a stored withholding rate or discount is 0, the edit form shows the default (22 or 15) instead, because zero counts as empty in `openEditRule`. Saving then changes the value. Confirmed by reading `templates/plan.html` only, not by running the page.
- Should the ESPP contribution fields compute the period amounts, or be removed from the form?
- Is the per-vest withholding rate worth splitting into federal, payroll and state parts?
- Should `engine/espp.py` be wired in or deleted? Its `immediate_gain` does not mean what its docstring says.

## 8. Sources and further reading

- Internal Revenue Service, Publication 525, *Taxable and Nontaxable Income*: how restricted stock and RSU income is taxed.
- Internal Revenue Service, Topic 427, *Stock Options*: includes employee stock purchase plans, the qualifying and disqualifying dispositions, and the purchase limit.
- Internal Revenue Service, Publication 15, *Employer's Tax Guide*: the flat rate on supplemental wages.
- Internal Revenue Service, Publication 15-B, *Employer's Tax Guide to Fringe Benefits*, and Publication 550, *Investment Income and Expenses*, for what happens when the shares are later sold.
- Internal Revenue Code section 423, the rules for employee stock purchase plans.
- Project files: `docs/SRD.md` sections 9.1 and 9.2, and the plans under `docs/design/plans/`.

## Changes

2026-11-24: first version.
