"""
Old Voucher Ledger Backfill Diagnostic Script

Diagnoses why old saved vouchers are not showing in Ledger.
Prints and saves report to reports/old_voucher_ledger_backfill_diagnosis.md
"""

import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import Database
from config import active_company_manager, resolve_active_company_id


def print_section(title):
    """Print a section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}\n")


def get_table_count(db, table_name, company_id):
    """Get count of records in a table for a specific company."""
    try:
        ph = db._get_placeholder()
        query = f"SELECT COUNT(*) as count FROM {table_name} WHERE company_id = {ph}"
        result = db.execute_query(query, (company_id,))
        return result[0]['count'] if result else 0
    except Exception as e:
        print(f"Error getting count for {table_name}: {e}")
        return 0


def main():
    """Run diagnosis on old voucher ledger backfill."""
    print_section("OLD VOUCHER LEDGER BACKFILL DIAGNOSIS")

    # Initialize database
    try:
        db = Database()
        print(f"Database path: {db.db_path}")
    except Exception as e:
        print(f"ERROR: Failed to initialize database: {e}")
        return

    # Get active company
    print_section("ACTIVE COMPANY")
    active_company = active_company_manager.get_active_company()
    if active_company:
        company_id = active_company.get('id')
        company_name = active_company.get('business_name', 'Unknown')
        print(f"Active company id: {company_id}")
        print(f"Active company name: {company_name}")
    else:
        # Try to resolve from database
        company_id = resolve_active_company_id(db)
        if company_id:
            active_company = active_company_manager.get_active_company()
            company_name = active_company.get('business_name', 'Unknown')
            print(f"Resolved active company id: {company_id}")
            print(f"Resolved active company name: {company_name}")
        else:
            print("ERROR: No active company found")
            return

    # Voucher counts
    print_section("VOUCHER COUNTS")
    sales_count = get_table_count(db, 'sales', company_id)
    purchases_count = get_table_count(db, 'purchases', company_id)
    
    try:
        sales_returns_count = get_table_count(db, 'sales_returns', company_id)
    except:
        sales_returns_count = 0
    
    try:
        purchase_returns_count = get_table_count(db, 'purchase_returns', company_id)
    except:
        purchase_returns_count = 0
    
    ledger_entries_before = get_table_count(db, 'ledger_entries', company_id)
    
    print(f"Sales count: {sales_count}")
    print(f"Purchases count: {purchases_count}")
    print(f"Sales Returns count: {sales_returns_count}")
    print(f"Purchase Returns count: {purchase_returns_count}")
    print(f"Ledger entries count: {ledger_entries_before}")

    # Sample old sales headers
    print_section("SAMPLE OLD SALES HEADERS")
    ph = db._get_placeholder()
    try:
        sales_sample = db.execute_query(
            f"SELECT id, invoice_number, invoice_date, party_id, sales_type, nature, "
            f"sub_total, discount_total, tax_total, grand_total, amount_received "
            f"FROM sales WHERE company_id = {ph} LIMIT 5",
            (company_id,)
        )
        if sales_sample:
            for i, sale in enumerate(sales_sample, 1):
                print(f"  {i}. Sales ID: {sale.get('id')}, Invoice No: {sale.get('invoice_number')}, "
                      f"Date: {sale.get('invoice_date')}, Party ID: {sale.get('party_id')}, "
                      f"Sub Total: {sale.get('sub_total')}, Tax Total: {sale.get('tax_total')}, "
                      f"Grand Total: {sale.get('grand_total')}, Amount Received: {sale.get('amount_received')}")
        else:
            print("  No sales found")
    except Exception as e:
        print(f"ERROR: Failed to get sales sample: {e}")

    # Sample old sales item rows
    print_section("SAMPLE OLD SALES ITEM ROWS")
    try:
        if sales_count > 0:
            # Get first sale ID
            first_sale = db.execute_query(
                f"SELECT id FROM sales WHERE company_id = {ph} LIMIT 1",
                (company_id,)
            )
            if first_sale:
                sale_id = first_sale[0]['id']
                sales_items = db.execute_query(
                    f"SELECT * FROM sales_items WHERE sale_id = {ph}",
                    (sale_id,)
                )
                if sales_items:
                    for i, item in enumerate(sales_items[:5], 1):
                        print(f"  {i}. Product ID: {item.get('product_id')}, Qty: {item.get('quantity')}, "
                              f"Rate: {item.get('rate')}, Amount: {item.get('amount')}, "
                              f"CGST Amount: {item.get('cgst_amount')}, SGST Amount: {item.get('sgst_amount')}, "
                              f"IGST Amount: {item.get('igst_amount')}, CESS Amount: {item.get('cess_amount')}, "
                              f"Tax Amount: {item.get('tax_amount')}")
                else:
                    print("  No sales items found for first sale")
        else:
            print("  No sales to sample items from")
    except Exception as e:
        print(f"ERROR: Failed to get sales items sample: {e}")

    # Sample old purchase headers
    print_section("SAMPLE OLD PURCHASE HEADERS")
    try:
        purchases_sample = db.execute_query(
            f"SELECT id, purchase_number, purchase_date, party_id, purchase_type, nature, "
            f"sub_total, discount_total, tax_total, grand_total, amount_paid "
            f"FROM purchases WHERE company_id = {ph} LIMIT 5",
            (company_id,)
        )
        if purchases_sample:
            for i, purchase in enumerate(purchases_sample, 1):
                print(f"  {i}. Purchase ID: {purchase.get('id')}, Purchase No: {purchase.get('purchase_number')}, "
                      f"Date: {purchase.get('purchase_date')}, Party ID: {purchase.get('party_id')}, "
                      f"Sub Total: {purchase.get('sub_total')}, Tax Total: {purchase.get('tax_total')}, "
                      f"Grand Total: {purchase.get('grand_total')}, Amount Paid: {purchase.get('amount_paid')}")
        else:
            print("  No purchases found")
    except Exception as e:
        print(f"ERROR: Failed to get purchases sample: {e}")

    # Sample old purchase item rows
    print_section("SAMPLE OLD PURCHASE ITEM ROWS")
    try:
        if purchases_count > 0:
            # Get first purchase ID
            first_purchase = db.execute_query(
                f"SELECT id FROM purchases WHERE company_id = {ph} LIMIT 1",
                (company_id,)
            )
            if first_purchase:
                purchase_id = first_purchase[0]['id']
                purchase_items = db.execute_query(
                    f"SELECT * FROM purchase_items WHERE purchase_id = {ph}",
                    (purchase_id,)
                )
                if purchase_items:
                    for i, item in enumerate(purchase_items[:5], 1):
                        print(f"  {i}. Product ID: {item.get('product_id')}, Qty: {item.get('quantity')}, "
                              f"Rate: {item.get('rate')}, Amount: {item.get('amount')}, "
                              f"CGST Amount: {item.get('cgst_amount')}, SGST Amount: {item.get('sgst_amount')}, "
                              f"IGST Amount: {item.get('igst_amount')}, CESS Amount: {item.get('cess_amount')}, "
                              f"Tax Amount: {item.get('tax_amount')}")
                else:
                    print("  No purchase items found for first purchase")
        else:
            print("  No purchases to sample items from")
    except Exception as e:
        print(f"ERROR: Failed to get purchase items sample: {e}")

    # Ledger entries analysis
    print_section("LEDGER ENTRIES ANALYSIS")
    try:
        ledger_entries = db.execute_query(
            f"SELECT voucher_type, voucher_id, COUNT(*) as count "
            f"FROM ledger_entries WHERE company_id = {ph} "
            f"GROUP BY voucher_type, voucher_id LIMIT 10",
            (company_id,)
        )
        if ledger_entries:
            print(f"Ledger entries by voucher:")
            for entry in ledger_entries:
                print(f"  Voucher Type: {entry.get('voucher_type')}, Voucher ID: {entry.get('voucher_id')}, Count: {entry.get('count')}")
        else:
            print("No ledger entries found")
    except Exception as e:
        print(f"ERROR: Failed to analyze ledger entries: {e}")

    # Check for missing data
    print_section("DATA COMPLETENESS CHECK")
    issues = []
    
    # Check sales for missing party_id
    if sales_count > 0:
        missing_party_sales = db.execute_query(
            f"SELECT COUNT(*) as count FROM sales WHERE company_id = {ph} AND (party_id IS NULL OR party_id = 0)",
            (company_id,)
        )
        if missing_party_sales and missing_party_sales[0]['count'] > 0:
            issues.append(f"Sales with missing party_id: {missing_party_sales[0]['count']}")
    
    # Check purchases for missing party_id
    if purchases_count > 0:
        missing_party_purchases = db.execute_query(
            f"SELECT COUNT(*) as count FROM purchases WHERE company_id = {ph} AND (party_id IS NULL OR party_id = 0)",
            (company_id,)
        )
        if missing_party_purchases and missing_party_purchases[0]['count'] > 0:
            issues.append(f"Purchases with missing party_id: {missing_party_purchases[0]['count']}")
    
    if issues:
        print("Data completeness issues found:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("No data completeness issues found")

    # Generate report
    report_date = datetime.now().strftime("%Y_%m_%d")
    report_filename = f"reports/old_voucher_ledger_backfill_diagnosis.md"
    
    report_content = f"""# Old Voucher Ledger Backfill Diagnosis

**Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Company:** {company_name} (id={company_id})

## Active Company

- Company ID: {company_id}
- Company Name: {company_name}

## Voucher Counts

- Sales: {sales_count}
- Purchases: {purchases_count}
- Sales Returns: {sales_returns_count}
- Purchase Returns: {purchase_returns_count}
- Ledger Entries (Before Rebuild): {ledger_entries_before}

## Sample Old Sales Headers

"""
    
    if sales_count > 0:
        try:
            sales_sample = db.execute_query(
                f"SELECT id, invoice_number, invoice_date, party_id, sales_type, nature, "
                f"sub_total, discount_total, tax_total, grand_total, amount_received "
                f"FROM sales WHERE company_id = {ph} LIMIT 5",
                (company_id,)
            )
            if sales_sample:
                for i, sale in enumerate(sales_sample, 1):
                    report_content += f"{i}. Sales ID: {sale.get('id')}, Invoice No: {sale.get('invoice_number')}, Date: {sale.get('invoice_date')}, Party ID: {sale.get('party_id')}, Sub Total: {sale.get('sub_total')}, Tax Total: {sale.get('tax_total')}, Grand Total: {sale.get('grand_total')}, Amount Received: {sale.get('amount_received')}\n"
        except:
            report_content += "Error retrieving sales sample\n"
    else:
        report_content += "No sales found\n"
    
    report_content += "\n## Sample Old Sales Item Rows\n\n"
    
    if sales_count > 0:
        try:
            first_sale = db.execute_query(
                f"SELECT id FROM sales WHERE company_id = {ph} LIMIT 1",
                (company_id,)
            )
            if first_sale:
                sale_id = first_sale[0]['id']
                sales_items = db.execute_query(
                    f"SELECT * FROM sales_items WHERE sale_id = {ph}",
                    (sale_id,)
                )
                if sales_items:
                    for i, item in enumerate(sales_items[:5], 1):
                        report_content += f"{i}. Product ID: {item.get('product_id')}, Qty: {item.get('quantity')}, Rate: {item.get('rate')}, Amount: {item.get('amount')}, CGST Amount: {item.get('cgst_amount')}, SGST Amount: {item.get('sgst_amount')}, IGST Amount: {item.get('igst_amount')}, CESS Amount: {item.get('cess_amount')}, Tax Amount: {item.get('tax_amount')}\n"
        except:
            report_content += "Error retrieving sales items sample\n"
    else:
        report_content += "No sales to sample items from\n"
    
    report_content += "\n## Sample Old Purchase Headers\n\n"
    
    if purchases_count > 0:
        try:
            purchases_sample = db.execute_query(
                f"SELECT id, purchase_number, purchase_date, party_id, purchase_type, nature, "
                f"sub_total, discount_total, tax_total, grand_total, amount_paid "
                f"FROM purchases WHERE company_id = {ph} LIMIT 5",
                (company_id,)
            )
            if purchases_sample:
                for i, purchase in enumerate(purchases_sample, 1):
                    report_content += f"{i}. Purchase ID: {purchase.get('id')}, Purchase No: {purchase.get('purchase_number')}, Date: {purchase.get('purchase_date')}, Party ID: {purchase.get('party_id')}, Sub Total: {purchase.get('sub_total')}, Tax Total: {purchase.get('tax_total')}, Grand Total: {purchase.get('grand_total')}, Amount Paid: {purchase.get('amount_paid')}\n"
        except:
            report_content += "Error retrieving purchases sample\n"
    else:
        report_content += "No purchases found\n"
    
    report_content += "\n## Sample Old Purchase Item Rows\n\n"
    
    if purchases_count > 0:
        try:
            first_purchase = db.execute_query(
                f"SELECT id FROM purchases WHERE company_id = {ph} LIMIT 1",
                (company_id,)
            )
            if first_purchase:
                purchase_id = first_purchase[0]['id']
                purchase_items = db.execute_query(
                    f"SELECT * FROM purchase_items WHERE purchase_id = {ph}",
                    (purchase_id,)
                )
                if purchase_items:
                    for i, item in enumerate(purchase_items[:5], 1):
                        report_content += f"{i}. Product ID: {item.get('product_id')}, Qty: {item.get('quantity')}, Rate: {item.get('rate')}, Amount: {item.get('amount')}, CGST Amount: {item.get('cgst_amount')}, SGST Amount: {item.get('sgst_amount')}, IGST Amount: {item.get('igst_amount')}, CESS Amount: {item.get('cess_amount')}, Tax Amount: {item.get('tax_amount')}\n"
        except:
            report_content += "Error retrieving purchase items sample\n"
    else:
        report_content += "No purchases to sample items from\n"
    
    report_content += "\n## Data Completeness Check\n\n"
    
    if issues:
        report_content += "Data completeness issues found:\n\n"
        for issue in issues:
            report_content += f"- {issue}\n"
    else:
        report_content += "No data completeness issues found\n"
    
    report_content += "\n## Why Each Old Voucher Was or Was Not Posted\n\n"
    
    report_content += f"""**Note:** This diagnosis shows the current state of vouchers and ledger entries.
The actual posting status will be determined when the rebuild process runs.

**Expected Behavior:**
- If sales_count > 0 and ledger_entries_before == 0: Old sales vouchers need to be posted
- If purchases_count > 0 and ledger_entries_before == 0: Old purchase vouchers need to be posted
- If sales_returns_count > 0 and ledger_entries_before == 0: Old sales return vouchers need to be posted
- If purchase_returns_count > 0 and ledger_entries_before == 0: Old purchase return vouchers need to be posted

**After Rebuild:**
- Ledger entries count should increase based on posted vouchers
- Each voucher should create 2 or more ledger entries (double-entry)
"""

    # Save report
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    report_path = reports_dir / f"old_voucher_ledger_backfill_diagnosis_{report_date}.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
    
    print(f"\nReport saved to: {report_path}")
    print_section("DIAGNOSIS COMPLETE")


if __name__ == "__main__":
    main()
