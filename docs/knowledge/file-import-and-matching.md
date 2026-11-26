# Reading bank files, receipts and pay stubs, and matching them to what you already have

## 1. What this is and why the project needs it

Typing every paycheck and card purchase by hand is the reason most people quit a finance tool. Banks will give you the data as files: spreadsheets, bank-format downloads, PDFs, even photos of receipts. Those files look different at every bank, and the same purchase can appear in three of them. The importer reads a file, works out which number is the date, the amount and the merchant, guesses a category, removes what you already have, and shows the result for you to approve. Nothing reaches your records until you accept it, and you can undo an accepted import. This note explains what these files contain, why they are hard to read, and the checks the code uses so a wrong guess is caught and shown instead of saved.

## 2. The ideas, built up from zero

### 2.1 Start with a bank statement

A paper statement is a list: date, description, amount, sometimes a running balance. The bank also offers the same list as a download. That download has no standard layout, so every bank invents its own. A program that reads it must answer four questions for every file:

1. What kind of file is this (spreadsheet, bank-format, PDF, photo)?
2. Which column is the date, the description and the amount?
3. Does a negative amount mean money out, or money in?
4. Is each row new to us, or already known?

The rest of this note follows those four questions.

### 2.2 What bank exports look like

**CSV.** CSV means "comma-separated values": one row per line, cells split by a delimiter. In practice the delimiter is sometimes a semicolon (common where a comma is the decimal mark), a tab or a vertical bar. Many banks put a few lines above the table ("Account: Everyday Checking ...1234", a download date). Some files have no header row at all. Excel files (.xlsx) are the same idea inside a zip container; the code reads the sheet with the most data rows.

**Sign conventions.** A bank account normally shows deposits as positive and spending as negative. Many credit card exports do the opposite: a purchase is a positive number, because it adds to what you owe, and a payment is negative. A program that assumes the bank convention would turn a card's groceries into income. Other files avoid signs: one column "Debit" and one column "Credit", or a "Details" column with the words DEBIT and CREDIT next to an unsigned amount.

**Number formats.** Writers disagree on how to write "minus twelve dollars": `-12.00`, `(12.00)` with parentheses (an accounting habit), `12.00-` with a trailing minus, `12.00 DR`, or a Unicode minus sign. CR means credit and DR means debit. In much of Europe the decimal mark is a comma and the thousands mark is a period: `1.234,56` means one thousand two hundred thirty-four and fifty-six hundredths. A lone `1,234` is a puzzle: one thousand two hundred thirty-four, or one and 234 thousandths? The code reads it as thousands unless the file as a whole shows a comma before two-digit cents.

**Dates.** `03/04/2026` is March 4 in the United States and April 3 in most other places. If every date in a file has a day of 12 or less, the file itself cannot say which. Some files give no year ("10/12") and rely on the statement period at the top.

**OFX, QFX and QBO.** These are bank-format files from the Open Financial Exchange specification. The OFX consortium published it, and it is now maintained by Financial Data Exchange (FDX). QFX is Intuit's variant and QBO is QuickBooks' variant. Both are OFX with small additions. Version 1 files are SGML: tags open but often never close, like `<TRNAMT>-12.30<FITID>A1`. Version 2 files are XML with closing tags. A file has a list of statement transactions (`STMTTRN`). Each has a type (`TRNTYPE`), a posting date (`DTPOSTED`, written `20261114120000[0:GMT]`), a signed amount (`TRNAMT`, negative for money out), a name and memo, and a financial-institution transaction id (`FITID`). The id is unique within one account at one bank and is what makes de-duplication reliable. The ledger balance (`LEDGERBAL`) holds an amount (`BALAMT`) and the date it applies to (`DTASOF`). OFX is the most trustworthy source: the sign, date and amount are never ambiguous.

**PDF statements.** A PDF may carry real text, which a program can pull out, or it may be a scan, which is only a picture. A scan needs reading by a vision model or character recognition, and that step can misread digits. The code treats a PDF as text if it finds at least 40 non-space characters, and otherwise as scanned pages (at most 5, one image per page).

**Receipts.** A receipt is a short list of items followed by a block that must add up: subtotal + tax + tip = total. This arithmetic is the best check we have. If the numbers on the page satisfy it, a misread is very unlikely.

