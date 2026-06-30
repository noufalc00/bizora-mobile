# DB Schema + Index MySQL Compatibility Scanner Report

**Date:** 2026-04-30 12:41:38
**File Scanned:** H:\Shared drives\My Drive\App making\apps with windsurf\accounting_app\db.py
**Total Issues Found:** 47

**Critical Issues:** 24
**Warning Issues:** 23

## ISSUES FOUND

### CRITICAL Issues (24)

#### CRITICAL Issue 1

**Line:** 79
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
self.connection.execute("PRAGMA foreign_keys = ON")
```
**Context:**
```
            # Enable foreign keys (SQLite-specific)
            self.connection.execute("PRAGMA foreign_keys = ON")
            # Enable WAL mode for better concurrency (SQLite-specific)
            self.connection.execute("PRAGMA journal_mode = WAL")
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 2

**Line:** 81
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
self.connection.execute("PRAGMA journal_mode = WAL")
```
**Context:**
```
            # Enable WAL mode for better concurrency (SQLite-specific)
            self.connection.execute("PRAGMA journal_mode = WAL")
            self.connection.execute("PRAGMA synchronous = NORMAL")
            return self.connection
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 3

**Line:** 82
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
self.connection.execute("PRAGMA synchronous = NORMAL")
```
**Context:**
```
            self.connection.execute("PRAGMA journal_mode = WAL")
            self.connection.execute("PRAGMA synchronous = NORMAL")
            return self.connection
        except sqlite3.Error as e:
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 4

**Line:** 889
**Description:** sqlite_master usage without clear SQLite-only guard
**Code:**
```
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")
```
**Context:**
```
            # Check if products table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")
            if not cursor.fetchone():
                return  # Table doesn't exist, no migration needed
```
**Suggested Fix:** Wrap sqlite_master usage in "if self._is_sqlite():" block or use information_schema for MySQL

#### CRITICAL Issue 5

**Line:** 894
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(products)")
```
**Context:**
```
            # Check if products table has old global barcode uniqueness constraint
            cursor.execute("PRAGMA table_info(products)")
            columns = [row[1] for row in cursor.fetchall()]
            
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 6

**Line:** 898
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA index_list(products)")
```
**Context:**
```
            # Check for old unique indexes on barcode only
            cursor.execute("PRAGMA index_list(products)")
            indexes = cursor.fetchall()
            
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 7

**Line:** 904
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute(f"PRAGMA index_info({index[1]})")
```
**Context:**
```
                if index[2]:  # unique flag
                    cursor.execute(f"PRAGMA index_info({index[1]})")
                    index_columns = [row[2] for row in cursor.fetchall()]
                    if len(index_columns) == 1 and index_columns[0] == 'barcode':
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 8

**Line:** 911
**Description:** sqlite_master usage without clear SQLite-only guard
**Code:**
```
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='products'")
```
**Context:**
```
            # Also check if barcode column has UNIQUE constraint in table definition
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='products'")
            table_sql = cursor.fetchone()
            if table_sql and 'barcode TEXT UNIQUE' in table_sql[0]:
```
**Suggested Fix:** Wrap sqlite_master usage in "if self._is_sqlite():" block or use information_schema for MySQL

#### CRITICAL Issue 9

**Line:** 996
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(stock_movements)")
```
**Context:**
```
        try:
            cursor.execute("PRAGMA table_info(stock_movements)")
            columns = [row[1] for row in cursor.fetchall()]

```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 10

**Line:** 1058
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(companies)")
```
**Context:**
```
            # Check if logo_path column exists in companies table
            cursor.execute("PRAGMA table_info(companies)")
            columns = [row[1] for row in cursor.fetchall()]

```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 11

**Line:** 1070
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(products)")
```
**Context:**
```
            # Check if all required product fields exist
            cursor.execute("PRAGMA table_info(products)")
            product_columns = [row[1] for row in cursor.fetchall()]
            
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 12

**Line:** 1095
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(parties)")
```
**Context:**
```
            # Check if state column exists in parties table
            cursor.execute("PRAGMA table_info(parties)")
            party_columns = [row[1] for row in cursor.fetchall()]

```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 13

**Line:** 1107
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(accounts)")
```
**Context:**
```
            # Check if accounts table needs company_id column
            cursor.execute("PRAGMA table_info(accounts)")
            account_columns = [row[1] for row in cursor.fetchall()]
            
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 14

**Line:** 1117
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(transactions)")
```
**Context:**
```
            # Check if transactions table needs company_id column
            cursor.execute("PRAGMA table_info(transactions)")
            transaction_columns = [row[1] for row in cursor.fetchall()]
            
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 15

**Line:** 1125
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(categories)")
```
**Context:**
```
            # Check if categories table needs company_id column
            cursor.execute("PRAGMA table_info(categories)")
            category_columns = [row[1] for row in cursor.fetchall()]
            
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 16

**Line:** 1172
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(parties)")
```
**Context:**
```
        try:
            cursor.execute("PRAGMA table_info(parties)")
            cols = [row[1] for row in cursor.fetchall()]
            if 'ledger_account_id' not in cols:
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 17

**Line:** 1192
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(sales_items)")
```
**Context:**
```
        try:
            cursor.execute("PRAGMA table_info(sales_items)")
            columns = [row[1] for row in cursor.fetchall()]
            
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 18

**Line:** 1219
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(purchase_items)")
```
**Context:**
```
        try:
            cursor.execute("PRAGMA table_info(purchase_items)")
            columns = [row[1] for row in cursor.fetchall()]
            
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 19

**Line:** 1246
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(sales_return_items)")
```
**Context:**
```
        try:
            cursor.execute("PRAGMA table_info(sales_return_items)")
            columns = [row[1] for row in cursor.fetchall()]
            
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 20

**Line:** 1269
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(purchase_return_items)")
```
**Context:**
```
        try:
            cursor.execute("PRAGMA table_info(purchase_return_items)")
            columns = [row[1] for row in cursor.fetchall()]
            
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 21

**Line:** 1296
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(sales_return_items)")
```
**Context:**
```
            # Check and add unit column to sales_return_items
            cursor.execute("PRAGMA table_info(sales_return_items)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'unit' not in columns:
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 22

**Line:** 1303
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(purchase_return_items)")
```
**Context:**
```
            # Check and add unit column to purchase_return_items
            cursor.execute("PRAGMA table_info(purchase_return_items)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'unit' not in columns:
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 23

**Line:** 1316
**Description:** PRAGMA statement without clear SQLite-only guard
**Code:**
```
cursor.execute("PRAGMA table_info(sales_returns)")
```
**Context:**
```
        try:
            cursor.execute("PRAGMA table_info(sales_returns)")
            cols = cursor.fetchall()
            if not cols:
