"""
Test Examples for Billing Calculation Engine

Run with: python -m logic.calculations.test_billing_calculation_examples
"""

import sys
import os

# Add parent directory to path for standalone execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bizora_core.calculations.billing_models import BillingRowInput, GstNature, TaxMode
from bizora_core.calculations.row_calculator import calculate_billing_row, quick_calculate_row
from bizora_core.calculations.footer_calculator import quick_calculate_footer
from bizora_core.calculations.validation import format_currency, format_number


def test_local_gst():
    """Test 1: Local GST
    qty 5, rate 100, discount 0, cgst 9, sgst 9, igst 18, cess 0, nature Local

    Expected:
    gross 500
    cgst_amount 45
    sgst_amount 45
    igst_amount 0
    tax_total 90
    row_total 590
    """
    print("\n" + "="*60)
    print("TEST 1: Local GST (CGST + SGST)")
    print("="*60)

    result = quick_calculate_row(
        qty=5,
        rate=100,
        discount=0,
        cgst=9,
        sgst=9,
        igst=18,
        cess=0,
        nature="Local",
        tax_mode="additive",
    )

    print(f"Input: qty=5, rate=100, cgst=9%, sgst=9%, igst=18%, nature=Local")
    print(f"Gross: {format_number(result.gross)} (expected: 500.00)")
    print(f"CGST: {format_number(result.cgst_amount)} (expected: 45.00)")
    print(f"SGST: {format_number(result.sgst_amount)} (expected: 45.00)")
    print(f"IGST: {format_number(result.igst_amount)} (expected: 0.00)")
    print(f"Tax Total: {format_number(result.total_tax)} (expected: 90.00)")
    print(f"Row Total: {format_number(result.row_total)} (expected: 590.00)")

    # Assertions
    assert result.gross == 500.00, f"Gross should be 500, got {result.gross}"
    assert result.cgst_amount == 45.00, f"CGST should be 45, got {result.cgst_amount}"
    assert result.sgst_amount == 45.00, f"SGST should be 45, got {result.sgst_amount}"
    assert result.igst_amount == 0.00, f"IGST should be 0, got {result.igst_amount}"
    assert result.total_tax == 90.00, f"Tax total should be 90, got {result.total_tax}"
    assert result.row_total == 590.00, f"Row total should be 590, got {result.row_total}"

    print("[PASS] Test 1 PASSED")
    return True


def test_inter_state_gst():
    """Test 2: Inter-state GST
    qty 5, rate 100, discount 0, cgst 9, sgst 9, igst 18, cess 0, nature Inter-state

    Expected:
    gross 500
    cgst_amount 0
    sgst_amount 0
    igst_amount 90
    tax_total 90
    row_total 590
    """
    print("\n" + "="*60)
    print("TEST 2: Inter-state GST (IGST only)")
    print("="*60)

    result = quick_calculate_row(
        qty=5,
        rate=100,
        discount=0,
        cgst=9,
        sgst=9,
        igst=18,
        cess=0,
        nature="Inter-state",
        tax_mode="additive",
    )

    print(f"Input: qty=5, rate=100, cgst=9%, sgst=9%, igst=18%, nature=Inter-state")
    print(f"Gross: {format_number(result.gross)} (expected: 500.00)")
    print(f"CGST: {format_number(result.cgst_amount)} (expected: 0.00)")
    print(f"SGST: {format_number(result.sgst_amount)} (expected: 0.00)")
    print(f"IGST: {format_number(result.igst_amount)} (expected: 90.00)")
    print(f"Tax Total: {format_number(result.total_tax)} (expected: 90.00)")
    print(f"Row Total: {format_number(result.row_total)} (expected: 590.00)")

    # Assertions
    assert result.gross == 500.00, f"Gross should be 500, got {result.gross}"
    assert result.cgst_amount == 0.00, f"CGST should be 0, got {result.cgst_amount}"
    assert result.sgst_amount == 0.00, f"SGST should be 0, got {result.sgst_amount}"
    assert result.igst_amount == 90.00, f"IGST should be 90, got {result.igst_amount}"
    assert result.total_tax == 90.00, f"Tax total should be 90, got {result.total_tax}"
    assert result.row_total == 590.00, f"Row total should be 590, got {result.row_total}"

    print("[PASS] Test 2 PASSED")
    return True


