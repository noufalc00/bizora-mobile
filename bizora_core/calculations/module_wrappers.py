"""
Module Wrapper Functions

Convenience wrappers for each billing module.
These add module-specific fields while using the core calculation engine.
"""

from typing import List, Dict, Any, Optional
from .billing_models import (
    BillingRowInput,
    BillingRowResult,
    BillingFooterInput,
    BillingFooterResult,
    GstNature,
    TaxMode,
)
from .row_calculator import calculate_billing_row
from .footer_calculator import calculate_billing_footer
from .validation import safe_float


def calculate_sales_bill(
    rows: List[BillingRowInput],
    freight: float = 0.0,
    footer_discount: float = 0.0,
    round_off_enabled: bool = True,
    amount_received: float = 0.0,
    old_balance: float = 0.0,
    return_adjustment: float = 0.0,
) -> Dict[str, Any]:
    """
    Calculate complete Sales bill.

    Args:
        rows: List of row inputs
        freight: Freight/shipping charges
        footer_discount: Additional discount at footer level
        round_off_enabled: Whether to apply round-off
        amount_received: Amount received from customer
        old_balance: Customer's previous balance
        return_adjustment: Sales return adjustment amount

    Returns:
        Dict with row_results, footer_result, and sales-specific fields
    """
    # Calculate all rows
    row_results = [calculate_billing_row(row) for row in rows]

    # Calculate footer
    footer_input = BillingFooterInput(
        rows=row_results,
        freight=freight,
        footer_discount=footer_discount,
        round_off_enabled=round_off_enabled,
        amount_received=amount_received,
        old_balance=old_balance,
    )
    footer_result = calculate_billing_footer(footer_input)

    # Sales-specific: Closing balance with return adjustment
    adjusted_final = footer_result.final_total - return_adjustment
    closing_balance = round(old_balance + adjusted_final - amount_received, 2)

    return {
        'row_results': row_results,
        'footer': footer_result,
        'freight': freight,
        'amount_received': amount_received,
        'old_balance': old_balance,
        'closing_balance': closing_balance,
        'return_adjustment': return_adjustment,
        'adjusted_final': adjusted_final,
    }


def calculate_purchase_bill(
    rows: List[BillingRowInput],
    freight: float = 0.0,
    footer_discount: float = 0.0,
    round_off_enabled: bool = True,
    amount_paid: float = 0.0,
    opening_balance: float = 0.0,
) -> Dict[str, Any]:
    """
    Calculate complete Purchase bill.

    Args:
        rows: List of row inputs
        freight: Freight/shipping charges
        footer_discount: Additional discount at footer level
        round_off_enabled: Whether to apply round-off
        amount_paid: Amount paid to supplier
        opening_balance: Supplier's previous balance

    Returns:
        Dict with row_results, footer_result, and purchase-specific fields
    """
    # Calculate all rows
    row_results = [calculate_billing_row(row) for row in rows]

    # Calculate footer
    footer_input = BillingFooterInput(
        rows=row_results,
        freight=freight,
        footer_discount=footer_discount,
        round_off_enabled=round_off_enabled,
        amount_paid=amount_paid,
        opening_balance=opening_balance,
    )
    footer_result = calculate_billing_footer(footer_input)

    # Purchase-specific: Creditor balance
    creditor_balance = round(opening_balance + footer_result.final_total - amount_paid, 2)

    return {
        'row_results': row_results,
        'footer': footer_result,
        'freight': freight,
        'amount_paid': amount_paid,
        'opening_balance': opening_balance,
        'creditor_balance': creditor_balance,
    }