```
**Suggested Fix:** Wrap PRAGMA in "if self._is_sqlite():" block

#### CRITICAL Issue 24

**Line:** 1779
**Description:** INSERT OR REPLACE (SQLite-only) without backend guard
**Code:**
```
"""Set a setting value using backend-safe INSERT OR REPLACE."""
```
**Context:**
```
    def set_setting(self, key: str, value: str) -> bool:
        """Set a setting value using backend-safe INSERT OR REPLACE."""
        ph = self._get_placeholder()
        if self._is_sqlite():
```
**Suggested Fix:** Use backend-safe: if self._is_sqlite(): INSERT OR REPLACE ... else: INSERT ... ON DUPLICATE KEY UPDATE ...

### WARNING Issues (23)

#### WARNING Issue 1

**Line:** 113
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
return "AUTOINCREMENT" if self.db_type == "sqlite" else "AUTO_INCREMENT"
```
**Context:**
```
        """Get the AUTO_INCREMENT syntax for the current backend."""
        return "AUTOINCREMENT" if self.db_type == "sqlite" else "AUTO_INCREMENT"
    
    def _get_primary_key_autoincrement(self) -> str:
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 2

**Line:** 115
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
def _get_primary_key_autoincrement(self) -> str:
```
**Context:**
```
    
    def _get_primary_key_autoincrement(self) -> str:
        """Get the PRIMARY KEY AUTO_INCREMENT syntax for the current backend."""
        if self.db_type == "sqlite":
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 3

**Line:** 118
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
return "INTEGER PRIMARY KEY AUTOINCREMENT"
```
**Context:**
```
        if self.db_type == "sqlite":
            return "INTEGER PRIMARY KEY AUTOINCREMENT"
        else:
            return "INT AUTO_INCREMENT PRIMARY KEY"
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 4

**Line:** 322
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create accounts table."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        varchar_255 = self._get_varchar_type(255)
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 5

**Line:** 343
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create transactions table."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        varchar_50 = self._get_varchar_type(50)
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 6

**Line:** 365
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create categories table."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        varchar_255 = self._get_varchar_type(255)
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 7

**Line:** 385
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create products table."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 8

**Line:** 440
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create stock_movements table for stock tracking foundation."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 9

**Line:** 463
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create bank_accounts table for bank account management."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 10

**Line:** 491
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create sales table for sales header information."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 11

**Line:** 547
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create sales_items table for sales line items."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 12

**Line:** 576
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create purchases table for purchase header information."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 13

**Line:** 628
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create ledger accounts table for double-entry accounting."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 14

**Line:** 661
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create ledger_entries table for double-entry accounting transactions."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 15

**Line:** 703
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create purchase_items table for purchase line items."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 16

**Line:** 732
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create sales_returns table for sales return header information."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 17

**Line:** 768
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create sales_return_items table for sales return line items."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 18

**Line:** 801
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create purchase_returns table for purchase return header information."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 19

**Line:** 839
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
        """Create purchase_return_items table for purchase return line items."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 20

**Line:** 913
**Description:** TEXT field "barcode" in UNIQUE constraint (should be VARCHAR for MySQL)
**Code:**
```
if table_sql and 'barcode TEXT UNIQUE' in table_sql[0]:
```
**Context:**
```
            table_sql = cursor.fetchone()
            if table_sql and 'barcode TEXT UNIQUE' in table_sql[0]:
                has_old_barcode_constraint = True
            
```
**Suggested Fix:** Use self._get_varchar_type(100) instead of TEXT

#### WARNING Issue 21

**Line:** 924
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
                # Create new products table with correct schema
                pk_autoinc = self._get_primary_key_autoincrement()
                varchar_255 = self._get_varchar_type(255)
                varchar_100 = self._get_varchar_type(100)
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 22

**Line:** 1329
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc = self._get_primary_key_autoincrement()
```
**Context:**
```
            cursor.execute("ALTER TABLE sales_returns RENAME TO sales_returns_old")
            pk_autoinc = self._get_primary_key_autoincrement()
            timestamp_default = self._get_timestamp_default()
            cursor.execute(f"""
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

#### WARNING Issue 23

**Line:** 1370
**Description:** AUTOINCREMENT usage (SQLite-specific)
**Code:**
```
pk_autoinc2 = self._get_primary_key_autoincrement()
```
**Context:**
```
            cursor.execute("ALTER TABLE sales_return_items RENAME TO sales_return_items_fk_old")
            pk_autoinc2 = self._get_primary_key_autoincrement()
            ts2 = self._get_timestamp_default()
            cursor.execute(f"""
```
**Suggested Fix:** Use self._get_primary_key_autoincrement() helper

