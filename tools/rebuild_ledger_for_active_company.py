"""
Ledger Rebuild Tool for Active Company

This tool rebuilds ledger entries for the active company by reposting all saved vouchers.
It ensures that ledger entries are properly created from existing sales, purchases, and returns.
"""

import sys
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import Database
from bizora_core.ledger_logic import LedgerLogic
from datetime import datetime


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
    print("=" * 70)
    print("LEDGER REBUILD TOOL FOR ACTIVE COMPANY")
    print("=" * 70)
    print()

    # Initialize database
    db = Database()
    
    # Load active company from database
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

    # Show counts before rebuild
    print("BEFORE REBUILD:")
    print("-" * 70)
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
    
    ledger_entries_count = get_table_count(db, 'ledger_entries', company_id)
    
    print(f"  Sales: {sales_count}")
    print(f"  Purchases: {purchases_count}")
    print(f"  Sales Returns: {sales_returns_count}")
    print(f"  Purchase Returns: {purchase_returns_count}")
    print(f"  Ledger Entries: {ledger_entries_count}")
    print()

    # Run rebuild
    print("RUNNING LEDGER REBUILD...")
    print("-" * 70)
    
    ledger_logic = LedgerLogic(db)
    result = ledger_logic.rebuild_ledger_for_company(company_id)
    
    print()
    print("REBUILD RESULT:")
    print("-" * 70)
    print(f"  Success: {result['success']}")
    print(f"  Message: {result['message']}")
    print(f"  Sales Posted: {result['sales_posted']}")
    print(f"  Purchases Posted: {result['purchases_posted']}")
    print(f"  Sales Returns Posted: {result['sales_returns_posted']}")
    print(f"  Purchase Returns Posted: {result['purchase_returns_posted']}")
    if result['failed']:
        print(f"  Failed: {len(result['failed'])}")
        for failed in result['failed']:
            print(f"    - {failed}")
    print()

    # Show counts after rebuild
    print("AFTER REBUILD:")
    print("-" * 70)
    print(f"  Ledger Entries Before: {result.get('ledger_entries_before', 0)}")
    print(f"  Ledger Entries After: {result.get('ledger_entries_after', 0)}")
    print()

    # Generate report
    report_date = datetime.now().strftime("%Y_%m_%d")
    report_filename = f"reports/ledger_backfill_report_{report_date}.md"

    report_content = f"""# Ledger Backfill Report

**Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Company:** {company_name} (id={company_id})

## Before Rebuild

- Sales: {sales_count}
- Purchases: {purchases_count}
- Sales Returns: {sales_returns_count}
- Purchase Returns: {purchase_returns_count}
- Ledger Entries: {result.get('ledger_entries_before', 0)}

## Rebuild Process

- Success: {result['success']}
- Message: {result['message']}
- Sales Posted: {result['sales_posted']}
- Purchases Posted: {result['purchases_posted']}
- Sales Returns Posted: {result['sales_returns_posted']}
- Purchase Returns Posted: {result['purchase_returns_posted']}
- Failed Count: {len(result['failed']) if result['failed'] else 0}

"""

    if result['failed']:
        report_content += "### Failed Vouchers\n\n"
        for failed in result['failed']:
            report_content += f"- {failed}\n"
        report_content += "\n"

    report_content += f"""## After Rebuild

- Ledger Entries: {result.get('ledger_entries_after', 0)}

## Summary

{'Ledger backfill completed successfully.' if result['success'] else 'Ledger backfill failed.'}

---

**Note:** This report documents the ledger backfill process for existing vouchers.
After this rebuild, old Sales, Purchase, Sales Return, and Purchase Return vouchers
should appear in Ledger and Trial Balance.
"""

    # Save report
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)

    report_path = reports_dir / f"ledger_backfill_report_{report_date}.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)

    print(f"Report saved to: {report_path}")
    print()
    print("=" * 70)
    print("BACKFILL COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
