"""
Runtime Diagnostic Script for Books & Reports Data
Diagnoses actual DB data counts from the active database.
Run outside UI to get accurate data state.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import active_company_manager, resolve_active_company_id
from db import Database


def print_section(title):
    """Print a section header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def main():
    """Run diagnostics on the books and reports data."""
    print_section("BOOKS & REPORTS RUNTIME DIAGNOSIS")

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
        print(f"Active company id: {active_company.get('id')}")
        print(f"Active company name: {active_company.get('business_name')}")
        print(f"Active company status: {active_company.get('is_active')}")
    else:
        print("Active company: None (manager)")
        # Try to resolve from database
        resolved_company_id = resolve_active_company_id(db)
        if resolved_company_id:
            active_company = active_company_manager.get_active_company()
            if active_company:
                print(f"Resolved active company id: {active_company.get('id')}")
                print(f"Resolved active company name: {active_company.get('business_name')}")
        else:
            print("No active company found in database")

    # Companies
    print_section("COMPANIES")
    try:
        companies = db.get_all_companies()
        print(f"Total companies: {len(companies)}")
        for company in companies:
            print(f"  - ID: {company.get('id')}, Name: {company.get('business_name')}, Active: {company.get('is_active')}")
    except Exception as e:
        print(f"ERROR: Failed to get companies: {e}")
        companies = []

    # Get company_id for further queries
    company_id = None
    if active_company:
        company_id = active_company.get('id')
    else:
        # Try to resolve from database again
        company_id = resolve_active_company_id(db)
        if company_id:
            active_company = active_company_manager.get_active_company()
            print(f"\nNote: Resolved active company from database (id={company_id})")

    if not company_id:
        print("\nERROR: No active company available for further queries")
        print("Please open a company in the application first.")
        return

    # Products
    print_section("PRODUCTS")
    try:
        products = db.get_products_by_company(company_id)
        print(f"Total products: {len(products)}")
    except Exception as e:
        print(f"ERROR: Failed to get products: {e}")
        products = []

    # Parties
    print_section("PARTIES")
    try:
        parties = db.get_parties_by_company(company_id)
        print(f"Total parties: {len(parties)}")

        # Count by party_type
        debitor_count = sum(1 for p in parties if str(p.get('party_type', '')).lower() == 'debitor')
        creditor_count = sum(1 for p in parties if str(p.get('party_type', '')).lower() == 'creditor')
        both_count = sum(1 for p in parties if str(p.get('party_type', '')).lower() == 'both')

        print(f"  Debitor count: {debitor_count}")
        print(f"  Creditor count: {creditor_count}")
        print(f"  Both count: {both_count}")
    except Exception as e:
        print(f"ERROR: Failed to get parties: {e}")
        parties = []

    # Stock movements
    print_section("STOCK MOVEMENTS")
    try:
        # Use execute_query to get raw stock movements
        ph = db._get_placeholder()
        query = f"""
            SELECT movement_type, COUNT(*) as count
            FROM stock_movements
            WHERE company_id = {ph}
            GROUP BY movement_type
            ORDER BY movement_type
        """
        result = db.execute_query(query, (company_id,))
        total_movements = sum(row.get('count', 0) for row in result)
        print(f"Total stock movements: {total_movements}")
        print(f"\nCount by movement_type:")
        for row in result:
            print(f"  - {row.get('movement_type')}: {row.get('count', 0)}")

        # Sample 10 rows
        print(f"\nSample 10 rows:")
        query = f"""
            SELECT * FROM stock_movements
            WHERE company_id = {ph}
            LIMIT 10
        """
        sample = db.execute_query(query, (company_id,))
        for i, row in enumerate(sample, 1):
            print(f"  {i}. movement_type={row.get('movement_type')}, product_id={row.get('product_id')}, quantity={row.get('quantity')}, reference_type={row.get('reference_type')}, reference_id={row.get('reference_id')}")
    except Exception as e:
        print(f"ERROR: Failed to get stock movements: {e}")

    # Ledger accounts
    print_section("LEDGER ACCOUNTS")
    try:
        ph = db._get_placeholder()
        query = f"""
            SELECT account_type, COUNT(*) as count
            FROM ledger_accounts
            WHERE company_id = {ph}
            GROUP BY account_type
            ORDER BY account_type
        """
        result = db.execute_query(query, (company_id,))
        total_accounts = sum(row.get('count', 0) for row in result)
        print(f"Total ledger accounts: {total_accounts}")
        print(f"\nCount by account_type:")
        for row in result:
            print(f"  - {row.get('account_type')}: {row.get('count', 0)}")

        # Sample 10 rows
        print(f"\nSample 10 rows:")
        query = f"""
            SELECT * FROM ledger_accounts
            WHERE company_id = {ph}
            LIMIT 10
        """
        sample = db.execute_query(query, (company_id,))
        for i, row in enumerate(sample, 1):
            print(f"  {i}. id={row.get('id')}, account_name={row.get('account_name')}, account_type={row.get('account_type')}, opening_balance={row.get('opening_balance')}")
    except Exception as e:
        print(f"ERROR: Failed to get ledger accounts: {e}")

    # Ledger entries
    print_section("LEDGER ENTRIES")
    try:
        ph = db._get_placeholder()
        query = f"""
            SELECT voucher_type, COUNT(*) as count
            FROM ledger_entries
            WHERE company_id = {ph}
            GROUP BY voucher_type
            ORDER BY voucher_type
        """
        result = db.execute_query(query, (company_id,))
        total_entries = sum(row.get('count', 0) for row in result)
        print(f"Total ledger entries: {total_entries}")
        print(f"\nCount by voucher_type:")
        for row in result:
            print(f"  - {row.get('voucher_type')}: {row.get('count', 0)}")

        # Sample 10 rows
        print(f"\nSample 10 rows:")
        query = f"""
            SELECT * FROM ledger_entries
            WHERE company_id = {ph}
            LIMIT 10
        """
        sample = db.execute_query(query, (company_id,))
        for i, row in enumerate(sample, 1):
            print(f"  {i}. voucher_type={row.get('voucher_type')}, voucher_id={row.get('voucher_id')}, account_id={row.get('account_id')}, debit={row.get('debit')}, credit={row.get('credit')}")
    except Exception as e:
        print(f"ERROR: Failed to get ledger entries: {e}")

    # Sales / purchases / returns counts
    print_section("SALES / PURCHASES / RETURNS")
    try:
        ph = db._get_placeholder()

        # Sales
        query = f"SELECT COUNT(*) as count FROM sales WHERE company_id = {ph}"
        result = db.execute_query(query, (company_id,))
        sales_count = result[0].get('count', 0) if result else 0
        print(f"Sales count: {sales_count}")

        # Purchases
        query = f"SELECT COUNT(*) as count FROM purchases WHERE company_id = {ph}"
        result = db.execute_query(query, (company_id,))
        purchases_count = result[0].get('count', 0) if result else 0
        print(f"Purchases count: {purchases_count}")

        # Sales Returns
        query = f"SELECT COUNT(*) as count FROM sales_returns WHERE company_id = {ph}"
        result = db.execute_query(query, (company_id,))
        sales_returns_count = result[0].get('count', 0) if result else 0
        print(f"Sales Returns count: {sales_returns_count}")

        # Purchase Returns
        query = f"SELECT COUNT(*) as count FROM purchase_returns WHERE company_id = {ph}"
        result = db.execute_query(query, (company_id,))
        purchase_returns_count = result[0].get('count', 0) if result else 0
        print(f"Purchase Returns count: {purchase_returns_count}")
    except Exception as e:
        print(f"ERROR: Failed to get sales/purchases/returns counts: {e}")

    # Trial balance query raw result count
    print_section("TRIAL BALANCE QUERY")
    try:
        # Simulate trial balance query
        ph = db._get_placeholder()
        query = f"""
            SELECT
                la.id,
                la.account_name,
                la.account_type,
                COALESCE(la.opening_balance, 0) as opening_balance,
                COALESCE(SUM(CASE WHEN le.debit > 0 THEN le.debit ELSE 0 END), 0) as total_debit,
                COALESCE(SUM(CASE WHEN le.credit > 0 THEN le.credit ELSE 0 END), 0) as total_credit
            FROM ledger_accounts la
            LEFT JOIN ledger_entries le ON la.id = le.account_id
            WHERE la.company_id = {ph}
            GROUP BY la.id, la.account_name, la.account_type, la.opening_balance
        """
        result = db.execute_query(query, (company_id,))
        print(f"Trial balance query result count: {len(result)}")
        if result:
            print(f"\nSample 5 rows:")
            for i, row in enumerate(result[:5], 1):
                print(f"  {i}. {row.get('account_name')} ({row.get('account_type')}) - Opening: {row.get('opening_balance')}, Debit: {row.get('total_debit')}, Credit: {row.get('total_credit')}")
    except Exception as e:
        print(f"ERROR: Failed to run trial balance query: {e}")

    print_section("DIAGNOSIS COMPLETE")


if __name__ == "__main__":
    main()
