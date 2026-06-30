# -*- coding: utf-8 -*-
"""
Day Book Commercial Consumer Diagnostic

Checks whether Day Book is reading commercial-engine posting output correctly,
especially Sales Amount Received / Purchase Amount Paid and Cash/Bank voucher
entries that should affect Balance Cash.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import Database
from bizora_core.book_report_common import resolve_active_company_id
from bizora_core.day_book_logic import DayBookLogic


def _query(db, query, params=()):
    try:
        return db.execute_query(query, params) or []
    except Exception as exc:
        print(f"QUERY ERROR: {exc}\nSQL: {query}\nPARAMS: {params}")
        return []


def main():
    # No explicit db_path: Database() resolves the shared accounting.db next
    # to db.py (BASE_DIR), never relative to the launch working directory.
    db = Database(db_type="sqlite")
    init_result = db.initialize_database()
    ph = db._get_placeholder()
    company_id = resolve_active_company_id(db)

    lines = []
    def add(text=""):
        print(text)
        lines.append(str(text))

    add("# Day Book Commercial Consumer Diagnosis")
    add("")
    add(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    add(f"DB initialize result: {init_result}")
    add(f"Active company id: {company_id}")

    if not company_id:
        add("No active company. Open a company first.")
        return

    company = _query(db, f"SELECT business_name FROM companies WHERE id = {ph}", (company_id,))
    company_name = company[0].get("business_name") if company else "Unknown"
    add(f"Active company: {company_name}")
    add("")

    sales = _query(
        db,
        f"""
        SELECT id, invoice_number, invoice_date, sales_type,
               COALESCE(grand_total, 0) AS grand_total,
               COALESCE(amount_received, 0) AS amount_received
        FROM sales
        WHERE company_id = {ph}
        ORDER BY invoice_date, id
        """,
        (company_id,),
    )
    purchases = _query(
        db,
        f"""
        SELECT id, purchase_number, purchase_date, purchase_type,
               COALESCE(grand_total, 0) AS grand_total,
               COALESCE(amount_paid, 0) AS amount_paid
        FROM purchases
        WHERE company_id = {ph}
        ORDER BY purchase_date, id
        """,
        (company_id,),
    )
    ledger_counts = _query(
        db,
        f"""
        SELECT voucher_type, COUNT(*) AS count,
               COALESCE(SUM(debit), 0) AS debit,
               COALESCE(SUM(credit), 0) AS credit
        FROM ledger_entries
        WHERE company_id = {ph}
        GROUP BY voucher_type
        ORDER BY voucher_type
        """,
        (company_id,),
    )

    add("## Source counts")
    add(f"sales rows: {len(sales)}")
    add(f"purchases rows: {len(purchases)}")
    add("ledger voucher counts:")
    for row in ledger_counts:
        add(f"- {row.get('voucher_type')}: count={row.get('count')}, debit={row.get('debit')}, credit={row.get('credit')}")
    add("")

    paid_sales = [r for r in sales if float(r.get("amount_received") or 0) > 0]
    paid_purchases = [r for r in purchases if float(r.get("amount_paid") or 0) > 0]
    add("## Paid/received voucher source check")
    add(f"sales with amount_received > 0: {len(paid_sales)}")
    for row in paid_sales[-10:]:
        add(f"- {row.get('invoice_date')} {row.get('invoice_number')} type={row.get('sales_type')} total={row.get('grand_total')} received={row.get('amount_received')}")
    add(f"purchases with amount_paid > 0: {len(paid_purchases)}")
    for row in paid_purchases[-10:]:
        add(f"- {row.get('purchase_date')} {row.get('purchase_number')} type={row.get('purchase_type')} total={row.get('grand_total')} paid={row.get('amount_paid')}")
    add("")

    day_book = DayBookLogic(db)
    if sales or purchases:
        all_dates = []
        all_dates.extend([str(r.get("invoice_date"))[:10] for r in sales if r.get("invoice_date")])
        all_dates.extend([str(r.get("purchase_date"))[:10] for r in purchases if r.get("purchase_date")])
        from_date = min(all_dates) if all_dates else datetime.now().strftime("%Y-%m-%d")
        to_date = max(all_dates) if all_dates else from_date
    else:
        from_date = to_date = datetime.now().strftime("%Y-%m-%d")

    result = day_book.get_day_book_entries(company_id, from_date, to_date)
    rows = result.get("data", []) if result.get("success") else []
    sales_receipt_rows = [r for r in rows if r.get("row_type") == "sales_receipt"]
    purchase_payment_rows = [r for r in rows if r.get("row_type") == "purchase_payment"]
    cash_receipt_rows = [r for r in rows if r.get("row_type") == "cash_receipt"]
    cash_payment_rows = [r for r in rows if r.get("row_type") == "cash_payment"]

    add("## Day Book result")
    add(f"date range: {from_date} to {to_date}")
    add(f"success: {result.get('success')}")
    add(f"rows: {len(rows)}")
    add(f"sales_receipt rows: {len(sales_receipt_rows)}")
    add(f"purchase_payment rows: {len(purchase_payment_rows)}")
    add(f"cash_receipt rows: {len(cash_receipt_rows)}")
    add(f"cash_payment rows: {len(cash_payment_rows)}")
    add("")

    add("## Sample Day Book receipt/payment rows")
    for row in (sales_receipt_rows + purchase_payment_rows + cash_receipt_rows + cash_payment_rows)[-20:]:
        add(f"- {row.get('date')} {row.get('row_type')} {row.get('particulars')} Dr={row.get('debit')} Cr={row.get('credit')} Source={row.get('source')}")

    os.makedirs("reports", exist_ok=True)
    report_path = os.path.join("reports", "day_book_diagnosis_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    add("")
    add(f"Report saved to: {report_path}")


if __name__ == "__main__":
    main()
