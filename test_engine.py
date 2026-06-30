import unittest
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import Database
from bizora_core.voucher_posting_engine import VoucherPostingEngine
from bizora_core.financial_reporting_engine import FinancialReportingEngine


class TestAccountingEngine(unittest.TestCase):
    def setUp(self):
        """Runs BEFORE every single test. Sets up a pristine environment."""
        self.db = Database()
        # Use a designated test company ID to keep production data safe
        self.TEST_COMPANY_ID = 999
        self.engine = VoucherPostingEngine(self.db)
        self.reporter = FinancialReportingEngine(self.db)
        
        # Clean up any leftover test data from previous runs
        self.db.execute_update("DELETE FROM ledger_entries WHERE company_id = ?", (self.TEST_COMPANY_ID,))
        
        # Ensure base Cash and Supplier accounts exist in our test set
        # Create test company if it doesn't exist
        self._ensure_test_company()
        self._ensure_test_accounts()
        
    def _ensure_test_company(self):
        """Ensure test company exists."""
        ph = self.db._get_placeholder()
        result = self.db.execute_query(
            f"SELECT id FROM companies WHERE id = {ph}",
            (self.TEST_COMPANY_ID,)
        )
        if not result:
            self.db.execute_update(
                f"INSERT INTO companies (id, business_name, gstin, address, state, phone_number, email) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})",
                (self.TEST_COMPANY_ID, "Test Company", "", "Test Address", "Test State", "", "")
            )
    
    def _ensure_test_accounts(self):
        """Ensure base Cash and Supplier accounts exist for testing."""
        ph = self.db._get_placeholder()
        
        # Ensure Cash Account exists
        cash_result = self.db.execute_query(
            f"SELECT id FROM ledger_accounts WHERE company_id = {ph} AND account_name = {ph}",
            (self.TEST_COMPANY_ID, "Cash Account")
        )
        if not cash_result:
            self.db.execute_update(
                f"INSERT INTO ledger_accounts (company_id, account_name, account_type, is_active) VALUES ({ph}, {ph}, {ph}, {ph})",
                (self.TEST_COMPANY_ID, "Cash Account", "cash_bank", 1)
            )
        
        # Ensure Sales Account exists
        sales_result = self.db.execute_query(
            f"SELECT id FROM ledger_accounts WHERE company_id = {ph} AND account_name = {ph}",
            (self.TEST_COMPANY_ID, "Sales Account")
        )
        if not sales_result:
            self.db.execute_update(
                f"INSERT INTO ledger_accounts (company_id, account_name, account_type, is_active) VALUES ({ph}, {ph}, {ph}, {ph})",
                (self.TEST_COMPANY_ID, "Sales Account", "income", 1)
            )
        
        # Ensure Purchase Account exists
        purchase_result = self.db.execute_query(
            f"SELECT id FROM ledger_accounts WHERE company_id = {ph} AND account_name = {ph}",
            (self.TEST_COMPANY_ID, "Purchase Account")
        )
        if not purchase_result:
            self.db.execute_update(
                f"INSERT INTO ledger_accounts (company_id, account_name, account_type, is_active) VALUES ({ph}, {ph}, {ph}, {ph})",
                (self.TEST_COMPANY_ID, "Purchase Account", "expense", 1)
            )
        
        # Ensure Sundry Creditors Account exists
        creditors_result = self.db.execute_query(
            f"SELECT id FROM ledger_accounts WHERE company_id = {ph} AND account_name = {ph}",
            (self.TEST_COMPANY_ID, "Sundry Creditors")
        )
        if not creditors_result:
            self.db.execute_update(
                f"INSERT INTO ledger_accounts (company_id, account_name, account_type, is_active) VALUES ({ph}, {ph}, {ph}, {ph})",
                (self.TEST_COMPANY_ID, "Sundry Creditors", "party", 1)
            )
        
        # Ensure Input CGST Account exists
        cgst_result = self.db.execute_query(
            f"SELECT id FROM ledger_accounts WHERE company_id = {ph} AND account_name = {ph}",
            (self.TEST_COMPANY_ID, "Input CGST")
        )
        if not cgst_result:
            self.db.execute_update(
                f"INSERT INTO ledger_accounts (company_id, account_name, account_type, is_active) VALUES ({ph}, {ph}, {ph}, {ph})",
                (self.TEST_COMPANY_ID, "Input CGST", "tax_liability", 1)
            )
        
        # Ensure Input SGST Account exists
        sgst_result = self.db.execute_query(
            f"SELECT id FROM ledger_accounts WHERE company_id = {ph} AND account_name = {ph}",
            (self.TEST_COMPANY_ID, "Input SGST")
        )
        if not sgst_result:
            self.db.execute_update(
                f"INSERT INTO ledger_accounts (company_id, account_name, account_type, is_active) VALUES ({ph}, {ph}, {ph}, {ph})",
                (self.TEST_COMPANY_ID, "Input SGST", "tax_liability", 1)
            )
        
        # Ensure test party exists
        party_result = self.db.execute_query(
            f"SELECT id FROM parties WHERE company_id = {ph} AND name = {ph}",
            (self.TEST_COMPANY_ID, "Test Supplier")
        )
        if not party_result:
            self.db.execute_update(
                f"INSERT INTO parties (company_id, name, party_type, opening_balance) VALUES ({ph}, {ph}, {ph}, {ph})",
                (self.TEST_COMPANY_ID, "Test Supplier", "Creditor", 0.0)
            )
    
    def test_cash_sale_posting(self):
        """Verify that a standard Cash Sale maps perfectly without duplicating entries."""
        # 1. Arrange: Define a dummy sales voucher payload
        voucher_payload = {
            "header": {
                "company_id": self.TEST_COMPANY_ID,
                "voucher_type": "Sales",
                "voucher_no": "TS-001",
                "voucher_date": "2026-03-24",
                "narration": "Automated Test Sale",
                "sales_type": "Cash Sale"
            },
            "items": [
                {
                    "product_name": "Test Product",
                    "quantity": 1,
                    "rate": 1000.0,
                    "tax": 0.0,
                    "total": 1000.0
                }
            ]
        }
        
        # 2. Act: Post the voucher using the engine
        result = self.engine.repost_voucher(
            company_id=self.TEST_COMPANY_ID,
            voucher_type="sales",
            voucher_id=1,
            header=voucher_payload["header"],
            items=voucher_payload["items"],
            apply_stock=False,
            dry_run=False
        )
        
        # 3. Assert: Verify database counts and exact balance calculations
        # Check that rows were created
        rows = self.db.execute_query(
            "SELECT COUNT(*) as count FROM ledger_entries WHERE company_id = ? AND voucher_no = ?", 
            (self.TEST_COMPANY_ID, "TS-001")
        )
        self.assertGreater(rows[0]['count'], 0, "Engine failed to create any ledger entries!")
        
        # Check that entries are balanced (debit == credit)
        debit_sum = self.db.execute_query(
            "SELECT SUM(debit) as total FROM ledger_entries WHERE company_id = ? AND voucher_no = ?",
            (self.TEST_COMPANY_ID, "TS-001")
        )
        credit_sum = self.db.execute_query(
            "SELECT SUM(credit) as total FROM ledger_entries WHERE company_id = ? AND voucher_no = ?",
            (self.TEST_COMPANY_ID, "TS-001")
        )
        self.assertAlmostEqual(
            debit_sum[0]['total'] or 0,
            credit_sum[0]['total'] or 0,
            places=2,
            msg="CRITICAL BUG: Ledger entries are not balanced!"
        )
    
    def test_cash_purchase_string_matching(self):
        """Verify that 'Cash Purchase' (partial string match) successfully maps to Cash ledger."""
        # First, get the test party ID
        party_result = self.db.execute_query(
            "SELECT id FROM parties WHERE company_id = ? AND name = ?",
            (self.TEST_COMPANY_ID, "Test Supplier")
        )
        party_id = party_result[0]['id'] if party_result else None
        self.assertIsNotNone(party_id, "Test party not found!")
        
        voucher_payload = {
            "header": {
                "company_id": self.TEST_COMPANY_ID,
                "voucher_type": "Purchase",
                "voucher_no": "TP-001",
                "voucher_date": "2026-03-24",
                "narration": "Automated Test Purchase",
                "purchase_type": "Cash Purchase",  # Verifies the 'in' inclusive string bug fix
                "party_id": party_id,
                "nature": "Local"
            },
            "items": [
                {
                    "product_name": "Test Purchase Item",
                    "quantity": 1,
                    "rate": 500.0,
                    "tax": 0.0,
                    "total": 500.0
                }
            ]
        }
        
        result = self.engine.repost_voucher(
            company_id=self.TEST_COMPANY_ID,
            voucher_type="purchase",
            voucher_id=2,
            header=voucher_payload["header"],
            items=voucher_payload["items"],
            apply_stock=False,
            dry_run=False
        )
        
        # Assert that rows were created
        rows = self.db.execute_query(
            "SELECT * FROM ledger_entries WHERE company_id = ? AND voucher_no = ?", 
            (self.TEST_COMPANY_ID, "TP-001")
        )
        self.assertTrue(len(rows) > 0, "Engine completely rejected the Cash Purchase entry!")
        
        # Check that entries are balanced
        debit_sum = self.db.execute_query(
            "SELECT SUM(debit) as total FROM ledger_entries WHERE company_id = ? AND voucher_no = ?",
            (self.TEST_COMPANY_ID, "TP-001")
        )
        credit_sum = self.db.execute_query(
            "SELECT SUM(credit) as total FROM ledger_entries WHERE company_id = ? AND voucher_no = ?",
            (self.TEST_COMPANY_ID, "TP-001")
        )
        self.assertAlmostEqual(
            debit_sum[0]['total'] or 0,
            credit_sum[0]['total'] or 0,
            places=2,
            msg="CRITICAL BUG: Ledger entries are not balanced!"
        )
    
    def tearDown(self):
        """Runs AFTER every single test to scrub the database clean."""
        self.db.execute_update("DELETE FROM ledger_entries WHERE company_id = ?", (self.TEST_COMPANY_ID,))
        self.db.execute_update("DELETE FROM parties WHERE company_id = ?", (self.TEST_COMPANY_ID,))
        self.db.execute_update("DELETE FROM ledger_accounts WHERE company_id = ?", (self.TEST_COMPANY_ID,))
        self.db.execute_update("DELETE FROM companies WHERE id = ?", (self.TEST_COMPANY_ID,))


if __name__ == '__main__':
    unittest.main()
