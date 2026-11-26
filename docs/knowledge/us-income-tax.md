# US income tax and payroll tax

This page is a planning estimate, not tax advice. It explains how the project's Taxes page works. It does not tell anyone what to do with their own money.

## 1. What this is and why the project needs it

The app projects a household's money forward in time. Take-home pay is the biggest input to that projection, and take-home pay is gross pay minus tax. So the app needs a rough tax figure for a year. The Taxes page gives one. It also shows where the gross dollars go and how much room is left in tax-advantaged accounts. It turns that into short findings, such as "you have unused 401(k) room".

The estimate covers US federal income tax, the payroll taxes that fund Social Security and Medicare, self-employment tax, a 3.8% tax on investment income for higher earners, and a single flat rate for state tax. It is built to be useful and honest, not exact. Whenever the code has to guess, it writes the guess on the page.

All numbers below come from `engine/tax_tables.py` (2026 values) unless a line says otherwise. Money in the code is stored in cents. This page uses dollars.

## 2. The ideas, built up from zero

### 2.1 A paycheck

Start with a paycheck. Your employer agrees to pay you a yearly salary. That yearly total is your **gross pay**. The money that reaches your bank account is smaller. Several different taxes and deductions come out of the gap.

Two families of tax take a bite. **Income tax** goes to the federal government (and, in most states, to the state). **Payroll tax** pays for two programs: **Social Security** (old-age and disability benefits) and **Medicare** (health cover for older people). Payroll tax is a different calculation from income tax. It has its own rates and its own rules about which money counts.

### 2.2 Filing status

The tax code treats people differently depending on their household. This is the **filing status**. The project supports three:

- **Single**: one adult, no special status.
- **Married filing jointly (mfj)**: a married couple files one combined return.
- **Head of household (hoh)**: an unmarried person who supports a dependent and meets some further tests. The code does not check those tests.

Filing status picks the standard deduction, the bracket edges and a few thresholds. The code defaults to Single and says so when you have not chosen one.

### 2.3 From gross income to taxable income

Income tax is not charged on gross pay. It is charged on **taxable income**, which is smaller. Three steps get you there.

1. **Pre-tax savings come off first.** Some money you put into certain accounts is not counted as income this year. The next section lists them. After they come out, you have what the project calls reduced wages.
2. **Adjustments give you AGI.** A few more items, such as half of self-employment tax and traditional IRA contributions, are subtracted. The result is **adjusted gross income (AGI)**. Many later rules use AGI as their yardstick.
3. **A deduction comes off AGI.** Everyone may subtract a **deduction**. You pick one of two kinds:
   - The **standard deduction** is a fixed amount for your filing status. For 2026 the table has $16,100 (Single), $32,200 (mfj) and $24,150 (hoh).
   - **Itemized deductions** add up specific costs: mortgage interest, state and local taxes (capped), charity, and medical costs above a floor. You use itemizing only if the total beats the standard deduction. The code takes whichever is larger.

In symbols, for the common case:

    taxable income = AGI - deduction

AGI and deduction are both in dollars. The code never lets taxable income go below zero.

### 2.4 Marginal brackets and effective rate

US income tax is **progressive**: higher slices of income face higher rates. A good picture is a row of buckets, filled in order. The first bucket holds the first $12,400 of a single filer's taxable income and is taxed at 10%. The second bucket holds the next slice, taxed at 12%, and so on up to 37% for the top bucket. Each dollar goes into one bucket only. You pay each bucket's rate on what is in it.

The rate on the bucket you are currently filling is your **marginal rate**. It is the rate on your next extra dollar. Your **effective rate** is total tax divided by income. It is always lower than the marginal rate, because your earlier dollars sat in cheaper buckets.

The analogy stops working in one place. Real buckets do not interact. The tax code does. Some benefits switch off at higher income, and long-term capital gains are taxed on a separate scale that sits on top of your ordinary income (section 2.7). The project's code leaves most of those switches out.

The 2026 single-filer buckets in the table, with each rate and the top of its bucket (taxable income):

| Rate | Top of bucket (Single) |
|---|---|
| 10% | $12,400 |
| 12% | $50,400 |
| 22% | $105,700 |
| 24% | $201,775 |
| 32% | $256,225 |
| 35% | $640,600 |
| 37% | no limit |

