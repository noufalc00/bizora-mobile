"""Regression tests for GST-filtered book report item aggregation."""

import sqlite3
import unittest

from bizora_core.quotation_book_logic import QuotationBookLogic
from bizora_core.sales_book_logic import SalesBookLogic


class InMemoryReportDb:
    """Small sqlite-backed adapter exposing the report logic database API."""

    def __init__(self):
        """Create an in-memory database with dict-like row output."""
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row

    def _get_placeholder(self):
        """Return the sqlite placeholder used by report SQL."""
        return "?"

    def execute_query(self, query, params=()):
        """Execute read-only test SQL and return dictionaries."""
        cursor = self.connection.execute(query, params or ())
        return [dict(row) for row in cursor.fetchall()]

    def execute_script(self, script):
        """Create the compact schema used by focused report tests."""
        self.connection.executescript(script)

    def execute(self, query, params=()):
        """Insert fixture rows for report tests."""
        self.connection.execute(query, params)
        self.connection.commit()

    def close(self):
        """Close the in-memory database after each test."""
        self.connection.close()


class BookReportGstFilterTest(unittest.TestCase):
    """Validate GST filters aggregate only matching item rows."""

    def setUp(self):
        """Create compact sales and quotation schemas with mixed-tax fixtures."""
        self.db = InMemoryReportDb()
        self.db.execute_script(
            """
            CREATE TABLE parties (
                id INTEGER PRIMARY KEY,
                name TEXT,
                party_type TEXT
            );
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                name TEXT,
                barcode TEXT,
                category TEXT,
                hsn TEXT
            );
            CREATE TABLE sales (
                id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                invoice_number TEXT NOT NULL,
                invoice_date TEXT NOT NULL,
                party_id INTEGER,
                sales_type TEXT,
                nature TEXT,
                due_date TEXT,
                narration TEXT,
                sub_total REAL DEFAULT 0,
                discount_total REAL DEFAULT 0,
                tax_total REAL DEFAULT 0,
                round_off REAL DEFAULT 0,
                grand_total REAL DEFAULT 0,
                amount_received REAL DEFAULT 0
            );
            CREATE TABLE sales_items (
                id INTEGER PRIMARY KEY,
                sale_id INTEGER NOT NULL,
                product_id INTEGER,
                sl_no INTEGER,
                hsn TEXT,
                tax_percent REAL DEFAULT 0,
                unit TEXT,
                rate REAL DEFAULT 0,
                quantity REAL DEFAULT 0,
                gross_value REAL DEFAULT 0,
                discount REAL DEFAULT 0,
                net_value REAL DEFAULT 0,
                tax_amount REAL DEFAULT 0,
                grand_total REAL DEFAULT 0,
                cgst REAL DEFAULT 0,
                sgst REAL DEFAULT 0,
                igst REAL DEFAULT 0,
                cess REAL DEFAULT 0,
                cgst_amount REAL DEFAULT 0,
                sgst_amount REAL DEFAULT 0,
                igst_amount REAL DEFAULT 0,
                cess_amount REAL DEFAULT 0
            );
            CREATE TABLE quotations (
                id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                quotation_no TEXT NOT NULL,
                quotation_date TEXT NOT NULL,
                party_id INTEGER,
                quotation_type TEXT,
                nature TEXT,
                narration TEXT,
                sub_total REAL DEFAULT 0,
                discount_total REAL DEFAULT 0,
                tax_total REAL DEFAULT 0,
                round_off REAL DEFAULT 0,
                grand_total REAL DEFAULT 0
            );
            CREATE TABLE quotation_items (
                id INTEGER PRIMARY KEY,
                quotation_id INTEGER NOT NULL,
                product_id INTEGER,
                sl_no INTEGER,
                hsn TEXT,
                tax_percent REAL DEFAULT 0,
                unit TEXT,
                rate REAL DEFAULT 0,
                quantity REAL DEFAULT 0,
                gross_value REAL DEFAULT 0,
                discount REAL DEFAULT 0,
                net_value REAL DEFAULT 0,
                tax_amount REAL DEFAULT 0,
                grand_total REAL DEFAULT 0,
                cgst REAL DEFAULT 0,
                sgst REAL DEFAULT 0,
                igst REAL DEFAULT 0,
                cess REAL DEFAULT 0
            );
            """
        )
        self._seed_common_rows()

    def tearDown(self):
        """Release the in-memory database connection."""
        self.db.close()

    def _seed_common_rows(self):
        """Insert one mixed GST sale, one zero GST sale, and one quotation."""
        self.db.execute("INSERT INTO parties VALUES (1, 'Acme Traders', 'Debitor')")
        self.db.execute("INSERT INTO products VALUES (1, 'Five GST Item', 'P5', 'Goods', '1001')")
        self.db.execute("INSERT INTO products VALUES (2, 'Eighteen GST Item', 'P18', 'Goods', '1002')")
        self.db.execute(
            """
            INSERT INTO sales
                (id, company_id, invoice_number, invoice_date, party_id, sales_type,
                 nature, due_date, narration, sub_total, tax_total, grand_total, amount_received)
            VALUES
                (1, 1, 'S-1', '2026-06-01', 1, 'Cash', 'Intra-state',
                 '2026-06-10', '', 1100, 185, 1285, 0),
                (2, 1, 'S-2', '2026-06-02', 1, 'Cash', 'Intra-state',
                 '2026-06-10', '', 150, 18, 168, 0)
            """
        )
        self.db.execute(
            """
            INSERT INTO sales_items
                (sale_id, product_id, sl_no, tax_percent, rate, quantity, gross_value,
                 net_value, tax_amount, grand_total, cgst, sgst, igst,
                 cgst_amount, sgst_amount, igst_amount)
            VALUES
                (1, 1, 1, 5, 100, 1, 100, 100, 5, 105, 2.5, 2.5, 0, 2.5, 2.5, 0),
                (1, 2, 2, 18, 1000, 1, 1000, 1000, 180, 1180, 9, 9, 0, 90, 90, 0),
                (2, 1, 1, 0, 50, 1, 50, 50, 0, 50, 0, 0, 0, 0, 0, 0),
                (2, 2, 2, 18, 100, 1, 100, 100, 18, 118, 0, 0, 0, 0, 0, 0)
            """
        )
        self.db.execute(
            """
            INSERT INTO quotations
                (id, company_id, quotation_no, quotation_date, party_id, quotation_type,
                 nature, narration, sub_total, tax_total, grand_total)
            VALUES
                (1, 1, 'Q-1', '2026-06-01', 1, 'Cash', 'Intra-state', '', 1100, 185, 1285)
            """
        )
        self.db.execute(
            """
            INSERT INTO quotation_items
                (quotation_id, product_id, sl_no, tax_percent, rate, quantity,
                 gross_value, net_value, cgst, sgst, igst)
            VALUES
                (1, 1, 1, 5, 100, 1, 100, 100, 2.5, 2.5, 0),
                (1, 2, 2, 18, 1000, 1, 1000, 1000, 9, 9, 0)
            """
        )

    def test_bill_wise_gst_filter_uses_matching_item_totals(self):
        """GST 5 bill totals must exclude the GST 18 item and parent totals."""
        rows = SalesBookLogic(self.db).get_bill_wise(
            1, "2026-06-01", "2026-06-30", {"tax_rate": 5.0}
        )["data"]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["voucher_no"], "S-1")
        self.assertAlmostEqual(rows[0]["taxable_amount"], 100.0)
        self.assertAlmostEqual(rows[0]["tax_total"], 5.0)
        self.assertAlmostEqual(rows[0]["grand_total"], 105.0)

    def test_missing_gst_rate_excludes_bill(self):
        """GST 12 must not return bills that only contain other GST rates."""
        rows = SalesBookLogic(self.db).get_bill_wise(
            1, "2026-06-01", "2026-06-30", {"tax_rate": 12.0}
        )["data"]

        self.assertEqual(rows, [])

    def test_zero_gst_filter_does_not_match_taxable_split_zero_rows(self):
        """GST 0 must require zero total tax, not only zero split columns."""
        rows = SalesBookLogic(self.db).get_bill_wise(
            1, "2026-06-01", "2026-06-30", {"tax_rate": 0.0}
        )["data"]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["voucher_no"], "S-2")
        self.assertAlmostEqual(rows[0]["taxable_amount"], 50.0)
        self.assertAlmostEqual(rows[0]["grand_total"], 50.0)

    def test_party_and_credit_reports_use_filtered_item_totals(self):
        """Summary reports must aggregate the already-filtered child rows."""
        logic = SalesBookLogic(self.db)
        party_rows = logic.get_party_wise(
            1, "2026-06-01", "2026-06-30", {"tax_rate": 5.0}
        )["data"]
        credit_rows = logic.get_credit_or_pending(
            1, "2026-06-01", "2026-06-30", {"tax_rate": 5.0}
        )["data"]

        self.assertEqual(len(party_rows), 1)
        self.assertAlmostEqual(party_rows[0]["taxable_amount"], 100.0)
        self.assertAlmostEqual(party_rows[0]["grand_total"], 105.0)
        self.assertEqual(len(credit_rows), 1)
        self.assertAlmostEqual(credit_rows[0]["grand_total"], 105.0)

    def test_quotation_gst_filter_calculates_tax_amount_from_rates(self):
        """Quotation reports must calculate tax from split rates when amount columns are absent."""
        rows = QuotationBookLogic(self.db).get_bill_wise(
            1, "2026-06-01", "2026-06-30", {"tax_rate": 5.0}
        )["data"]

        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["taxable_amount"], 100.0)
        self.assertAlmostEqual(rows[0]["tax_total"], 5.0)
        self.assertAlmostEqual(rows[0]["grand_total"], 105.0)


if __name__ == "__main__":
    unittest.main()
