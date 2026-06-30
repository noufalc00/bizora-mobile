"""
Common Finance Helper Module

Foundation helper file for Decimal-based money handling.
Provides safe, standardized financial calculation utilities.

All monetary values use Decimal for precision.
No float conversions for financial calculations.
"""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Union


# Constants for money handling
MONEY_ZERO = Decimal("0.00")
MONEY_QUANT = Decimal("0.01")


def to_decimal(value: Any) -> Decimal:
    """
    Safe financial decimal conversion.
    Returns Decimal('0.00') for blank/invalid values.
    Quantized to 2 decimal places with ROUND_HALF_UP for commercial rounding.

    Args:
        value: Any value to convert (str, int, float, Decimal, None)

    Returns:
        Decimal quantized to 2 decimal places
    """
    try:
        if value is None:
            return MONEY_ZERO

        value_str = str(value).strip()

        if value_str == "":
            return MONEY_ZERO

        return Decimal(value_str).quantize(
            MONEY_QUANT,
            rounding=ROUND_HALF_UP
        )

    except (InvalidOperation, ValueError, TypeError):
        return MONEY_ZERO


def money_round(value: Union[Decimal, str, int, float, None]) -> Decimal:
    """
    Round a monetary value to 2 decimal places using ROUND_HALF_UP.

    Args:
        value: Value to round (Decimal, str, int, float, or None)

    Returns:
        Decimal rounded to 2 decimal places, or MONEY_ZERO if invalid
    """
    try:
        if value is None:
            return MONEY_ZERO

        dec_value = Decimal(str(value)) if not isinstance(value, Decimal) else value
        return dec_value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    except (InvalidOperation, ValueError, TypeError):
        return MONEY_ZERO


def format_money(value: Union[Decimal, str, int, float, None], 
                currency_symbol: str = "₹") -> str:
    """
    Format a monetary value as a string with currency symbol.

    Args:
        value: Value to format
        currency_symbol: Currency symbol to prepend (default: ₹)

    Returns:
        Formatted string like "₹1,234.56" or "₹0.00" for invalid values
    """
    try:
        dec_value = to_decimal(value)
        # Format with comma separators for thousands
        formatted = f"{dec_value:,.2f}"
        return f"{currency_symbol}{formatted}"
    except Exception:
        return f"{currency_symbol}0.00"


def decimal_equal(left: Union[Decimal, str, int, float, None],
                  right: Union[Decimal, str, int, float, None]) -> bool:
    """
    Compare two monetary values for equality after rounding.

    Args:
        left: First value to compare
        right: Second value to compare

    Returns:
        True if values are equal after rounding to 2 decimal places
    """
    left_rounded = money_round(left)
    right_rounded = money_round(right)
    return left_rounded == right_rounded


def is_balanced(total_debit: Union[Decimal, str, int, float, None],
                total_credit: Union[Decimal, str, int, float, None]) -> bool:
    """
    Check if debit and credit totals are balanced (strict equality after rounding).

    Args:
        total_debit: Total debit amount
        total_credit: Total credit amount

    Returns:
        True if total_debit equals total_credit after rounding
    """
    return decimal_equal(total_debit, total_credit)


def calculate_round_off(amount: Union[Decimal, str, int, float, None]) -> Decimal:
    """
    Calculate round-off amount for a given total.
    Returns the difference between the amount and its rounded value.

    Args:
        amount: Amount to calculate round-off for

    Returns:
        Round-off amount (positive or negative)
    """
    try:
        dec_amount = to_decimal(amount)
        rounded = money_round(dec_amount)
        return rounded - dec_amount
    except Exception:
        return MONEY_ZERO


def safe_add(*values: Union[Decimal, str, int, float, None]) -> Decimal:
    """
    Safely add multiple monetary values.
    Returns MONEY_ZERO if all values are invalid.

    Args:
        *values: Variable number of values to add

    Returns:
        Sum of all values quantized to 2 decimal places
    """
    total = MONEY_ZERO
    for value in values:
        total += to_decimal(value)
    return total.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def safe_subtract(left: Union[Decimal, str, int, float, None],
                 right: Union[Decimal, str, int, float, None]) -> Decimal:
    """
    Safely subtract right from left.
    Returns MONEY_ZERO if either value is invalid.

    Args:
        left: Minuend
        right: Subtrahend

    Returns:
        Result of left - right quantized to 2 decimal places
    """
    left_dec = to_decimal(left)
    right_dec = to_decimal(right)
    result = left_dec - right_dec
    return result.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