Source: `engine/tax_tables.py`, `TAX_YEARS[2026]["brackets"]["single"]`. The mfj and hoh lists are in the same file.

The code's effective rate is different from the usual textbook one. It is **all taxes** (federal income, payroll, state) divided by gross income. The number on the page is therefore higher than a federal-only rate.

### 2.5 Pre-tax accounts

Several accounts let you set money aside before it is taxed as income. Putting money in lowers your taxable income now. Whether you pay tax later depends on the account.

- **Traditional 401(k).** An employer retirement plan. Contributions come out of your pay before income tax. You pay income tax when you withdraw in retirement. 2026 limit: $24,500. A **catch-up** adds more room: $8,000 from age 50, or $11,250 instead from age 60 to 63. The code adds the catch-up to the base limit, so the age 60 to 63 limit is $35,750.
- **Roth 401(k).** The reverse: no deduction now, no tax on qualified withdrawals later. It shares the same $24,500 limit with the traditional kind. The code counts it against the limit but gives no deduction.
- **HSA (health savings account).** Available only with a qualifying high-deductible health plan. 2026 limits: $4,400 for self-only cover, $8,750 for family cover, plus $1,000 from age 55. Money put in through payroll skips income tax and payroll tax.
- **Health FSA (flexible spending account).** An employer account for medical costs. 2026 limit: $3,400. It is pre-tax and mostly use-it-or-lose-it. A **limited-purpose FSA** (dental and vision only) shares the same limit in the code and can sit beside an HSA.
- **Dependent-care FSA.** Pre-tax money for childcare and similar costs. 2026 limit: $7,500 per household.
- **IRA (individual retirement account).** A personal retirement account. 2026 limit: $7,500, plus $1,100 from age 50. A traditional IRA is deductible (the code ignores the income limits that can remove the deduction). A Roth IRA is not deductible and shares the same limit.

Why the payroll-tax effect matters. A traditional 401(k) lowers income tax but not payroll tax. In the code the 401(k) comes off `taxable_wages` but not `fica_wages`. The HSA and both FSAs come off both. The code assumes the HSA goes through payroll; the part of an HSA contribution larger than wages is treated as a deduction on the return instead, which does not avoid payroll tax. Source: `compute_tax()` in `engine/tax.py`.

### 2.6 Payroll taxes and self-employment tax

Payroll tax is flat, with two kinds of ceiling.

- **Social Security**: 6.2% of wages, but only on wages up to the **wage base**. For 2026 the code uses $184,500. Pay above that is not charged Social Security tax.
- **Medicare**: 1.45% of all wages, with no ceiling.
- **Additional Medicare**: an extra 0.9% on wages above a threshold: $200,000 (Single), $250,000 (mfj), $200,000 (hoh).

An employer pays a matching share of Social Security and Medicare on top of what you see. The Taxes page shows the employee share only.

A **self-employed** person (a 1099 worker) is both employee and employer. They pay both halves, so the rates double: 12.4% for Social Security and 2.9% for Medicare, 15.3% together. The tax applies to 92.35% of net self-employment income. That fraction removes the employer half of the tax from the base, as the tax rules do. Half of the resulting self-employment tax is then deductible when computing AGI. The code applies the Social Security part only up to whatever room is left under the wage base after any W-2 wages.

### 2.7 Capital gains and losses

When you sell an investment for more than you paid, the difference is a **capital gain**. The price you paid, adjusted, is the **basis**. The code takes the gain as proceeds minus basis, scaled by the share of the asset sold.

How long you held it matters. A **short-term** gain is from an asset held one year or less. It is taxed like ordinary income. A **long-term** gain is from an asset held more than a year. It gets lower rates: 0%, 15% or 20%. The code calls a sale long-term when the days between purchase and sale exceed 365. If the purchase date is missing, it assumes long-term and says so.

The 0/15/20 rates work by **stacking**. First fill the ordinary buckets from the bottom with your ordinary taxable income. The long-term gains then sit on top. The part of the gains that lands below the 0% line pays nothing. The part between the lines pays 15%. Any part above the second line pays 20%. In 2026, for a single filer, the lines are $49,450 and $545,500 of taxable income. For mfj they are $98,900 and $613,700. For hoh they are $66,200 and $579,600. Qualified dividends use the same scale. Source: `ltcg` in `tax_tables.py`.

