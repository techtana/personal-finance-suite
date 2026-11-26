# User guide

For whoever uses the app day to day. It explains what each page shows and how to do the common tasks.

## The idea

You tell the app what you know: your accounts and what they hold today, your salary, bills, RSU grants, ESPP plan and loans. The app projects where your money goes. Now and then you check in with real balances, and the app tells you where reality and the plan part ways.

Background on the ideas behind this: [docs/knowledge/](../knowledge/README.md).

## Finding your way

The sidebar (on a phone: the tab bar and **Menu**) groups pages by what you do there:

| Group | Pages | What you can do |
|---|---|---|
| **Your picture** | Overview, Forecast, Then vs. Now, Taxes | Look. These pages are computed from your inputs |
| **Your inputs** | Plan, Balances, Import | Enter and change data. Nothing else changes your data |
| **Guidance** | Insights | See what stands out, and why |
| **App** | Settings | Configure the app |

Each block has a chip that says what it is:

- **View only**: computed for you.
- **You manage**: your own entries.
- **Guidance**: what stands out.
- **AI**: worded by a model. Check it.

The Taxes page says **View + inputs**: it is computed, but its tax profile is yours to fill in.

On a phone, the tab bar holds Overview, Forecast, Plan, Balances and Insights. The rest is under **Menu**.

Every list has a search box, **Filters**, **Clear** and sortable column headers. The filters are kept in the page address, so you can bookmark a filtered view. When AI is available, you can also type a filter in words ("groceries over $100 last month") and click **Set filters**.

## First steps

On a new install, **Overview** shows "Three steps to a first picture".

1. **Add your accounts.** Open **Balances**, click **+ Add**, and choose **Cash account**, **Asset** or **Liability**. Enter the value today.
2. **Add what repeats.** Open **Plan**, click **+ Add rule**, and add your salary, rent and main bills.
3. **Look at the result.** Open **Overview** and **Forecast**.

## Pages

### Overview

Where you stand today. Tiles for **Net worth**, **Cash**, **Assets**, **Liabilities** and **This month, planned**. The net worth tile shows the change since the last month-end. Below them:

- **Needs your attention**: up to four items from Insights.
- **What you have and owe, over time**: recorded values for 12 months, 2 years or 5 years.
- **Next 12 months**: the forecast in short.
- **Coming up in the next 30 days**: planned events.

### Forecast

Your net worth and monthly cash flow from today, for 1 to 10 years (**Look ahead**). It starts from today's recorded net worth and adds every Plan rule, one-off entry and loan payment. It does not add investment growth or inflation.

Click a bar in **Cash flow by month** to see that month's events.

**What if…**: untick any rule or entry to see the forecast without it. A dashed line shows the change. Nothing in your Plan changes; click **Reset** to put everything back.

### Then vs. Now

For each decision (an RSU grant, an ESPP purchase, an asset you bought), what it was worth when you decided or received it, and what it is worth today. Use **Compare today with** to switch between "The day I decided" and "The day I received it".

It needs share prices. Click **Enter share prices** to add them on Balances. A value between two known prices is estimated and marked so.

### Taxes

An estimate of US federal tax for one **Tax year**, with a flat state rate. It is a planning estimate, not tax advice, and not a return.

Click **Tax profile** to set your filing status, state rate, age, HSA coverage and any capital loss carried over. Click **Save profile**.

The page shows where your income goes, how you get from gross to taxable income, which brackets you fill, room left in tax-advantaged accounts, standard vs. itemized deduction and investment sales. **What stands out** lists findings. **Filled in for you** lists every default the estimate used, such as untagged income counted as wages.

To make the estimate better, give your Plan entries a **Tax treatment** (wages, 401(k), HSA, investment sale, charity and so on).

### Plan

Everything you expect to happen.

- **Recurring rules**: income, expenses, RSU grants and ESPP plans. Click **+ Add rule**.
- **One-off entries**: a single event on a date. Click **+ Add entry**. Amounts in are positive, amounts out negative ("1500 or -250").

