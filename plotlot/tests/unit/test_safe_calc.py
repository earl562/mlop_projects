"""Unit tests for the sandboxed chat calculator (safe_calc)."""

from __future__ import annotations

import pytest

from plotlot.pipeline.safe_calc import CalcError, safe_calculate


class TestArithmetic:
    @pytest.mark.parametrize(
        "expr,expected",
        [
            ("7 * 750000", 5_250_000.0),  # units × exit
            ("7710 / 1000", 7.71),  # lot area ÷ min-lot → density
            ("(4500000 - 240000) / 7", (4_500_000 - 240_000) / 7),  # per-unit residual
            ("1500000 - 444900", 1_055_100.0),  # gap vs asking
            ("40000 * 6", 240_000.0),
            ("350 * 7710", 2_698_500.0),
            ("-5 + 3", -2.0),
            ("2 ** 3", 8.0),
            ("17 // 5", 3.0),
            ("17 % 5", 2.0),
        ],
    )
    def test_evaluates_arithmetic(self, expr, expected):
        assert safe_calculate(expr) == pytest.approx(expected)


class TestSecurityAndValidation:
    @pytest.mark.parametrize(
        "expr",
        [
            '__import__("os").system("ls")',
            "open('/etc/passwd')",
            "x + 1",  # bare name
            "price * 2",  # name
            "[i for i in range(10)]",
            "().__class__",
            "1 .__class__",
            "lambda: 1",
        ],
    )
    def test_rejects_non_arithmetic(self, expr):
        with pytest.raises(CalcError):
            safe_calculate(expr)

    def test_rejects_division_by_zero(self):
        with pytest.raises(CalcError):
            safe_calculate("5 / 0")

    def test_rejects_huge_exponent_dos(self):
        with pytest.raises(CalcError):
            safe_calculate("9 ** 9 ** 9")

    def test_rejects_empty_and_blank(self):
        with pytest.raises(CalcError):
            safe_calculate("")
        with pytest.raises(CalcError):
            safe_calculate("   ")

    def test_rejects_overlong_expression(self):
        with pytest.raises(CalcError):
            safe_calculate("1+" * 200 + "1")

    def test_rejects_booleans(self):
        with pytest.raises(CalcError):
            safe_calculate("True + 1")
