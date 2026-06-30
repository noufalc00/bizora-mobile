"""
GST Rules Module

Centralized GST nature logic. No UI dependencies.
All GST formulas are defined here and nowhere else.
"""

from typing import Dict, Tuple
from .billing_models import GstNature


def normalize_gst_for_nature(
    cgst: float,
    sgst: float,
    igst: float,
    cess: float,
    nature: GstNature
) -> Dict[str, float]:
    """
    Normalize GST percentages based on transaction nature.

    Rules:
    - Local: CGST + SGST apply, IGST = 0
    - Inter-state: IGST applies, CGST = SGST = 0
    - CESS: Always applies regardless of nature

    Args:
        cgst: Product CGST percentage (e.g., 9 for 9%)
        sgst: Product SGST percentage (e.g., 9 for 9%)
        igst: Product IGST percentage (e.g., 18 for 18%)
        cess: Product CESS percentage (e.g., 1 for 1%)
        nature: Transaction nature (Local or Inter-state)

    Returns:
        Dict with active_cgst, active_sgst, active_igst, active_cess
    """
    if nature == GstNature.INTER_STATE:
        # Inter-state: Only IGST + CESS
        return {
            'active_cgst': 0.0,
            'active_sgst': 0.0,
            'active_igst': float(igst),
            'active_cess': float(cess),
        }
    else:
        # Local: CGST + SGST + CESS, no IGST
        return {
            'active_cgst': float(cgst),
            'active_sgst': float(sgst),
            'active_igst': 0.0,
            'active_cess': float(cess),
        }


def get_active_tax_percentages(
    cgst: float,
    sgst: float,
    igst: float,
    cess: float,
    nature: GstNature
) -> Tuple[float, float, float, float, float]:
    """
    Get all active tax percentages and their sum.

    Returns:
        Tuple of (cgst, sgst, igst, cess, total)
    """
    active = normalize_gst_for_nature(cgst, sgst, igst, cess, nature)

    cgst_pct = active['active_cgst']
    sgst_pct = active['active_sgst']
    igst_pct = active['active_igst']
    cess_pct = active['active_cess']
    total_pct = cgst_pct + sgst_pct + igst_pct + cess_pct

    return cgst_pct, sgst_pct, igst_pct, cess_pct, total_pct


def calculate_tax_amounts(
    taxable_value: float,
    cgst_pct: float,
    sgst_pct: float,
    igst_pct: float,
    cess_pct: float,
) -> Dict[str, float]:
    """
    Calculate individual tax amounts from percentages.

    Args:
        taxable_value: The value on which tax is calculated
        cgst_pct: Active CGST percentage
        sgst_pct: Active SGST percentage
        igst_pct: Active IGST percentage
        cess_pct: Active CESS percentage

    Returns:
        Dict with cgst_amount, sgst_amount, igst_amount, cess_amount, total_tax
    """
    cgst_amount = round(taxable_value * cgst_pct / 100, 2)
    sgst_amount = round(taxable_value * sgst_pct / 100, 2)
    igst_amount = round(taxable_value * igst_pct / 100, 2)
    cess_amount = round(taxable_value * cess_pct / 100, 2)
    total_tax = round(cgst_amount + sgst_amount + igst_amount + cess_amount, 2)

    return {
        'cgst_amount': cgst_amount,
        'sgst_amount': sgst_amount,
        'igst_amount': igst_amount,
        'cess_amount': cess_amount,
        'total_tax': total_tax,
    }


def split_tax_for_divide_mode(
    total_with_tax: float,
    total_tax_percent: float,
    cgst_pct: float,
    sgst_pct: float,
    igst_pct: float,
    cess_pct: float,
) -> Dict[str, float]:
    """
    Split total amount into taxable value and tax components.
    Used when price is inclusive of tax (divide/tax-included mode).

    Formula:
        taxable_value = total / (1 + total_tax_percent/100)
        total_tax = total - taxable_value
        Then split total_tax proportionally among tax types.

    Args:
        total_with_tax: The total amount including tax
        total_tax_percent: Sum of all applicable tax percentages
        cgst_pct: Active CGST percentage
        sgst_pct: Active SGST percentage
        igst_pct: Active IGST percentage
        cess_pct: Active CESS percentage

    Returns:
        Dict with taxable_value, cgst_amount, sgst_amount, igst_amount, cess_amount, total_tax
    """
    if total_tax_percent <= 0:
        # No tax, everything is taxable value
        return {
            'taxable_value': round(total_with_tax, 2),
            'cgst_amount': 0.0,
            'sgst_amount': 0.0,
            'igst_amount': 0.0,
            'cess_amount': 0.0,
            'total_tax': 0.0,
        }

    # Calculate taxable value by removing tax
    taxable_value = total_with_tax / (1 + total_tax_percent / 100)
    total_tax = total_with_tax - taxable_value

    # Split tax proportionally
    if total_tax_percent > 0:
        cgst_amount = total_tax * cgst_pct / total_tax_percent
        sgst_amount = total_tax * sgst_pct / total_tax_percent
        igst_amount = total_tax * igst_pct / total_tax_percent
        cess_amount = total_tax * cess_pct / total_tax_percent
    else:
        cgst_amount = 0.0
        sgst_amount = 0.0
        igst_amount = 0.0
        cess_amount = 0.0

    # Round to 2 decimal places
    return {
        'taxable_value': round(taxable_value, 2),
        'cgst_amount': round(cgst_amount, 2),
        'sgst_amount': round(sgst_amount, 2),
        'igst_amount': round(igst_amount, 2),
        'cess_amount': round(cess_amount, 2),
        'total_tax': round(total_tax, 2),
    }
