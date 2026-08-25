"""Tests for vendor CSV parsers."""

import pytest

from utils import csv_importers as ci


def test_youtube_studio_sums_rows_case_insensitive():
    raw = b"Views,Likes,Comments\n1000,50,10\n2000,100,20\n"
    out = ci.parse_youtube_studio_csv(raw)
    assert out == {"views": 3000, "likes": 150, "comments": 30}


def test_youtube_studio_turkish_headers():
    raw = "izlenme,Beğeni,Yorum\n500,40,5\n".encode("utf-8")
    out = ci.parse_youtube_studio_csv(raw)
    assert out["views"] == 500 and out["likes"] == 40 and out["comments"] == 5


def test_youtube_studio_rejects_unrecognized_columns():
    with pytest.raises(ValueError):
        ci.parse_youtube_studio_csv(b"foo,bar\n1,2\n")


def test_shopify_orders_revenue_and_conversions():
    raw = b"Name,Total\n#1001,$120.50\n#1002,79.50\n"
    out = ci.parse_shopify_orders_csv(raw)
    assert out == {"conversions": 2, "revenue": 200.0}


def test_stripe_payouts_sums_gross():
    raw = b"id,Gross,Fee\np_1,100.00,3.00\np_2,50.00,1.50\n"
    out = ci.parse_stripe_payouts_csv(raw)
    assert out == {"revenue": 150.0}


def test_currency_symbols_and_thousands_separators():
    assert ci._to_float("$1,234.56") == 1234.56
    assert ci._to_int("1,000") == 1000
    assert ci._to_float("") == 0.0
    assert ci._to_int("not-a-number") == 0


def test_empty_csv_raises():
    with pytest.raises(ValueError):
        ci.parse_shopify_orders_csv(b"")