def test_cess():
    """Test 3: CESS calculation
    qty 10, rate 100, cgst 2.5, sgst 2.5, cess 1, Local

    Expected cess amount = 10 (10 items × 100 = 1000 × 1% = 10)
    """
    print("\n" + "="*60)
    print("TEST 3: CESS Calculation")
    print("="*60)

    result = quick_calculate_row(
        qty=10,
        rate=100,
        discount=0,
        cgst=2.5,
        sgst=2.5,
        igst=0,
        cess=1,
        nature="Local",
        tax_mode="additive",
    )

    print(f"Input: qty=10, rate=100, cgst=2.5%, sgst=2.5%, cess=1%, nature=Local")
    print(f"Gross: {format_number(result.gross)} (expected: 1000.00)")
    print(f"Taxable: {format_number(result.taxable_value)} (expected: 1000.00)")
    print(f"CGST: {format_number(result.cgst_amount)} (expected: 25.00)")
    print(f"SGST: {format_number(result.sgst_amount)} (expected: 25.00)")
    print(f"CESS: {format_number(result.cess_amount)} (expected: 10.00)")
    print(f"Tax Total: {format_number(result.total_tax)} (expected: 60.00)")
    print(f"Row Total: {format_number(result.row_total)} (expected: 1060.00)")

    # Assertions
    assert result.gross == 1000.00, f"Gross should be 1000, got {result.gross}"
    assert result.cess_amount == 10.00, f"CESS should be 10, got {result.cess_amount}"
    assert result.total_tax == 60.00, f"Tax total should be 60 (25+25+10), got {result.total_tax}"

    print("[PASS] Test 3 PASSED")
    return True


def test_discount():
    """Test 4: Discount calculation
    qty 2, rate 100, discount 20, local 9+9

    Expected taxable 180, tax 32.40 (9% of 180 = 16.20 each), total 212.40
    """
    print("\n" + "="*60)
    print("TEST 4: Discount Calculation")
    print("="*60)

    result = quick_calculate_row(
        qty=2,
        rate=100,
        discount=20,
        cgst=9,
        sgst=9,
        igst=0,
        cess=0,
        nature="Local",
        tax_mode="additive",
    )

    print(f"Input: qty=2, rate=100, discount=20, cgst=9%, sgst=9%, nature=Local")
    print(f"Gross: {format_number(result.gross)} (expected: 200.00)")
    print(f"Discount: {format_number(result.discount)} (expected: 20.00)")
    print(f"Taxable: {format_number(result.taxable_value)} (expected: 180.00)")
    print(f"CGST: {format_number(result.cgst_amount)} (expected: 16.20)")
    print(f"SGST: {format_number(result.sgst_amount)} (expected: 16.20)")
    print(f"Tax Total: {format_number(result.total_tax)} (expected: 32.40)")
    print(f"Row Total: {format_number(result.row_total)} (expected: 212.40)")

    # Assertions
    assert result.gross == 200.00, f"Gross should be 200, got {result.gross}"
    assert result.discount == 20.00, f"Discount should be 20, got {result.discount}"
    assert result.taxable_value == 180.00, f"Taxable should be 180, got {result.taxable_value}"
    assert result.cgst_amount == 16.20, f"CGST should be 16.20 (9% of 180), got {result.cgst_amount}"
    assert result.sgst_amount == 16.20, f"SGST should be 16.20 (9% of 180), got {result.sgst_amount}"
    assert result.total_tax == 32.40, f"Tax total should be 32.40, got {result.total_tax}"
    assert result.row_total == 212.40, f"Row total should be 212.40, got {result.row_total}"

    print("[PASS] Test 4 PASSED")
    return True


