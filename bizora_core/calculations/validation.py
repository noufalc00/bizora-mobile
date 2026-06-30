"""
Validation and Utility Module

Safe number conversion and validation helpers.
No UI dependencies.
"""

from typing import Optional, Union


def safe_float(value: any, default: float = 0.0) -> float:
    """
    Safely convert any value to float.

    Handles:
    - None -> default
    - Empty string -> default
    - Strings with currency symbols (₹, $, etc.)
    - Strings with commas
    - Strings with percentage signs
    - Already numeric values

    Args:
        value: Any value to convert
        default: Default value if conversion fails

    Returns:
        float value or default
    """
    if value is None:
        return default

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        # Remove common formatting characters
        cleaned = value.strip()
        cleaned = cleaned.replace('₹', '').replace('$', '').replace('€', '').replace('£', '')
        cleaned = cleaned.replace(',', '').replace('%', '').replace(' ', '')

        if cleaned == '' or cleaned.lower() == 'none':
            return default

        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return default

    return default


def safe_positive_float(value: any, default: float = 0.0) -> float:
    """
    Safely convert to float and ensure non-negative.

    Args:
        value: Any value to convert
        default: Default value if conversion fails or value is negative

    Returns:
        Non-negative float value or default
    """
    result = safe_float(value, default)
    return result if result >= 0 else default


def safe_int(value: any, default: int = 0) -> int:
    """
    Safely convert any value to int.

    Args:
        value: Any value to convert
        default: Default value if conversion fails

    Returns:
        int value or default
    """
    if value is None:
        return default

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if isinstance(value, str):
        cleaned = value.strip().replace(',', '').replace(' ', '')
        if cleaned == '' or cleaned.lower() == 'none':
            return default
        try:
            return int(float(cleaned))
        except (ValueError, TypeError):
            return default

    return default


def is_valid_quantity(value: any) -> bool:
    """
    Check if value is a valid quantity (> 0).

    Args:
        value: Value to check

    Returns:
        True if valid positive quantity
    """
    qty = safe_float(value)
    return qty > 0


def is_valid_rate(value: any) -> bool:
    """
    Check if value is a valid rate (>= 0).

    Args:
        value: Value to check

    Returns:
        True if valid non-negative rate
    """
    rate = safe_float(value)
    return rate >= 0


def is_blank_row(
    qty: any,
    rate: any,
    product_id: Optional[any] = None,
    product_name: Optional[str] = None
) -> bool:
    """
    Check if a row is effectively blank/empty.

    A row is blank if:
    - qty is 0 or None
    - rate is 0 or None
    - AND no product identification

    Args:
        qty: Quantity value
        rate: Rate value
        product_id: Optional product ID
        product_name: Optional product name

    Returns:
        True if row should be considered blank
    """
    qty_val = safe_float(qty)
    rate_val = safe_float(rate)

    has_qty = qty_val > 0
    has_rate = rate_val > 0
    has_product = product_id is not None or (product_name and str(product_name).strip())

    return not (has_qty and has_rate) and not has_product


def round_amount(amount: float, decimals: int = 2) -> float:
    """
    Round amount to specified decimal places.

    Args:
        amount: Amount to round
        decimals: Number of decimal places (default 2)

    Returns:
        Rounded amount
    """
    return round(amount, decimals)


def format_currency(amount: float, symbol: str = '₹', decimals: int = 2) -> str:
    """
    Format amount as currency string.

    Args:
        amount: Amount to format
        symbol: Currency symbol (default ₹)
        decimals: Number of decimal places

    Returns:
        Formatted currency string
    """
    return f"{symbol} {amount:,.{decimals}f}"


def format_number(amount: float, decimals: int = 2) -> str:
    """
    Format number with specified decimal places.

    Args:
        amount: Number to format
        decimals: Number of decimal places

    Returns:
        Formatted number string
    """
    return f"{amount:.{decimals}f}"


def validate_percentage(value: any, max_value: float = 100.0) -> float:
    """
    Validate and clamp percentage value.

    Args:
        value: Percentage value
        max_value: Maximum allowed value

    Returns:
        Validated percentage (0 to max_value)
    """
    pct = safe_float(value, 0.0)
    return max(0.0, min(pct, max_value))


def sum_safe(values: list, default: float = 0.0) -> float:
    """
    Safely sum a list of values, handling None and invalid entries.

    Args:
        values: List of values to sum
        default: Default for invalid entries

    Returns:
        Sum of valid values
    """
    total = 0.0
    for v in values:
        total += safe_float(v, default)
    return round(total, 2)
