"""
Row Calculator Module

Calculates individual billing row values.
No UI dependencies - works with pure numbers.
"""

from .billing_models import BillingRowInput, BillingRowResult, TaxMode
from .gst_rules import (
    normalize_gst_for_nature,
    get_active_tax_percentages,
    calculate_tax_amounts,
    split_tax_for_divide_mode,
)


def calculate_billing_row(input_data: BillingRowInput) -> BillingRowResult:
    """
    Calculate all values for a single billing row.

    This is the CENTRAL function for all row-level billing calculations.
    All UI modules must call this function - no duplicate formulas allowed.

    Args:
        input_data: BillingRowInput with qty, rate, discount, tax percentages, nature

    Returns:
        BillingRowResult with all calculated values
    """
    try:
        # Basic validation
        if input_data.qty < 0 or input_data.rate < 0:
            return BillingRowResult(
                is_valid=False,
                error_message="Quantity and rate must be non-negative",
            )

        # Calculate gross
        gross = round(input_data.qty * input_data.rate, 2)

        # Apply discount (absolute amount)
        discount = input_data.discount if input_data.discount > 0 else 0.0

        # Ensure discount doesn't exceed gross
        if discount > gross:
            discount = gross

        # Calculate taxable value
        taxable_value = round(gross - discount, 2)

        # Handle zero taxable value
        if taxable_value <= 0:
            return BillingRowResult(
                qty=input_data.qty,
                rate=input_data.rate,
                discount=discount,
                gross=gross,
                taxable_value=0.0,
                cgst_amount=0.0,
                sgst_amount=0.0,
                igst_amount=0.0,
                cess_amount=0.0,
                total_tax=0.0,
                row_total=0.0,
                active_cgst_percent=0.0,
                active_sgst_percent=0.0,
                active_igst_percent=0.0,
                active_cess_percent=0.0,
                active_tax_percent=0.0,
                nature=input_data.nature,
                tax_mode=input_data.tax_mode,
                is_valid=True,
            )

        # Get active tax percentages based on nature
        active_cgst, active_sgst, active_igst, active_cess, total_tax_pct = get_active_tax_percentages(
            input_data.cgst_percent,
            input_data.sgst_percent,
            input_data.igst_percent,
            input_data.cess_percent,
            input_data.nature,
        )

        if input_data.tax_mode == TaxMode.DIVIDE:
            # Tax-included mode: Split total into taxable + tax
            # First calculate what the total would be with tax
            # Then split it back
            # For divide mode, we work backwards from a known total
            # But here we calculate the total first, then split

            # Calculate total with tax included
            total_with_tax = taxable_value  # This IS the total in divide mode

            # Split into taxable + tax
            split_result = split_tax_for_divide_mode(
                total_with_tax,
                total_tax_pct,
                active_cgst,
                active_sgst,
                active_igst,
                active_cess,
            )

            cgst_amount = split_result['cgst_amount']
            sgst_amount = split_result['sgst_amount']
            igst_amount = split_result['igst_amount']
            cess_amount = split_result['cess_amount']
            total_tax = split_result['total_tax']
            # In divide mode, the taxable_value we calculated is actually the total
            # The real taxable value is less
            actual_taxable = split_result['taxable_value']
            row_total = total_with_tax  # Row total is the original amount

        else:
            # Additive mode: Calculate tax on taxable value and add
            tax_amounts = calculate_tax_amounts(
                taxable_value,
                active_cgst,
                active_sgst,
                active_igst,
                active_cess,
            )

            cgst_amount = tax_amounts['cgst_amount']
            sgst_amount = tax_amounts['sgst_amount']
            igst_amount = tax_amounts['igst_amount']
            cess_amount = tax_amounts['cess_amount']
            total_tax = tax_amounts['total_tax']
            actual_taxable = taxable_value
            row_total = round(taxable_value + total_tax, 2)

        return BillingRowResult(
            qty=input_data.qty,
            rate=input_data.rate,
            discount=discount,
            gross=gross,
            taxable_value=actual_taxable,
            cgst_amount=cgst_amount,
            sgst_amount=sgst_amount,
            igst_amount=igst_amount,
            cess_amount=cess_amount,
            total_tax=total_tax,
            row_total=row_total,
            active_cgst_percent=active_cgst,
            active_sgst_percent=active_sgst,
            active_igst_percent=active_igst,
            active_cess_percent=active_cess,
            active_tax_percent=total_tax_pct,
            nature=input_data.nature,
            tax_mode=input_data.tax_mode,
            is_valid=True,
        )

    except Exception as e:
        return BillingRowResult(
            is_valid=False,
            error_message=f"Calculation error: {str(e)}",
        )


def quick_calculate_row(
    qty: float,
    rate: float,
    discount: float = 0.0,
    cgst: float = 0.0,
    sgst: float = 0.0,
    igst: float = 0.0,
    cess: float = 0.0,
    nature: str = "Local",
    tax_mode: str = "additive",
) -> BillingRowResult:
    """
    Quick calculation without creating BillingRowInput.

    Args:
        qty: Quantity
        rate: Rate per unit
        discount: Discount amount (absolute)
        cgst: CGST percentage
        sgst: SGST percentage
        igst: IGST percentage
        cess: CESS percentage
        nature: "Local" or "Inter-state"
        tax_mode: "additive" or "divide"

    Returns:
        BillingRowResult
    """
    from .billing_models import GstNature, TaxMode

    input_data = BillingRowInput(
        qty=qty,
        rate=rate,
        discount=discount,
        cgst_percent=cgst,
        sgst_percent=sgst,
        igst_percent=igst,
        cess_percent=cess,
        nature=GstNature.LOCAL if nature == "Local" else GstNature.INTER_STATE,
        tax_mode=TaxMode.ADDITIVE if tax_mode == "additive" else TaxMode.DIVIDE,
    )

    return calculate_billing_row(input_data)
