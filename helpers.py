"""
Helper utility functions for the Accounting Desktop Application.
Contains common utility functions used throughout the application.
"""

import os
import sys
from datetime import datetime
from typing import Optional, Union, List, Dict, Any
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from config import (
    CURRENCY_SYMBOL,
    DATE_FORMAT,
    DB_DATE_FORMAT,
    DECIMAL_PLACES,
    PYTHON_DB_DATE_FORMAT,
    PYTHON_DISPLAY_DATE_FORMAT,
)


def format_currency(amount: Union[float, int, Decimal, str], currency_symbol: str = CURRENCY_SYMBOL) -> str:
    """Format amount as currency string."""
    try:
        decimal_amount = Decimal(str(amount))
        formatted = f"{currency_symbol}{decimal_amount:.{DECIMAL_PLACES}f}"
        return formatted
    except (InvalidOperation, ValueError):
        return f"{currency_symbol}0.00"


def parse_currency(currency_string: str) -> Decimal:
    """Parse currency string to Decimal."""
    # Remove currency symbols and whitespace
    cleaned = currency_string.replace(CURRENCY_SYMBOL, "").replace("$", "").replace("£", "").replace("¥", "").strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0.00")


def format_date(date_obj: Optional[datetime] = None, date_format: str = DATE_FORMAT) -> str:
    """Format date object to string."""
    if date_obj is None:
        date_obj = datetime.now()
    return date_obj.strftime(date_format)


def parse_date(date_string: str, date_format: str = DATE_FORMAT) -> Optional[datetime]:
    """Parse date string to datetime object."""
    for fmt in (date_format, PYTHON_DISPLAY_DATE_FORMAT, "%d-%m-%Y", "%d/%m/%Y", PYTHON_DB_DATE_FORMAT):
        try:
            return datetime.strptime(date_string, fmt)
        except ValueError:
            continue
    return None


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for development and PyInstaller."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)


def ensure_directory_exists(directory_path: str) -> bool:
    """Ensure directory exists, create if it doesn't."""
    try:
        os.makedirs(directory_path, exist_ok=True)
        return True
    except OSError:
        return False


def safe_filename(filename: str) -> str:
    """Create safe filename by removing/replacing problematic characters."""
    import re
    # Remove invalid characters
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove leading/trailing spaces and dots
    safe_name = safe_name.strip(' .')
    # Ensure it's not empty
    return safe_name if safe_name else "unnamed"


def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate string to specified length with suffix."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def validate_email(email: str) -> bool:
    """Basic email validation."""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_phone(phone: str) -> bool:
    """Basic phone number validation."""
    import re
    # Remove common formatting characters
    cleaned = re.sub(r'[\s\-\(\)]', '', phone)
    # Check if it's all digits and reasonable length
    return cleaned.isdigit() and 10 <= len(cleaned) <= 15


def calculate_percentage(part: Union[float, int], total: Union[float, int]) -> float:
    """Calculate percentage safely."""
    if total == 0:
        return 0.0
    return (part / total) * 100


def deep_merge_dict(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries."""
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def flatten_dict(d: Dict[str, Any], parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
    """Flatten nested dictionary."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def get_file_size_mb(file_path: str) -> float:
    """Get file size in megabytes."""
    try:
        size_bytes = os.path.getsize(file_path)
        return size_bytes / (1024 * 1024)
    except OSError:
        return 0.0


def is_valid_decimal(value: str) -> bool:
    """Check if string can be converted to Decimal."""
    try:
        Decimal(value)
        return True
    except (InvalidOperation, ValueError):
        return False


def clean_numeric_input(value: str) -> str:
    """Clean numeric input by removing invalid characters."""
    import re
    # Keep digits, decimal point, and minus sign
    cleaned = re.sub(r'[^\d.-]', '', value)
    # Ensure only one decimal point
    parts = cleaned.split('.')
    if len(parts) > 2:
        cleaned = parts[0] + '.' + ''.join(parts[1:])
    return cleaned


def generate_unique_id(prefix: str = "", length: int = 8) -> str:
    """Generate unique ID with optional prefix."""
    import uuid
    unique_str = str(uuid.uuid4()).replace('-', '')[:length]
    return f"{prefix}{unique_str}" if prefix else unique_str


def log_message(message: str, level: str = "INFO") -> None:
    """Simple logging function."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {level}: {message}")


def to_decimal(value: Any) -> Decimal:
    """
    Safe financial decimal conversion for accounting engine.
    Returns Decimal('0.00') for blank/invalid values.
    Quantized to 2 decimal places with ROUND_HALF_UP for commercial rounding.

    Args:
        value: Any value to convert (str, int, float, Decimal, None)

    Returns:
        Decimal quantized to 2 decimal places
    """
    try:
        if value is None:
            return Decimal("0.00")

        value_str = str(value).strip()

        if value_str == "":
            return Decimal("0.00")

        return Decimal(value_str).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")
