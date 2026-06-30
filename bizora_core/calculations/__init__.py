"""
Shared Billing Calculation Engine for Accounting Desktop Application.

This package provides centralized, UI-independent billing calculations
for Sales, Purchase, Sales Return, and Purchase Return modules.

All GST formulas are centralized here - no duplication in UI files.
"""

from .billing_models import (
    BillingRowInput,
    BillingRowResult,
    BillingFooterInput,
    BillingFooterResult,
    GstNature,
    TaxMode,
)

from .gst_rules import normalize_gst_for_nature, get_active_tax_percentages

from .row_calculator import calculate_billing_row

from .footer_calculator import calculate_billing_footer, quick_calculate_footer

from .module_wrappers import (
    calculate_sales_bill,
    calculate_purchase_bill,
    calculate_sales_return,
    calculate_purchase_return,
)

from .validation import (
    safe_float,
    safe_positive_float,
    format_currency,
    format_number,
    round_amount,
)

__all__ = [
    # Models
    'BillingRowInput',
    'BillingRowResult',
    'BillingFooterInput',
    'BillingFooterResult',
    'GstNature',
    'TaxMode',
    # GST Rules
    'normalize_gst_for_nature',
    'get_active_tax_percentages',
    # Calculators
    'calculate_billing_row',
    'calculate_billing_footer',
    'quick_calculate_footer',
    # Module Wrappers
    'calculate_sales_bill',
    'calculate_purchase_bill',
    'calculate_sales_return',
    'calculate_purchase_return',
    # Validation
    'safe_float',
    'safe_positive_float',
    'format_currency',
    'format_number',
    'round_amount',
]