A **loss** works the other way. Losses first cancel gains of the same type, then the other type. If your total is still a loss, you may deduct up to **$3,000** against ordinary income in one year. The rest is a **carryover** to future years. The code treats carried-in losses as long-term. It reads the carryover amount from the tax profile.

### 2.8 Investment-income tax (NIIT)

The **net investment income tax** is 3.8% on the smaller of two amounts: your investment income, or the amount by which AGI exceeds a threshold. The thresholds are $200,000 (Single), $250,000 (mfj), $200,000 (hoh). The code counts interest, dividends, rental income and net capital gains as investment income. It folds NIIT into "federal income tax".

### 2.9 Stock pay: RSUs and ESPP

A **restricted stock unit (RSU)** is a promise of company shares. When the shares **vest**, their market value at that moment is wages, and the usual income and payroll taxes apply. The employer usually sells some shares or withholds cash to cover tax. The code treats a vest as W-2 wages worth shares times price. If the rule gives a withholding rate, the code records the withheld amount as tax already paid. If no current price is known, it falls back to the grant price and flags this. With no price at all, the vest is left out.

An **employee stock purchase plan (ESPP)** lets employees buy company shares at a discount. The tax on the discount arrives when the shares are sold. The code takes no tax at purchase, and adds a note that says so. The sale itself is only taxed if it is entered as an asset sale with a cost basis. The code does not split an ESPP sale into discount and gain.

### 2.10 State tax

State rules vary widely. The code uses one flat number, the **state rate**, which you enter in the profile. It multiplies AGI by that rate. That is a rough stand-in. Real states use their own brackets, deductions and credits, or have no income tax at all. The state amount also counts toward the itemized state-and-local-tax (SALT) deduction.

### 2.11 One full example

A single filer earns $150,000 in wages and puts $24,500 into a traditional 401(k). There is no state tax, no other income and no age. All values are from the 2026 table in `tax_tables.py`.

1. **Gross income:** $150,000.
2. **Pre-tax savings:** the 401(k) comes out. Reduced wages: $150,000 - $24,500 = $125,500.
3. **AGI:** no adjustments. AGI = $125,500.
4. **Deduction:** the standard deduction for Single is $16,100. Itemized costs are zero. The standard deduction wins.
5. **Taxable income:** $125,500 - $16,100 = $109,400.
6. **Fill the buckets:**
   - 10% of the first $12,400 = $1,240.
   - 12% of the next $38,000 (to $50,400) = $4,560.
   - 22% of the next $55,300 (to $105,700) = $12,166.
   - 24% of the last $3,700 (to $109,400) = $888.
   - Federal income tax = $1,240 + $4,560 + $12,166 + $888 = **$18,854**. The marginal rate is 24%.
