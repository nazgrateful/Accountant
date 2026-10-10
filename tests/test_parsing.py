from datetime import date

import pytest

from ledgerlens.extract.parsing import detect_currency, find_amounts, parse_amount, parse_date


@pytest.mark.parametrize("raw, expected", [
    ("1,234.56", 1234.56), ("$1,234.56", 1234.56), ("(45.00)", -45.0), ("-12.30", -12.3),
    ("12.30-", -12.3), ("150.00 DR", -150.0), ("150.00 CR", 150.0), ("1.234,56", 1234.56),
    ("12,50", 12.5), ("1,250", 1250.0), ("€ 99", 99.0), ("", None), ("abc", None), (None, None),
    (float("nan"), None), (7, 7.0),
])
def test_parse_amount(raw, expected):
    assert parse_amount(raw) == expected


def test_find_amounts_skips_quantities_and_dates():
    assert find_amounts("Widget 3 4.50 13.50") == [4.5, 13.5]
    assert find_amounts("Posted 15.03.2024 fee 5.00") == [5.0]
    assert find_amounts("Total $1,234") == [1234.0]


@pytest.mark.parametrize("raw, day_first, expected", [
    ("2024-01-05", False, date(2024, 1, 5)),
    ("01/05/2024", False, date(2024, 1, 5)),
    ("01/05/2024", True, date(2024, 5, 1)),
    ("Jan 5, 2024", False, date(2024, 1, 5)),
    ("5 January 2024", False, date(2024, 1, 5)),
    ("March 3rd, 2024", False, date(2024, 3, 3)),
    ("5-Mar-24", False, date(2024, 3, 5)),
    ("2024-01-05 00:00:00", False, date(2024, 1, 5)),
    ("not a date", False, None),
])
def test_parse_date(raw, day_first, expected):
    assert parse_date(raw, day_first) == expected


def test_detect_currency():
    assert detect_currency("Total $10.00 and $5") == "USD"
    assert detect_currency("Betrag 10,00 € EUR") == "EUR"
    assert detect_currency("no money here") is None
