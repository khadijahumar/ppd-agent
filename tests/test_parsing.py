"""Tests for the number / range parser."""
from __future__ import annotations

import math

from ppd_agent.parsing import fmt_number, in_range, parse_number, parse_range


def test_parse_number_basic() -> None:
    assert parse_number("0,15") == 0.15
    assert parse_number("0.15") == 0.15
    assert parse_number("12,5 mm") == 12.5
    assert parse_number("0,030 %") == 0.03
    assert parse_number("< 10,000") == 10.0
    assert parse_number(">= 27") == 27.0
    assert parse_number("410 N/mm²") == 410.0
    assert parse_number(None) is None
    assert parse_number("nan") is None
    assert parse_number("-") is None


def test_parse_number_thousand_separator() -> None:
    # european: 1.200,5 -> 1200.5  (dot is thousand, comma is decimal)
    assert parse_number("1.200,5") == 1200.5
    # us: 1,200.5 -> 1200.5         (comma is thousand, dot is decimal)
    assert parse_number("1,200.5") == 1200.5
    # bare integer: 1200 -> 1200
    assert parse_number("1200") == 1200.0
    # ambiguous "1.200" alone is parsed as US decimal (1.2). The xlsx data
    # never has bare ambiguous strings — they always have units or another
    # separator, so this edge-case is acceptable.


def test_parse_number_passthrough() -> None:
    assert parse_number(42) == 42.0
    assert parse_number(3.14) == 3.14
    assert parse_number(float("nan")) is None


def test_parse_range_basic() -> None:
    rng = parse_range("0,000 - 2,999")
    assert rng is not None
    lo, hi = rng
    assert math.isclose(lo, 0.0, abs_tol=1e-6)
    assert math.isclose(hi, 2.999, abs_tol=1e-6)


def test_parse_range_exclusive_upper() -> None:
    rng = parse_range("7,000 - < 10,000")
    assert rng is not None
    lo, hi = rng
    assert math.isclose(lo, 7.0, abs_tol=1e-6)
    # exclusive: should be just under 10
    assert math.isclose(hi, 9.999, abs_tol=1e-3)


def test_in_range() -> None:
    assert in_range(5.0, (0.0, 10.0)) is True
    assert in_range(0.0, (0.0, 10.0)) is True   # inclusive default
    assert in_range(10.0, (0.0, 10.0)) is True
    assert in_range(-0.1, (0.0, 10.0)) is False
    assert in_range(10.1, (0.0, 10.0)) is False
    assert in_range(5.0, (None, 10.0)) is True  # open lower
    assert in_range(5.0, (0.0, None)) is True   # open upper
    assert in_range(None, (0.0, 10.0)) is False


def test_fmt_number() -> None:
    assert fmt_number(None) == "-"
    assert fmt_number(0.0) == "0"
    assert fmt_number(0.15) == "0.15"
    assert fmt_number(1234.5) == "1,234.5"