7. **Payroll tax.** The 401(k) does not reduce payroll wages, so the base is the full $150,000. That is under the $184,500 wage base. Social Security = 6.2% x $150,000 = $9,300. Medicare = 1.45% x $150,000 = $2,175. Additional Medicare is zero because wages are under $200,000. Payroll tax = **$11,475**.
8. **Total tax:** $18,854 + $11,475 = $30,329.
9. **Effective rate:** $30,329 / $150,000 = about 20.2%. The federal income tax alone is about 12.6% of gross.
10. **Take-home** (the code's definition): gross - total tax - sheltered savings = $150,000 - $30,329 - $24,500 = $95,171.

Check the idea against the tests. `test_single_wage_earner_matches_hand_calculation` does the same sum for $120,000 and no 401(k): taxable income $103,900, tax $17,570 (as $1,240 + $4,560 + $11,770). `test_traditional_401k_lowers_income_tax_but_not_payroll_tax` shows a $24,500 contribution saving $5,390 at 22%.

Symbols used above: tax and income are in dollars; rates are fractions (0.24 means 24%); the wage base is in dollars of yearly wages.

## 3. Rules of thumb and typical numbers

All 2026 figures are from `engine/tax_tables.py`. The table gives the value the code uses, not an independent check.

| Item | 2026 value in the code | Source |
|---|---|---|
| Standard deduction | Single $16,100; mfj $32,200; hoh $24,150 | `tax_tables.py`; cited as Rev. Proc. 2025-32 |
| Ordinary bracket rates | 10, 12, 22, 24, 32, 35, 37% | same |
| Long-term gain rates | 0, 15, 20% | same |
| 0% band top (taxable income) | Single $49,450; mfj $98,900; hoh $66,200 | same |
| 15% band top | Single $545,500; mfj $613,700; hoh $579,600 | same |
| Social Security rate and wage base | 6.2%; $184,500 | `tax_tables.py`; cited as SSA 2026 wage base |
| Medicare rate | 1.45% on all wages | `tax_tables.py` |
| Additional Medicare | 0.9% above $200,000 (Single, hoh) or $250,000 (mfj) | `tax_tables.py` |
| NIIT | 3.8% above $200,000 (Single, hoh) or $250,000 (mfj) | `tax_tables.py` |
| Self-employment base and rate | 92.35% of net; 12.4% + 2.9% | `tax.py` (92.35% is in code, not in the tables file) |
| 401(k) limit | $24,500; catch-up $8,000 (50+) or $11,250 (60 to 63) | `tax_tables.py`; cited as Notice 2025-67 |
| IRA limit | $7,500; catch-up $1,100 (50+) | same |
| HSA limit | $4,400 self; $8,750 family; catch-up $1,000 (55+) | `tax_tables.py`; cited as Rev. Proc. 2025-19 |
| Health FSA limit | $3,400 | `tax_tables.py`; cited as Rev. Proc. 2025-32 |
| Dependent-care FSA limit | $7,500 | `tax_tables.py`; source not recorded in the header |
| Capital loss deduction cap | $3,000 a year | `tax_tables.py` |
| Student loan interest deduction | up to $2,500 | `tax_tables.py` |
| Medical expense floor | 7.5% of AGI | `tax_tables.py` |
| SALT cap | $40,400, falls by 30 cents per dollar of AGI above $505,000, never below $10,000 | `tax_tables.py`; not confirmed (section 6) |
| Long-term holding period | more than 365 days | `tax.py` |

Rules of thumb that follow from the numbers:

- A single filer's first $16,100 of income is shielded by the standard deduction. Most households with no mortgage take it.
- Each dollar of traditional 401(k) saves tax at your marginal rate now. At 24% that is 24 cents, though payroll tax is unchanged.
- An HSA or FSA dollar through payroll saves income tax plus 7.65% payroll tax (6.2% + 1.45%). The code's insight text uses 7.65%.
- Itemizing pays only when mortgage interest, capped state and local tax, charity and above-floor medical costs together pass the standard deduction.

## 4. Common misconceptions and edge cases

**"A raise that pushes me into a higher bracket cuts my take-home pay."** It does not. Only the dollars above the bracket edge are taxed at the higher rate. Take a single filer whose taxable income is $105,000, just inside the 22% bucket. Add $2,000. The first $700 is taxed at 22% and the other $1,300 at 24%. The whole $105,000 is not re-taxed at 24%.

**"Marginal rate is my tax rate."** It is the rate on your next dollar. Your effective rate is lower. On the Taxes page the effective rate also includes payroll and state tax, so the two numbers measure different things.

**Roth versus traditional.** Both are limited by the same cap. A traditional contribution lowers tax now and is taxed later. A Roth costs more tax now and avoids tax on qualified withdrawals. Which is better depends on whether your rate will be higher now or in retirement. The code does not compare them. It gives a deduction for traditional money only.

**A 401(k) does not reduce Social Security or Medicare tax.** The HSA and FSAs through payroll do. The code treats these two groups differently on purpose.

**HSA outside payroll.** If an HSA contribution is larger than wages, the code moves the excess to the adjustments step, where it lowers AGI but not payroll tax. Payroll-route HSA money avoids FICA only when the employer runs it through payroll. The code assumes it does.

**HSA together with a general health FSA.** A general health FSA normally makes you ineligible for an HSA. The code warns about this. A limited-purpose FSA is allowed.

**Over-limit contributions.** The code caps each deduction at the limit and shows a warning. It does not model penalties.

**Short versus long term.** The code counts "more than 365 days". A holding that spans a leap day can differ by one day from a strict "more than one year" reading. The code does not handle that edge.

**Wash sales are not modelled.** A wash sale is a loss sale followed by a repurchase of the same investment within 30 days. The tax code disallows the loss. The project has no repurchase tracking, so such a loss would still count as deductible in the estimate.

**Capital losses on cars and property.** A loss on selling a vehicle or a home is personal. The code ignores it and says so. Gains on property are counted in full. The home-sale exclusion ($250,000 or $500,000) is mentioned in a note but not applied.

**Withholding is not the bill.** Tax withheld from pay is a prepayment. The final bill depends on the whole year. On the page, "federal balance due" is federal income tax plus additional Medicare plus self-employment tax, minus entered withholding. Ordinary Social Security and Medicare tax are left out of that figure, because they are assumed paid through payroll.

**RSU withholding.** Employers often withhold at a flat rate that can differ from your real marginal rate. The code uses whatever rate you enter. The usual flat rates are not recorded in this project's sources.

**Self-employment minimum.** Actual rules apply self-employment tax only above a small earnings floor. The code has no floor.

**A negative net result is clamped.** AGI and taxable income never go below zero in the code.

## 5. How the project uses it

Files and settings, in the order data flows:

- `engine/tax_tables.py`: tax treatments (the labels users pick from), filing statuses, the 2026 parameter table and `tables_for(year)`. `tables_for` returns the nearest year in the table. Only 2026 exists, so every other year reuses the 2026 numbers and the page says so.
- `engine/tax.py`:
  - `normalize_profile()` fills the profile with defaults and returns a list of assumptions.
  - `collect_tax_items()` turns recurring rules, one-off changes, asset sales and loans into dated tax items for one year.
  - `compute_tax()` runs the sums above. Helpers: `_bracket_tax()` fills the ordinary buckets and `_preferential_tax()` stacks long-term gains.
  - `build_insights()` writes the plain-language findings.
  - `estimate_taxes()` runs the whole chain.
- `api/taxes.py`: the REST endpoints under `/taxes`. They list treatments, read and update the tax profile in settings, and return the summary. `compute_tax_summary()` is also used by the Insights page.
- `templates/taxes.html`: the page. Section titles: Estimated taxes; Tax profile; Where your gross income goes; From gross income to taxable income; Federal brackets you fill; Tax-advantaged account room; Standard vs. itemized deduction; Investment sales and loss deduction; What stands out; Filled in for you.
- `tests/test_tax.py`: test names read as a short list of rules (401(k) lowers income tax but not payroll tax; Social Security stops at the wage base; net capital loss deducts $3,000 and carries the rest forward; itemizing wins only when it beats the standard deduction; SALT is capped; the RSU vest is wages with withholding as a payment).

The tax profile holds seven settings: filing status, state rate (percent times 100, so 500 means 5%), age, HSA coverage (self, family or none), loss carryover, and untracked short-term and long-term gains. Every missing value gets a default and an entry in the assumptions list.

Defaults the code picks:

- Income with no tax treatment counts as W-2 wages entered before tax.
- A one-off gain with no treatment counts as other taxable income.
- An expense with no treatment has no tax effect.
- An asset sale with no basis is left out.
- Loan interest on a mortgage, HELOC or student loan is estimated from the loan's schedule if you did not enter it yourself.

Why 401(k), HSA and IRA contributions are called "transfers" in the treatments list: the money goes into your own account, so the projection does not count it as spending.

What the project simplifies or leaves out:

- Credits (child, education, energy and others).
- The alternative minimum tax.
- Income phase-outs, including traditional IRA deduction limits, student-loan interest limits and Roth eligibility.
- State brackets and rules. A flat rate stands in.
- Extra standard deduction for age or blindness.
- Dependents and head-of-household tests.
- The itemized mortgage-interest limit, the cap on charity as a share of income, and similar limits.
- Other years. Years other than 2026 use the 2026 tables.
- Filing, forms and penalties. This is an estimate, not a return.
- Ordinary-versus-qualified treatment of dividends beyond the two categories the user picks.
- The split of an ESPP sale into discount and gain.
- Wash sales.

Why: the owner wanted charts first and analysis second. A readable approximation that lists its guesses is more useful than a partial return that looks exact. Design record: [DECISIONS.md](../design/DECISIONS.md) and the plan [tax treatments and a Taxes page](../design/plans/2026-11-22-tax-treatments-taxes-page.md).

## 6. What we found

Research on 2026-11-23 checked the 2026 numbers in the code against secondary sources. These were web pages by accounting firms, a savings site, a legal association, an HR advice site and a brokerage:

- A CPA firm's page "2026 Standard Deduction and Tax Brackets" (sdocpa.com).
- Another CPA firm's page "2026 Tax Brackets, Standard Deductions and More" (alanburkecpa.com).
- "2026 Capital Gains Tax Rates & Brackets" (bearsavings.com).
- A 2026 IRS contribution limits summary (alpa.org).
- FSA and HSA limits (hrcalifornia.calchamber.com).
- 401(k) catch-up rules (fidelity.com).
- A 2026 limits summary (hiltzikcpa.com).

What the research settled: the standard deductions, ordinary brackets, long-term gain thresholds, and the 401(k), IRA, HSA and FSA limits and catch-ups now in `tax_tables.py` were taken from those secondary pages. The pages cite the IRS documents named in the file's header (Rev. Proc. 2025-32, Notice 2025-67, Rev. Proc. 2025-19, and the SSA 2026 wage base). The IRS documents themselves were not opened, so the table has not been checked against a primary source.

What it did not settle: the **SALT cap figure** ($40,400, with the phase-out above $505,000 and the $10,000 floor) was not confirmed by those searches. The code uses it as written. Treat it as unverified until checked against an IRS source. The plan record also says the 2026 SALT cap was not checked against an IRS source.

## 7. Open questions

- Is the SALT cap of $40,400 correct, and do the $505,000 phase-out start, 30% rate and $10,000 floor match the law? Source not recorded.
- Are the $184,500 Social Security wage base and the $7,500 dependent-care FSA limit correct? The first is cited to SSA in the header; the second has no cited source.
- Do 2026 rules require catch-up contributions to be Roth for higher-paid workers? The code ignores any such rule. Source not recorded.
- Which year's tables should the next release add, and should other years keep reusing 2026 until then?
- Should the NIIT threshold test use modified AGI instead of AGI? The code uses AGI.
- Should the Additional Medicare tax use filing-status thresholds for married people filing separately? The code has no such status.
- Should the page model ESPP sales (discount versus gain) and wash sales? Today it models neither.
- Should the app move toward state-specific brackets for the most common states, or keep one flat rate?
- Should the federal balance-due figure include regular payroll tax, so that it matches what a pay stub shows?

## 8. Sources and further reading

All primary IRS documents are on irs.gov. Search the document number there. I give no exact addresses.

| Title | Organisation, year | Good for |
|---|---|---|
| Rev. Proc. 2025-32 | IRS, 2025 | Cited in the code header for 2026 brackets, standard deduction, capital gain thresholds and health FSA limit. Read this first to verify the table. |
| Notice 2025-67 | IRS, 2025 | Cited for 2026 401(k) and IRA limits and catch-ups. |
| Rev. Proc. 2025-19 | IRS, 2025 | Cited for 2026 HSA limits. |
| Social Security wage base for 2026 | Social Security Administration, 2025 | Cited for the $184,500 base. Exact title not recorded. |
| "2026 Standard Deduction and Tax Brackets" | sdocpa.com, 2026 | Secondary summary used in the 2026-11-23 research. |
| "2026 Tax Brackets, Standard Deductions and More" | alanburkecpa.com, 2026 | Secondary summary used in the research. |
| "2026 Capital Gains Tax Rates & Brackets" | bearsavings.com, 2026 | Secondary summary of the 0/15/20 thresholds. |
| 2026 IRS contribution limits | alpa.org, 2026 | Secondary summary of retirement and savings limits. |
| FSA and HSA limits | hrcalifornia.calchamber.com, 2026 | Secondary summary of FSA and HSA limits. |
| 401(k) catch-up contribution rules | fidelity.com, 2026 | Secondary explanation of age 50 and 60 to 63 catch-ups. |
| 2026 limits summary | hiltzikcpa.com, 2026 | Secondary summary used in the research. |
| IRS Publications 505, 550, 969 and Schedule SE instructions | IRS, various | Not used in this research. Named here as places to look for withholding and estimated tax, investment income and capital gains, HSA and FSA rules, and self-employment tax. Confirm current editions on irs.gov. |

For the project's own context: [DECISIONS.md](../design/DECISIONS.md), the tax treatments plan above, `engine/tax.py` and `tests/test_tax.py`.

## Changes

- 2026-11-24: first version.
