"""
Database module for the Accounting Desktop Application.
Handles SQLite database initialization and basic operations.
"""

import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any

from config import DATABASE_NAME, DATABASE_BACKUP_DIR


class Database:
    """SQLite database manager for the accounting application."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize database connection."""
        if db_path is None:
            self.db_path = DATABASE_NAME
        else:
            self.db_path = db_path
        
        self.connection = None
    
    def connect(self) -> sqlite3.Connection:
        """Establish database connection."""
        try:
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row  # Enable dict-like access
            # Enable foreign keys
            self.connection.execute("PRAGMA foreign_keys = ON")
            return self.connection
        except sqlite3.Error as e:
            raise Exception(f"Database connection error: {e}")
    
    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def initialize_database(self) -> bool:
        """Initialize the database with all required tables."""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            # Create all tables
            self._create_accounts_table(cursor)
            self._create_transactions_table(cursor)
            self._create_categories_table(cursor)
            self._create_companies_table(cursor)
            self._create_products_table(cursor)
            self._create_parties_table(cursor)
            self._create_settings_table(cursor)
            
            # Add missing columns for existing databases
            self._migrate_database(cursor)
            
            conn.commit()
            print("Database tables created successfully")
            return True
            
        except sqlite3.Error as e:
            print(f"Database initialization error: {e}")
            return False
        finally:
            self.disconnect()
    
    def _create_accounts_table(self, cursor: sqlite3.Cursor):
        """Create accounts table."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('checking', 'savings', 'credit', 'cash', 'investment')),
                balance REAL DEFAULT 0.0,
                currency TEXT DEFAULT 'USD',
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(company_id, name)
            )
        """)
    
    def _create_transactions_table(self, cursor: sqlite3.Cursor):
        """Create transactions table."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                category_id INTEGER,
                type TEXT NOT NULL CHECK (type IN ('income', 'expense', 'transfer')),
                amount REAL NOT NULL,
                description TEXT,
                date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE SET NULL
            )
        """)
    
    def _create_categories_table(self, cursor: sqlite3.Cursor):
        """Create categories table."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('income', 'expense')),
                color TEXT DEFAULT '#2196F3',
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(company_id, name)
            )
        """)
    
    def _create_companies_table(self, cursor: sqlite3.Cursor):
        """Create companies table."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_name TEXT NOT NULL UNIQUE,
                phone_number TEXT,
                gstin TEXT,
                email TEXT,
                business_type TEXT,
                business_category TEXT,
                address TEXT,
                state TEXT,
                pincode TEXT,
                logo_path TEXT,
                signature_path TEXT,
                is_active BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    def _create_products_table(self, cursor: sqlite3.Cursor):
        """Create products table."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                barcode TEXT,
                hsn TEXT,
                unit TEXT DEFAULT 'pcs',
                category TEXT,
                color TEXT,
                size TEXT,
                purchase_rate REAL DEFAULT 0.0,
                sale_price REAL DEFAULT 0.0,
                wholesale_rate REAL DEFAULT 0.0,
                mrp REAL DEFAULT 0.0,
                cgst REAL DEFAULT 0.0,
                sgst REAL DEFAULT 0.0,
                igst REAL DEFAULT 0.0,
                cess REAL DEFAULT 0.0,
                reorder_level REAL DEFAULT 0.0,
                description TEXT,
                quantity REAL DEFAULT 0.0,
                auto_barcode INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE
            )
        """)
    
    def _create_settings_table(self, cursor: sqlite3.Cursor):
        """Create settings table."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    def _create_parties_table(self, cursor: sqlite3.Cursor):
        """Create parties table for Debitor/Creditor module."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                party_type TEXT NOT NULL CHECK (party_type IN ('Debitor', 'Creditor', 'Both')),
                opening_balance REAL DEFAULT 0.0,
                mobile_number TEXT,
                email TEXT,
                address TEXT,
                gstin TEXT,
                credit_limit REAL DEFAULT 0.0,
                contact_person TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                UNIQUE(company_id, name)
            )
        """)
    
    def _migrate_products_table(self, cursor: sqlite3.Cursor):
        """Migrate products table to remove old global barcode uniqueness constraints."""
        try:
            # Check if products table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products'")
            if not cursor.fetchone():
                return  # Table doesn't exist, no migration needed
            
            # Check if products table has old global barcode uniqueness constraint
            cursor.execute("PRAGMA table_info(products)")
            columns = [row[1] for row in cursor.fetchall()]
            
            # Check for old unique indexes on barcode only
            cursor.execute("PRAGMA index_list(products)")
            indexes = cursor.fetchall()
            
            has_old_barcode_constraint = False
            for index in indexes:
                if index[2]:  # unique flag
                    cursor.execute(f"PRAGMA index_info({index[1]})")
                    index_columns = [row[2] for row in cursor.fetchall()]
                    if len(index_columns) == 1 and index_columns[0] == 'barcode':
                        has_old_barcode_constraint = True
                        break
            
            # Also check if barcode column has UNIQUE constraint in table definition
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='products'")
            table_sql = cursor.fetchone()
            if table_sql and 'barcode TEXT UNIQUE' in table_sql[0]:
                has_old_barcode_constraint = True
            
            if has_old_barcode_constraint:
                print("Detected old global barcode uniqueness constraint, rebuilding products table...")
                
                # Rename current products table
                cursor.execute("ALTER TABLE products RENAME TO products_old")
                print("Renamed products table to products_old")
                
                # Create new products table with correct schema
                cursor.execute("""
                    CREATE TABLE products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        barcode TEXT,
                        hsn TEXT,
                        unit TEXT DEFAULT 'pcs',
                        category TEXT,
                        color TEXT,
                        size TEXT,
                        purchase_rate REAL DEFAULT 0.0,
                        sale_price REAL DEFAULT 0.0,
                        wholesale_rate REAL DEFAULT 0.0,
                        mrp REAL DEFAULT 0.0,
                        cgst REAL DEFAULT 0.0,
                        sgst REAL DEFAULT 0.0,
                        igst REAL DEFAULT 0.0,
                        cess REAL DEFAULT 0.0,
                        reorder_level REAL DEFAULT 0.0,
                        description TEXT,
                        quantity REAL DEFAULT 0.0,
                        auto_barcode INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE
                    )
                """)
                print("Created new products table with correct schema")
                
                # Copy data from old table to new table
                cursor.execute("""
                    INSERT INTO products (
                        id, company_id, name, barcode, hsn, unit, category, color, size,
                        purchase_rate, sale_price, wholesale_rate, mrp, cgst, sgst, igst,
                        cess, reorder_level, description, quantity, auto_barcode, created_at, updated_at
                    )
                    SELECT 
                        id, company_id, name, barcode, hsn, unit, category, color, size,
                        purchase_rate, sale_price, wholesale_rate, mrp, cgst, sgst, igst,
                        cess, reorder_level, description, quantity, auto_barcode, created_at, updated_at
                    FROM products_old
                """)
                print("Copied data from products_old to products")
                
                # Drop the old table
                cursor.execute("DROP TABLE products_old")
                print("Dropped products_old table")
                
                # Create company-specific unique index for barcode
                cursor.execute("CREATE UNIQUE INDEX idx_products_company_barcode ON products (company_id, barcode)")
                print("Created company-specific unique index on products (company_id, barcode)")
                
                print("Products table migration completed successfully")
            
            # Ensure company-specific unique index exists
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_products_company_barcode ON products (company_id, barcode)")
            
        except sqlite3.Error as e:
            print(f"Products table migration error: {e}")
            raise

    def _migrate_database(self, cursor: sqlite3.Cursor):
        """Migrate existing database to add missing columns."""
        try:
            # Check if products table needs migration for barcode uniqueness
            self._migrate_products_table(cursor)
            
            # Check if logo_path column exists in companies table
            cursor.execute("PRAGMA table_info(companies)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'logo_path' not in columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN logo_path TEXT")
                print("Added logo_path column to companies table")
            
            if 'signature_path' not in columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN signature_path TEXT")
                print("Added signature_path column to companies table")
                
            # Check if all required product fields exist
            cursor.execute("PRAGMA table_info(products)")
            product_columns = [row[1] for row in cursor.fetchall()]
            
            required_product_fields = [
                ('hsn', 'TEXT'),
                ('color', 'TEXT'),
                ('size', 'TEXT'),
                ('purchase_rate', 'REAL DEFAULT 0.0'),
                ('wholesale_rate', 'REAL DEFAULT 0.0'),
                ('mrp', 'REAL DEFAULT 0.0'),
                ('cgst', 'REAL DEFAULT 0.0'),
                ('sgst', 'REAL DEFAULT 0.0'),
                ('igst', 'REAL DEFAULT 0.0'),
                ('cess', 'REAL DEFAULT 0.0'),
                ('reorder_level', 'REAL DEFAULT 0.0'),
                ('quantity', 'REAL DEFAULT 0.0'),
                ('auto_barcode', 'INTEGER DEFAULT 1')
            ]
            
            for field_name, field_type in required_product_fields:
                if field_name not in product_columns:
                    cursor.execute(f"ALTER TABLE products ADD COLUMN {field_name} {field_type}")
                    print(f"Added {field_name} column to products table")
                
                # Add company-specific unique constraint for barcode
                cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_products_company_barcode ON products (company_id, barcode)")
                print("Added company-specific unique index on products (company_id, barcode)")
                
            # Check if accounts table needs company_id column
            cursor.execute("PRAGMA table_info(accounts)")
            account_columns = [row[1] for row in cursor.fetchall()]
            
            if 'company_id' not in account_columns:
                cursor.execute("ALTER TABLE accounts ADD COLUMN company_id INTEGER NOT NULL DEFAULT 1")
                # Add unique constraint for company_id, name
                cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_company_name ON accounts (company_id, name)")
                print("Added company_id column to accounts table")
                
            # Check if transactions table needs company_id column
            cursor.execute("PRAGMA table_info(transactions)")
            transaction_columns = [row[1] for row in cursor.fetchall()]
            
            if 'company_id' not in transaction_columns:
                cursor.execute("ALTER TABLE transactions ADD COLUMN company_id INTEGER NOT NULL DEFAULT 1")
                print("Added company_id column to transactions table")
                
            # Check if categories table needs company_id column
            cursor.execute("PRAGMA table_info(categories)")
            category_columns = [row[1] for row in cursor.fetchall()]
            
            if 'company_id' not in category_columns:
                cursor.execute("ALTER TABLE categories ADD COLUMN company_id INTEGER NOT NULL DEFAULT 1")
                # Add unique constraint for company_id, name
                cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_categories_company_name ON categories (company_id, name)")
                print("Added company_id column to categories table")
                
        except sqlite3.Error as e:
            print(f"Database migration error: {e}")
    
    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results."""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = [dict(row) for row in cursor.fetchall()]
            return results
        except sqlite3.Error as e:
            print(f"Query execution error: {e}")
            return []
        finally:
            self.disconnect()
    
    def execute_update(self, query: str, params: tuple = ()) -> bool:
        """Execute an INSERT, UPDATE, or DELETE query."""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Update execution error: {e}")
            return False
        finally:
            self.disconnect()
    
    def backup_database(self, backup_path: Optional[str] = None) -> bool:
        """Create a backup of the database."""
        if backup_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = DATABASE_BACKUP_DIR
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, f"backup_{timestamp}.db")
        
        try:
            source = sqlite3.connect(self.db_path)
            backup = sqlite3.connect(backup_path)
            source.backup(backup)
            source.close()
            backup.close()
            print(f"Database backed up to: {backup_path}")
            return True
        except sqlite3.Error as e:
            print(f"Backup error: {e}")
            return False
    
    def company_name_exists(self, business_name: str) -> bool:
        """Check if a company name already exists (case-insensitive, ignoring leading/trailing spaces)."""
        normalized_name = business_name.strip().lower()
        query = "SELECT COUNT(*) as count FROM companies WHERE LOWER(TRIM(business_name)) = ?"
        result = self.execute_query(query, (normalized_name,))
        return result[0]['count'] > 0 if result else False
    
    def create_company(self, company_data: Dict[str, Any]) -> bool:
        """Create a new company record and set it as active."""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            # Deactivate all existing companies first
            cursor.execute("UPDATE companies SET is_active = 0")
            
            # Insert new company as active
            query = """
                INSERT INTO companies (
                    business_name, phone_number, gstin, email, business_type, 
                    business_category, address, state, pincode, logo_path, signature_path, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """
            params = (
                company_data.get('business_name'),
                company_data.get('phone_number'),
                company_data.get('gstin'),
                company_data.get('email'),
                company_data.get('business_type'),
                company_data.get('business_category'),
                company_data.get('address'),
                company_data.get('state'),
                company_data.get('pincode'),
                company_data.get('logo_path'),
                company_data.get('signature_path')
            )
            cursor.execute(query, params)
            
            conn.commit()
            self.disconnect()
            return True
        except Exception as e:
            print(f"Error creating company: {e}")
            return False
    
    def get_all_companies(self) -> List[Dict[str, Any]]:
        """Get all companies."""
        query = "SELECT * FROM companies ORDER BY business_name"
        return self.execute_query(query)
    
    def get_active_company(self) -> Optional[Dict[str, Any]]:
        """Get the currently active company."""
        query = "SELECT * FROM companies WHERE is_active = 1 LIMIT 1"
        result = self.execute_query(query)
        return result[0] if result else None
    
    def set_active_company(self, company_id: int) -> bool:
        """Set a company as active (deactivate all others first)."""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            # Deactivate all companies
            cursor.execute("UPDATE companies SET is_active = 0")
            
            # Activate the specified company
            cursor.execute("UPDATE companies SET is_active = 1 WHERE id = ?", (company_id,))
            
            conn.commit()
            self.disconnect()
            return True
        except sqlite3.Error as e:
            print(f"Error setting active company: {e}")
            return False
    
    def update_company(self, company_id: int, company_data: Dict[str, Any]) -> bool:
        """Update an existing company record."""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            # Update company
            query = """
                UPDATE companies SET 
                    business_name = ?, phone_number = ?, gstin = ?, email = ?, 
                    business_type = ?, business_category = ?, address = ?, 
                    state = ?, pincode = ?, logo_path = ?, signature_path = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            params = (
                company_data.get('business_name'),
                company_data.get('phone_number'),
                company_data.get('gstin'),
                company_data.get('email'),
                company_data.get('business_type'),
                company_data.get('business_category'),
                company_data.get('address'),
                company_data.get('state'),
                company_data.get('pincode'),
                company_data.get('logo_path'),
                company_data.get('signature_path'),
                company_id
            )
            cursor.execute(query, params)
            
            conn.commit()
            self.disconnect()
            return True
        except Exception as e:
            print(f"Error updating company: {e}")
            return False
    
    def company_name_exists_excluding_id(self, business_name: str, exclude_id: int) -> bool:
        """Check if a company name already exists, excluding a specific company ID."""
        normalized_name = business_name.strip().lower()
        query = "SELECT COUNT(*) as count FROM companies WHERE LOWER(TRIM(business_name)) = ? AND id != ?"
        result = self.execute_query(query, (normalized_name, exclude_id))
        return result[0]['count'] > 0 if result else False
    
    def delete_company(self, company_id: int) -> bool:
        """Delete a company permanently from database."""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            # Delete related data in correct order to avoid foreign key constraints
            # Delete transactions first
            cursor.execute("DELETE FROM transactions WHERE company_id = ?", (company_id,))
            # Delete categories
            cursor.execute("DELETE FROM categories WHERE company_id = ?", (company_id,))
            # Delete accounts
            cursor.execute("DELETE FROM accounts WHERE company_id = ?", (company_id,))
            # Delete products
            cursor.execute("DELETE FROM products WHERE company_id = ?", (company_id,))
            # Delete parties
            cursor.execute("DELETE FROM parties WHERE company_id = ?", (company_id,))
            # Finally delete the company
            cursor.execute("DELETE FROM companies WHERE id = ?", (company_id,))
            
            conn.commit()
            self.disconnect()
            return True
        except sqlite3.Error as e:
            print(f"Error deleting company: {e}")
            return False
    
    def get_accounts(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all accounts for a specific company."""
        query = """
            SELECT id, name, type, balance, currency, description, created_at, updated_at
            FROM accounts 
            WHERE company_id = ?
            ORDER BY name
        """
        return self.execute_query(query, (company_id,))
    
    def create_account(self, company_id: int, name: str, account_type: str, 
                    balance: float = 0.0, currency: str = 'USD', 
                    description: str = None) -> bool:
        """Create a new account for a specific company."""
        query = """
            INSERT INTO accounts (company_id, name, type, balance, currency, description)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        return self.execute_update(query, (company_id, name, account_type, balance, currency, description))
    
    def update_account(self, account_id: int, name: str, account_type: str,
                    balance: float, currency: str, description: str) -> bool:
        """Update an existing account."""
        query = """
            UPDATE accounts 
            SET name = ?, type = ?, balance = ?, currency = ?, description = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        return self.execute_update(query, (name, account_type, balance, currency, description, account_id))
    
    def delete_account(self, account_id: int) -> bool:
        """Delete an account."""
        query = "DELETE FROM accounts WHERE id = ?"
        return self.execute_update(query, (account_id,))
    
    def get_setting(self, key: str) -> Optional[str]:
        """Get a setting value."""
        query = "SELECT value FROM settings WHERE key = ?"
        result = self.execute_query(query, (key,))
        return result[0]['value'] if result else None
    
    def get_transactions(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all transactions for a specific company."""
        query = """
            SELECT t.id, t.account_id, t.category_id, t.type, t.amount, 
                   t.description, t.date, t.created_at, t.updated_at,
                   a.name as account_name, c.name as category_name
            FROM transactions t
            LEFT JOIN accounts a ON t.account_id = a.id
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.company_id = ?
            ORDER BY t.date DESC, t.created_at DESC
        """
        return self.execute_query(query, (company_id,))
    
    def create_transaction(self, company_id: int, account_id: int, amount: float,
                         transaction_type: str, description: str = None, 
                         date: str = None, category_id: int = None) -> bool:
        """Create a new transaction for a specific company."""
        query = """
            INSERT INTO transactions (company_id, account_id, amount, type, description, date, category_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        return self.execute_update(query, (company_id, account_id, amount, transaction_type, description, date, category_id))
    
    def get_categories(self, company_id: int, category_type: str = None) -> List[Dict[str, Any]]:
        """Get all categories for a specific company."""
        if category_type:
            query = """
                SELECT id, name, type, color, description, created_at
                FROM categories 
                WHERE company_id = ? AND type = ?
                ORDER BY name
            """
            return self.execute_query(query, (company_id, category_type))
        else:
            query = """
                SELECT id, name, type, color, description, created_at
                FROM categories 
                WHERE company_id = ?
                ORDER BY name
            """
            return self.execute_query(query, (company_id,))
    
    def create_category(self, company_id: int, name: str, category_type: str,
                       color: str = '#2196F3', description: str = None) -> bool:
        """Create a new category for a specific company."""
        query = """
            INSERT INTO categories (company_id, name, type, color, description)
            VALUES (?, ?, ?, ?, ?)
        """
        return self.execute_update(query, (company_id, name, category_type, color, description))
    
    def set_setting(self, key: str, value: str) -> bool:
        """Set a setting value."""
        query = """
            INSERT OR REPLACE INTO settings (key, value, updated_at) 
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """
        return self.execute_update(query, (key, value))
