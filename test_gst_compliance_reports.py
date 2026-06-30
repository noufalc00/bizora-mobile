"""Focused tests for GST compliance report helpers."""

import os
import unittest

from db import Database
from bizora_core.gst_compliance import classify_invoice, is_valid_gstin, place_of_supply_label
from bizora_core.gstr1_logic import GSTR1Logic

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class GSTComplianceReportTest(unittest.TestCase):
    """Verify GST classification, HSN aggregation, and export transforms."""

    def test_classification_and_pos_helpers(self):
        """Invalid GSTINs are B2C and POS labels use GST state codes."""
        self.assertTrue(is_valid_gstin("32ABCDE1234F1Z5"))
        self.assertFalse(is_valid_gstin("32ABCDE1234F1Z"))
        self.assertEqual(place_of_supply_label("Kerala"), "32-Kerala")
        self.assertEqual(
            classify_invoice("32ABCDE1234F1Z5", "32-Kerala", "32-Kerala", 1000),
            "B2B",
        )
        self.assertEqual(
            classify_invoice("INVALID", "33-Tamil Nadu", "32-Kerala", 300000),
            "B2CL",
        )
        self.assertEqual(
            classify_invoice("", "33-Tamil Nadu", "32-Kerala", 250000),
            "B2CS",
        )
        self.assertEqual(
            classify_invoice("", "32-Kerala", "32-Kerala", 300000),
            "B2CS",
        )

    def test_hsn_summary_groups_by_hsn_and_uqc(self):
        """HSN summary aggregates split tax amounts by HSN/UQC."""
        db = Database(db_type="sqlite", db_path=":memory:")
        conn = db.connect()
        cursor = conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE sales (
                id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                invoice_date TEXT NOT NULL,
                status TEXT
            );
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                hsn TEXT,
                unit TEXT
            );
            CREATE TABLE sales_items (
                id INTEGER PRIMARY KEY,
                sale_id INTEGER NOT NULL,
                product_id INTEGER,
                hsn TEXT,
                unit TEXT,
                quantity REAL,
                net_value REAL,
                igst_amount REAL,
                cgst_amount REAL,
                sgst_amount REAL,
                cess_amount REAL,
                tax_amount REAL
            );
            """
        )
        cursor.execute(
            "INSERT INTO sales (id, company_id, invoice_date, status) VALUES (?, ?, ?, ?)",
            (1, 1, "2026-04-01", "Active"),
        )
        cursor.executemany(
            """
            INSERT INTO sales_items
                (sale_id, product_id, hsn, unit, quantity, net_value,
                 igst_amount, cgst_amount, sgst_amount, cess_amount, tax_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, None, "1001", "PCS", 2, 100, 18, 0, 0, 0, 18),
                (1, None, "1001", "PCS", 3, 150, 27, 0, 0, 0, 27),
                (1, None, "1001", "KGS", 4, 200, 0, 18, 18, 0, 36),
            ],
        )
        conn.commit()

        rows = GSTR1Logic(db)._generate_hsn_summary(1, "2026-04-01", "2026-04-30")
        by_uqc = {row["uqc"]: row for row in rows}

        self.assertEqual(len(rows), 2)
        self.assertEqual(by_uqc["PCS"]["qty"], 5)
        self.assertEqual(by_uqc["PCS"]["val"], 250)
        self.assertEqual(by_uqc["PCS"]["iamt"], 45)
        self.assertEqual(by_uqc["KGS"]["qty"], 4)
        self.assertEqual(by_uqc["KGS"]["camt"], 18)
        self.assertEqual(by_uqc["KGS"]["samt"], 18)
        db.force_disconnect()

    def test_gstr1_categorization_and_tax_mapping(self):
        """GSTR-1 sections classify once and map split taxes correctly."""
        logic = GSTR1Logic(Database(db_type="sqlite", db_path=":memory:"))
        company = {"state": "32-Kerala"}
        sales = [
            {
                "invoice_number": "B2B-1",
                "invoice_date": "2026-04-01",
                "party_gstin": "32ABCDE1234F1Z5",
                "party_state": "Kerala",
                "grand_total": 118,
                "taxable_value": 100,
                "cgst_total": 9,
                "sgst_total": 9,
                "igst_total": 0,
                "cess_total": 0,
            },
            {
                "invoice_number": "B2CL-1",
                "invoice_date": "2026-04-02",
                "party_gstin": "",
                "party_state": "Tamil Nadu",
                "grand_total": 300000,
                "taxable_value": 250000,
                "cgst_total": 0,
                "sgst_total": 0,
                "igst_total": 45000,
                "cess_total": 0,
            },
            {
                "invoice_number": "B2CS-1",
                "invoice_date": "2026-04-03",
                "party_gstin": "INVALID",
                "party_state": "Tamil Nadu",
                "grand_total": 250000,
                "taxable_value": 200000,
                "cgst_total": 0,
                "sgst_total": 0,
                "igst_total": 36000,
                "cess_total": 0,
            },
        ]

        b2b = logic._categorize_b2b(sales, company)
        b2cl = logic._categorize_b2cl(sales, company)
        b2cs = logic._categorize_b2cs(sales, company)

        self.assertEqual(len(b2b), 1)
        self.assertEqual(len(b2cl), 1)
        self.assertEqual(sum(row["inv_count"] for row in b2cs), 1)
        self.assertEqual(b2b[0]["inv"]["itms"][0]["itm_det"]["camt"], 9)
        self.assertEqual(b2b[0]["inv"]["itms"][0]["itm_det"]["samt"], 9)
        self.assertEqual(b2cl[0]["inv"]["itms"][0]["itm_det"]["iamt"], 45000)
        self.assertEqual(b2cs[0]["iamt"], 36000)

    def test_portal_export_headers(self):
        """Portal export rows expose offline-tool style headers."""
        logic = GSTR1Logic(Database(db_type="sqlite", db_path=":memory:"))
        rows = logic.build_portal_export_rows({
            "b2b": [{
                "ctin": "32ABCDE1234F1Z5",
                "inv": {
                    "inum": "S-1",
                    "idt": "01-04-2026",
                    "val": 118.0,
                    "pos": "32-Kerala",
                    "rchrg": "N",
                    "itms": [{"itm_det": {"rt": 18, "txval": 100, "csamt": 0}}],
                },
            }],
            "b2cl": [],
            "b2cs": [],
            "hsn": [],
        })

        self.assertIn("GSTIN/UIN of Recipient", rows["b2b"][0])
        self.assertIn("Invoice Number", rows["b2b"][0])
        self.assertIn("Place Of Supply", rows["b2b"][0])
        self.assertIn("Cess Amount", rows["b2b"][0])

    def test_gst_sales_report_footer_totals(self):
        """GST Sales Report footer totals update from structured report data."""
        try:
            from PySide6.QtWidgets import QApplication
            from ui.gst_sales_report_page import GSTSalesReportPage
        except ImportError:
            self.skipTest("PySide6 is not available")

        app = QApplication.instance() or QApplication([])
        _ = app
        page = GSTSalesReportPage(db=Database(db_type="sqlite", db_path=":memory:"))
        page._on_report_ready(
            {
                "b2b": [{
                    "grand_total": 118,
                    "taxable_value": 100,
                    "cgst": 9,
                    "sgst": 9,
                    "igst": 0,
                    "cess": 0,
                }],
                "b2cl": [{
                    "grand_total": 300000,
                    "taxable_value": 250000,
                    "cgst": 0,
                    "sgst": 0,
                    "igst": 45000,
                    "cess": 0,
                }],
                "b2cs": {
                    ("32-Kerala", 18): {
                        "total_value": 590,
                        "taxable_value": 500,
                        "cgst": 45,
                        "sgst": 45,
                        "igst": 0,
                        "cess": 0,
                        "rate": 18,
                        "place_of_supply": "32-Kerala",
                        "type": "B2CS",
                        "invoice_count": 1,
                        "sale_ids": [1],
                    }
                },
                "hsn": [],
            },
        )

        self.assertEqual(page.b2b_b2cl_table.rowCount(), 2)
        self.assertEqual(page.b2cs_table.rowCount(), 1)
        self.assertIn("300708.00", page.footer_total_labels["invoice_value"].text())
        self.assertIn("250600.00", page.footer_total_labels["taxable_value"].text())
        self.assertIn("54.00", page.footer_total_labels["cgst"].text())
        self.assertIn("54.00", page.footer_total_labels["sgst"].text())
        self.assertIn("45000.00", page.footer_total_labels["igst"].text())
        self.assertIn("0.00", page.footer_total_labels["cess"].text())


if __name__ == "__main__":
    unittest.main()
