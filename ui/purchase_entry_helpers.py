"""
Helper methods for Purchase Entry widget.
Contains generic utility methods for table operations and data validation.
"""


from PySide6.QtWidgets import QTableWidgetItem

def safe_item_text(table, row, col, default=""):
    """Safely get text from table item, return default if item is None."""
    item = table.item(row, col)
    if item is None:
        return default
    return item.text().strip() if item.text() else default


def safe_float_from_cell(table, row, col, default=0.0):
    """Safely parse float from table cell, return default on error.
    Handles percentage values by stripping % suffix.
    Returns None if cell is empty or contains only whitespace (to distinguish from 0).
    """
    text = safe_item_text(table, row, col, "")
    if not text or not text.strip():
        return None if default is None else default
    try:
        # Strip % suffix for percentage columns
        text = str(text).replace('%', '').strip()
        return float(text)
    except (ValueError, TypeError):
        return default


def ensure_row_items_initialized(table, row):
    """Ensure all editable columns have QTableWidgetItem objects."""
    # Column indices: 0=SL, 1=Sales Rate, 2=Product, 3=HSN, 4=CGST, 5=SGST, 6=IGST, 7=CESS, 8=Rate, 9=Qty, 10=Gross, 11=Disc, 12=Net, 13=Tax, 14=Total
    for col in range(15):
        if table.item(row, col) is None:
            # Create empty item - do NOT overwrite existing data
            table.setItem(row, col, QTableWidgetItem(""))


def clear_product_linked_row_data(table, row, purchase_items):
    """Clear all product-linked fields in a row when Product is cleared.
    
    This clears:
    - Table cells: Sales Rate, HSN, CGST, SGST, IGST, CESS, Rate, Qty, Gross, Disc, Net, Tax, Total
    - Internal data: product_id, hsn, cgst, sgst, igst, cess, tax_percent, rate
    
    Preserves:
    - SL No (column 0)
    - Product cell (column 2) - already cleared by user
    - Row itself (not deleted)
    """
    # Column indices: 0=SL, 1=Sales Rate, 2=Product, 3=HSN, 4=CGST, 5=SGST, 6=IGST, 7=CESS, 8=Rate, 9=Qty, 10=Gross, 11=Disc, 12=Net, 13=Tax, 14=Total
    columns_to_clear = [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    
    was_blocked = table.blockSignals(True)
    try:
        for col in columns_to_clear:
            item = table.item(row, col)
            if item:
                item.setText("")
    finally:
        table.blockSignals(was_blocked)
    
    # Clear internal purchase_items data for this row
    if row < len(purchase_items):
        purchase_items[row]['product_id'] = None
        purchase_items[row]['hsn'] = ''
        purchase_items[row]['cgst'] = 0
        purchase_items[row]['sgst'] = 0
        purchase_items[row]['igst'] = 0
        purchase_items[row]['cess'] = 0
        purchase_items[row]['tax_percent'] = 0
        purchase_items[row]['rate'] = 0