"""
Calculation logic for Sales Entry widget.
Uses the shared billing calculation engine - no duplicate GST formulas.
"""

import math

from .sales_entry_helpers import safe_float_from_cell, safe_item_text, ensure_row_items_initialized

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


def _safe_float(text, default=0.0):
    """Parse text to float safely; blank/invalid returns default."""
    return safe_float(text, default)


def recalculate_row(widget, row, source_column=None, live_value=None):
    """Recalculate row totals based on current Qty, Rate, Gross, Disc, and Tax values."""
    if row < 0 or row >= widget.items_table.rowCount():
        return

    ensure_row_items_initialized(widget.items_table, row)

    try:
        qty = safe_float_from_cell(widget.items_table, row, 8, 0)
        rate = safe_float_from_cell(widget.items_table, row, 7, 0)
        disc = safe_float_from_cell(widget.items_table, row, 10, 0)

        # Get tax values from cells
        cgst = safe_float_from_cell(widget.items_table, row, 3, 0)
        sgst = safe_float_from_cell(widget.items_table, row, 4, 0)
        igst = safe_float_from_cell(widget.items_table, row, 5, 0)
        cess = safe_float_from_cell(widget.items_table, row, 6, 0)
        non_taxable = bool(
            hasattr(widget, 'non_taxable_checkbox')
            and widget.non_taxable_checkbox.isChecked()
        )

        gross = safe_float_from_cell(widget.items_table, row, 9, 0)

        # Handle live value updates based on source column
        if source_column == 8:
            qty = float(live_value or 0)
            gross = rate * qty
        elif source_column == 7:
            rate = float(live_value or 0)
            gross = rate * qty
        elif source_column == 9:
            gross = float(live_value or 0)
            if qty > 0:
                rate = gross / qty
        elif source_column == 10:
            disc = float(live_value or 0)
        elif source_column in (3, 4, 5, 6):
            # One of the tax columns changed
            if live_value is not None:
                if source_column == 3:
                    cgst = float(live_value or 0)
                elif source_column == 4:
                    sgst = float(live_value or 0)
                elif source_column == 5:
                    igst = float(live_value or 0)
                elif source_column == 6:
                    cess = float(live_value or 0)
        elif source_column in (2, None):
            gross = rate * qty
        else:
            gross = rate * qty

        if non_taxable:
            cgst = 0.0
            sgst = 0.0
            igst = 0.0
            cess = 0.0

        # Check if divide tax from unit rate mode is active
        divide_tax_mode = (hasattr(widget, 'divide_tax_tick') and
                         widget.divide_tax_tick.isChecked())

        # Get GST nature from widget
        nature_str = "Local"
        if hasattr(widget, 'nature_combo'):
            nature_str = widget.nature_combo.currentText()
        nature = GstNature.INTER_STATE if nature_str == "Inter-state" else GstNature.LOCAL

        # Calculate total tax percent for storage
        if nature == GstNature.INTER_STATE:
            tax_percent = igst + cess
        else:
            tax_percent = cgst + sgst + cess

        tax_mode = TaxMode.DIVIDE if divide_tax_mode else TaxMode.ADDITIVE

        # Use the shared calculation engine - ALL GST FORMULAS ARE CENTRALIZED THERE
        row_input = BillingRowInput(
            qty=qty,
            rate=rate,
            discount=disc,
            cgst_percent=cgst,
            sgst_percent=sgst,
            igst_percent=igst,
            cess_percent=cess,
            nature=nature,
            tax_mode=tax_mode,
        )

        result = calculate_billing_row(row_input)

        # Extract calculated values from result
        net = result.taxable_value
        tax_amount = result.total_tax
        total = result.row_total
        # Note: In divide mode, the engine splits correctly
        # In additive mode, the engine adds tax correctly

        table = widget.items_table
        was_blocked = table.blockSignals(True)
        try:
            if non_taxable:
                for tax_col in (3, 4, 5, 6):
                    tax_rate_item = table.item(row, tax_col)
                    if tax_rate_item:
                        tax_rate_item.setText("0.00")
            if source_column != 7:
                rate_item = table.item(row, 7)
                if rate_item:
                    rate_item.setText(f"{rate:.2f}")
            # Only overwrite qty if source_column is 8 (Qty column) or 9 (Gross column)
            # This prevents resetting qty to 0 when source_column is None (row initialization)
            if source_column in [8, 9]:
                qty_item = table.item(row, 8)
                if qty_item:
                    qty_item.setText(f"{qty:.2f}")
            if source_column != 9:
                gross_item = table.item(row, 9)
                if gross_item:
                    gross_item.setText(f"{gross:.2f}")
            if source_column != 10:
                disc_item = table.item(row, 10)
                if disc_item:
                    disc_item.setText(f"{disc:.2f}")

            net_item = table.item(row, 11)
            if net_item:
                net_item.setText(f"{net:.2f}")

            tax_item = table.item(row, 12)
            if tax_item:
                tax_item.setText(f"{tax_amount:.2f}")

            total_item = table.item(row, 13)
            if total_item:
                total_item.setText(f"{total:.2f}")
        finally:
            table.blockSignals(was_blocked)

        if row < len(widget.sale_items):
            widget.sale_items[row]['rate'] = rate
            widget.sale_items[row]['tax_percent'] = tax_percent
            widget.sale_items[row]['cgst'] = cgst
            widget.sale_items[row]['sgst'] = sgst
            widget.sale_items[row]['igst'] = igst
            widget.sale_items[row]['cess'] = cess
            widget.sale_items[row]['cgst_amount'] = result.cgst_amount
            widget.sale_items[row]['sgst_amount'] = result.sgst_amount
            widget.sale_items[row]['igst_amount'] = result.igst_amount
            widget.sale_items[row]['cess_amount'] = result.cess_amount
            widget.sale_items[row]['hsn'] = safe_item_text(widget.items_table, row, 2, widget.sale_items[row].get('hsn', ''))

        if not getattr(widget, '_skip_inline_row_totals', False):
            totals = calculate_totals(widget)
            _write_totals_to_widgets(widget, totals)

    except (ValueError, AttributeError):
        pass  # Handle invalid numeric input gracefully


