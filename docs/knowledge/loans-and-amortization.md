# Loans and amortization

General explanation of how the app treats borrowed money. It is not financial or tax advice.

## 1. What this is and why the project needs it

Most households owe money: a mortgage, a car loan, a student loan, maybe a home equity line. A net worth figure that ignores those debts is too high, and a forecast that ignores the monthly payments is too rosy. Loans also feed the tax estimate, because interest on some loans reduces tax. The app therefore stores each loan, subtracts what is owed from net worth, puts the monthly payment into the forecast, and works out how much of each payment is interest. This note explains how a loan works, where the standard payment formula comes from, and how the code uses it. It also records a few places where the code and its documents disagree.

## 2. The ideas, built up from zero

### 2.1 Borrowing and interest

When you borrow money, you promise to give back what you took and a fee for using it. The amount you took is the **principal**. The fee is **interest**. The lender states the fee as a yearly percentage of what you still owe. That yearly figure is the **annual percentage rate**, or **APR**. In its simplest meaning it is the interest for one year divided by the balance, before any compounding.

Payments are usually monthly, so the lender charges interest monthly too. The **monthly rate** is the APR divided by 12. A 12 percent APR is a 1 percent monthly rate. Borrow 1,000 dollars at that rate and you owe 10 dollars of interest after one month. Pay 110 dollars that month and 10 dollars covers the interest. The other 100 dollars reduces the principal to 900. Next month the interest is 1 percent of 900, which is 9 dollars. The interest shrinks as the balance shrinks. That is the whole mechanism. Everything else in this note is a way to handle it over hundreds of months.

### 2.2 The level payment

Most home, car and student loans use one fixed payment every month. The payment has to be big enough that the balance reaches exactly zero after the last month. A payment too small leaves a balance at the end. A payment too large pays the loan off early. The lender needs the one amount in between. Loans built this way are called **amortizing** (the word means "killing off slowly").

The size of that payment comes from one idea. Money paid later is worth less than money paid now. So the value, today, of all the future payments has to equal the amount borrowed. Working that out gives the standard **annuity formula**. In words: the payment is the principal times the monthly rate, divided by one minus the growth factor raised to the power of minus the number of payments. In symbols:

    M = P * r / (1 - (1 + r) ^ -n)

The symbols are:

- `M` is the monthly payment, in dollars.
- `P` is the principal, the amount borrowed, in dollars.
- `r` is the monthly rate as a decimal, which is the APR as a decimal divided by 12. It has no unit and means "per month".
- `n` is the number of monthly payments, a count of months.
- `(1 + r) ^ -n` is the factor that shrinks a future dollar back to today's value. It is the same as one divided by (1 + r) multiplied by itself n times.

The top part, `P * r`, is the first month's interest. The bottom part, which is always less than 1, scales it up. A longer loan makes the bottom part closer to 1, so the payment gets closer to the bare interest. A zero rate breaks the formula, because the top and bottom both become zero. With no interest the payment is just `P / n`.

Here is one worked example, which the code reproduces. Borrow 300,000 dollars at 6.5 percent APR for 360 months, which is 30 years. The monthly rate is 0.065 / 12 = 0.0054167. The growth factor over 360 months, `(1.0054167) ^ -360`, is about 0.1430. One minus that is about 0.8570. The first month's interest is 300,000 x 0.0054167 = 1,625.00 dollars. The payment is 1,625.00 / 0.8570 = 1,896.20 dollars. The code gives 189,620 cents, which is the same number cut off after the cent.

### 2.3 The amortization schedule

An **amortization schedule** is the month-by-month table that follows the loan from start to end. Each row has the balance at the start of the month, the interest charged, the part of the payment that reduces the principal, and the balance at the end. For the example loan, the first rows and the last row look like this (money in dollars):

| Payment | Interest | Principal | Balance after | Interest share of payment |
| --- | --- | --- | --- | --- |
| 1 | 1,625.00 | 271.20 | 299,728.80 | 85.7 percent |
| 2 | 1,623.53 | 272.67 | 299,456.13 | 85.6 percent |
| 180 | 1,182.94 | 713.26 | 217,677.15 | 62.4 percent |
| 360 | 10.20 | 1,884.92 | 0.00 | 0.5 percent |

