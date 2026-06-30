"""
Calculation logic for Sales Return widget.
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


class SalesReturnCalculationsMixin:
    """Mixin class containing all calculation methods for Sales Return."""

    def calculate_row_totals(self, row_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate row values using the shared billing engine.
        Discount is treated as absolute rupee amount.
        """
        # Convert input to BillingRowInput and use engine
        nature_str = row_data.get('nature', 'Local')
        nature = GstNature.INTER_STATE if nature_str == 'Inter-state' else GstNature.LOCAL

        tax_mode = TaxMode.DIVIDE if (
            hasattr(self, 'divide_tax_tick') and self.divide_tax_tick.isChecked()
        ) else TaxMode.ADDITIVE

        row_input = BillingRowInput(
            qty=safe_float(row_data.get('quantity', 0.0)),
            rate=safe_float(row_data.get('rate', 0.0)),
            discount=safe_float(row_data.get('discount', 0.0)),
            cgst_percent=safe_float(row_data.get('cgst_pct', 0.0)),
            sgst_percent=safe_float(row_data.get('sgst_pct', 0.0)),
            igst_percent=safe_float(row_data.get('igst_pct', 0.0)),
            cess_percent=safe_float(row_data.get('cess_pct', 0.0)),
            nature=nature,
            tax_mode=tax_mode,
        )

        result = calculate_billing_row(row_input)

        return {
            'gross_value': result.gross,
            'discount': result.discount,
            'net_value': result.taxable_value,
            'cgst_amt': result.cgst_amount,
            'sgst_amt': result.sgst_amount,
            'igst_amt': result.igst_amount,
            'cess_amt': result.cess_amount,
            'tax_amount': result.total_tax,
            'grand_total': result.row_total,
        }

    def calculate_tax_distribution(self, net_value: float, cgst_pct: float, sgst_pct: float,
                                   igst_pct: float, cess_pct: float,
                                   nature: str = 'Local') -> Dict[str, float]:
        """
        Distribute tax amounts using the shared engine.
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
            'cgst_amt': result.cgst_amount,
            'sgst_amt': result.sgst_amount,
            'igst_amt': result.igst_amount,
            'cess_amt': result.cess_amount,
            'tax_amount': result.total_tax,
        }

    def calculate_summary_totals(self, items: list) -> Dict[str, float]:
        """
        Calculate footer summary totals using the shared billing engine.
        """
        # Convert items to BillingRowResults and use footer calculator
        from bizora_core.calculations.billing_models import BillingRowResult

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

        footer_discount = 0.0
        if hasattr(self, 'discount_total_input'):
            footer_discount = safe_float(self.discount_total_input.text())

        round_off_enabled = True
        if hasattr(self, 'round_off_checkbox'):
            round_off_enabled = self.round_off_checkbox.isChecked()

        # Use footer calculator
        footer_result = quick_calculate_footer(
            rows=row_results,
            freight=0.0,
            footer_discount=footer_discount,
            round_off_enabled=round_off_enabled,
        )

        return {
            'sub_total': footer_result.subtotal,
            'discount_total': footer_result.discount_total,
            'net_value': footer_result.taxable_total,
            'cgst_total': footer_result.cgst_total,
            'sgst_total': footer_result.sgst_total,
            'igst_total': footer_result.igst_total,
            'cess_total': footer_result.cess_total,
            'tax_total': footer_result.tax_total,
            'grand_total': footer_result.final_total,
            'round_off': footer_result.round_off,
            'rounded_total': footer_result.final_total,
        }

    def calculate_balance(self, final_amount: float, amount_refunded: float) -> float:
        """Return balance = final_amount - amount_refunded."""
        return round(final_amount - amount_refunded, 2)