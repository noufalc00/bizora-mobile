#!/usr/bin/env python3
"""Test script to verify Sales Entry save fix."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from ui.sales_entry_calculations import calculate_totals, _calculate_totals
from PySide6.QtWidgets import QApplication, QTableWidget
from PySide6.QtCore import Qt

def test_calculate_totals_return():
    """Test that calculate_totals returns proper values."""
    print("Testing calculate_totals function...")
    
    # Create a minimal widget for testing
    app = QApplication(sys.argv)
    widget = type('TestWidget', (), {})()
    
    # Mock required attributes
    widget.items_table = QTableWidget()
    widget.items_table.setColumnCount(14)
    widget.items_table.setRowCount(1)
    
    # Mock input fields
    class MockInput:
        def __init__(self, text="0.00"):
            self._text = text
        def text(self):
            return self._text
        def isChecked(self):
            return False
    
    widget.freight_input = MockInput("50.00")
    widget.discount_total_input = MockInput("10.00") 
    widget.amount_receive_input = MockInput("100.00")
    widget.old_balance_input = MockInput("0.00")
    widget.round_off_checkbox = MockInput()
    widget.nature_combo = MockInput()
    widget.nature_combo.currentText = lambda: "Local"
    widget.divide_tax_tick = MockInput()
    
    # Test calculation
    try:
        result = _calculate_totals(widget)
        print(f"✓ _calculate_totals returned: {type(result)}")
        if result:
            print(f"  - grand_total: {result.get('grand_total', 'N/A')}")
            print(f"  - sub_total: {result.get('sub_total', 'N/A')}")
            print(f"  - tax_total: {result.get('tax_total', 'N/A')}")
        else:
            print("✗ _calculate_totals returned None/empty")
            return False
    except Exception as e:
        print(f"✗ _calculate_totals failed: {e}")
        return False
    
    print("✓ calculate_totals test passed")
    return True

if __name__ == "__main__":
    success = test_calculate_totals_return()
    sys.exit(0 if success else 1)
