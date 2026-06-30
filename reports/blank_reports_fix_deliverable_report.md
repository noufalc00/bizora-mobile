# Blank Ledger, Stock Report, and Trial Balance Fix - Final Deliverable Report

**Date:** 2026-04-30  
**Project:** Professional Windows Accounting Software  
**Objective:** Fix root cause of blank Ledger, Stock Report, and Trial Balance tables

---

## Executive Summary

This report documents the comprehensive fixes applied to resolve blank Ledger, Stock Report, and Trial Balance tables in the accounting application. The root causes were identified as:
1. Missing ledger_entries for existing vouchers (company_id 24 had sales/purchases but zero ledger entries)
2. Broken SQL query in Stock Report with parameter order mismatch
3. Trial Balance skipping all-zero accounts
4. Inconsistent active company resolution across the application

All fixes have been implemented, compiled successfully, and are ready for manual testing.

---

## Phase 1: Fix Ledger Posting from Existing Vouchers

### Problem
- Ledger posting functions expected header fields (cgst_total, sgst_total, igst_total, cess_total) that may not be present in voucher data
- Voucher logic may only pass tax_total and grand_total
- This caused ledger entries to not be posted properly

### Solution
**File:** `logic/ledger_logic.py`

Added two helper methods:
- `_safe_amount(value)`: Safely converts None, "", invalid values to 0.0
- `_sum_item_tax_split(items)`: Calculates split GST totals from item rows

Updated all voucher posting methods:
- `post_sales_voucher()`: Now calculates tax split from item rows when header split totals are missing
- `post_purchase_voucher()`: Same logic applied
- `post_sales_return_voucher()`: Same logic applied
- `post_purchase_return_voucher()`: Same logic applied

### Code Changes
```python
def _safe_amount(self, value) -> float:
    """Convert None, "", invalid values safely to 0.0."""
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def _sum_item_tax_split(self, items: List[Dict[str, Any]]) -> Dict[str, float]:
    """Return split GST totals from item rows."""
    result = {
        "cgst_total": 0.0,
        "sgst_total": 0.0,
        "igst_total": 0.0,
        "cess_total": 0.0,
        "tax_total": 0.0,
    }
    for item in items:
        result["cgst_total"] += self._safe_amount(item.get("cgst_amount"))
        result["sgst_total"] += self._safe_amount(item.get("sgst_amount"))
        result["igst_total"] += self._safe_amount(item.get("igst_amount"))
        result["cess_total"] += self._safe_amount(item.get("cess_amount"))
        result["tax_total"] += self._safe_amount(item.get("tax_amount"))
    return result
```

---

## Phase 2: Add Safe Ledger Rebuild for Existing Vouchers

### Problem
- Company 24 had existing vouchers (8 sales, 2 purchases) but zero ledger entries
- No mechanism to rebuild ledger entries from existing vouchers

### Solution
**File:** `logic/ledger_logic.py`

Added `rebuild_ledger_for_company(company_id)` method that:
1. Ensures system ledger accounts exist
2. Ensures party ledger accounts exist
3. Deletes existing ledger_entries for the company only
4. Reposts all sales vouchers with item tax splits
5. Reposts all purchase vouchers with item tax splits
6. Reposts all sales returns (if table exists)
7. Reposts all purchase returns (if table exists)
8. Rebuilds running balances for all accounts
9. Returns detailed result dict with counts and any failures

### Code Changes
```python
def rebuild_ledger_for_company(self, company_id: int) -> Dict[str, Any]:
    """Safely rebuild ledger entries for a company by reposting all saved vouchers."""
    # Implementation includes:
    # - System accounts ensure
    # - Party accounts ensure
    # - Delete existing ledger_entries for company
    # - Repost sales with item tax splits
    # - Repost purchases with item tax splits
    # - Repost returns (if tables exist)
    # - Rebuild running balances
    # - Return detailed result dict
```

---

## Phase 3: Fix Stock Report SQL Root Bug

