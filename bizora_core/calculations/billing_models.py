"""
Billing Calculation Models

UI-independent dataclasses for billing calculations.
No PySide imports - pure Python data structures.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class GstNature(str, Enum):
    """GST transaction nature."""
    LOCAL = "Local"
    INTER_STATE = "Inter-state"


class TaxMode(str, Enum):
    """Tax calculation mode."""
    ADDITIVE = "additive"  # Tax added to taxable value
    DIVIDE = "divide"      # Tax included in total (reverse calc)


@dataclass
class BillingRowInput:
    """Input data for calculating a single billing row.

    All monetary values should be in base currency units (e.g., rupees).
    All percentages should be in percent units (e.g., 9 for 9%, not 0.09).
    """
    qty: float = 0.0
    rate: float = 0.0
    discount: float = 0.0  # Absolute amount, not percentage

    # Product GST percentages from database
    cgst_percent: float = 0.0
    sgst_percent: float = 0.0
    igst_percent: float = 0.0
    cess_percent: float = 0.0

    # Transaction nature determines which taxes apply
    nature: GstNature = GstNature.LOCAL

    # Calculation mode
    tax_mode: TaxMode = TaxMode.ADDITIVE

    # Optional product identification for debugging
    product_id: Optional[int] = None
    product_name: Optional[str] = None

    def __post_init__(self):
        """Ensure all numeric values are float."""
        self.qty = float(self.qty) if self.qty is not None else 0.0
        self.rate = float(self.rate) if self.rate is not None else 0.0
        self.discount = float(self.discount) if self.discount is not None else 0.0
        self.cgst_percent = float(self.cgst_percent) if self.cgst_percent is not None else 0.0
        self.sgst_percent = float(self.sgst_percent) if self.sgst_percent is not None else 0.0
        self.igst_percent = float(self.igst_percent) if self.igst_percent is not None else 0.0
        self.cess_percent = float(self.cess_percent) if self.cess_percent is not None else 0.0


@dataclass
class BillingRowResult:
    """Result of calculating a single billing row."""

    # Input values (echoed back for reference)
    qty: float = 0.0
    rate: float = 0.0
    discount: float = 0.0

    # Calculated values
    gross: float = 0.0           # qty * rate
    taxable_value: float = 0.0   # gross - discount

    # Tax amounts (after nature normalization)
    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    igst_amount: float = 0.0
    cess_amount: float = 0.0
    total_tax: float = 0.0       # Sum of all applicable taxes

    # Final totals
    row_total: float = 0.0       # taxable_value + total_tax (or total for divide mode)

    # Active tax percentages (after nature normalization)
    active_cgst_percent: float = 0.0
    active_sgst_percent: float = 0.0
    active_igst_percent: float = 0.0
    active_cess_percent: float = 0.0
    active_tax_percent: float = 0.0  # Sum of active percentages

    # Metadata
    nature: GstNature = GstNature.LOCAL
    tax_mode: TaxMode = TaxMode.ADDITIVE
    is_valid: bool = True
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for easy serialization."""
        return {
            'qty': self.qty,
            'rate': self.rate,
            'discount': self.discount,
            'gross': self.gross,
            'taxable_value': self.taxable_value,
            'cgst_amount': self.cgst_amount,
            'sgst_amount': self.sgst_amount,
            'igst_amount': self.igst_amount,
            'cess_amount': self.cess_amount,
            'total_tax': self.total_tax,
            'row_total': self.row_total,
            'active_cgst_percent': self.active_cgst_percent,
            'active_sgst_percent': self.active_sgst_percent,
            'active_igst_percent': self.active_igst_percent,
            'active_cess_percent': self.active_cess_percent,
            'active_tax_percent': self.active_tax_percent,
            'nature': self.nature.value,
            'tax_mode': self.tax_mode.value,
            'is_valid': self.is_valid,
            'error_message': self.error_message,
        }


@dataclass
class BillingFooterInput:
    """Input data for calculating footer totals."""

    # List of row results
    rows: List[BillingRowResult] = field(default_factory=list)

    # Footer-level adjustments
    freight: float = 0.0
    footer_discount: float = 0.0  # Additional discount at footer level
    round_off_enabled: bool = True

    # Module-specific fields (optional)
    amount_received: float = 0.0  # For sales
    amount_paid: float = 0.0      # For purchase
    old_balance: float = 0.0      # For sales credit
    opening_balance: float = 0.0  # For purchase credit

    def __post_init__(self):
        """Ensure all numeric values are float."""
        self.freight = float(self.freight) if self.freight is not None else 0.0
        self.footer_discount = float(self.footer_discount) if self.footer_discount is not None else 0.0
        self.amount_received = float(self.amount_received) if self.amount_received is not None else 0.0
        self.amount_paid = float(self.amount_paid) if self.amount_paid is not None else 0.0
        self.old_balance = float(self.old_balance) if self.old_balance is not None else 0.0
        self.opening_balance = float(self.opening_balance) if self.opening_balance is not None else 0.0


@dataclass
class BillingFooterResult:
    """Result of calculating footer totals."""

    # Row aggregations
    subtotal: float = 0.0           # Sum of gross values
    discount_total: float = 0.0     # Sum of row discounts + footer discount
    taxable_total: float = 0.0      # Sum of taxable values

    # Tax aggregations
    cgst_total: float = 0.0
    sgst_total: float = 0.0
    igst_total: float = 0.0
    cess_total: float = 0.0
    tax_total: float = 0.0          # Sum of all taxes

    # Grand totals
    freight: float = 0.0
    grand_total_before_round: float = 0.0  # Before round-off
    round_off: float = 0.0
    final_total: float = 0.0        # After round-off

    # Balance calculations
    amount_received: float = 0.0
    amount_paid: float = 0.0
    closing_balance: float = 0.0   # For sales: old_balance + final_total - received
    creditor_balance: float = 0.0    # For purchase: opening_balance + final_total - paid

    # Metadata
    row_count: int = 0
    is_valid: bool = True

    def to_dict(self) -> dict:
        """Convert to dictionary for easy serialization."""
        return {
            'subtotal': self.subtotal,
            'discount_total': self.discount_total,
            'taxable_total': self.taxable_total,
            'cgst_total': self.cgst_total,
            'sgst_total': self.sgst_total,
            'igst_total': self.igst_total,
            'cess_total': self.cess_total,
            'tax_total': self.tax_total,
            'freight': self.freight,
            'grand_total_before_round': self.grand_total_before_round,
            'round_off': self.round_off,
            'final_total': self.final_total,
            'amount_received': self.amount_received,
            'amount_paid': self.amount_paid,
            'closing_balance': self.closing_balance,
            'creditor_balance': self.creditor_balance,
            'row_count': self.row_count,
            'is_valid': self.is_valid,
        }