Note the shape. In the first year, 19,401.21 dollars of the payments go to interest and only 3,353.19 dollars reduce the debt. After 12 payments the balance is 296,646.81 dollars, so the owner has paid back about 1.1 percent of the debt after 3.3 percent of the loan's life. At the halfway point (payment 180) the interest is still over 60 percent of each payment. Over all 360 payments the owner pays 382,630.92 dollars of interest on a 300,000 dollar loan. That is more than the loan itself. The interest share falls every month, because the balance falls and the payment stays the same.

An analogy: bailing a leaky boat with a bucket of fixed size. At first most of each scoop only keeps up with the leak (the interest). As the water drops the leak slows and each scoop removes more. The analogy stops working at the end, because a real boat's leak does not depend on how much water is in it.

### 2.4 Payoff date

The **payoff date** is the date of the last payment, when the balance reaches zero. If the payment is the level payment, the payoff date is the start date plus the term. If the owner pays a different amount, the payoff date moves. A higher payment finishes sooner, because more of each payment cuts the principal and the interest shrinks faster.

### 2.5 Extra payments

An **extra payment** is money paid on top of the required amount, aimed at the principal. It works because the interest next month is based on a smaller balance. The saving compounds. Example: add 100 dollars to the 1,896.20 dollar payment. The code's schedule then ends after 312 payments instead of 360, which is 4 years earlier, and interest drops from 382,630.92 dollars to 321,636.59 dollars, a saving of 60,994.33 dollars. Extra money sent early saves more than the same money sent late.

### 2.6 When the payment does not cover the interest

Suppose the payment is smaller than one month's interest. In the example, interest is 1,625.00 dollars. If the owner pays only 1,000.00 dollars, 625.00 dollars of interest is left unpaid, and it is added to the balance. The debt grows instead of shrinking. This is **negative amortization**. It is real: some adjustable and option loans allow it, and a home equity line often runs interest-only during its draw period. A payment that exactly equals the interest is **interest-only**. The balance stays flat forever. The standard formula cannot describe either case, because there is no payment amount that ever ends the loan. The next sections show what the code does with it.

### 2.7 Interest and tax

In the United States, interest on some loans lowers tax. This is general background and depends on the year and the person.

- **Mortgage interest** on a loan used to buy, build or improve a main or second home can be deducted if the owner itemizes deductions (IRS Publication 936). There is a limit on the size of the loan whose interest counts.
- **HELOC interest** (home equity line of credit) counts only when the money was used on the home that secures it (IRS Publication 936). A HELOC used for a car or tuition does not qualify.
- **Student loan interest** can be deducted up to a yearly cap, even without itemizing, and the deduction shrinks as income rises (IRS Publication 970).
- Interest on a car loan or a personal loan is not deductible for most people.

Whether a deduction helps depends on the **standard deduction**, a fixed amount everyone may subtract. Itemizing only helps when all itemized items together are larger than that fixed amount. The Taxes page makes that comparison.

### 2.8 Balance history

A loan's balance moves every month, but the app does not watch the bank. The owner records the amount owed from time to time. Each recording is a **snapshot**: a balance on a date. The list of snapshots is the **balance history**. The history lets the app draw the past, for example net worth a year ago. It also means the balance the app shows is whatever the owner last typed, not a number worked out from the schedule.

## 3. Rules of thumb and typical numbers