def calculate_totals(widget):
    """Calculate bill totals from all table rows + footer adjustments.

    Uses the shared billing calculation engine - no duplicate GST formulas.
    Returns a dict with all computed totals. Does NOT write to UI widgets.
    """
    try:
        # Get GST nature from widget
        nature_str = "Local"
        if hasattr(widget, 'nature_combo'):
            nature_str = widget.nature_combo.currentText()
        nature = GstNature.INTER_STATE if nature_str == "Inter-state" else GstNature.LOCAL

        # Check if divide tax mode is active
        divide_tax_mode = (hasattr(widget, 'divide_tax_tick') and
                         widget.divide_tax_tick.isChecked())
        tax_mode = TaxMode.DIVIDE if divide_tax_mode else TaxMode.ADDITIVE

        # Build row inputs and calculate using engine
        row_results = []
        for row in range(widget.items_table.rowCount()):
            ensure_row_items_initialized(widget.items_table, row)

            qty = safe_float_from_cell(widget.items_table, row, 8, 0)
            rate = safe_float_from_cell(widget.items_table, row, 7, 0)
            discount = safe_float_from_cell(widget.items_table, row, 10, 0)
            cgst = safe_float_from_cell(widget.items_table, row, 3, 0)
            sgst = safe_float_from_cell(widget.items_table, row, 4, 0)
            igst = safe_float_from_cell(widget.items_table, row, 5, 0)
            cess = safe_float_from_cell(widget.items_table, row, 6, 0)
            non_taxable = bool(
                hasattr(widget, 'non_taxable_checkbox')
                and widget.non_taxable_checkbox.isChecked()
            )
            if non_taxable:
                cgst = 0.0
                sgst = 0.0
                igst = 0.0
                cess = 0.0

            # Skip blank rows
            if qty <= 0 and rate <= 0:
                continue

            row_input = BillingRowInput(
                qty=qty,
                rate=rate,
                discount=discount,
                cgst_percent=cgst,
                sgst_percent=sgst,
                igst_percent=igst,
                cess_percent=cess,
                nature=nature,
                tax_mode=tax_mode,
            )

            result = calculate_billing_row(row_input)
            if result.is_valid:
                row_results.append(result)

        # Get footer values
        freight = _safe_float(widget.freight_input.text()) if hasattr(widget, 'freight_input') else 0.0
        footer_discount = _safe_float(widget.discount_total_input.text()) if hasattr(widget, 'discount_total_input') else 0.0
        amount_received = _safe_float(widget.amount_received_input.text()) if hasattr(widget, 'amount_received_input') else 0.0
        old_balance = _safe_float(widget.old_balance_input.text()) if hasattr(widget, 'old_balance_input') else 0.0

        # Round-off based on checkbox state
        round_off_checked = bool(
            hasattr(widget, 'round_off_checkbox') and widget.round_off_checkbox.isChecked()
        )

        # Calculate footer using engine
        footer_result = quick_calculate_footer(
            rows=row_results,
            freight=freight,
            footer_discount=footer_discount,
            round_off_enabled=round_off_checked,
            amount_received=amount_received,
            old_balance=old_balance,
        )

        # Calculate return adjustment if any
        return_adjustment = getattr(widget, '_linked_sales_return_amount', 0.0)
        adjusted_final = footer_result.final_total - return_adjustment

        # Legacy format for backward compatibility with _write_totals_to_widgets
        result = {
            'sub_total': footer_result.subtotal,
            'row_discount_total': footer_result.discount_total - footer_discount,  # Row-level only
            'tax_total': footer_result.tax_total,
            'cgst_total': footer_result.cgst_total,
            'sgst_total': footer_result.sgst_total,
            'igst_total': footer_result.igst_total,
            'cess_total': footer_result.cess_total,
            'raw_grand': footer_result.grand_total_before_round,
            'round_off_val': footer_result.round_off,
            'grand_total': footer_result.final_total,
            'adjusted_final': adjusted_final,
            'closing_balance': footer_result.closing_balance - return_adjustment,
            # Also include full footer result for new code
            'footer_result': footer_result,
            'row_results': row_results,
        }
        return result
    except Exception as e:
        print(f"[ERROR] Calculation failed: {e}")
        import traceback
        traceback.print_exc()
        # Fallback to prevent crash
        return {
            'sub_total': 0.0,
            'row_discount_total': 0.0,
            'tax_total': 0.0,
            'cgst_total': 0.0,
            'sgst_total': 0.0,
            'igst_total': 0.0,
            'cess_total': 0.0,
            'raw_grand': 0.0,
            'round_off_val': 0.0,
            'grand_total': 0.0,
            'adjusted_final': 0.0,
            'closing_balance': 0.0,
            'footer_result': None,
            'row_results': [],
        }