**Pay stubs.** A pay stub also has a built-in equation: gross pay - deductions = net pay. Gross pay is the full amount earned. Deductions include taxes (federal income tax, Social Security, Medicare), benefits (health insurance), and savings taken before you see the money, such as a pre-tax 401(k) contribution, which is a retirement saving that lowers taxable pay. Net pay is what lands in your bank. Each line usually has two columns: this period and year to date (YTD). The first column is the one we need. Many employers also add a matching contribution to your 401(k). It is paid by the employer, is not part of gross pay, and appears in a separate block.

**Equity documents.** Employees at some companies receive restricted stock units (RSUs): a promise of shares that arrive ("vest") on set dates. A grant notice lists the grant date, the total units and the vest dates and quantities. A release summary lists what already vested, the share price on that day and the shares withheld for tax. The importer reads the grant notice only. It stores shares in thousandths (`MILLI = 1000`) so fractional shares stay exact integers.

### 2.3 From a table to transactions

The importer takes four steps. First it finds the header row, skipping lines above it, by looking for a row of mostly words followed within three rows by a row containing a date or an amount. If none exists it names columns "Column 1", "Column 2", and so on.

Second, it assigns roles to columns. It tries, in order: a layout saved from an earlier import of the same header row (keyed by a hash of the header names); rules that match header words ("posting date", "description", "amount", "debit", "credit", "balance") and check what the cells look like; and finally a small language model that sees column profiles and a few rows. Whatever layout wins is applied to every row by plain code, so the model never touches an individual amount.

Third, it settles the sign. If the file has a direction column or a debit and a credit column, the sign is known. Otherwise one amount column has to be read as either "negative is money out" or the reverse. The code looks at rows whose description makes the direction obvious (a shop, a payroll deposit, "payment thank you") and counts how many agree with the normal convention. If the rows that disagree outnumber twice the rows that agree, the file is flipped. If the rows are not telling, a second rule applies: when 85% or more of the amounts are positive and the account is a card, positive means money out.

Fourth, it parses each cell with `Decimal`, never a float, into signed integer cents. `-8217` is -$82.17. Summary lines ("Total", "Beginning balance") are dropped. A balance column becomes a proposed balance snapshot taken from the newest row.

### 2.4 Duplicates

Duplicates arrive in several ways: you drop the same file twice, two statements overlap by a week, a receipt photo and the card line describe the same purchase, a pay stub and the bank deposit describe one paycheck. The project uses layers, strongest first.

- **Bank id.** The `FITID` of an OFX row, compared within the same account. If we have seen it, it is a duplicate.
- **Fingerprint.** A short hash of account, date, amount and a cleaned merchant name. If a file has two identical coffees on one day, a counter makes them two different fingerprints, so the second coffee is not lost; a re-read of the same file gives the same pair.
- **Near match.** An entry already in your records with the exact same amount in cents, in the same account (when both are known), dated within 3 days. The slack exists because a card posts a day or three after the receipt date. A near match is called a "possible duplicate", because two real purchases can look alike: it is accepted as a match when the other entry was typed in by hand, or comes from a receipt or pay stub, or the two descriptions share a merchant word.

A match sets a flag on the row and, by default, the row is unticked. You decide.

### 2.5 Transfers and card payments

Moving $500 from checking to savings shows up twice: a -$500 line in one account and +$500 in the other. Paying a card from checking shows up as -$612.40 in checking and a payment on the card. Neither is spending or income, and counting them would double the apparent flow. The importer marks them in two ways. First, by words: "transfer", "autopay", "payment thank you", "card payment", and a bank category of "payment" or "transfer". Second, by pairing: if a row looks like a transfer and another account already holds the same amount with the opposite sign within 3 days, it is the other side of that transfer. Person-to-person apps (Zelle, Venmo, Cash App) are not treated as transfers by words alone, because a Zelle "transfer" is usually a payment to someone else.

### 2.6 Categories

A category is a label such as groceries or rent. The code chooses from the cheapest, surest source down:

1. A category you picked for this merchant earlier ("learned").
2. A category the document itself supports, such as salary on a pay stub, or one the model suggested after reading a receipt.
3. A built-in keyword rule: an ordered list of patterns, first match wins, with a direction (an income category cannot be money out).
4. The bank's own category column, mapped to ours.
5. The language model, once per merchant, choosing from a fixed list.

Anything left over is flagged "uncategorized".

A merchant key makes grouping possible. "POS PURCHASE WHOLE FOODS MKT #10234 SEATTLE WA" becomes `WHOLE FOODS MKT`: noise words, anything with a digit and trailing US state codes are removed, and at most 3 words are kept. Learned categories, fingerprints and suggested rules all depend on this key.