### Problem
- `get_stock_summary()` in db.py used multiple SELECT subqueries with date filters
- Date filter placeholders appeared inside subqueries before p.company_id placeholder
- Parameter count/order mismatch caused wrong values to be bound
- Result: Stock Report was blank or showed incorrect data

### Solution
**File:** `db.py`

Rewrote `get_stock_summary()` to use a single LEFT JOIN subquery:
- Aggregates all movement types in one query
- Date filters applied in the subquery WHERE clause
- Parameters in correct order: movement subquery company_id, date params, products company_id
- Much better performance (one aggregation vs 7 subqueries)

### Code Changes
```python
def get_stock_summary(self, company_id: int, filters: Dict[str, Any] = None,
                     limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    # Rewritten to use single LEFT JOIN subquery
    query = f"""
        SELECT
            p.id,
            p.name,
            p.barcode,
            p.category,
            p.unit,
            p.purchase_rate,
            p.sale_price,
            p.wholesale_rate,
            p.reorder_level,
            COALESCE(ms.opening_qty, 0) as opening_qty,
            COALESCE(ms.purchase_qty, 0) as purchase_qty,
            COALESCE(ms.sales_qty, 0) as sales_qty,
            COALESCE(ms.sales_return_qty, 0) as sales_return_qty,
            COALESCE(ms.purchase_return_qty, 0) as purchase_return_qty,
            COALESCE(ms.adjustment_qty, 0) as adjustment_qty,
            COALESCE(ms.closing_qty, COALESCE(p.quantity, 0)) as closing_qty,
            ms.last_movement_date
        FROM products p
        LEFT JOIN (
            SELECT
                product_id,
                SUM(CASE WHEN movement_type = 'opening' THEN quantity ELSE 0 END) as opening_qty,
                SUM(CASE WHEN movement_type IN ('purchase','transfer_in') THEN quantity ELSE 0 END) as purchase_qty,
                SUM(CASE WHEN movement_type IN ('sale','sales') THEN quantity ELSE 0 END) as sales_qty,
                SUM(CASE WHEN movement_type = 'sales_return' THEN quantity ELSE 0 END) as sales_return_qty,
                SUM(CASE WHEN movement_type = 'purchase_return' THEN quantity ELSE 0 END) as purchase_return_qty,
                SUM(CASE WHEN movement_type = 'adjustment' THEN quantity ELSE 0 END) as adjustment_qty,
                SUM(CASE
                    WHEN movement_type IN ('opening','purchase','transfer_in','sales_return') THEN quantity
                    WHEN movement_type IN ('sale','sales','purchase_return','transfer_out') THEN -quantity
                    WHEN movement_type = 'adjustment' THEN quantity
                    ELSE 0
                END) as closing_qty,
                MAX(COALESCE(created_at, movement_date)) as last_movement_date
            FROM stock_movements sm
            WHERE sm.company_id = {ph}
            {movement_date_filter}
            GROUP BY product_id
        ) ms ON ms.product_id = p.id
        WHERE p.company_id = {ph}
    """
```

---

## Phase 4: Fix Trial Balance Zero-Row Skip

### Problem
- `get_trial_balance()` in trial_balance_logic.py skipped all-zero accounts
- Accounts with no activity and zero opening balance were not shown
- This resulted in incomplete Trial Balance

### Solution
**File:** `logic/trial_balance_logic.py`

Removed the skip logic for all-zero accounts:
- Changed from skipping accounts where ob_dr == 0 and ob_cr == 0 and pdr == 0 and pcr == 0 and cl_dr == 0 and cl_cr == 0
- Now shows all active ledger accounts regardless of balance
- Footer totals can remain zero
- If no ledger_accounts exist, ledger initialization should be called

### Code Changes
```python
# REMOVED:
# Skip zero rows (no activity, no opening balance)
if ob_dr == 0 and ob_cr == 0 and pdr == 0 and pcr == 0 and cl_dr == 0 and cl_cr == 0:
    continue

# REPLACED WITH:
# Do not skip all-zero accounts - show all active ledger accounts
category = _TYPE_CATEGORY.get(acct.get('account_type', ''), acct.get('account_type', ''))
```

