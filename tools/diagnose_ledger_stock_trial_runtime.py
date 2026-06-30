"""
Runtime Diagnosis Tool for Ledger, Stock Report, and Trial Balance

This tool diagnoses the current state of the accounting application by checking:
- Project root path
- Database path
- Active company
- Table counts
- Stock movement types
- Ledger entries before/after rebuild
- Report row counts
"""

import sys
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import Database
from datetime import datetime


def get_table_count(db, table_name, company_id=None):
    """Get count of records in a table."""
    try:
        ph = db._get_placeholder()
        if company_id:
            query = f"SELECT COUNT(*) as count FROM {table_name} WHERE company_id = {ph}"
            params = (company_id,)
        else:
            query = f"SELECT COUNT(*) as count FROM {table_name}"
            params = ()
        result = db.execute_query(query, params)
        return result[0]['count'] if result else 0
    except Exception as e:
        print(f"Error getting count for {table_name}: {e}")
        return 0


def get_movement_type_counts(db, company_id):
    """Get counts by movement_type in stock_movements."""
    try:
        ph = db._get_placeholder()
        query = f"""
            SELECT movement_type, COUNT(*) as count
            FROM stock_movements
            WHERE company_id = {ph}
            GROUP BY movement_type
            ORDER BY movement_type
        """
        result = db.execute_query(query, (company_id,))
        return {row['movement_type']: row['count'] for row in result} if result else {}
    except Exception as e:
        print(f"Error getting movement type counts: {e}")
        return {}