### 2.7 Suggested recurring rules

A subscription shows up as the same merchant, a steady amount and a steady gap. The importer groups rows by merchant and direction, and suggests a rule when the amounts stay within 15% of the median and the gaps fit one of five frequencies. It proposes the next expected date as the start. A suggestion is off by default; you tick it. This turns a few months of history into the schedule that the forecast uses (see `planning-and-reconciliation.md`).

### 2.8 Review, commit, undo

Every row lands in a review screen with its source and flags. The importer writes rows only when you press Import. A commit creates change events (imported), balance snapshots, rules and RSU grants, and records each created id. Undo deletes exactly those records and puts the file back in review. This works like a staging table: the file is a proposal, not an action. The analogy stops at one point: a staging table in a database is usually exact, while here the proposal contains guesses, and the flags are how the guesses are shown.

## 3. Rules of thumb and typical numbers

All values below are code constants unless noted. Each is "project choice" with the file and function that holds it.

| Item | Value | Source |
|---|---|---|
| Date slack for duplicates and transfers | 3 days | project choice, `importer/matching.py` (`DATE_SLACK`) |
| Duplicate amount match | exact cents, no tolerance | project choice, `importer/matching.py:refresh_matches` |
| Fingerprint | first 40 hex characters of SHA-256 | project choice, `importer/matching.py:fingerprint` |
| Positive-share rule | 85% or more positive | project choice, `importer/statements.py:detect_sign` |
| Sign vote | needs 2+ recognisable rows and a 2-to-1 majority | project choice, `importer/statements.py:detect_sign` |
| Receipt sum check | within 2 cents | project choice, `importer/documents.py:from_receipt` |
| Pay stub sum check | within 100 cents ($1) | project choice, `importer/documents.py:from_payslip` (`reconciles`) |
| Salary rule mismatch warning | more than the larger of $1 or 1% | project choice, `importer/documents.py:from_payslip` |
| Suggested rule: amount spread | within 15% of the median | project choice, `importer/statements.py:suggest_rules` |
| Suggested rule: gap | weekly 7 +-1, biweekly 14 +-2, monthly 30.4 +-4, quarterly 91 +-8, annual 365 +-20 days; every gap within the tolerance + 1 | project choice, same function (`_FREQS`) |
| Two occurrences are enough only for | monthly with identical amounts | project choice, same function |
| Pay period to frequency | 6-8 days weekly, 13-15 biweekly, 27-32 monthly; semi-monthly not supported | project choice, `importer/documents.py:pay_frequency` |
| Year for dates without one | inside the statement period, +-7 days; else not in the future | project choice, `importer/parsing.py:year_resolver` |
| Date column accepted | 80% of cells parse | project choice, `importer/statements.py:heuristic_map` |
| Column layout trust | 1.0 if 3 or more roles matched by header name, else 0.7 (then the model is asked) | project choice, `importer/statements.py:heuristic_map` |
| Row confidence: OFX / table by rules / statement text / model-found text | 0.97 / 0.95 / 0.85 / 0.7 | project choice, `importer/statements.py` |
| Model category confidence | capped at 0.9, floored at 0.3; under 0.6 raises a "low confidence" flag | project choice, `importer/categorize.py` (`LOW_CONFIDENCE`) |
| Receipt confidence: rules and model agree / model only / disagree | 0.95 / 0.75 / 0.55 | project choice, `importer/documents.py:from_receipt` |
| Pay stub confidence: reconciles / unflagged / flagged | 0.95 / 0.7 / 0.5 | project choice, `importer/documents.py:from_payslip` |
| Scanned PDF | at most 5 pages; image long side 1600 px | project choice, `importer/extract.py` |
| Header search | first 40 rows | project choice, `importer/statements.py:detect_header` |

Typical real-world ranges, such as how many rows a statement holds or how many days a card takes to post: source not recorded. The 1-to-3 day posting delay is stated in a code comment in `importer/matching.py` and is not backed by a cited source.

## 4. Common misconceptions and edge cases