def test_divide_tax_mode():
    """Test 5: Divide (tax-included) mode
    Price includes tax - split into taxable + tax.

    If total is 590 with 18% tax (9+9):
    taxable = 590 / 1.18 = 500
    tax = 590 - 500 = 90
    cgst = 45, sgst = 45
    """
    print("\n" + "="*60)
    print("TEST 5: Divide Tax Mode (Tax-included pricing)")
    print("="*60)

    # In divide mode, the "taxable_value" we pass is actually the TOTAL
    # But our calculator expects qty, rate, discount to compute gross first
    # So for divide mode test, we simulate: price 118 includes 18% tax
    # qty=1, rate=118 (this is the tax-inclusive price)
    # But that's not how divide mode typically works in practice

    # Better test: Create a scenario where tax is included
    # qty=5, rate=118 each = 590 total includes 18% tax
    # Actually rate should be the unit price

    # For proper divide mode, we need to think differently:
    # In India, MRP is usually tax-inclusive
    # So if MRP is 118 and tax is 18%, the pre-tax price is 100

    # Let's use qty=1, rate=118 as tax-inclusive price
    # With divide mode, we get back taxable=100, tax=18

    result = quick_calculate_row(
        qty=1,
        rate=118,
        discount=0,
        cgst=9,
        sgst=9,
        igst=0,
        cess=0,
        nature="Local",
        tax_mode="divide",  # This is the key - tax is included in rate
    )

    print(f"Input: qty=1, rate=118 (tax-included), cgst=9%, sgst=9%, mode=divide")
    print(f"Gross: {format_number(result.gross)} (rate × qty = 118)")
    print(f"Taxable Value: {format_number(result.taxable_value)} (expected: ~100.00)")
    print(f"CGST: {format_number(result.cgst_amount)} (expected: ~9.00)")
    print(f"SGST: {format_number(result.sgst_amount)} (expected: ~9.00)")
    print(f"Total Tax: {format_number(result.total_tax)} (expected: ~18.00)")
    print(f"Row Total: {format_number(result.row_total)} (expected: 118.00)")

    # In divide mode:
    # gross = 118
    # taxable = 118 / 1.18 = 100
    # total_tax = 118 - 100 = 18
    # cgst = 9, sgst = 9 (split proportionally)

    assert result.taxable_value == 100.00, f"Taxable should be 100, got {result.taxable_value}"
    assert result.row_total == 118.00, f"Row total should be 118, got {result.row_total}"
    assert result.total_tax == 18.00, f"Tax should be 18, got {result.total_tax}"
    assert result.cgst_amount == 9.00, f"CGST should be 9, got {result.cgst_amount}"
    assert result.sgst_amount == 9.00, f"SGST should be 9, got {result.sgst_amount}"

    print("[PASS] Test 5 PASSED")
    return True


def test_footer_calculation():
    """Test 6: Footer totals with multiple rows"""
    print("\n" + "="*60)
    print("TEST 6: Footer Calculation")
    print("="*60)

    # Create 3 rows
    row1 = quick_calculate_row(qty=2, rate=100, discount=0, cgst=9, sgst=9, nature="Local")
    row2 = quick_calculate_row(qty=1, rate=200, discount=20, cgst=9, sgst=9, nature="Local")
    row3 = quick_calculate_row(qty=5, rate=50, discount=0, cgst=18, sgst=0, igst=0, nature="Inter-state")

    rows = [row1, row2, row3]

    footer = quick_calculate_footer(
        rows=rows,
        freight=50,
        footer_discount=10,
        round_off_enabled=True,
        amount_received=500,
        old_balance=100,
    )

    print(f"Row 1: Gross={row1.gross}, Tax={row1.total_tax}, Total={row1.row_total}")
    print(f"Row 2: Gross={row2.gross}, Tax={row2.total_tax}, Total={row2.row_total}")
    print(f"Row 3: Gross={row3.gross}, Tax={row3.total_tax}, Total={row3.row_total}")
    print(f"Subtotal: {format_number(footer.subtotal)}")
    print(f"Tax Total: {format_number(footer.tax_total)}")
    print(f"Freight: {format_number(footer.freight)}")
    print(f"Round Off: {format_number(footer.round_off)}")
    print(f"Final Total: {format_number(footer.final_total)}")
    print(f"Closing Balance: {format_number(footer.closing_balance)}")

    # Verify calculations
    expected_subtotal = row1.gross + row2.gross + row3.gross
    expected_tax = row1.total_tax + row2.total_tax + row3.total_tax

    assert footer.subtotal == expected_subtotal, f"Subtotal mismatch"
    assert footer.tax_total == expected_tax, f"Tax total mismatch"
    assert footer.row_count == 3, f"Row count should be 3"

    print("[PASS] Test 6 PASSED")
    return True


def run_all_tests():
    """Run all test cases."""
    print("\n" + "="*60)
    print("BILLING CALCULATION ENGINE TEST SUITE")
    print("="*60)

    tests = [
        test_local_gst,
        test_inter_state_gst,
        test_cess,
        test_discount,
        test_divide_tax_mode,
        test_footer_calculation,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERR] {test.__name__} ERROR: {e}")
            failed += 1

    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