For an **RSU grant**, enter the ticker, total shares, grant date, withholding and vesting (cliff months, cliff %, then every month or quarter, % per vest). Click **Preview schedule** to check the dates before you save. A grant read from a grant notice keeps the notice's dates.

For an **ESPP plan**, enter the offering dates, the contribution, the discount, and whether it has a lookback. Add each purchase period with **+ Add period** and its estimated value.

With AI available, type something like "rent 2400 a month from March" and click **Draft entry**. The form opens filled in. Nothing is saved until you click **Save**.

### Balances

What you have and owe today.

- **Update value** on a row records today's value. **History** shows and edits the recorded values.
- **Check-in**: the card says how many balances haven't been updated recently. Click **Update the stale ones** or **Check in on all**. For each one, enter the value and click **Save and next**, or **Unchanged** or **Skip**.
- For a liability, enter the lender, original balance, interest rate, monthly payment and dates. The forecast uses the payment.
- For an asset, **Events** holds planned buys and sells.
- The **Share prices** tab lists prices that are missing. Enter them and click **Save prices**.

### Import

Drop files from your bank, card or payroll and review them before anything is saved.

1. Click **Choose files** or drop files on **Drop files here**: CSV, Excel, OFX/QFX, PDF, text, or a photo when AI is available. Up to 20 MB each.
2. Pick the **Account**, or leave "Work it out". Pick **What is it?** (statement, receipt, pay stub), or leave "Work it out".
3. Review the rows. Each row says where its values came from: your earlier choice, a rule, the bank's category, the document, or an AI suggestion. Use the filters (**Needs review**, **Chosen by AI**, **Duplicates**, **Transfers**, **Skipped**) to find rows that need a look.
4. Fix what's wrong. If the columns were misread, open the mapping panel and click **Re-read with these columns**. If money in and out are swapped, click **Flip signs**.
5. To change many rows, click **Change several rows**, pick rows or all that match, set a category, account or date, and click **Apply to N rows**.
6. Click **Import N items**.

After import, **See it in Plan** shows the entries and **Undo this import** removes them.

Transfers between your accounts and card payments are left unticked, so they don't count as spending. Duplicates are flagged across files: the same file twice, overlapping statements, a receipt and the card line for the same purchase.

A photo or scanned PDF needs the AI. If the server's AI is the home computer and it is off, the file shows "Waiting for the home computer" and is read when it comes back.

An **RSU grant notice** becomes one RSU grant in Plan. Type the **Ticker (not in the document)**, check the vests, and tick **Add to Plan**.

**Learned categories** lists the merchant categories the app remembers from your choices. Click **×** to forget one.

### Insights

What stands out: stale balances, net worth off plan, months that run negative, large events in the next 30 days, loan payoffs, missing share prices, imports waiting for review, and tax findings. Each item says what it is based on and has a button to act on it.

With AI available:

- **Ask about your numbers**: type a question such as "What is my net worth today?" and click **Ask**. The figures come from the app; the model only words the answer. Open **Figures this answer is based on** to check them.
- **Explain** on an item rewords it in plain language.

### Settings

- **General**: currency, locale, fiscal year start, default withholding, and when Insights speaks up (after how many days a balance is stale; how far off plan net worth may drift).
- **Categories**: add, edit or delete categories.
- **Backups**: the Google Cloud project and bucket, how often to back up, and how many to keep. **Back up now** makes one. **Restore points** lists them; **Restore** backs up the current data first, then replaces it.
- **Data**: **Export as JSON** downloads everything. **Import JSON** replaces everything with a file. **Clear All Data** backs up to Google Cloud first and deletes nothing if that backup fails.
- **This device**: which optional features work on the device in your hand, and why not if one doesn't. Click **Check again** after fixing something.
- **Activity**: every change, with when, who and what. Values are not recorded.

## What "normal" looks like

- Overview shows a net worth and "Nothing needs your attention", or a short list.
- The sidebar footer shows "AI ready" when a model is reachable. Without AI, AI controls are simply absent.
- If you save something another device changed after you opened the page, the app refuses the save and asks you to reload. That protects the other change.
- When a new version is running, a bar says "A new version is ready." Click **Reload**.

Problems: see [troubleshooting.md](troubleshooting.md).