- "A negative number is always a purchase." On many card exports it is a payment or a refund.
- "The AI reads my amounts." It does not. It may pick columns or suggest a category, but the numbers are parsed by code, and any amount a model reports must appear in the document text.
- "Same amount, same day, same store means duplicate." Not always: two real coffees look identical. The counter in the fingerprint keeps both inside one file. Across files, only the near-match rule applies, and it asks you.
- "A matching amount near a transfer is a transfer." The pair has to be in different accounts, opposite signs, and the words have to look like a transfer.
- "A credit card statement's balance is my balance." It is money owed. The importer does not offer it as a cash balance (flag `card_balance`).
- "Net pay is the paycheck." True for the bank deposit. The 401(k) contribution, employer match and stock-plan deductions never reach the bank. The importer adds a second row for retirement contributions (your deduction plus the employer match) into your retirement account. Other deductions, such as an ESPP deduction, stay in the note and are not moved anywhere.
- "A date like 03/04/2026 has one meaning." It depends on locale. When every date in a file is ambiguous, the importer reads it with your locale setting and warns.
- Semi-monthly pay (twice a month) has no matching rule frequency. The pay stub imports, but no salary rule is suggested.
- A tax line like "Sales Tax 10.25%" holds two numbers. The reader ignores the percentage (it requires two decimals and rejects `%`), so tax is 6.20.
- Receipt "TOTAL" lines compete with "Subtotal" and "Total savings"; the code excludes the latter and prefers "grand total", "total due", "amount due".
- An old Excel `.xls` file is refused with instructions to save as .xlsx or .csv; an encrypted PDF is refused unless it has an empty password.
- Files without an account: a statement cannot be committed until you choose an account.

## 5. How the project uses it

Pipeline (`importer/pipeline.py:process_batch`): read the file (`extract.load_document`), classify it (`documents.classify`), read it by type (`statements.from_ofx`, `from_table`, `from_text`; `documents.from_receipt`, `from_payslip`; `equity.from_grant_notice`), apply a flip-signs override if set, categorize (`categorize.categorize`), suggest rules (`statements.suggest_rules`), suggest an account (`matching.suggest_account`), and mark duplicates and transfers (`matching.refresh_matches`). The batch then waits in status "review". `commit_batch` re-runs `refresh_matches` just before writing; if new duplicates appear (another file was committed meanwhile) it unticks them and refuses once, unless forced. `undo_batch` removes created records.

Where each piece lives:

- `importer/parsing.py`: amounts (`parse_amount`, `find_amounts`, `detect_decimal_comma`), dates (`parse_date`, `detect_date_format`, `year_resolver`), merchants (`merchant_key`, `merchant_similar`).
- `importer/extract.py`: files to documents; `parse_ofx` handles SGML and XML.
- `importer/statements.py`: columns, signs, statement text, suggested rules.
- `importer/documents.py`: classification, receipts, pay stubs. `importer/equity.py`: RSU grant notices.
- `importer/taxonomy.py`: starter categories, keyword rules, bank-category map, direction check.
- `importer/matching.py`: duplicates, transfers, balance checks, account suggestion.
- `importer/core.py`: the flag sets. `SKIP_FLAGS` rows start unticked; `REVIEW_FLAGS` rows go in the "needs review" filter.

