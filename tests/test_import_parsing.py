from datetime import date

import pytest

from importer.parsing import (
    amount_in_text, detect_date_format, detect_decimal_comma, find_amounts, find_dates, merchant_key, parse_amount,
    parse_date, year_resolver,
)


@pytest.mark.parametrize("raw,cents", [
    ("$1,234.56", 123456), ("-12.00", -1200), ("(12.00)", -1200), ("$(12.00)", -1200), ("12.00-", -1200),
    ("12.00 CR", 1200), ("12.00 DR", -1200), ("−45.67", -4567), ("1.234,56", 123456), ("12,50", 1250),
    ("1 234,56", 123456), ("USD 45.67", 4567), ("+3,250.00", 325000), ("0.10", 10), (45.67, 4567), (3, 300),
])
def test_parse_amount(raw, cents):
    assert parse_amount(raw) == cents


@pytest.mark.parametrize("raw", ["", None, "abc", "11/02/2026", "2026-11-02", "12.3.4", "N/A", True])
def test_parse_amount_rejects_non_amounts(raw):
    assert parse_amount(raw) is None


def test_decimal_comma_forced_and_detected():
    assert parse_amount("1,234", decimal_comma=False) == 123400
    assert parse_amount("1,234", decimal_comma=True) == 123
    assert detect_decimal_comma(["12,50", "-3,99", "1.000,00"]) is True
    assert detect_decimal_comma(["12.50", "-3.99", "1,000.00"]) is False


def test_find_amounts_ignores_dates_cards_and_percentages():
    line = "11/14/2026 VISA ****4821 Sales Tax 10.25% 6.20 TOTAL $78.70 (5.00)"
    assert [c for _, c in find_amounts(line)] == [620, 7870, -500]
    assert amount_in_text(-7870, line) and not amount_in_text(7800, line)


def test_detect_date_format_us_and_ambiguous():
    fmt, rate, ambiguous = detect_date_format(["11/30/2026", "11/02/2026"])
    assert (fmt, rate, ambiguous) == ("%m/%d/%Y", 1.0, False)
    fmt, _, ambiguous = detect_date_format(["30/11/2026", "02/11/2026"])
    assert fmt == "%d/%m/%Y" and not ambiguous
    fmt, _, ambiguous = detect_date_format(["01/02/2026", "03/04/2026"])
    assert fmt == "%m/%d/%Y" and ambiguous
    fmt, _, ambiguous = detect_date_format(["01/02/2026", "03/04/2026"], prefer_dayfirst=True)
    assert fmt == "%d/%m/%Y" and ambiguous


def test_dates_with_times_weekdays_and_names():
    assert parse_date("2026-11-02T14:33:00Z") == "2026-11-02"
    assert parse_date("Mon, Nov 2, 2026") == "2026-11-02"
    assert parse_date("02 Nov 2026") == "2026-11-02"
    assert parse_date("20261102") == "2026-11-02"


def test_yearless_dates_use_statement_period_across_new_year():
    resolve = year_resolver("2026-12-15", "2027-01-14")
    assert parse_date("12/20", "%m/%d", resolve) == "2026-12-20"
    assert parse_date("01/03", "%m/%d", resolve) == "2027-01-03"
    no_period = year_resolver(today=date(2027, 1, 5))
    assert parse_date("12/28", "%m/%d", no_period) == "2026-12-28"


def test_find_dates_in_text():
    assert [iso for _, iso in find_dates("Pay Date: 11/14/2026  Period 10/26/2026 - 11/08/2026")] == [
        "2026-11-14", "2026-10-26", "2026-11-08"]


@pytest.mark.parametrize("desc,key", [
    ("POS PURCHASE WHOLE FOODS MKT #10234 SEATTLE WA", "WHOLE FOODS MKT"),
    ("WHOLE FOODS MKT #99 PORTLAND OR", "WHOLE FOODS MKT"),
    ("SQ *BLUE BOTTLE COFFEE SEATTLE WA", "BLUE BOTTLE COFFEE"),
    ("NETFLIX.COM 866-579-7172 CA", "NETFLIX"),
    ("PAYPAL *SPOTIFY", "SPOTIFY"),
    ("ACME CORP PAYROLL PPD ID: 9876543210", "ACME CORP PAYROLL"),
])
def test_merchant_key(desc, key):
    assert merchant_key(desc) == key