| Item | Typical value | Source |
| --- | --- | --- |
| Mortgage term in the US | 15 or 30 years | source not recorded |
| Interest share of the first mortgage payment | Over 80 percent for a 30-year loan at 6 to 7 percent | Worked out from the formula above |
| Car loan term | 3 to 7 years | source not recorded |
| Student loan standard term | 10 years for federal loans | source not recorded |
| Student loan interest deduction cap | 2,500 dollars a year (also the code's limit) | IRS Publication 970 |
| Cost of a longer term | A 15-year payment at the same rate is higher but cuts total interest sharply: 2,613.32 dollars a month in the code, against 1,896.20 | Code run, see section 6 |

A handy check: the payment on a 30-year loan at 6.5 percent is about 0.63 percent of the amount borrowed per month (1,896.20 / 300,000).

## 4. Common misconceptions and edge cases

**"APR and monthly rate are the same thing."** They are not. Divide the APR by 12 to get the monthly rate. This note and the code use the simple divide-by-12 rule. A lender's disclosed APR can include fees, so it can be a little higher than the note rate.

**"I pay equal parts of principal and interest."** You pay equal totals, not equal parts. Early payments are mostly interest.

**"The balance falls in a straight line."** It falls slowly at first and fast at the end.

**"Extra payments are applied the same way everywhere."** Some lenders apply extra money to the next month's payment instead of to principal. The code does not know. It does not model extra payments in the forecast at all.

**A payment below the interest.** The code does not stop you. See section 6 for what it returns.

**A rate of zero.** The payment formula would divide by zero. The code returns the principal divided by the months.

**Rate resets.** Variable-rate loans and HELOCs change their rate over time. The app stores one fixed rate.

**First payment date.** Real loans usually take the first payment one month after closing. The code takes the start date as the date of the first payment. This is a simplification, not a bug that changes the totals much.

**Rounding.** Cents cut off every month. Over 360 payments, the final row in the code carries a small leftover (108 cents in the example).

## 5. How the project uses it

### 5.1 Units

Money is stored in cents. Rates are stored in basis points, which are hundredths of a percent. So 6.5 percent is stored as 650 and 5.49 percent as 549. The code comments call this "annual rate x 10000". That means the decimal rate times 10,000: 0.065 x 10,000 = 650. The comment in `engine/amortization.py` gives the example "65000 = 6.5%", which is wrong by a factor of 100 (section 6). See [the design decision record](../design/DECISIONS.md) for how units were chosen.

### 5.2 Where loans live

The `Loan` model in `models.py` has a name, a type (mortgage, auto, student, personal, heloc, other), an institution, an original balance, a current balance, the rate, the monthly payment, a start date and a payoff date. All of them are typed by the owner. Nothing is computed on save. The Balances page (`templates/balances.html`) is the form. The owner types the rate as a percent, for example 6.875. The page turns it into basis points with `Math.round(percent x 100)`, and when the form is reopened it shows `basis points / 100` with three decimals. The form requires both a start date and a payoff date. The SRD (section 9.3) says the payoff date is computed when missing, but the form never lets it be missing.

Balance history is stored in the `Snapshot` table with `entity_type` set to `liability`. The value is a positive number of cents. Every "update value" on the Balances page records one. The Then vs. Now page uses the latest snapshot on or before a date. Before the first snapshot it falls back to the original balance from the start date, and to zero before the loan began (`engine/lookback.py`, `_entity_value`).

### 5.3 The amortization module

`engine/amortization.py` has three functions:

- `calculate_monthly_payment(principal, annual_rate, months)` is the annuity formula. It returns 0 for a non-positive term or a negative rate, `principal // months` for a zero rate, and otherwise the formula result cut to a whole cent.
- `calculate_payoff_date(start_date, principal, annual_rate, monthly_payment)` walks the balance forward one month at a time, up to 600 months, and returns the date reached. It stops early if a payment fails to reduce the balance.
- `amortize_loan(start_date, principal, annual_rate, monthly_payment, num_months)` produces the schedule rows: date, beginning balance, payment, principal, interest and ending balance. Interest is the balance times rate divided by 120,000, cut to a whole cent. The last payment is capped at the balance.

Only `amortize_loan` is called anywhere in the app. The other two functions are not used (section 6).

### 5.4 Taxes

`engine/tax.py` derives loan interest when the owner has not entered it. Mortgage and HELOC loans map to the `mortgage_interest` treatment. Student loans map to `student_loan_interest`. Other types add nothing. For each such loan it calls `amortize_loan` with the original balance, the rate and the monthly payment, for 600 months, and adds up the interest on rows dated inside the tax year. It adds the total as one item dated at the year end. The item is marked as an assumption in the report. If the owner has already entered any item with the same treatment, the derived one is skipped. The test `test_mortgage_interest_is_derived_from_the_loan_when_not_entered` in `tests/test_tax.py` covers this.

Mortgage interest then enters the itemized deductions. Student loan interest is capped at 2,500 dollars (`engine/tax_tables.py`). The code does not apply the mortgage debt limit, the HELOC use test or the student loan income phase-out. The schedule starts from the original balance and the scheduled payment. It does not use the current balance or any extra payments, so it drifts from reality when the owner pays extra.

### 5.5 Forecast

`engine/projection.py` (`project_v2`) adds one expense event for each month from the loan's start date to its payoff date, for the full monthly payment, in the "debt" category. It does not split the payment into principal and interest. It does not lower the loan's balance. The starting net worth already has the current balance taken out and that debt stays the same size for the whole forecast. So the forecast treats the whole payment as a net worth loss. In truth only the interest is a loss; the principal part swaps cash for a smaller debt. The effect is that the forecast net worth is too low, and more so each year. The payoff insight (`engine/insights.py`) says when a payment will end.

### 5.6 Left out, and why

Left out as of 2026-11-24: the principal and interest split in the forecast, extra payments, rate changes, escrow (property tax and insurance paid with a mortgage), fees, mortgage insurance, the tax limits in section 5.4, and the first-payment-date offset. The project prefers a short list of explainable simplifications to a lender-grade model. The design record may say more.

## 6. What we found

Checks run on 2026-11-24 from the worktree root. Each command was run as written.

**Worked example (300,000 dollars, 6.5 percent, 360 months).** Command:

    PYTHONPATH=. python -c "from engine.amortization import calculate_monthly_payment as pay, amortize_loan; p=pay(30000000,650,360); s=amortize_loan('2026-01-01',30000000,650,p,600); print(p, len(s), s[0], s[-1], sum(r['interest'] for r in s))"

Result: payment `189620` cents (1,896.20 dollars); 360 rows; the first row has interest `162500` and principal `27120`; the last row is dated `2055-12-01` with beginning balance `188492`, interest `1020` and ending balance `0`; total interest `38263092` cents (382,630.92 dollars). The unrounded formula value is 1,896.2041 dollars (`300000*r/(1-(1+r)**-360)` with `r=0.065/12`), so the code cuts the payment by 0.41 cents.

**Rate unit: does the docstring disagree with the code?** Yes. The docstring says 65000 means 6.5 percent. The code divides by 120,000, which treats 650 as 6.5 percent. Command:

    PYTHONPATH=. python -c "from engine.amortization import calculate_monthly_payment as pay; print(pay(30000000,650,360), pay(30000000,65000,360))"

Result: `189620 16250000`. With 65000 the payment is 162,500.00 dollars a month, which is 650 percent a year. The models file comment ("annual rate x 10000"), the Balances form (percent x 100), the tax tests (rate 600 for 6 percent) and sample data (549) all agree with 650. Wrong places: the docstring example in `engine/amortization.py`, the SRD loans table (section 4.3, "6.5% = 65000"), and the mortgage in `tests/lookback_sample.py` (rate 62500, meant as 6.25 percent, would be 625 percent). The SRD formula in section 9.3 divides by 10,000 and so agrees with the code.

**Rate precision in the form.** Command: `node -e "console.log(Math.round(6.875*100), (688/100).toFixed(3))"`. Result: `688 6.880`. The form's placeholder is 6.875 and it accepts three decimals, but the rate is stored to two. 6.875 percent is saved as 6.88 percent.

**Extra payment.** Command:

    PYTHONPATH=. python -c "from engine.amortization import *; P=30000000; p=calculate_monthly_payment(P,650,360); a=amortize_loan('2026-01-01',P,650,p,600); e=amortize_loan('2026-01-01',P,650,p+10000,600); print(len(e), e[-1]['date'], sum(r['interest'] for r in a)-sum(r['interest'] for r in e))"

Result: `312 2051-12-01 6099433`. That is 312 payments and 60,994.33 dollars less interest.

**Payment that does not cover the interest.** Commands:

    PYTHONPATH=. python -c "from engine.amortization import *; print(calculate_payoff_date('2026-01-01',30000000,650,100000), calculate_payoff_date('2026-01-01',30000000,650,162500))"
    PYTHONPATH=. python -c "from engine.amortization import *; print(amortize_loan('2026-01-01',30000000,650,100000,2))"

Result of the first: `2026-01-01 2026-01-01`. When the payment is below the interest, or equal to it, `calculate_payoff_date` returns the start date, which reads as "paid off on day one". The second shows the schedule going the wrong way: principal `-62500`, ending balance `30062500`, then `30125338`. `amortize_loan` has no guard, so the balance grows and the row's principal is negative. With a payment of 0 (a blank field on the form), the tax code's 600-month schedule gives 2,009,149 cents (20,091.49 dollars) of derived interest in year one, and an ending balance of 766,951,828 cents after 600 months. A mortgage with a blank payment therefore produces an inflated interest deduction.

**One-month offset between the two payoff functions.** For the extra-payment case, `calculate_payoff_date` returns `2052-01-01`, one month after the last schedule row (`2051-12-01`). The schedule dates its first payment on the start date, the payoff function dates the end one month after the last payment.

**Last row.** The `payment` column of the last row says 189,620, but principal plus interest is 189,512. The listed payments add up to 68,263,200 cents, while principal plus interest add up to 68,263,092, a difference of 108 cents.

**Forecast treatment of loan payments.** Command:

    PYTHONPATH=. python -c "from engine.projection import project_v2; l={'id':'l1','name':'Home','current_balance':30000000,'monthly_payment':189620,'start_date':'2026-01-01','payoff_date':'2056-01-01'}; b,ev=project_v2([],[],[l],0,{},'2026-01-01','2026-12-31'); print(len(ev), b[-1].cumulative_net_worth)"

Result: `12 -2275440`. Twelve payments take 22,754.40 dollars off net worth. The schedule says only 19,401.21 dollars of that is interest and 3,353.19 dollars is principal, which is a debt swap and not a loss. So the forecast is too pessimistic by the principal paid, here 3,353.19 dollars in year one.

**Unused functions.** Command: `grep -rn "calculate_monthly_payment\|calculate_payoff_date\|amortize_loan" --include=*.py --include=*.html . | grep -v "^./engine/amortization.py"`. Result: only `engine/tax.py` (and its import) uses `amortize_loan`. Nothing calls `calculate_monthly_payment` or `calculate_payoff_date`.

**15-year payment.** `calculate_monthly_payment(30000000,650,180)` returns `261332` (2,613.32 dollars).

## 7. Open questions

- Should the forecast split each payment, using `amortize_loan`, so that only interest reduces net worth and the loan balance falls? This changes every forecast with a loan.
- Should `calculate_payoff_date` and `amortize_loan` stop or warn when the payment does not cover the interest, instead of returning the start date or a growing balance?
- Should the Balances form refuse a monthly payment of 0 for a mortgage or student loan, or should the tax code skip such loans?
- Should the rate be stored with more precision (for example in hundredths of a basis point), or the form limited to two decimals?
- Fix the 65000 example in the docstring and the SRD, and the sample rate 62500? Not changed here because this note only records them.
- Should the tax code use the current balance, or the snapshots, instead of the original balance, so extra payments and refinances show up?
- Should the tax code apply the mortgage debt limit, the HELOC use test and the student loan income phase-out?
- Does the first payment fall on the start date, as the code assumes, or one month later?

## 8. Sources and further reading

- Consumer Financial Protection Bureau, material on how mortgage amortization and monthly payments work (the "Ask CFPB" and mortgage guides on consumerfinance.gov).
- Internal Revenue Service, Publication 936, *Home Mortgage Interest Deduction*: mortgage and HELOC interest, and the debt limit.
- Internal Revenue Service, Publication 970, *Tax Benefits for Education*: the student loan interest deduction and its phase-out.
- Internal Revenue Service, Publication 17, *Your Federal Income Tax*: standard and itemized deductions.
- Any introductory finance text, chapter on the time value of money and annuities, for the derivation of the payment formula.
- Project files: `docs/SRD.md` section 9.3 and `docs/design/plans/2026-11-22-tax-treatments-taxes-page.md`.

## Changes

2026-11-24: first version.
