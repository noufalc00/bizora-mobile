"""
Calculation logic for Purchase Entry widget.
Uses the shared billing calculation engine - no duplicate GST formulas.
"""

import math

from .purchase_entry_helpers import safe_float_from_cell, safe_item_text, ensure_row_items_initialized

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
    """Recalculate row totals based on current Qty, Rate, Gross, Disc, and Tax values.
    Returns the BillingRowResult for live calculation support.
    """
    if row < 0 or row >= widget.items_table.rowCount():
        return None

    ensure_row_items_initialized(widget.items_table, row)

    # Check if Product column is blank AND no product_id - if so, clear all columns except SL No and return
    product_name = safe_item_text(widget.items_table, row, 2, "")
    product_id = None
    if row < len(widget.purchase_items):
        product_id = widget.purchase_items[row].get('product_id')

    if (not product_name or not product_name.strip()) and not product_id:
        # Clear all columns except SL No (column 0) without firing cellChanged.
        was_blocked = widget.items_table.blockSignals(True)
        try:
            for col in range(1, 15):  # Columns 1-14 (Sales Rate through Total)
                item = widget.items_table.item(row, col)
                if item:
                    item.setText("")
        finally:
            widget.items_table.blockSignals(was_blocked)
        # Update internal purchase_items
        if row < len(widget.purchase_items):
            widget.purchase_items[row] = {
                'product_id': None,
                'hsn': '',
                'cgst': 0,
                'sgst': 0,
                'igst': 0,
                'cess': 0,
                'rate': 0,
                'tax_percent': 0,
                'quantity': 0,
            }
        calculate_totals(widget)
        return None

    try:
        qty = safe_float_from_cell(widget.items_table, row, 9, 0)
        rate = safe_float_from_cell(widget.items_table, row, 8, 0)
        disc = safe_float_from_cell(widget.items_table, row, 11, 0)

        # Get tax values from cells - use purchase_items if table cells are empty
        # This handles the case where user enters qty before tax percentages are set
        cgst_cell = safe_float_from_cell(widget.items_table, row, 4, None)
        sgst_cell = safe_float_from_cell(widget.items_table, row, 5, None)
        igst_cell = safe_float_from_cell(widget.items_table, row, 6, None)
        cess_cell = safe_float_from_cell(widget.items_table, row, 7, None)

        # Fall back to purchase_items if table cells are None or 0
        if row < len(widget.purchase_items):
            cgst = cgst_cell if cgst_cell is not None else widget.purchase_items[row].get('cgst', 0)
            sgst = sgst_cell if sgst_cell is not None else widget.purchase_items[row].get('sgst', 0)
            igst = igst_cell if igst_cell is not None else widget.purchase_items[row].get('igst', 0)
            cess = cess_cell if cess_cell is not None else widget.purchase_items[row].get('cess', 0)
        else:
            cgst = cgst_cell if cgst_cell is not None else 0
            sgst = sgst_cell if sgst_cell is not None else 0
            igst = igst_cell if igst_cell is not None else 0
            cess = cess_cell if cess_cell is not None else 0

        gross = safe_float_from_cell(widget.items_table, row, 10, 0)

        # Handle live value updates based on source column
        if source_column == 9:
            qty = _safe_float(live_value, qty) if live_value is not None else qty
            gross = rate * qty
        elif source_column == 8:
            rate = _safe_float(live_value, rate) if live_value is not None else rate
            gross = rate * qty
        elif source_column == 10:
            gross = _safe_float(live_value, gross) if live_value is not None else gross
            if qty > 0:
                rate = gross / qty
        elif source_column == 11:
            disc = _safe_float(live_value, disc) if live_value is not None else disc
        elif source_column in (4, 5, 6, 7):
            # One of the tax columns changed
            if live_value is not None:
                if source_column == 4:
                    cgst = _safe_float(live_value, cgst)
                elif source_column == 5:
                    sgst = _safe_float(live_value, sgst)
                elif source_column == 6:
                    igst = _safe_float(live_value, igst)
                elif source_column == 7:
                    cess = _safe_float(live_value, cess)
        elif source_column in (3, None):
            gross = rate * qty
        else:
            gross = rate * qty

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

        # The Disc cell always holds a flat cash amount. Percentage entries are
        # converted to their flat equivalent at input time (Down Arrow handler),
        # so the engine simply consumes the absolute discount here.
        disc_amount = disc if disc > 0 else 0.0

        # Use the shared calculation engine - ALL GST FORMULAS ARE CENTRALIZED THERE
        row_input = BillingRowInput(
            qty=qty,
            rate=rate,
            discount=disc_amount,
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

        table = widget.items_table
        was_blocked = table.blockSignals(True)
        try:
            if source_column != 8:
                rate_item = table.item(row, 8)
                if rate_item:
                    rate_item.setText(f"{rate:.2f}")
            if source_column != 9:
                qty_item = table.item(row, 9)
                if qty_item:
                    qty_item.setText(f"{qty:.2f}")
            if source_column != 10:
                gross_item = table.item(row, 10)
                if gross_item:
                    gross_item.setText(f"{gross:.2f}")
            if source_column != 11:
                disc_item = table.item(row, 11)
                if disc_item:
                    disc_item.setText(f"{disc:.2f}")

            net_item = table.item(row, 12)
            if net_item:
                net_item.setText(f"{net:.2f}")

            tax_item = table.item(row, 13)
            if tax_item:
                tax_item.setText(f"{tax_amount:.2f}")

            total_item = table.item(row, 14)
            if total_item:
                total_item.setText(f"{total:.2f}")
        finally:
            table.blockSignals(was_blocked)

        if row < len(widget.purchase_items):
            widget.purchase_items[row]['rate'] = rate
            widget.purchase_items[row]['tax_percent'] = tax_percent
            widget.purchase_items[row]['cgst'] = cgst
            widget.purchase_items[row]['sgst'] = sgst
            widget.purchase_items[row]['igst'] = igst
            widget.purchase_items[row]['cess'] = cess
            widget.purchase_items[row]['cgst_amount'] = result.cgst_amount
            widget.purchase_items[row]['sgst_amount'] = result.sgst_amount
            widget.purchase_items[row]['igst_amount'] = result.igst_amount
            widget.purchase_items[row]['cess_amount'] = result.cess_amount
            widget.purchase_items[row]['hsn'] = safe_item_text(widget.items_table, row, 3, widget.purchase_items[row].get('hsn', ''))

        # Always call calculate_totals for live updates with live row result
        # This ensures footer updates immediately when user types in qty/rate/etc
        calculate_totals(widget, live_row=row, live_row_result=result)

        # Push the active row's equivalent discount percentage to the top bar tracker.
        if hasattr(widget, 'update_discount_status_label'):
            widget.update_discount_status_label(row)

        return result

    except (ValueError, AttributeError):
        pass  # Handle invalid numeric input gracefully


def calculate_totals(widget, live_row=None, live_row_result=None):
    """Calculate bill totals from all table rows + footer adjustments.

    Uses the shared billing calculation engine - no duplicate GST formulas.

    Args:
        widget: PurchaseEntry widget
        live_row: Optional row index that is currently being edited
        live_row_result: Optional BillingRowResult for the currently edited row
                         This is used to avoid reading stale table values during live typing
    """
    # Get GST nature from widget
    nature_str = "Local"
    if hasattr(widget, 'nature_combo'):
        nature_str = widget.nature_combo.currentText()
    nature = GstNature.INTER_STATE if nature_str == "Inter-state" else GstNature.LOCAL

    # Check if divide tax mode is active
    divide_tax_mode = (hasattr(widget, 'divide_tax_tick') and
                     widget.divide_tax_tick.isChecked())

    # Collect only committed product rows. The grid is intentionally prefilled
    # with blank QTableWidgetItems, so empty/unlinked rows must never affect math.
    table = getattr(widget, 'table', widget.items_table)
    row_results = []
    for row in range(table.rowCount()):
        product_name = safe_item_text(table, row, 2, "")
        if not product_name.strip():
            continue
        if hasattr(widget, '_row_has_committed_product') and not widget._row_has_committed_product(row):
            continue

        # Use live_row_result if this is the currently edited row
        if live_row is not None and row == live_row and live_row_result is not None:
            if live_row_result.is_valid:
                row_results.append(live_row_result)
            continue

        qty = safe_float_from_cell(table, row, 9, 0)
        rate = safe_float_from_cell(table, row, 8, 0)
        disc_value = safe_float_from_cell(table, row, 11, 0)
        cgst = safe_float_from_cell(table, row, 4, 0)
        sgst = safe_float_from_cell(table, row, 5, 0)
        igst = safe_float_from_cell(table, row, 6, 0)
        cess = safe_float_from_cell(table, row, 7, 0)

        tax_mode = TaxMode.DIVIDE if divide_tax_mode else TaxMode.ADDITIVE

        # Disc cell always holds a flat cash amount (percent entries are converted
        # to flat at input time via the Down Arrow handler).
        discount = disc_value if disc_value > 0 else 0.0

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
    amount_paid = _safe_float(widget.amt_paid_input.text()) if hasattr(widget, 'amt_paid_input') else 0.0
    opening_balance = _safe_float(widget.opening_balance_input.text()) if hasattr(widget, 'opening_balance_input') else 0.0
    purchase_expense = _safe_float(widget.purchase_expense_input.text()) if hasattr(widget, 'purchase_expense_input') else 0.0

    # Round-off based on checkbox state
    round_off_checked = bool(
        hasattr(widget, 'round_off_checkbox') and widget.round_off_checkbox.isChecked()
    )

    # Calculate footer using engine
    # Add purchase expense to freight for calculation
    total_freight = freight + purchase_expense
    footer_result = quick_calculate_footer(
        rows=row_results,
        freight=total_freight,
        footer_discount=footer_discount,
        round_off_enabled=round_off_checked,
        amount_paid=amount_paid,
        opening_balance=opening_balance,
    )

    # Write Round Off field safely
    if hasattr(widget, 'round_off_input'):
        was_blocked = widget.round_off_input.blockSignals(True)
        try:
            widget.round_off_input.setText(f"{footer_result.round_off:.2f}")
        finally:
            widget.round_off_input.blockSignals(was_blocked)

    # Hidden backward-compat fields
    widget.sub_total_input.setText(f"{footer_result.subtotal:.2f}")
    widget.tax_total_input.setText(f"{footer_result.tax_total:.2f}")
    widget.grand_total_input.setText(f"{footer_result.final_total:.2f}")

    # Expose row-level discount total
    widget._row_discount_total = footer_result.discount_total - footer_discount

    # Visible footer display fields
    if hasattr(widget, 'net_value_display'):
        widget.net_value_display.setText(f"{footer_result.subtotal:.2f}")
    if hasattr(widget, 'cgst_display'):
        widget.cgst_display.setText(f"{footer_result.cgst_total:.2f}")
    if hasattr(widget, 'sgst_display'):
        widget.sgst_display.setText(f"{footer_result.sgst_total:.2f}")
    if hasattr(widget, 'igst_display'):
        widget.igst_display.setText(f"{footer_result.igst_total:.2f}")
    if hasattr(widget, 'tax_amount_display'):
        widget.tax_amount_display.setText(f"{footer_result.tax_total:.2f}")
    if hasattr(widget, 'cess_display'):
        widget.cess_display.setText(f"{footer_result.cess_total:.2f}")
    if hasattr(widget, 'net_amount_display'):
        widget.net_amount_display.setText(f"{footer_result.grand_total_before_round:.2f}")

    if hasattr(widget, 'final_amount_display'):
        widget.final_amount_display.setText(f"₹ {footer_result.final_total:.2f}")

    # Call apply_purchase_payment_mode if available
    if hasattr(widget, 'apply_purchase_payment_mode'):
        widget.apply_purchase_payment_mode()