def calculate_sales_return(
    rows: List[BillingRowInput],
    round_off_enabled: bool = True,
    refund_amount: float = 0.0,
    adjusted_amount: float = 0.0,
    return_type: str = "Cash",  # "Cash" or "Credit"
) -> Dict[str, Any]:
    """
    Calculate complete Sales Return.

    Args:
        rows: List of row inputs
        round_off_enabled: Whether to apply round-off
        refund_amount: Amount to be refunded
        adjusted_amount: Amount adjusted against new bill
        return_type: "Cash" or "Credit"

    Returns:
        Dict with row_results, footer_result, and return-specific fields
    """
    # Calculate all rows
    row_results = [calculate_billing_row(row) for row in rows]

    # Calculate footer (no freight for returns)
    footer_input = BillingFooterInput(
        rows=row_results,
        freight=0.0,
        footer_discount=0.0,
        round_off_enabled=round_off_enabled,
        amount_received=0.0,  # Not applicable for returns
        old_balance=0.0,
    )
    footer_result = calculate_billing_footer(footer_input)

    # Return-specific calculations
    total_return = footer_result.final_total

    if return_type == "Cash":
        # Cash return: full amount should be refunded
        expected_refund = total_return
        balance = 0.0
    else:
        # Credit return: track against customer balance
        expected_refund = refund_amount
        balance = total_return - refund_amount - adjusted_amount

    return {
        'row_results': row_results,
        'footer': footer_result,
        'return_type': return_type,
        'total_return': total_return,
        'refund_amount': refund_amount,
        'adjusted_amount': adjusted_amount,
        'expected_refund': expected_refund,
        'balance': balance,
    }


def calculate_purchase_return(
    rows: List[BillingRowInput],
    round_off_enabled: bool = True,
    refund_amount: float = 0.0,
    adjusted_amount: float = 0.0,
    return_type: str = "Cash",  # "Cash" or "Credit"
) -> Dict[str, Any]:
    """
    Calculate complete Purchase Return.

    Args:
        rows: List of row inputs
        round_off_enabled: Whether to apply round-off
        refund_amount: Amount received from supplier
        adjusted_amount: Amount adjusted against future purchases
        return_type: "Cash" or "Credit"

    Returns:
        Dict with row_results, footer_result, and return-specific fields
    """
    # Calculate all rows
    row_results = [calculate_billing_row(row) for row in rows]

    # Calculate footer (no freight for returns)
    footer_input = BillingFooterInput(
        rows=row_results,
        freight=0.0,
        footer_discount=0.0,
        round_off_enabled=round_off_enabled,
        amount_paid=0.0,  # Not applicable for returns
        opening_balance=0.0,
    )
    footer_result = calculate_billing_footer(footer_input)

    # Return-specific calculations
    total_return = footer_result.final_total

    if return_type == "Cash":
        # Cash return: full amount should be received
        expected_refund = total_return
        balance = 0.0
    else:
        # Credit return: track against supplier balance
        expected_refund = refund_amount
        balance = total_return - refund_amount - adjusted_amount

    return {
        'row_results': row_results,
        'footer': footer_result,
        'return_type': return_type,
        'total_return': total_return,
        'refund_amount': refund_amount,
        'adjusted_amount': adjusted_amount,
        'expected_refund': expected_refund,
        'supplier_balance': balance,
    }


def recalculate_row_with_nature_change(
    row_result: BillingRowResult,
    new_nature: GstNature,
) -> BillingRowResult:
    """
    Recalculate a row when GST nature changes (Local <-> Inter-state).

    This preserves qty, rate, discount but recalculates tax.

    Args:
        row_result: Previous row result
        new_nature: New GST nature

    Returns:
        New BillingRowResult with updated tax calculations
    """
    # Create new input with same values but new nature
    new_input = BillingRowInput(
        qty=row_result.qty,
        rate=row_result.rate,
        discount=row_result.discount,
        cgst_percent=row_result.active_cgst_percent,
        sgst_percent=row_result.active_sgst_percent,
        igst_percent=row_result.active_igst_percent,
        cess_percent=row_result.active_cess_percent,
        nature=new_nature,
        tax_mode=row_result.tax_mode,
    )

    return calculate_billing_row(new_input)