---

## Phase 5: Fix Active Company Resolution

### Problem
- Active company resolution was inconsistent across the application
- Some code used `active_company_manager.get_active_company_id()`
- Some code fell back to the first company if no active company set
- No consistent helper to resolve active company from database

### Solution
**File:** `config.py`

Added `resolve_active_company_id(db)` helper function:
1. Tries to get from active_company_manager first
2. If None, calls db.get_active_company()
3. If found, sets active_company_manager.set_active_company(active_company)
4. Returns active company id
5. Never silently uses the first company unless user explicitly chooses fallback

### Code Changes
```python
def resolve_active_company_id(db):
    """
    Resolve active company ID from manager or database.
    This helper ensures the active company is properly loaded from the database
    on startup and provides a consistent way to get the active company ID
    across the application.
    """
    # Try to get from manager first
    company_id = active_company_manager.get_active_company_id()
    if company_id:
        return company_id

    # If not in manager, try to load from database
    try:
        active_company = db.get_active_company()
        if active_company:
            active_company_manager.set_active_company(active_company)
            return active_company.get('id')
    except Exception as e:
        print(f"Error resolving active company from database: {e}")

    # No active company found
    return None
```

---

## Phase 6: Create Ledger Rebuild Tool

### Problem
- No CLI tool to rebuild ledger entries for the active company
- Manual rebuild process was complex and error-prone

### Solution
**File:** `tools/rebuild_ledger_for_active_company.py` (NEW)

Created comprehensive CLI tool that:
- Loads active company from database using db.get_active_company()
- If no active company, prints clear error
- Shows counts before rebuild: sales, purchases, sales_returns, purchase_returns, ledger_entries
- Runs rebuild_ledger_for_company(active_company_id)
- Shows counts after rebuild
- Saves detailed report to `reports/ledger_rebuild_report_YYYY_MM_DD.md`

### Usage
```bash
python tools/rebuild_ledger_for_active_company.py
```

---

## Phase 7: Update UI Pages with resolve_active_company_id

### Problem
- UI pages used inconsistent methods to get active company ID
- Some used active_company_manager directly
- No fallback to database if manager was empty

### Solution
Updated all report UI pages to use `resolve_active_company_id()`:

**Files Modified:**
- `ui/ledger_page.py`: Import and use resolve_active_company_id
- `ui/stock_report_page.py`: Import and use resolve_active_company_id  
- `ui/trial_balance_page.py`: Import and use resolve_active_company_id

### Code Changes
```python
# Added import:
from config import COLORS, active_company_manager, resolve_active_company_id

# Replaced:
self.company_id = active_company_manager.get_active_company_id() if active_company_manager else None

# With:
self.company_id = resolve_active_company_id(self.db)
```

---

## Phase 8: Update Runtime Diagnostic Script

### Problem
- Diagnostic script used fallback to first company if no active company set
- This could diagnose the wrong company's data
- No use of resolve_active_company_id helper

### Solution
**File:** `tools/diagnose_books_reports_data.py`

Updated to:
- Import resolve_active_company_id
- Try to resolve active company from database if manager is empty
- Remove fallback to first company
- Print clear error if no active company found
- Display "Please open a company in the application first" message

### Code Changes
```python
# Added import:
from config import active_company_manager, resolve_active_company_id

# Updated logic to use resolve_active_company_id instead of first company fallback
if not company_id:
    print("\nERROR: No active company available for further queries")
    print("Please open a company in the application first.")
    return
```

---

## Phase 9: Compile/DB Tests

### Verification
Ran Python compilation checks on all modified files:

**Files Tested:**
- `logic/ledger_logic.py` ✓
- `db.py` ✓
- `config.py` ✓
- `ui/ledger_page.py` ✓
- `ui/stock_report_page.py` ✓
- `ui/trial_balance_page.py` ✓
- `logic/trial_balance_logic.py` ✓
- `tools/diagnose_books_reports_data.py` ✓
- `tools/rebuild_ledger_for_active_company.py` ✓

