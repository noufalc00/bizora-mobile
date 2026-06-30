
"""
Footer Calculator Module

Calculates billing footer totals from row results.
No UI dependencies.
"""

from typing import List
from .billing_models import BillingRowResult, BillingFooterInput, BillingFooterResult


def calculate_billing_footer(
    input_data: BillingFooterInput
) -> BillingFooterResult:
    """
    Calculate footer totals from row results.

    This is the CENTRAL function for all footer-level billing calculations.
    All UI modules must call this function - no duplicate formulas allowed.

    Args:
        input_data: BillingFooterInput with rows and footer adjustments

    Returns:
        BillingFooterResult with all calculated totals
    """
    rows = input_data.rows if input_data.rows else []

    # Aggregate row values
    subtotal = 0.0
    row_discount_total = 0.0
    taxable_total = 0.0
    cgst_total = 0.0
    sgst_total = 0.0
    igst_total = 0.0
    cess_total = 0.0
    tax_total = 0.0
    rows_total = 0.0

    for row in rows:
        if not row.is_valid:
            continue

        subtotal += row.gross
        row_discount_total += row.discount
        taxable_total += row.taxable_value
        cgst_total += row.cgst_amount
        sgst_total += row.sgst_amount
        igst_total += row.igst_amount
        cess_total += row.cess_amount
        tax_total += row.total_tax
        rows_total += row.row_total

    # Round all aggregates to 2 decimal places
    subtotal = round(subtotal, 2)
    row_discount_total = round(row_discount_total, 2)
    taxable_total = round(taxable_total, 2)
    cgst_total = round(cgst_total, 2)
    sgst_total = round(sgst_total, 2)
    igst_total = round(igst_total, 2)
    cess_total = round(cess_total, 2)
    tax_total = round(tax_total, 2)
    rows_total = round(rows_total, 2)

    # Footer adjustments
    freight = round(input_data.freight, 2)
    footer_discount = round(input_data.footer_discount, 2)

    # CRITICAL FIX:
    # Footer discount MUST reduce the final invoice amount.
    # Previous logic added freight but completely ignored footer_discount
    # during final grand total calculation.
    #
    # Correct flow:
    # rows total
    # + freight
    # - footer discount
    #
    # This preserves all row-level tax calculations and only adjusts
    # the footer-level invoice value.
    grand_total_before_round = round(
        rows_total + freight - footer_discount,
        2
    )

    # Safety clamp
    if grand_total_before_round < 0:
        grand_total_before_round = 0.0

    # Calculate round-off
    if input_data.round_off_enabled:
        final_total = round(grand_total_before_round)
        round_off = round(final_total - grand_total_before_round, 2)
    else:
        final_total = grand_total_before_round
        round_off = 0.0

    # Calculate balances
    closing_balance = round(
        input_data.old_balance + final_total - input_data.amount_received,
        2
    )

    creditor_balance = round(
        input_data.opening_balance + final_total - input_data.amount_paid,
        2
    )

    return BillingFooterResult(
        subtotal=subtotal,
        discount_total=round(row_discount_total + footer_discount, 2),
        taxable_total=taxable_total,
        cgst_total=cgst_total,
        sgst_total=sgst_total,
        igst_total=igst_total,
        cess_total=cess_total,
        tax_total=tax_total,
        freight=freight,
        grand_total_before_round=grand_total_before_round,
        round_off=round_off,
        final_total=final_total,
        amount_received=input_data.amount_received,
        amount_paid=input_data.amount_paid,
        closing_balance=closing_balance,
        creditor_balance=creditor_balance,
        row_count=len(rows),
        is_valid=True,
    )


def quick_calculate_footer(
    rows: List[BillingRowResult],
    freight: float = 0.0,
    footer_discount: float = 0.0,
    round_off_enabled: bool = True,
    amount_received: float = 0.0,
    amount_paid: float = 0.0,
    old_balance: float = 0.0,
    opening_balance: float = 0.0,
) -> BillingFooterResult:
    """
    Quick footer calculation without creating BillingFooterInput.
    """
    input_data = BillingFooterInput(
        rows=rows,
        freight=freight,
        footer_discount=footer_discount,
        round_off_enabled=round_off_enabled,
        amount_received=amount_received,
        amount_paid=amount_paid,
        old_balance=old_balance,
        opening_balance=opening_balance,
    )

    return calculate_billing_footer(input_data)
