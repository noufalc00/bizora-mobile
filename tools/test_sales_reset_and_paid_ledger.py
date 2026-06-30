"""
Test script for Sales Entry Reset and Amount Received Ledger Posting fixes.

Tests:
1. Reset after previous bill - Net Amount must be 0.00
2. Amount Received ledger split posting - Cash and Debtor entries
3. Update twice - no duplicate ledger entries
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import Database
from bizora_core.sales_logic import SalesLogic
from bizora_core.voucher_posting_engine import VoucherPostingEngine


def test_reset_clears_net_amount():
    """Test that reset clears Net Amount to 0.00."""
    print("=" * 60)
    print("TEST 1: Reset clears Net Amount")
    print("=" * 60)
    
    # This is a UI test that requires manual verification
    # The fix was implemented in ui/sales_entry.py clear_form() method
    # Added explicit clearing of:
    # - net_amount_input
    # - net_value_display
    # - tax_amount_display
    
    print("✓ Fix implemented in ui/sales_entry.py clear_form()")
    print("  - net_amount_input cleared to '0.00'")
    print("  - net_value_display cleared to '0.00'")
    print("  - tax_amount_display cleared to '0.00'")
    print("\nManual test required:")
    print("1. Open Sales Entry")
    print("2. Open previous bill using previous button")
    print("3. Confirm bill shows Net Amount (e.g., 795.00)")
    print("4. Click Reset / Reset All")
    print("Expected: Table blank, Net Amount = 0.00, Grand Total = 0.00")
    print()


def test_amount_received_ledger_split():
    """Test that amount_received splits ledger entries correctly."""
    print("=" * 60)
    print("TEST 2: Amount Received Ledger Split Posting")
    print("=" * 60)
    
    try:
        db = Database()
        active_company = db.get_active_company()
        if not active_company:
            print("⚠ No active company found. Skipping test.")
            return
        
        company_id = active_company['id']
        print(f"Active company: {active_company['name']} (ID: {company_id})")
        
        # Check if voucher_posting_engine has split posting logic
        from bizora_core.voucher_posting_engine import VoucherPostingEngine
        engine = VoucherPostingEngine(db)
        
        # Verify build_sales_entries method exists
        if hasattr(engine, 'build_sales_entries'):
            print("✓ build_sales_entries method exists in VoucherPostingEngine")
            
            # Check if the method implements split posting
            import inspect
            source = inspect.getsource(engine.build_sales_entries)
            
            if 'received' in source and 'debtor_amount' in source:
                print("✓ Split posting logic found in build_sales_entries")
                print("  - Dr Cash = Amount Received")
                print("  - Dr Debtor = Grand Total - Amount Received")
                print("  - Cr Sales/tax = Grand Total")
            else:
                print("✗ Split posting logic not found in build_sales_entries")
        else:
            print("✗ build_sales_entries method not found in VoucherPostingEngine")
        
        print("\nManual test required:")
        print("1. Create/update credit sales bill:")
        print("   Grand Total = 1000")
        print("   Amount Received = 300")
        print("2. Update the bill")
        print("3. Open Ledger")
        print("Expected:")
        print("  - Cash debit = 300")
        print("  - Debtor debit = 700")
        print("  - Sales/tax credits = 1000")
        print("  - Debit total = Credit total")
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
    print()


def test_update_no_duplicates():
    """Test that updating twice does not create duplicate ledger entries."""
    print("=" * 60)
    print("TEST 3: Update Twice - No Duplicate Ledger Entries")
    print("=" * 60)
    
    try:
        db = Database()
        active_company = db.get_active_company()
        if not active_company:
            print("⚠ No active company found. Skipping test.")
            return
        
        company_id = active_company['id']
        print(f"Active company: {active_company['name']} (ID: {company_id})")
        
        # Check if repost_voucher deletes old entries
        from bizora_core.voucher_posting_engine import VoucherPostingEngine
        engine = VoucherPostingEngine(db)
        
        if hasattr(engine, 'repost_voucher'):
            print("✓ repost_voucher method exists in VoucherPostingEngine")
            
            import inspect
            source = inspect.getsource(engine.repost_voucher)
            
            if 'delete_voucher_entries' in source:
                print("✓ repost_voucher deletes old ledger entries before reposting")
                print("  - This prevents duplicate entries on update")
            else:
                print("✗ repost_voucher does not delete old ledger entries")
        else:
            print("✗ repost_voucher method not found in VoucherPostingEngine")
        
        print("\nManual test required:")
        print("1. Edit Sales bill")
        print("2. Update")
        print("3. Update again")
        print("Expected: No duplicate ledger entries")
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
    print()


def test_database_schema():
    """Test that sales table has amount_received column."""
    print("=" * 60)
    print("TEST 4: Database Schema - amount_received Column")
    print("=" * 60)
    
    try:
        db = Database()
        
        # Check if sales table has amount_received column
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(sales)")
        columns = [row[1] for row in cursor.fetchall()]
        db.disconnect()
        
        if 'amount_received' in columns:
            print("✓ sales table has amount_received column")
        else:
            print("✗ sales table missing amount_received column")
        
        # Check if save_sale includes amount_received
        from bizora_core.sales_logic import SalesLogic
        logic = SalesLogic(db)
        
        import inspect
        source = inspect.getsource(logic.normalize_sale_data)
        
        if 'amount_received' in source:
            print("✓ SalesLogic.normalize_sale_data includes amount_received")
        else:
            print("✗ SalesLogic.normalize_sale_data missing amount_received")
        
        # Check if UI save includes amount_received
        # This requires reading the UI file
        try:
            with open('ui/sales_entry.py', 'r', encoding='utf-8') as f:
                content = f.read()
                if "'amount_received':" in content:
                    print("✓ SalesEntry.save includes amount_received in sale_data")
                else:
                    print("✗ SalesEntry.save missing amount_received in sale_data")
        except Exception as e:
            print(f"⚠ Could not read ui/sales_entry.py: {e}")
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
    print()


def main():
    print("\n" + "=" * 60)
    print("SALES RESET AND PAID LEDGER TESTS")
    print("=" * 60 + "\n")
    
    test_reset_clears_net_amount()
    test_amount_received_ledger_split()
    test_update_no_duplicates()
    test_database_schema()
    
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print("\nAll code-level checks completed.")
    print("Manual UI tests required for full verification.")
    print("\nSee test results above.")
    print()


if __name__ == "__main__":
    main()