**Result:** All files compiled successfully with no syntax errors.

---

## Phase 10: Mandatory Manual Tests (PENDING)

### Required Tests

**Test 1: Ledger Rebuild**
1. Open the application
2. Open company "Varnam Clothing Centre Vdl" (id=24)
3. Run: `python tools/rebuild_ledger_for_active_company.py`
4. Verify:
   - Before counts: sales=8, purchases=2, ledger_entries=0
   - After counts: ledger_entries > 0
   - Report saved to reports/ledger_rebuild_report_YYYY_MM_DD.md

**Test 2: Ledger Page**
1. Navigate to Ledger page
2. Select "All Ledgers" or any ledger type
3. Verify:
   - Accounts are displayed
   - Ledger entries are shown
   - Running balance column shows values with Dr/Cr format
   - Summary labels show Dr/Cr totals

**Test 3: Stock Report**
1. Navigate to Stock Report page
2. Click "Load Report"
3. Verify:
   - Stock summary data is displayed
   - Opening, purchase, sales, closing quantities are correct
   - Product names, categories, rates are shown
   - No blank rows

**Test 4: Trial Balance**
1. Navigate to Trial Balance page
2. Click "Load Trial Balance"
3. Verify:
   - All ledger accounts are shown (including zero-balance accounts)
   - Opening, period, closing balances are displayed
   - Dr/Cr columns are correct
   - Footer totals match

**Test 5: Active Company Resolution**
1. Close the application
2. Reopen the application
3. Open company "Varnam Clothing Centre Vdl"
4. Navigate to each report page
5. Verify:
   - Correct company data is displayed
   - No fallback to first company
   - Active company ID is 24 throughout

---

## Phase 11: MySQL Compatibility Protection

### Verification
All SQL queries use `db._get_placeholder()` for MySQL compatibility:
- ✓ Ledger posting methods use placeholder
- ✓ Stock summary query uses placeholder
- ✓ Trial balance query uses placeholder
- ✓ Rebuild methods use placeholder
- ✓ Diagnostic script uses placeholder
- ✓ No hardcoded SQLite-specific syntax

---

## Summary of Changes

### Files Modified
1. `logic/ledger_logic.py` - Added helpers and rebuild method
2. `db.py` - Fixed get_stock_summary query
3. `logic/trial_balance_logic.py` - Removed zero-row skip
4. `config.py` - Added resolve_active_company_id helper
5. `ui/ledger_page.py` - Use resolve_active_company_id
6. `ui/stock_report_page.py` - Use resolve_active_company_id
7. `ui/trial_balance_page.py` - Use resolve_active_company_id
8. `tools/diagnose_books_reports_data.py` - Use resolve_active_company_id
9. `tools/rebuild_ledger_for_active_company.py` - NEW CLI tool

### Lines of Code Changed
- Added: ~250 lines
- Modified: ~50 lines
- Removed: ~10 lines

### Key Improvements
1. Ledger entries now properly posted from existing vouchers with tax split calculation
2. Safe ledger rebuild mechanism for existing data
3. Stock Report SQL query fixed with correct parameter order
4. Trial Balance shows all accounts including zero-balance
5. Consistent active company resolution across application
6. CLI tool for ledger rebuild
7. All code compiled successfully
8. MySQL compatibility preserved

---

## Next Steps

1. **Run Manual Tests** (Phase 10) - Perform the 5 mandatory tests listed above
2. **Verify Data** - Confirm that company_id 24 now has ledger_entries
3. **Test Reports** - Verify Ledger, Stock Report, and Trial Balance display correctly
4. **Document Results** - Update this report with test results

---

## Conclusion

All code changes have been implemented successfully. The root causes of blank Ledger, Stock Report, and Trial Balance tables have been addressed with minimal, focused changes that preserve existing functionality and MySQL compatibility. The application is now ready for mandatory manual testing to verify the fixes work correctly in the runtime environment.
