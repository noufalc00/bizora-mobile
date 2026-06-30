"""
Calculation logic for Purchase Return widget.
Uses the shared billing calculation engine - no duplicate GST formulas.
"""

from typing import Dict, Any

# Import the shared billing calculation engine
from bizora_core.calculations import (
    BillingRowInput,
    BillingRowResult,
    GstNature,
    TaxMode,
    calculate_billing_row,
    quick_calculate_footer,
    safe_float,
)



class PurchaseReturnCalculationsMixin:
    """Mixin class containing all calculation methods for Purchase Return."""

    def calculate_row_totals(self, row_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate all values for a single row using the shared billing engine.

        Args:
            row_data: Dictionary containing rate, quantity, discount, tax percentages

        Returns:
            Dictionary with calculated values: gross, net, tax_amount, grand_total
        """
        # Convert discount to absolute amount if percentage
        discount_val = safe_float(row_data.get('discount', 0.0))
        rate = safe_float(row_data.get('rate', 0.0))
        qty = safe_float(row_data.get('quantity', 0.0))
        gross = rate * qty

        if 0 < discount_val <= 100:  # Percentage discount
            discount_amount = gross * (discount_val / 100)
        else:  # Absolute discount
            discount_amount = discount_val

        # Use shared engine with per-product GST rates
        nature_str = row_data.get('nature', 'Local')
        nature = GstNature.INTER_STATE if nature_str == 'Inter-state' else GstNature.LOCAL

        row_input = BillingRowInput(
            qty=qty,
            rate=rate,
            discount=discount_amount,
            cgst_percent=safe_float(row_data.get('cgst_pct', 0.0)),
            sgst_percent=safe_float(row_data.get('sgst_pct', 0.0)),
            igst_percent=safe_float(row_data.get('igst_pct', 0.0)),
            cess_percent=safe_float(row_data.get('cess_pct', 0.0)),
            nature=nature,
            tax_mode=TaxMode.ADDITIVE,
        )

        result = calculate_billing_row(row_input)

        return {
            'gross_value': result.gross,
            'discount': discount_amount,
            'net_value': result.taxable_value,
            'tax_amount': result.total_tax,
            'grand_total': result.row_total,
            'cgst_amt': result.cgst_amount,
            'sgst_amt': result.sgst_amount,
            'igst_amt': result.igst_amount,
            'cess_amt': result.cess_amount,
        }

    def calculate_tax_distribution(self, net_value: float, cgst_pct: float,
                                   sgst_pct: float, igst_pct: float, cess_pct: float,
                                   nature: str = 'Local') -> Dict[str, float]:
        """
        Distribute tax into CGST, SGST, IGST, and CESS using the shared engine.

        Args:
            net_value: Net value after discount
            cgst_pct: CGST percentage
            sgst_pct: SGST percentage
            igst_pct: IGST percentage
            cess_pct: CESS percentage
            nature: 'Local' or 'Inter-state'

        Returns:
            Dictionary with cgst, sgst, igst, cess amounts
        """
        gst_nature = GstNature.INTER_STATE if nature == 'Inter-state' else GstNature.LOCAL

        row_input = BillingRowInput(
            qty=1.0,
            rate=net_value,
            discount=0.0,
            cgst_percent=cgst_pct,
            sgst_percent=sgst_pct,
            igst_percent=igst_pct,
            cess_percent=cess_pct,
            nature=gst_nature,
            tax_mode=TaxMode.ADDITIVE,
        )

        result = calculate_billing_row(row_input)

        return {
            'cgst': result.cgst_amount,
            'sgst': result.sgst_amount,
            'igst': result.igst_amount,
            'cess': result.cess_amount,
        }

    def calculate_summary_totals(self, items: list) -> Dict[str, float]:
        """
        Calculate summary totals from all items using the shared billing engine.

        Args:
            items: List of item dictionaries

        Returns:
            Dictionary with sub_total, discount_total, tax_total, grand_total
        """
        # Convert items to BillingRowResults
        row_results = []
        for item in items:
            result = BillingRowResult(
                qty=safe_float(item.get('quantity', 0.0)),
                rate=safe_float(item.get('rate', 0.0)),
                discount=safe_float(item.get('discount', 0.0)),
                gross=safe_float(item.get('gross_value', 0.0)),
                taxable_value=safe_float(item.get('net_value', 0.0)),
                cgst_amount=safe_float(item.get('cgst_amt', 0.0)),
                sgst_amount=safe_float(item.get('sgst_amt', 0.0)),
                igst_amount=safe_float(item.get('igst_amt', 0.0)),
                cess_amount=safe_float(item.get('cess_amt', 0.0)),
                total_tax=safe_float(item.get('tax_amount', 0.0)),
                row_total=safe_float(item.get('grand_total', 0.0)),
                is_valid=True,
            )
            row_results.append(result)

        # Use footer calculator
        footer_result = quick_calculate_footer(
            rows=row_results,
            freight=0.0,
            footer_discount=0.0,
            round_off_enabled=True,
        )

        return {
            'sub_total': footer_result.subtotal,
            'net_value': footer_result.taxable_total,
            'discount_total': footer_result.discount_total,
            'tax_total': footer_result.tax_total,
            'cgst_total': footer_result.cgst_total,
            'sgst_total': footer_result.sgst_total,
            'igst_total': footer_result.igst_total,
            'cess_total': footer_result.cess_total,
            'grand_total': footer_result.final_total,
            'round_off': footer_result.round_off,
            'rounded_total': footer_result.final_total,
        }

    def calculate_balance_adjustment(self, grand_total: float,
                                    amount_received: float) -> float:
        """
        Calculate balance adjustment for credit returns.

        Args:
            grand_total: Total return amount
            amount_received: Amount already received

        Returns:
            Balance adjustment amount
        """
        return round(grand_total - amount_received, 2)

    def _safe_float_str(self, text: str) -> float:
        """Safely convert string to float."""
        if not text:
            return 0.0
        try:
            return float(text.replace('₹', '').replace(',', '').strip())
        except (ValueError, TypeError):
            return 0.0