What was left out, and why: stock-plan files other than RSU grant notices are recognised and refused with advice (reading them is not built); currencies are not converted (amounts are taken in the file's currency); semi-monthly pay has no rule frequency; photos and scanned PDFs need the model (the code says so and, when the home computer is off, waits).

Design record: [DECISIONS](../design/DECISIONS.md), [import plan](../design/plans/2026-11-22-import-statements-local-ai.md), [paging and bulk edit](../design/plans/2026-11-24-import-paging-bulk-edit.md), [equity documents](../design/plans/2026-11-24-equity-document-type.md), [RSU grant notice](../design/plans/2026-11-24-rsu-grant-notice-import.md), [tax treatments and transfers](../design/plans/2026-11-22-tax-treatments-taxes-page.md).

Test names that map to this note: in `tests/test_import_parsing.py`, `test_parse_amount`, `test_decimal_comma_forced_and_detected`, `test_find_amounts_ignores_dates_cards_and_percentages`, `test_detect_date_format_us_and_ambiguous`, `test_yearless_dates_use_statement_period_across_new_year`, `test_merchant_key`. In `tests/test_import_readers.py`, `test_card_export_sign_is_detected_from_the_rows`, `test_heuristic_map_debit_credit_columns`, `test_european_csv_without_ai_uses_content_rules`, `test_ofx_parse`, `test_card_statement_text_uses_sections_and_skips_card_balance`, `test_receipt_and_payslip_rules`. In `tests/test_import_api.py`, `test_receipt_then_card_export_is_caught_as_duplicate`, `test_payslip_then_statement_flags_the_paycheck`, `test_commit_rechecks_duplicates_added_meanwhile`.

## 6. What we found

All commands were run on 2026-11-24 from the repository root of this worktree.

**The tests pass.**

```
python -m pytest tests/test_import_parsing.py tests/test_import_readers.py -q
python -m pytest tests/test_import_api.py tests/test_import_equity.py tests/test_import_ai_guardrails.py -q
```

Results: 52 passed, then 45 passed.

**Amount parsing, run on real strings.**

```
python -c "from importer.parsing import parse_amount as p; print([p(s) for s in ['(12.00)','12.00-','12.00 CR','12.00 DR','1.234,56','12,50','1,234.56','1,234']])"
```

Output: `[-1200, -1200, 1200, -1200, 123456, 1250, 123456, 123400]`. The lone `1,234` is read as $1,234.00. With `decimal_comma=True` it is $1.23, which the test `test_decimal_comma_forced_and_detected` confirms.

**Worked example: `docs/sample-data/imports/checking-activity.csv`** (fictional data; 15 transactions and a balance column, preceded by two lines of preamble). Command:

```
python - <<'EOF'
import tempfile
from app import create_app
from config import TestingConfig
from importer.core import Ctx
from importer.llm import LLMClient
from importer.extract import load_document
from importer.statements import from_table, suggest_rules
from importer.categorize import categorize
from importer.taxonomy import allowed_categories
class Cfg(TestingConfig): IMPORT_STORAGE_DIR = tempfile.mkdtemp()
with create_app(Cfg).app_context():
    ctx = Ctx(llm=LLMClient(provider="off"), ai_ok=False)
    props = from_table(load_document(open("docs/sample-data/imports/checking-activity.csv","rb").read(),"c.csv").tables[0], ctx)
    categorize(props, ctx, allowed_categories([]), {}, {})
    for p in props: print(p.date, p.amount, p.category, p.category_source, p.flags)
    for s in suggest_rules(props, [], None): print("RULE", s.date, s.description, s.amount, s.frequency, s.note)
EOF
```

What it showed. The preamble ("Account: Everyday Checking ...1234") was skipped and kept as an account hint ending 1234. The header was found right after the preamble. The columns were mapped by rules with full trust: date = "Posting Date", description, amount, balance, and the "Details" column (DEBIT/CREDIT) as direction. Because a direction column exists, no sign guessing was needed. Examples of the 16 proposals:

- `2026-11-20 -8217 groceries keyword`: "WHOLE FOODS MKT #10234 SEATTLE WA" became the key `WHOLE FOODS MKT` (-$82.17).
- `2026-11-14 325000 salary keyword`: the payroll deposit (+$3,250.00).
- `2026-11-14 -50000 transfer keyword`: "ONLINE TRANSFER TO SAV ..." (-$500.00). Flagged as a transfer, so unticked by default.
- `2026-11-05 -61240 transfer keyword`: the card autopay (-$612.40), also a transfer.
- `2026-10-16 -6000 None`, flag `uncategorized`: a Zelle payment to a person; keywords refuse to guess.
- A last proposal, the balance snapshot dated 2026-11-20 for $4,120.55 (from the newest row's balance).

Two rules were suggested. "Acme Corp Payroll", biweekly, +$3,250.00, next date 2026-11-28, "Seen 3 times". "Netflix", monthly, -$15.49, next date 2026-12-19, "Seen 2 times" (two rows are enough only because the amounts are identical and monthly). Both are unticked.

**Sign detection on `card-activity.csv`.** Headers `Date, Description, Amount`; purchases are positive (`34.99`), the autopay is `-612.40`. Command (the first five rows of the file):

```
python -c "from importer.statements import detect_sign as d; from importer.parsing import parse_amount as p; r=[('34.99','AMAZON.COM*2K4L59 AMZN.COM/BILL WA'),('52.10','SHELL OIL 57444 SEATTLE WA'),('23.40','MOD PIZZA 0123 SEATTLE WA'),('-612.40','AUTOPAY PAYMENT - THANK YOU'),('61.25',\"TRADER JOE'S #131 SEATTLE WA\")]; print(d([p(a) for a,_ in r],[x for _,x in r]))"
```

Result: `positive_is_money_out`, "5 of 5 recognisable rows", confident (all ten rows of the full file also agree). The refund line `-19.99` therefore became +$19.99 income, which `test_card_export_rows_come_out_as_spending` asserts.

**Bank category column on `rewards-card.csv`** (separate Debit and Credit columns, a "Category" column). With no model, "Payment/Credit" mapped to `transfer` (source `bank`), "Merchandise" to `shopping` (`bank`), and "Grocery" matched the keyword rule first (`groceries`, source `keyword`) because keywords come before the bank column.

**Receipt and pay stub arithmetic, on the sample files.** `receipt.txt`: subtotal 60.50 + tax 6.20 + tip 12.00 = 78.70, in cents 6050 + 620 + 1200 = 7870, equal to the total the reader found. `paystub.txt`: gross 5,000.00 - deductions 1,750.00 = net 3,250.00. The 1,750.00 is the sum of the seven deduction lines: 640.00 + 310.00 + 72.50 + 14.50 + 400.00 + 163.00 + 150.00. The 401(k) deduction (400.00) plus the match (200.00) would be proposed as 600.00 into a retirement account. Pay period 10/26 to 11/08 is 14 days, so `pay_frequency` says biweekly (verified: `python -c "from importer.documents import pay_frequency as f; print(f('2026-10-26','2026-11-08'))"`).

**OFX, version 1 and version 2.** `bank-statement.ofx` is SGML (`OFXHEADER:100`, `VERSION:102`). `parse_ofx` returned amounts 50000, 1241, -500, FITID `202611140001` for the first, and balance 1850741 dated 2026-11-21. A hand-written XML (version 2 style) file with closing tags also parsed: amount -1230, FITID `A1`, balance 10000.

**Date ambiguity.** `detect_date_format(['03/04/2026','05/06/2026'])` returns `('%m/%d/%Y', 1.0, True)`: ambiguous, month-first chosen. With a value such as `25/06/2026` it returns `%d/%m/%Y`, not ambiguous.

**Finding: unused constant.** `importer/categorize.py` defines `CONF = {"learned": 0.97, "document": 0.9, "keyword": 0.85, "bank": 0.75}` as the confidence for each category source. Command: `grep -rn "CONF\b" --include=*.py importer tests api` finds only the definition. The numbers are never applied. The order of sources (learned, document, keyword, bank, model) is real; the numbers are dead code. Only the model path changes a row's confidence (cap 0.9, floor 0.3).

**Finding: the code's header comment on categorization agrees with the code.** The order in the docstring of `importer/categorize.py` matches the branches in `categorize()`. One extra: a category with source `ai` from an earlier pass is kept without asking again.

**Finding: README says what the code does.** The README's "File import" section describes receipts and pay stubs as checked by arithmetic, and `documents.py` does just that. Its claim that "a pay stub and the payroll deposit" are caught as duplicates matches the test `test_payslip_then_statement_flags_the_paycheck`.

## 7. Open questions

- Remove `CONF` or use it? If the numbers are meant to rank sources, the review screen should show them. If not, delete the constant so no one trusts it.
- Is a 3-day slack right for card statements that post on a weekend or after a holiday? No evidence in the repository; no measurement of real posting delays.
- Exact-cent matching cannot catch a tip added after authorisation (a restaurant receipt for 78.70 against a card line for 83.20). Should near matches allow a tip-sized difference?
- Suggested rules take the next date from the last seen date and, for months, clamp the day (`_safe_date`). The engine that later uses the rule skips short months instead (see `planning-and-reconciliation.md`, finding 1). The two ends disagree.
- Semi-monthly pay (twice a month) has no frequency. A rule type for it would remove a common gap.
- Currency: files in other currencies import as if they were the account's currency. Nothing warns, except that OFX carries `CURDEF`, which the code reads but does not check.

## 8. Sources and further reading

- Project files: `importer/parsing.py`, `importer/extract.py`, `importer/statements.py`, `importer/matching.py`, `importer/documents.py`, `importer/taxonomy.py`, `importer/categorize.py`, `importer/equity.py`, `importer/pipeline.py`, `importer/core.py`.
- `README.md`, section "File import" (what goes where, and the five-step "rules first" order).
- Sample files: `docs/sample-data/imports/` (all fictional).
- Open Financial Exchange (OFX) specification, published by the OFX consortium and now maintained by Financial Data Exchange. Search for "OFX specification" together with those names. It defines `STMTTRN`, `TRNAMT`, `FITID` and `LEDGERBAL`.
- RFC 4180, "Common Format and MIME Type for Comma-Separated Values (CSV) Files", Internet Engineering Task Force. It notes that CSV has no single true standard, which is why this importer guesses.
- Python `decimal` module documentation, for exact decimal arithmetic.

## Changes

2026-11-24: first version.