def _write_totals_to_widgets(widget, totals):
    """Write computed totals dict to UI widgets. Preserves all existing behavior."""
    sub_total = totals['sub_total']
    tax_total = totals['tax_total']
    cgst_total = totals['cgst_total']
    sgst_total = totals['sgst_total']
    igst_total = totals['igst_total']
    cess_total = totals['cess_total']
    raw_grand = totals['raw_grand']
    round_off_val = totals['round_off_val']
    grand_total = totals['grand_total']
    row_discount_total = totals['row_discount_total']

    # Expose row-level discount total as an internal attribute (used by save() etc.)
    widget._row_discount_total = row_discount_total

    # Write Round Off field safely (avoid re-entry into calculate_totals)
    if hasattr(widget, 'round_off_input'):
        was_blocked = widget.round_off_input.blockSignals(True)
        try:
            widget.round_off_input.setText(f"{round_off_val:.2f}")
        finally:
            widget.round_off_input.blockSignals(was_blocked)

    # Hidden backward-compat fields (combined discount = row + footer, for save layer)
    widget.sub_total_input.setText(f"{sub_total:.2f}")
    widget.tax_total_input.setText(f"{tax_total:.2f}")
    widget.grand_total_input.setText(f"{grand_total:.2f}")

    # Visible footer display fields
    if hasattr(widget, 'net_value_display'):
        widget.net_value_display.setText(f"{sub_total:.2f}")
    if hasattr(widget, 'cgst_display'):
        widget.cgst_display.setText(f"{cgst_total:.2f}")
    if hasattr(widget, 'sgst_display'):
        widget.sgst_display.setText(f"{sgst_total:.2f}")
    if hasattr(widget, 'igst_display'):
        widget.igst_display.setText(f"{igst_total:.2f}")
    if hasattr(widget, 'tax_amount_display'):
        widget.tax_amount_display.setText(f"{tax_total:.2f}")
    if hasattr(widget, 'cess_display'):
        widget.cess_display.setText(f"{cess_total:.2f}")
    # Net Amt shows the value AFTER round-off deduction (final amount).
    if hasattr(widget, 'net_amount_display'):
        widget.net_amount_display.setText(f"{grand_total:.2f}")
    # Also update the input field if it exists
    if hasattr(widget, 'net_amount_input'):
        widget.net_amount_input.setText(f"{grand_total:.2f}")

    if hasattr(widget, 'final_amount_display'):
        widget.final_amount_display.setText(f"{grand_total:.2f}")