"""
Helper methods for Sales Entry widget.
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
    """Safely parse float from table cell, return default on error."""
    text = safe_item_text(table, row, col, "0")
    try:
        return float(text)
    except (ValueError, TypeError):
        return default


def ensure_row_items_initialized(table, row):
    """Ensure all editable columns have QTableWidgetItem objects."""
    # Column indices: 0=SL, 1=Product, 2=HSN, 3=CGST, 4=SGST, 5=IGST, 6=CESS, 7=Rate, 8=Qty, 9=Gross, 10=Disc, 11=Net, 12=Tax, 13=Total
    for col in range(14):
        if table.item(row, col) is None:
            # Create empty item - do NOT overwrite existing data
            table.setItem(row, col, QTableWidgetItem(""))


def clear_product_linked_row_data(table, row, sale_items):
    """Clear all product-linked fields in a row when Product is cleared.
    
    This clears:
    - Table cells: HSN, CGST, SGST, IGST, CESS, Rate, Qty, Gross, Disc, Net, Tax, Total
    - Internal data: product_id, hsn, cgst, sgst, igst, cess, tax_percent, rate
    
    Preserves:
    - SL No (column 0)
    - Product cell (column 1) - already cleared by user
    - Row itself (not deleted)
    """
    # Column indices: 0=SL, 1=Product, 2=HSN, 3=CGST, 4=SGST, 5=IGST, 6=CESS, 7=Rate, 8=Qty, 9=Gross, 10=Disc, 11=Net, 12=Tax, 13=Total
    columns_to_clear = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    
    was_blocked = table.blockSignals(True)
    try:
        for col in columns_to_clear:
            item = table.item(row, col)
            if item:
                item.setText("")
    finally:
        table.blockSignals(was_blocked)
    
    # Clear internal sale_items data for this row
    if row < len(sale_items):
        sale_items[row]['product_id'] = None
        sale_items[row]['hsn'] = ''
        sale_items[row]['cgst'] = 0
        sale_items[row]['sgst'] = 0
        sale_items[row]['igst'] = 0
        sale_items[row]['cess'] = 0
        sale_items[row]['tax_percent'] = 0
        sale_items[row]['rate'] = 0