def main():
    print("=" * 70)
    print("RUNTIME DIAGNOSIS TOOL - LEDGER, STOCK, TRIAL BALANCE")
    print("=" * 70)
    print()

    # Project root path
    project_root = Path(__file__).parent.parent.resolve()
    print(f"Project Root Path: {project_root}")
    print()

    # Database path
    db_path = Path(project_root) / "accounting.db"
    print(f"Database Path: {db_path}")
    print(f"Database Exists: {db_path.exists()}")
    print()

    # Initialize database
    db = Database()

    # Load active company
    print("Loading active company from database...")
    active_company = db.get_active_company()

    if not active_company:
        print("ERROR: No active company found in database.")
        print("Please open a company first using the application.")
        return

    company_id = active_company.get('id')
    company_name = active_company.get('business_name', 'Unknown')

    print(f"Active Company: {company_name} (id={company_id})")
    print()

    # Table counts
    print("TABLE COUNTS:")
    print("-" * 70)
    products_count = get_table_count(db, 'products', company_id)
    parties_count = get_table_count(db, 'parties', company_id)
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

    stock_movements_count = get_table_count(db, 'stock_movements', company_id)
    ledger_accounts_count = get_table_count(db, 'ledger_accounts', company_id)
    ledger_entries_count = get_table_count(db, 'ledger_entries', company_id)

    print(f"  Products: {products_count}")
    print(f"  Parties: {parties_count}")
    print(f"  Sales: {sales_count}")
    print(f"  Purchases: {purchases_count}")
    print(f"  Sales Returns: {sales_returns_count}")
    print(f"  Purchase Returns: {purchase_returns_count}")
    print(f"  Stock Movements: {stock_movements_count}")
    print(f"  Ledger Accounts: {ledger_accounts_count}")
    print(f"  Ledger Entries: {ledger_entries_count}")
    print()

    # Movement type counts
    print("STOCK MOVEMENT TYPE COUNTS:")
    print("-" * 70)
    movement_type_counts = get_movement_type_counts(db, company_id)
    for movement_type, count in sorted(movement_type_counts.items()):
        print(f"  {movement_type}: {count}")
    if not movement_type_counts:
        print("  (No stock movements found)")
    print()

    # Ledger summary rows (use LedgerLogic grouping, not raw account_type guesses)
    print("LEDGER SUMMARY ROW COUNTS:")
    print("-" * 70)
    try:
        from datetime import date
        from bizora_core.ledger_logic import LedgerLogic
        ledger_logic = LedgerLogic(db)
        today = date.today()
        fy_start = date(today.year if today.month >= 4 else today.year - 1, 4, 1)

        sales_summary = ledger_logic.get_group_account_summary(company_id, "sales", fy_start, today)
        debtors_summary = ledger_logic.get_group_account_summary(company_id, "debtors", fy_start, today)
        creditors_summary = ledger_logic.get_group_account_summary(company_id, "creditors", fy_start, today)

        sales_ledger_count = len(sales_summary.get("accounts", []))
        debtors_ledger_count = len(debtors_summary.get("accounts", []))
        creditors_ledger_count = len(creditors_summary.get("accounts", []))

        print(f"  Sales Summary Accounts: {sales_ledger_count}")
        print(f"  Sundry Debtors Summary Accounts: {debtors_ledger_count}")
        print(f"  Sundry Creditors Summary Accounts: {creditors_ledger_count}")
    except Exception as e:
        print(f"  Ledger Summary Rows: Error - {e}")
        sales_ledger_count = debtors_ledger_count = creditors_ledger_count = 0
    print()

    # Stock summary rows
    print("STOCK SUMMARY ROW COUNT:")
    print("-" * 70)
    try:
        stock_summary = db.get_stock_summary(company_id, limit=1000, offset=0)
        stock_summary_count = len(stock_summary) if stock_summary else 0
        print(f"  Stock Summary Rows: {stock_summary_count}")
    except Exception as e:
        print(f"  Stock Summary Rows: Error - {e}")
        stock_summary_count = 0
    print()

    # Trial Balance rows
    print("TRIAL BALANCE ROW COUNT:")
    print("-" * 70)
    try:
        from datetime import date
        from bizora_core.trial_balance_logic import TrialBalanceLogic
        tb_logic = TrialBalanceLogic(db)
        today = date.today()
        fy_start = date(today.year if today.month >= 4 else today.year - 1, 4, 1)
        tb_result = tb_logic.get_trial_balance(company_id, fy_start, today)
        tb_rows_count = len(tb_result.get('rows', []))
        print(f"  Trial Balance Rows: {tb_rows_count}")
        print(f"  Trial Balance Totals - OB Dr: {tb_result.get('totals', {}).get('ob_dr', 0):.2f}")
        print(f"  Trial Balance Totals - OB Cr: {tb_result.get('totals', {}).get('ob_cr', 0):.2f}")
        print(f"  Trial Balance Totals - Period Dr: {tb_result.get('totals', {}).get('period_dr', 0):.2f}")
        print(f"  Trial Balance Totals - Period Cr: {tb_result.get('totals', {}).get('period_cr', 0):.2f}")
        print(f"  Trial Balance Totals - Closing Dr: {tb_result.get('totals', {}).get('closing_dr', 0):.2f}")
        print(f"  Trial Balance Totals - Closing Cr: {tb_result.get('totals', {}).get('closing_cr', 0):.2f}")
        print(f"  Trial Balance Balanced: {tb_result.get('totals', {}).get('balanced', False)}")
    except Exception as e:
        print(f"  Trial Balance Rows: Error - {e}")
        tb_rows_count = 0
    print()

    # Generate report
    report_date = datetime.now().strftime("%Y_%m_%d")
    report_filename = f"reports/ledger_stock_trial_runtime_report_{report_date}.md"

    report_content = f"""# Ledger, Stock Report, and Trial Balance Runtime Diagnosis Report

**Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Company:** {company_name} (id={company_id})

## Project Information

- Project Root Path: {project_root}
- Database Path: {db_path}
- Database Exists: {db_path.exists()}

## Table Counts

- Products: {products_count}
- Parties: {parties_count}
- Sales: {sales_count}
- Purchases: {purchases_count}
- Sales Returns: {sales_returns_count}
- Purchase Returns: {purchase_returns_count}
- Stock Movements: {stock_movements_count}
- Ledger Accounts: {ledger_accounts_count}
- Ledger Entries: {ledger_entries_count}

## Stock Movement Type Counts

"""

    for movement_type, count in sorted(movement_type_counts.items()):
        report_content += f"- {movement_type}: {count}\n"

    if not movement_type_counts:
        report_content += "(No stock movements found)\n"

    report_content += f"""
## Ledger Summary Row Counts

- Sales Ledger Entries: {sales_ledger_count}
- Sundry Debtors Ledger Entries: {debtors_ledger_count}
- Sundry Creditors Ledger Entries: {creditors_ledger_count}

## Stock Summary Row Count

- Stock Summary Rows: {stock_summary_count}

## Trial Balance Row Count

- Trial Balance Rows: {tb_rows_count}

## Summary

Runtime diagnosis completed successfully.
"""

    # Save report
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)

    report_path = reports_dir / f"ledger_stock_trial_runtime_report_{report_date}.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)

    print(f"Report saved to: {report_path}")
    print()
    print("=" * 70)
    print("DIAGNOSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
