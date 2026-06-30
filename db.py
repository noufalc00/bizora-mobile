"""
Database module for the Accounting Desktop Application.
Handles SQLite and MySQL database initialization and basic operations.
"""

import os
import re
import sqlite3
import hashlib
from contextlib import closing
from datetime import datetime
from typing import Optional, List, Dict, Any

from config import (
    DATABASE_BACKUP_DIR,
    DATABASE_NAME,
    DATABASE_TYPE,
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_db_path():
    """Return the configured SQLite database name or path."""
    return DATABASE_NAME


DB_PATH = get_db_path()
_INITIALIZED_SQLITE_PATHS = set()


def hash_password(password: str) -> str:
    """Return a SHA-256 hex digest for the supplied password string."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_default_database_path() -> str:
    """Return the configured default SQLite database path."""
    return DB_PATH


def ensure_company_users_table(db_path: str, company_id: Optional[int] = None) -> None:
    """Ensure a company SQLite database has scoped users and an Admin user."""
    if not db_path:
        raise ValueError("A company database path is required.")

    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    with closing(sqlite3.connect(db_path, timeout=30.0)) as connection:
        connection.execute("PRAGMA busy_timeout = 5000;")
        connection.execute("PRAGMA journal_mode = DELETE;")
        connection.execute("PRAGMA synchronous = NORMAL;")
        _ensure_scoped_users_table(connection, company_id)
        existing_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        required_columns = {
            "company_id": "INTEGER",
            "password": "TEXT",
            "password_hash": "TEXT",
            "role": "TEXT",
            "permissions": "TEXT",
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE users ADD COLUMN {column_name} {column_type}"
                )

        cursor = connection.cursor()
        if company_id is None:
            cursor.execute("SELECT COUNT(*) FROM users")
            row = cursor.fetchone()
            user_count = int(row[0] or 0) if row else 0
        else:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM users
                WHERE company_id = ?
                """,
                (company_id,),
            )
            row = cursor.fetchone()
            user_count = int(row[0] or 0) if row else 0

        if user_count == 0:
            cursor.execute(
                """
                INSERT INTO users (
                    company_id, username, password, password_hash, role, permissions
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id,
                    "admin",
                    "admin123",
                    hash_password("admin123"),
                    "Admin",
                    "ALL",
                ),
            )
        else:
            if company_id is None:
                cursor.execute(
                    """
                    UPDATE users
                    SET role = ?,
                        permissions = COALESCE(permissions, ?)
                    WHERE username = ?
                      AND LOWER(TRIM(COALESCE(role, ''))) = ?
                    """,
                    ("Admin", "ALL", "admin", "admin"),
                )
            else:
                cursor.execute(
                    """
                    UPDATE users
                    SET role = ?,
                        permissions = COALESCE(permissions, ?)
                    WHERE company_id = ?
                      AND username = ?
                      AND LOWER(TRIM(COALESCE(role, ''))) = ?
                    """,
                    ("Admin", "ALL", company_id, "admin", "admin"),
                )
        connection.commit()


def _ensure_scoped_users_table(
    connection: sqlite3.Connection,
    company_id: Optional[int] = None,
) -> None:
    """Create or migrate users to a company-scoped username model."""
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            company_id INTEGER,
            username TEXT,
            password TEXT,
            password_hash TEXT,
            role TEXT,
            permissions TEXT,
            UNIQUE(company_id, username)
        )
        """
    )
    cursor.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table'
          AND name = 'users'
        """
    )
    row = cursor.fetchone()
    table_sql = (row[0] or "") if row else ""
    cursor.execute("PRAGMA table_info(users)")
    columns = {column[1] for column in cursor.fetchall()}
    needs_rebuild = (
        "company_id" not in columns
        or "USERNAME TEXT UNIQUE" in table_sql.upper()
        or "UNIQUE(COMPANY_ID, USERNAME)" not in table_sql.upper()
    )
    if not needs_rebuild:
        return

    cursor.execute("ALTER TABLE users RENAME TO users_legacy_migration")
    cursor.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            company_id INTEGER,
            username TEXT,
            password TEXT,
            password_hash TEXT,
            role TEXT,
            permissions TEXT,
            UNIQUE(company_id, username)
        )
        """
    )
    cursor.execute("PRAGMA table_info(users_legacy_migration)")
    legacy_columns = {column[1] for column in cursor.fetchall()}
    company_expr = "company_id" if "company_id" in legacy_columns else "NULL"
    password_expr = "password" if "password" in legacy_columns else "NULL"
    password_hash_expr = "password_hash" if "password_hash" in legacy_columns else "NULL"
    role_expr = "role" if "role" in legacy_columns else "'User'"
    permissions_expr = "permissions" if "permissions" in legacy_columns else "''"
    cursor.execute(
        f"""
        INSERT OR IGNORE INTO users (
            id, company_id, username, password, password_hash, role, permissions
        )
        SELECT
            id,
            {company_expr},
            username,
            {password_expr},
            {password_hash_expr},
            {role_expr},
            {permissions_expr}
        FROM users_legacy_migration
        """,
    )
    cursor.execute("DROP TABLE users_legacy_migration")

# Try to import MySQL connector, but don't fail if not present
MYSQL_AVAILABLE = False
try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False


class Database:
    """Database manager for the accounting application supporting SQLite and MySQL."""
    
    def __init__(self, db_type: Optional[str] = None, db_path: Optional[str] = None):
        """Initialize database connection with backend type selection.
        
        Args:
            db_type: Database type ('sqlite' or 'mysql'). Defaults to config DATABASE_TYPE.
            db_path: Optional SQLite database name or path.
        """
        if db_type is None:
            self.db_type = DATABASE_TYPE
        else:
            self.db_type = db_type
        
        if self.db_type == "mysql":
            if not MYSQL_AVAILABLE:
                raise ImportError("MySQL connector is not installed. Please install mysql-connector-python: pip install mysql-connector-python")
            self.db_path = None
            self.mysql_config = {
                'host': MYSQL_HOST,
                'port': MYSQL_PORT,
                'user': MYSQL_USER,
                'password': MYSQL_PASSWORD,
                'database': MYSQL_DATABASE
            }
        else:
            self.db_path = db_path if db_path is not None else DB_PATH
            self.mysql_config = None
        
        self.connection = None
        self.last_error_message = None
        self._schema_initialized = False
    
    def connect(self):
        """Return an open connection, creating one when needed."""
        try:
            if self.db_type == "mysql":
                if self.connection is None:
                    return self._connect_mysql()
                return self.connection
            else:
                if self.connection is None:
                    return self._connect_sqlite()
                return self.connection
        except sqlite3.Error as e:
            print(f"Database Error: {e}")
            raise Exception(f"Database connection error: {e}") from e
        except Exception as e:
            raise Exception(f"Database connection error: {e}")
    
    def _resolve_sqlite_database_path(self) -> str:
        """Return the configured SQLite database path."""
        return self.db_path

    def _ensure_directory_writable(self, directory_path: str) -> None:
        """Raise OSError if SQLite's target directory cannot be written."""
        probe_path = os.path.join(directory_path, ".db_write_test")
        with open(probe_path, "w", encoding="utf-8") as probe_file:
            probe_file.write("ok")
        os.remove(probe_path)

    def _connect_sqlite(self) -> sqlite3.Connection:
        """Establish a SQLite database connection."""
        try:
            self.db_path = self._resolve_sqlite_database_path()
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
                self._ensure_directory_writable(db_dir)
            # Add timeout of 30 seconds to handle concurrent access
            self.connection = sqlite3.connect(self.db_path, timeout=30.0)
            self.connection.execute("PRAGMA journal_mode = DELETE;")
            self.connection.row_factory = sqlite3.Row  # Enable dict-like access
            with closing(self.connection.cursor()) as cursor:
                # Enable foreign keys and Windows-friendly lock handling (SQLite-specific)
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.execute("PRAGMA busy_timeout = 5000;")
                cursor.execute("PRAGMA synchronous = NORMAL;")
                self._initialize_sqlite_schema_on_connect(cursor)
            self.connection.commit()
            return self.connection
        except sqlite3.Error as e:
            print(f"Database Error: {e}")
            raise Exception(f"SQLite connection error: {e}") from e
        except OSError as e:
            print(f"Database path error: {e}")
            raise Exception(f"SQLite path error: {e}") from e
    
    def _connect_mysql(self):
        """Establish MySQL database connection."""
        try:
            self.connection = mysql.connector.connect(**self.mysql_config)
            # Enable foreign keys
            with closing(self.connection.cursor()) as cursor:
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
            return self.connection
        except MySQLError as e:
            raise Exception(f"MySQL connection error: {e}")

    def _initialize_sqlite_schema_on_connect(self, cursor) -> None:
        """Create required SQLite schema before any startup UI can query it."""
        if self.db_path in _INITIALIZED_SQLITE_PATHS:
            self._schema_initialized = True
            return

        self._create_database_schema(cursor)
        _INITIALIZED_SQLITE_PATHS.add(self.db_path)
        self._schema_initialized = True
    
    def disconnect(self):
        """Close the current database connection promptly."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def force_disconnect(self):
        """Actually close the database connection (use on app shutdown only)."""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    def _get_auto_increment(self) -> str:
        """Get the AUTO_INCREMENT syntax for the current backend."""
        return "AUTOINCREMENT" if self.db_type == "sqlite" else "AUTO_INCREMENT"
    
    def _get_primary_key_autoincrement(self) -> str:
        """Get the PRIMARY KEY AUTO_INCREMENT syntax for the current backend."""
        if self.db_type == "sqlite":
            return "INTEGER PRIMARY KEY AUTOINCREMENT"
        else:
            return "INT AUTO_INCREMENT PRIMARY KEY"
    
    def _get_primary_key_autoincrement_2(self) -> str:
        """Get the AUTO_INCREMENT syntax for second column in composite primary key.
        
        SQLite only supports AUTOINCREMENT on the first column of a composite key,
        so this returns just INTEGER for SQLite.
        MySQL supports AUTO_INCREMENT on any column.
        """
        if self.db_type == "sqlite":
            return "INTEGER"
        else:
            return "INT AUTO_INCREMENT"
    
    def _get_boolean_type(self) -> str:
        """Get the BOOLEAN type for the current backend."""
        return "BOOLEAN" if self.db_type == "sqlite" else "TINYINT(1)"
    
    def _get_timestamp_default(self) -> str:
        """Get the default timestamp syntax for the current backend."""
        return "CURRENT_TIMESTAMP" if self.db_type == "sqlite" else "CURRENT_TIMESTAMP"

    def _get_last_insert_id(self, cursor) -> Optional[int]:
        """Get the last inserted ID in a cross-database compatible way."""
        if self.db_type == "sqlite":
            return cursor.lastrowid
        else:
            # MySQL: use SELECT LAST_INSERT_ID()
            cursor.execute("SELECT LAST_INSERT_ID()")
            result = cursor.fetchone()
            return result[0] if result else None
    
    def _check_table_exists(self, cursor, table_name: str) -> bool:
        """Check if a table exists in the current backend."""
        if self.db_type == "sqlite":
            ph = self._get_placeholder()
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name={ph}", (table_name,))
            return cursor.fetchone() is not None
        else:
            cursor.execute("SHOW TABLES LIKE %s", (table_name,))
            return cursor.fetchone() is not None
    
    def _get_placeholder(self) -> str:
        """Get the parameter placeholder for the current backend."""
        return "?" if self.db_type == "sqlite" else "%s"
    
    def _get_cast_integer(self) -> str:
        """Get the CAST syntax for integer conversion."""
        return "AS INTEGER" if self.db_type == "sqlite" else "AS SIGNED"
    
    def _is_sqlite(self) -> bool:
        """Check if current backend is SQLite."""
        return self.db_type == "sqlite"
    
    def _is_mysql(self) -> bool:
        """Check if current backend is MySQL."""
        return self.db_type == "mysql"
    
    def get_year_expression(self, column_name: str) -> str:
        """Get DB-specific year extraction expression.
        
        Args:
            column_name: The date column name
            
        Returns:
            SQLite: strftime('%Y', column_name)
            MySQL: YEAR(column_name)
        """
        if self._is_sqlite():
            return f"strftime('%Y', {column_name})"
        elif self._is_mysql():
            return f"YEAR({column_name})"
        else:
            # Fallback
            return f"strftime('%Y', {column_name})"
    
    def get_month_expression(self, column_name: str) -> str:
        """Get DB-specific month extraction expression.
        
        Args:
            column_name: The date column name
            
        Returns:
            SQLite: strftime('%m', column_name)
            MySQL: MONTH(column_name)
        """
        if self._is_sqlite():
            return f"strftime('%m', {column_name})"
        elif self._is_mysql():
            return f"MONTH({column_name})"
        else:
            # Fallback
            return f"strftime('%m', {column_name})"
    
    def _safe_identifier(self, identifier: str) -> str:
        """
        Validate and return a safe SQL identifier.
        Only allows letters, numbers, and underscore.
        Cannot start with a number.
        Raises ValueError if invalid.
        """
        if not identifier:
            raise ValueError("Identifier cannot be empty")
        
        # Check if identifier is valid
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
            raise ValueError(f"Invalid SQL identifier: {identifier}")
        
        return identifier

    def _quote_sqlite_identifier(self, identifier: str) -> str:
        """Return a double-quoted SQLite identifier with embedded quotes escaped."""
        if identifier is None or identifier == "":
            raise ValueError("SQLite identifier cannot be empty")
        return f'"{identifier.replace(chr(34), chr(34) + chr(34))}"'

    def _cleanup_legacy_sales_type_sqlite_objects(self, cursor) -> None:
        """Drop obsolete SQLite trigger/view objects that reference old tables."""
        if not self._is_sqlite():
            return

        try:
            obsolete_names = ("sales_type_old", "quotation_master_fk_old")
            obsolete_conditions = " OR ".join(
                "LOWER(COALESCE(sql, '')) LIKE ?"
                for _obsolete_name in obsolete_names
            )
            cursor.execute(
                f"""
                SELECT type, name
                FROM sqlite_master
                WHERE type IN ('trigger', 'view')
                  AND (
                      (type = 'trigger' AND name = ?)
                      OR {obsolete_conditions}
                  )
                """,
                (
                    "delete_company_dependencies",
                    *[f"%{obsolete_name}%" for obsolete_name in obsolete_names],
                )
            )
            legacy_objects = cursor.fetchall()

            for row in legacy_objects:
                object_type = row["type"] if isinstance(row, sqlite3.Row) else row[0]
                object_name = row["name"] if isinstance(row, sqlite3.Row) else row[1]
                if object_type not in ("trigger", "view"):
                    continue

                quoted_name = self._quote_sqlite_identifier(object_name)
                drop_keyword = "TRIGGER" if object_type == "trigger" else "VIEW"
                cursor.execute(f"DROP {drop_keyword} IF EXISTS {quoted_name}")
                print(
                    f"Dropped legacy SQLite {object_type} "
                    f"referencing obsolete migration table: {object_name}"
                )
        except sqlite3.Error as e:
            print(f"Legacy SQLite object cleanup error: {e}")
        except ValueError as e:
            print(f"Legacy SQLite object cleanup error: {e}")

    def _get_sqlite_foreign_key_targets(self, cursor, table_name: str) -> List[str]:
        """Return foreign-key target tables for a SQLite table."""
        if not self._is_sqlite() or not self._check_table_exists(cursor, table_name):
            return []

        quoted_table = self._quote_sqlite_identifier(table_name)
        cursor.execute(f"PRAGMA foreign_key_list({quoted_table})")
        targets = []
        for row in cursor.fetchall():
            targets.append(row["table"] if isinstance(row, sqlite3.Row) else row[2])
        return targets

    def _get_sqlite_tables_referencing_targets(
        self,
        cursor,
        target_names: tuple,
    ) -> List[str]:
        """Find SQLite tables with FK metadata referencing any target table."""
        if not self._is_sqlite():
            return []

        cursor.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
        table_names = [
            row["name"] if isinstance(row, sqlite3.Row) else row[0]
            for row in cursor.fetchall()
        ]
        broken_tables = []
        for table_name in table_names:
            targets = self._get_sqlite_foreign_key_targets(cursor, table_name)
            if any(target in target_names for target in targets):
                broken_tables.append(table_name)
        return broken_tables

    def _drop_sqlite_table_if_exists(self, cursor, table_name: str) -> None:
        """Drop a SQLite table by quoted identifier if it exists."""
        if not self._is_sqlite() or not self._check_table_exists(cursor, table_name):
            return

        quoted_table = self._quote_sqlite_identifier(table_name)
        cursor.execute(f"DROP TABLE IF EXISTS {quoted_table}")

    def _restore_sqlite_rebuild_pragmas(
        self,
        cursor,
        foreign_keys_were_enabled: bool,
        legacy_alter_table_was_enabled: bool,
    ) -> None:
        """Restore SQLite pragmas changed for a table rebuild."""
        legacy_value = 1 if legacy_alter_table_was_enabled else 0
        foreign_key_value = 1 if foreign_keys_were_enabled else 0
        cursor.execute(f"PRAGMA legacy_alter_table = {legacy_value}")
        cursor.execute(f"PRAGMA foreign_keys = {foreign_key_value}")
    
    def _get_text_type(self, length: Optional[int] = None) -> str:
        """Get TEXT/VARCHAR type for the current backend.
        
        Args:
            length: Optional length for VARCHAR (ignored for SQLite TEXT).
        
        Returns:
            'TEXT' for SQLite, 'VARCHAR(N)' for MySQL if length provided, else 'TEXT'
        """
        if self._is_sqlite():
            return "TEXT"
        elif length:
            return f"VARCHAR({length})"
        else:
            return "TEXT"
    
    def _get_datetime_type(self) -> str:
        """Get DATETIME type for the current backend."""
        return "TIMESTAMP" if self._is_sqlite() else "DATETIME"
    
    def _get_decimal_type(self, precision: int = 18, scale: int = 2) -> str:
        """Get DECIMAL type for the current backend.
        
        Args:
            precision: Total number of digits
            scale: Number of digits after decimal point
        
        Returns:
            'REAL' for SQLite, 'DECIMAL(precision,scale)' for MySQL
        """
        if self._is_sqlite():
            return "REAL"
        else:
            return f"DECIMAL({precision},{scale})"
    
    def _get_varchar_type(self, length: int = 255) -> str:
        """Get VARCHAR type for the current backend.
        
        Args:
            length: Maximum length for VARCHAR
        
        Returns:
            'TEXT' for SQLite, 'VARCHAR(length)' for MySQL
        """
        if self._is_sqlite():
            return "TEXT"
        else:
            return f"VARCHAR({length})"
    
    def _get_voucher_no_type(self, length: int = 50) -> str:
        """Get VARCHAR type for voucher numbers.
        
        Args:
            length: Maximum length for voucher number
        
        Returns:
            'TEXT' for SQLite, 'VARCHAR(length)' for MySQL
        """
        return self._get_varchar_type(length)
    
    def _get_date_type(self) -> str:
        """Get DATE type for the current backend.
        
        Returns:
            'TEXT' for SQLite (stored as ISO date string), 'DATE' for MySQL
        """
        if self._is_sqlite():
            return "TEXT"
        else:
            return "DATE"
    
    def _get_account_name_type(self, length: int = 255) -> str:
        """Get VARCHAR type for account names.
        
        Args:
            length: Maximum length for account name
        
        Returns:
            'TEXT' for SQLite, 'VARCHAR(length)' for MySQL
        """
        return self._get_varchar_type(length)
    
    def _get_narration_type(self, length: int = 1000) -> str:
        """Get TEXT type for narration fields.
        
        Args:
            length: Maximum length for narration (ignored for SQLite TEXT)
        
        Returns:
            'TEXT' for SQLite, 'VARCHAR(length)' for MySQL
        """
        return self._get_varchar_type(length)
    
    def _get_if_not_exists_supported(self) -> bool:
        """Check if CREATE TABLE IF NOT EXISTS is supported (both backends support this)."""
        return True
    
    def _check_column_exists(self, cursor, table_name: str, column_name: str) -> bool:
        """Check if a column exists in a table for the current backend."""
        if self._is_sqlite():
            safe_table = self._safe_identifier(table_name)
            cursor.execute(f"PRAGMA table_info({safe_table})")
            columns = [row[1] for row in cursor.fetchall()]
            return column_name in columns
        else:
            # MySQL: use information_schema
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s",
                (table_name, column_name)
            )
            result = cursor.fetchone()
            return result[0] > 0 if result else False
    
    def _check_index_exists(self, cursor, table_name: str, index_name: str) -> bool:
        """Check if an index exists for the current backend."""
        if self._is_sqlite():
            ph = self._get_placeholder()
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='index' AND name={ph}", (index_name,))
            return cursor.fetchone() is not None
        else:
            # MySQL: use information_schema
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.statistics "
                "WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s",
                (table_name, index_name)
            )
            result = cursor.fetchone()
            return result[0] > 0 if result else False
    
    def _create_index_if_missing(self, cursor, table_name: str, index_name: str, columns: str, unique: bool = False) -> None:
        """Create an index if it doesn't exist, using backend-safe method."""
        try:
            if not self._check_index_exists(cursor, table_name, index_name):
                unique_kw = "UNIQUE " if unique else ""
                if self._is_sqlite():
                    cursor.execute(f"CREATE {unique_kw}INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns})")
                else:
                    cursor.execute(f"CREATE {unique_kw}INDEX {index_name} ON {table_name} ({columns})")
        except Exception as e:
            print(f"Note: Index creation for {index_name} skipped: {e}")

    def _create_unique_index_if_no_duplicates(self, cursor, table_name: str,
                                              index_name: str, columns: str,
                                              duplicate_query: str) -> None:
        """Create a unique index only when existing data can satisfy it."""
        try:
            if self._check_index_exists(cursor, table_name, index_name):
                return
            cursor.execute(duplicate_query)
            duplicate = cursor.fetchone()
            if duplicate:
                print(
                    f"Note: Unique index {index_name} skipped because "
                    f"duplicate historical {table_name} rows exist."
                )
                return
            self._create_index_if_missing(
                cursor, table_name, index_name, columns, unique=True
            )
        except Exception as e:
            print(f"Note: Unique index creation for {index_name} skipped: {e}")
    
    def initialize_database(self) -> bool:
        """Initialize the database with all required tables."""
        try:
            conn = self.connect()
            if self.db_type == "sqlite" and self._schema_initialized:
                print("Database tables created successfully")
                return True

            with closing(conn.cursor()) as cursor:
                self._create_database_schema(cursor)
            
            conn.commit()
            self._schema_initialized = True
            if self.db_type == "sqlite":
                _INITIALIZED_SQLITE_PATHS.add(self.db_path)
            print("Database tables created successfully")
            return True
            
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            print(f"Database initialization error: {e}")
            return False
        except Exception as e:
            print(f"Database initialization error: {e}")
            return False
        finally:
            self.disconnect()

    def _create_database_schema(self, cursor) -> None:
        """Create all application tables and run schema migrations."""
        self._create_users_table(cursor)
        self._seed_default_admin_user(cursor)
        self._ensure_default_admin_permissions(cursor)
        self._create_accounts_table(cursor)
        self._create_transactions_table(cursor)
        self._create_categories_table(cursor)
        self._create_companies_table(cursor)
        self._create_audit_logs_table(cursor)
        self._create_products_table(cursor)
        self._create_parties_table(cursor)
        self._create_bank_accounts_table(cursor)
        self._create_stock_movements_table(cursor)
        self._create_salesmen_table(cursor)
        self._create_sales_table(cursor)
        self._create_sales_items_table(cursor)
        self._create_sales_returns_table(cursor)
        self._create_sales_return_items_table(cursor)
        self._create_purchases_table(cursor)
        self._create_purchase_items_table(cursor)
        self._create_purchase_returns_table(cursor)
        self._create_purchase_return_items_table(cursor)
        self._create_settings_table(cursor)
        self._create_company_settings_table(cursor)
        self._create_print_settings_table(cursor)
        self._create_general_settings_table(cursor)
        self._seed_general_settings_row(cursor)
        self._create_cash_tender_history_table(cursor)
        self._ensure_cash_tender_history_columns(cursor)
        self._create_barcode_settings_table(cursor)
        self._seed_barcode_settings_row(cursor)
        self._create_ledger_accounts_table(cursor)
        self._create_ledger_entries_table(cursor)
        self._create_cash_receipts_table(cursor)
        self._create_cash_receipt_items_table(cursor)
        self._create_cash_payments_table(cursor)
        self._create_cash_payment_items_table(cursor)
        self._create_bank_receipts_table(cursor)
        self._create_bank_payments_table(cursor)
        self._create_journal_vouchers_table(cursor)
        self._create_journal_voucher_lines_table(cursor)
        self._create_quotations_table(cursor)
        self._create_quotation_master_table(cursor)
        self._create_quotation_items_table(cursor)
        self._create_purchase_orders_table(cursor)
        self._create_purchase_order_items_table(cursor)
        self._create_pdc_register_table(cursor)
        self._create_stock_adjustments_table(cursor)
        self._create_stock_adjustment_items_table(cursor)
        self._create_stock_draft_session_table(cursor)

        self._migrate_database(cursor)

    def _create_users_table(self, cursor):
        """Create authentication users table for application login."""
        id_type = "INTEGER PRIMARY KEY"
        username_type = "TEXT" if self._is_sqlite() else self._get_varchar_type(255)
        password_type = "TEXT" if self._is_sqlite() else self._get_varchar_type(255)
        role_type = "TEXT" if self._is_sqlite() else self._get_varchar_type(50)
        permissions_type = "TEXT" if self._is_sqlite() else self._get_varchar_type(1000)

        if self._is_mysql():
            id_type = "INT AUTO_INCREMENT PRIMARY KEY"

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS users (
                id {id_type},
                company_id INTEGER,
                username {username_type},
                password {password_type},
                password_hash {password_type},
                role {role_type},
                permissions {permissions_type},
                UNIQUE(company_id, username)
            )
        """)
        self._ensure_users_compat_columns(cursor)

    def _ensure_users_compat_columns(self, cursor):
        """Add missing user columns for upgraded databases without resetting users."""
        text_type = "TEXT" if self._is_sqlite() else self._get_varchar_type(1000)
        password_type = "TEXT" if self._is_sqlite() else self._get_varchar_type(255)
        required_columns = {
            "password": password_type,
            "password_hash": password_type,
            "company_id": "INTEGER",
            "role": text_type,
            "permissions": text_type,
        }
        for column_name, column_type in required_columns.items():
            if self._check_column_exists(cursor, "users", column_name):
                continue
            cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")

    def _seed_default_admin_user(self, cursor):
        """Insert the default Admin user only when no users exist."""
        ph = self._get_placeholder()
        try:
            cursor.execute("SELECT COUNT(*) FROM users")
            result = cursor.fetchone()
            user_count = result[0] if result else 0

            if user_count != 0:
                cursor.execute(
                    f"""
                    UPDATE users
                    SET role = {ph},
                        permissions = COALESCE(permissions, {ph})
                    WHERE username = {ph}
                      AND LOWER(TRIM(COALESCE(role, ''))) = {ph}
                    """,
                    ("Admin", "ALL", "admin", "admin"),
                )
                return

            cursor.execute(
                f"""
                INSERT INTO users (
                    username, password, password_hash, role, permissions
                ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
                """,
                ("admin", "admin123", hash_password("admin123"), "Admin", "ALL"),
            )
        except Exception as e:
            print(f"Default admin seed error: {e}")

    def _ensure_default_admin_permissions(self, cursor):
        """Set ALL permissions for the default Admin only when the value is missing."""
        ph = self._get_placeholder()
        try:
            cursor.execute(
                f"""
                UPDATE users
                SET permissions = {ph}
                WHERE username = {ph}
                  AND role = {ph}
                  AND permissions IS NULL
                """,
                ("ALL", "admin", "Admin"),
            )
        except Exception as e:
            print(f"Default admin permissions migration note: {e}")
    
    def _create_accounts_table(self, cursor):
        """Create accounts table."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        varchar_255 = self._get_varchar_type(255)
        varchar_50 = self._get_varchar_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS accounts (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                name {varchar_255} NOT NULL,
                type {varchar_50} NOT NULL CHECK (type IN ('checking', 'savings', 'credit', 'cash', 'investment')),
                balance REAL DEFAULT 0.0,
                currency TEXT DEFAULT 'USD',
                description TEXT,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                UNIQUE(company_id, name)
            )
        """)
    
    def _create_transactions_table(self, cursor):
        """Create transactions table."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        varchar_50 = self._get_varchar_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS transactions (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                category_id INTEGER,
                type {varchar_50} NOT NULL CHECK (type IN ('income', 'expense', 'transfer')),
                amount REAL NOT NULL,
                description TEXT,
                date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE SET NULL
            )
        """)
    
    def _create_categories_table(self, cursor):
        """Create categories table."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        varchar_255 = self._get_varchar_type(255)
        varchar_50 = self._get_varchar_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS categories (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                name {varchar_255} NOT NULL,
                type {varchar_50} NOT NULL CHECK (type IN ('income', 'expense')),
                color TEXT DEFAULT '#2196F3',
                description TEXT,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                UNIQUE(company_id, name)
            )
        """)
    
    def _create_companies_table(self, cursor):
        """Create companies table."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        varchar_255 = self._get_varchar_type(255)
        varchar_50 = self._get_varchar_type(50)
        varchar_20 = self._get_varchar_type(20)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS companies (
                id {pk_autoinc},
                business_name {varchar_255} NOT NULL UNIQUE,
                phone_number {varchar_50},
                gstin {varchar_255},
                gst_type TEXT DEFAULT 'Regular',
                email {varchar_255},
                business_type {varchar_50},
                business_category {varchar_50},
                address TEXT,
                state {varchar_50},
                pincode {varchar_20},
                logo_path TEXT,
                signature_path TEXT,
                print_phone BOOLEAN DEFAULT 1,
                print_gstin BOOLEAN DEFAULT 1,
                print_email BOOLEAN DEFAULT 1,
                print_business_type BOOLEAN DEFAULT 1,
                print_business_category BOOLEAN DEFAULT 1,
                print_address BOOLEAN DEFAULT 1,
                print_state BOOLEAN DEFAULT 1,
                print_pincode BOOLEAN DEFAULT 1,
                print_logo BOOLEAN DEFAULT 1,
                print_signature BOOLEAN DEFAULT 1,
                is_active BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default}
            )
        """)
        self._ensure_company_columns(cursor)

    def _ensure_company_columns(self, cursor):
        """Ensure company GST and invoice print preference columns exist."""
        required_columns = {
            'gst_type': "TEXT DEFAULT 'Regular'",
            'financial_year': 'TEXT',
            'db_path': 'TEXT',
            'print_phone': 'BOOLEAN DEFAULT 1',
            'print_gstin': 'BOOLEAN DEFAULT 1',
            'print_email': 'BOOLEAN DEFAULT 1',
            'print_business_type': 'BOOLEAN DEFAULT 1',
            'print_business_category': 'BOOLEAN DEFAULT 1',
            'print_address': 'BOOLEAN DEFAULT 1',
            'print_state': 'BOOLEAN DEFAULT 1',
            'print_pincode': 'BOOLEAN DEFAULT 1',
            'print_logo': 'BOOLEAN DEFAULT 1',
            'print_signature': 'BOOLEAN DEFAULT 1',
            'visibility': "TEXT NOT NULL DEFAULT 'normal'",
        }
        try:
            if self.db_type == "sqlite":
                cursor.execute("PRAGMA table_info(companies)")
                existing = {row[1] for row in cursor.fetchall()}
            else:
                ph = self._get_placeholder()
                cursor.execute(
                    f"""
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = {ph}
                    """,
                    ("companies",),
                )
                existing = {row[0] for row in cursor.fetchall()}

            for column_name, column_type in required_columns.items():
                if column_name not in existing:
                    cursor.execute(f"ALTER TABLE companies ADD COLUMN {column_name} {column_type}")
        except Exception as e:
            print(f"Company column migration note: {e}")

    def _ensure_company_print_columns(self, cursor):
        """Backward-compatible wrapper for older migration call sites."""
        self._ensure_company_columns(cursor)

    def _create_audit_logs_table(self, cursor):
        """Create audit log table for human-readable voucher actions."""
        pk_autoinc = self._get_primary_key_autoincrement()
        module_type = self._get_varchar_type(100)
        action_type = self._get_varchar_type(20)
        reference_type = self._get_varchar_type(100)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                user_id INTEGER,
                action_date TEXT NOT NULL,
                module {module_type} NOT NULL,
                action_type {action_type} NOT NULL CHECK (action_type IN ('CREATE', 'UPDATE', 'DELETE')),
                reference_id {reference_type},
                description TEXT,
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE
            )
        """)
        self._create_index_if_missing(
            cursor,
            'audit_logs',
            'idx_audit_logs_company_date',
            'company_id, action_date'
        )
        self._create_index_if_missing(
            cursor,
            'audit_logs',
            'idx_audit_logs_company_module',
            'company_id, module'
        )
        self._create_index_if_missing(
            cursor,
            'audit_logs',
            'idx_audit_logs_reference',
            'company_id, reference_id'
        )
    
    def _create_parties_table(self, cursor):
        """Create parties table for Debitor/Creditor module."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        varchar_255 = self._get_varchar_type(255)
        varchar_50 = self._get_varchar_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS parties (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                name {varchar_255} NOT NULL,
                party_code {varchar_50},
                party_type {varchar_50} NOT NULL CHECK (party_type IN ('Debitor', 'Creditor', 'Both')),
                opening_balance REAL DEFAULT 0.0,
                mobile_number {varchar_50},
                email {varchar_255},
                address TEXT,
                gstin {varchar_255},
                state {varchar_50},
                credit_limit REAL DEFAULT 0.0,
                contact_person TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                UNIQUE(company_id, name)
            )
        """)
        self._create_index_if_missing(cursor, 'parties', 'idx_parties_company_code', 'company_id, party_code')
    
    def _create_products_table(self, cursor):
        """Create products table."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
        name_type = self._get_varchar_type(255)
        barcode_type = self._get_varchar_type(100)
        hsn_type = self._get_varchar_type(50)
        unit_type = self._get_varchar_type(50)
        category_type = self._get_varchar_type(100)
        color_type = self._get_varchar_type(50)
        size_type = self._get_varchar_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS products (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                name {name_type} NOT NULL,
                barcode {barcode_type},
                hsn {hsn_type},
                unit {unit_type} DEFAULT 'pcs',
                category {category_type},
                color {color_type},
                size {size_type},
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
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE
            )
        """)
        # Create indexes for fast lookup (barcode and name searches)
        self._create_index_if_missing(cursor, 'products', 'idx_products_company_name', 'company_id, name')
        self._create_index_if_missing(cursor, 'products', 'idx_products_company_barcode', 'company_id, barcode')
        self._create_index_if_missing(cursor, 'products', 'idx_products_company_category', 'company_id, category')
        self._create_index_if_missing(cursor, 'products', 'idx_products_lookup', 'id, category, size, color')
    
    def _create_settings_table(self, cursor):
        """Create settings table."""
        timestamp_default = self._get_timestamp_default()
        varchar_255 = self._get_varchar_type(255)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS settings (
                key {varchar_255} PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT {timestamp_default}
            )
        """)

    def _create_company_settings_table(self, cursor):
        """Create per-company application settings for tenant-safe overrides."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        setting_key_type = self._get_varchar_type(255)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS company_settings (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                setting_key {setting_key_type} NOT NULL,
                setting_value TEXT,
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                UNIQUE(company_id, setting_key)
            )
        """)
        self._ensure_company_settings_columns(cursor)
        self._create_index_if_missing(
            cursor,
            "company_settings",
            "idx_company_settings_company_key",
            "company_id, setting_key",
            unique=True,
        )

    def _ensure_company_settings_columns(self, cursor):
        """Add missing company_settings columns without disturbing existing rows."""
        required_columns = {
            "company_id": "INTEGER",
            "setting_key": self._get_varchar_type(255),
            "setting_value": "TEXT",
        }
        try:
            if self._is_sqlite():
                cursor.execute("PRAGMA table_info(company_settings)")
                existing = {row[1] for row in cursor.fetchall()}
            else:
                ph = self._get_placeholder()
                cursor.execute(
                    f"""
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = {ph}
                    """,
                    ("company_settings",),
                )
                existing = {row[0] for row in cursor.fetchall()}

            for column_name, column_type in required_columns.items():
                if column_name not in existing:
                    cursor.execute(
                        f"ALTER TABLE company_settings ADD COLUMN {column_name} {column_type}"
                    )
        except Exception as e:
            print(f"Company settings migration note: {e}")

    def _create_print_settings_table(self, cursor):
        """Create company-scoped invoice print defaults for future UI use."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS print_settings (
                company_id INTEGER PRIMARY KEY,
                default_format TEXT,
                default_theme TEXT,
                printer_name TEXT,
                printer_type TEXT,
                paper_size TEXT,
                header_quote TEXT,
                footer_terms TEXT,
                layout_coordinates TEXT,
                show_item_barcode TEXT DEFAULT '0',
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE
            )
        """)
        self._ensure_print_settings_columns(cursor)

    def _ensure_print_settings_columns(self, cursor):
        """Add missing print_settings columns for existing installations."""
        required_columns = {
            "company_id": "INTEGER",
            "default_format": "TEXT",
            "default_theme": "TEXT",
            "printer_name": "TEXT",
            "printer_type": "TEXT",
            "paper_size": "TEXT",
            "header_quote": "TEXT",
            "footer_terms": "TEXT",
            "layout_coordinates": "TEXT",
            "show_item_barcode": "TEXT DEFAULT '0'",
        }
        try:
            if self._is_sqlite():
                cursor.execute("PRAGMA table_info(print_settings)")
                existing = {row[1] for row in cursor.fetchall()}
            else:
                ph = self._get_placeholder()
                cursor.execute(
                    f"""
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = {ph}
                    """,
                    ("print_settings",),
                )
                existing = {row[0] for row in cursor.fetchall()}

            for column_name, column_type in required_columns.items():
                if column_name not in existing:
                    cursor.execute(
                        f"ALTER TABLE print_settings ADD COLUMN {column_name} {column_type}"
                    )
        except Exception as e:
            print(f"Print settings migration note: {e}")

    def ensure_print_settings_table(self) -> bool:
        """Public migration helper for print settings callers outside startup."""
        try:
            conn = self.connect()
            with closing(conn.cursor()) as cursor:
                self._create_print_settings_table(cursor)
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Database Error: {e}")
            print(f"Print settings table ensure error: {e}")
            return False
        except Exception as e:
            print(f"Print settings table ensure error: {e}")
            return False
        finally:
            self.disconnect()

    def ensure_company_settings_table(self) -> bool:
        """Public migration helper for settings callers outside startup init."""
        try:
            conn = self.connect()
            with closing(conn.cursor()) as cursor:
                self._create_company_settings_table(cursor)
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Database Error: {e}")
            print(f"Company settings table ensure error: {e}")
            return False
        except Exception as e:
            print(f"Company settings table ensure error: {e}")
            return False
        finally:
            self.disconnect()

    def _create_general_settings_table(self, cursor):
        """Create global application settings used outside accounting ledgers."""
        setting_key_type = self._get_varchar_type(255)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS general_settings (
                setting_key {setting_key_type} PRIMARY KEY,
                setting_value TEXT
            )
        """)

    def _seed_general_settings_row(self, cursor):
        """Seed default Cash Tender setting without overwriting user choices."""
        ph = self._get_placeholder()
        try:
            if self._is_sqlite():
                cursor.execute(
                    f"""
                    INSERT OR IGNORE INTO general_settings (
                        setting_key, setting_value
                    ) VALUES ({ph}, {ph})
                    """,
                    ("enable_cash_tender", "1"),
                )
            else:
                cursor.execute(
                    f"""
                    INSERT INTO general_settings (
                        setting_key, setting_value
                    ) VALUES ({ph}, {ph})
                    ON DUPLICATE KEY UPDATE setting_key = setting_key
                    """,
                    ("enable_cash_tender", "1"),
                )
        except Exception as e:
            print(f"General settings seed error: {e}")

    def _create_cash_tender_history_table(self, cursor):
        """Create non-ledger Cash Tender audit history for Sales Entry."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        bill_no_type = self._get_varchar_type(50)
        payment_mode_type = self._get_varchar_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS cash_tender_history (
                id {pk_autoinc},
                bill_no {bill_no_type},
                bill_amount REAL,
                cash_received REAL,
                balance_returned REAL,
                payment_mode {payment_mode_type} DEFAULT 'Cash',
                created_at DATETIME DEFAULT {timestamp_default}
            )
        """)

    def _ensure_cash_tender_history_columns(self, cursor):
        """Add Cash Tender history columns introduced after initial installs."""
        try:
            if self._check_column_exists(
                cursor,
                "cash_tender_history",
                "payment_mode",
            ):
                return
            payment_mode_type = self._get_varchar_type(50)
            cursor.execute(
                "ALTER TABLE cash_tender_history "
                f"ADD COLUMN payment_mode {payment_mode_type} DEFAULT 'Cash'"
            )
        except Exception as e:
            print(f"Cash Tender history column migration error: {e}")

    def _create_barcode_settings_table(self, cursor):
        """Global barcode label preferences (single row id=1)."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS barcode_settings (
                id INTEGER PRIMARY KEY,
                company_name TEXT DEFAULT '',
                cipher_string TEXT DEFAULT '',
                default_size TEXT DEFAULT '',
                default_gap TEXT DEFAULT '',
                default_printer TEXT DEFAULT '',
                element_offsets TEXT DEFAULT '',
                typography_settings TEXT DEFAULT ''
            )
        """)

    def _seed_barcode_settings_row(self, cursor):
        """Insert default barcode preferences when the table has no rows (silent)."""
        try:
            cursor.execute("SELECT id FROM barcode_settings WHERE id = 1")
            if cursor.fetchone():
                return
            cursor.execute(
                """
                INSERT INTO barcode_settings (
                    id, company_name, cipher_string, default_size,
                    default_gap, default_printer
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "My Company",
                    "RCNXZYBQWM",
                    '2.00" x 1.00" (50x25mm Single)',
                    "With Gap (3mm standard)",
                    "",
                ),
            )
        except Exception:
            pass
    
    def _create_stock_movements_table(self, cursor):
        """Create stock_movements table for stock tracking foundation."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
        movement_type_type = self._get_text_type(50)
        reference_type_type = self._get_text_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS stock_movements (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                movement_type {movement_type_type} NOT NULL CHECK (movement_type IN ('opening', 'purchase', 'sale', 'return', 'sales_return', 'purchase_return', 'adjustment', 'adjustment_in', 'adjustment_out', 'transfer_in', 'transfer_out')),
                quantity REAL NOT NULL,
                reference_type {reference_type_type},
                reference_id INTEGER,
                notes TEXT,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
            )
        """)
        self._create_index_if_missing(cursor, 'stock_movements', 'idx_stock_balance_calc', 'product_id, company_id, quantity')
    
    def _create_bank_accounts_table(self, cursor):
        """Create bank_accounts table for bank account management."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
        account_name_type = self._get_text_type(255)
        bank_name_type = self._get_text_type(255)
        account_number_type = self._get_text_type(50)
        ifsc_code_type = self._get_text_type(50)
        branch_name_type = self._get_text_type(255)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS bank_accounts (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                account_name {account_name_type} NOT NULL,
                bank_name {bank_name_type} NOT NULL,
                account_number {account_number_type} NOT NULL,
                ifsc_code {ifsc_code_type},
                branch_name {branch_name_type},
                opening_balance REAL DEFAULT 0.0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                UNIQUE(company_id, account_name)
            )
        """)
    
    def _create_salesmen_table(self, cursor):
        """Create salesmen master table for sales bill tracking."""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS salesmen (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE
            )
        """)

    def _create_sales_table(self, cursor):
        """Create sales table for sales header information."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
        invoice_number_type = self._get_text_type(100)
        sales_type_type = self._get_text_type(50)
        bill_series_type = self._get_text_type(50)
        nature_type = self._get_text_type(50)
        gstin_type = self._get_text_type(15)
        state_type = self._get_text_type(100)
        sales_rate_type = self._get_text_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS sales (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                invoice_number {invoice_number_type} NOT NULL,
                invoice_date DATE NOT NULL,
                party_id INTEGER NOT NULL,
                sales_type {sales_type_type} DEFAULT 'Sales' CHECK (sales_type IN ('Sales', 'Credit Sales', 'Return', 'Bill of Supply')),
                bill_series {bill_series_type},
                nature {nature_type},
                due_date DATE,
                address TEXT,
                gstin {gstin_type},
                state {state_type},
                sales_rate {sales_rate_type} DEFAULT 'Exclusive',
                narration TEXT,
                salesman TEXT,
                sub_total REAL DEFAULT 0.0,
                discount_total REAL DEFAULT 0.0,
                tax_total REAL DEFAULT 0.0,
                round_off REAL DEFAULT 0.0,
                grand_total REAL DEFAULT 0.0,
                amount_received REAL DEFAULT 0.0,
                payment_mode TEXT DEFAULT 'Cash',
                status VARCHAR(20) DEFAULT 'Active',
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE CASCADE,
                UNIQUE(company_id, invoice_number)
            )
        """)
        self._create_index_if_missing(cursor, 'sales', 'idx_sales_invoice_search', 'company_id, invoice_date, invoice_number')

    def _migrate_sales_table(self, cursor):
        """Migrate sales table to add missing columns safely."""
        if self.db_type == "sqlite":
            try:
                cursor.execute("ALTER TABLE sales ADD COLUMN amount_received REAL DEFAULT 0.0")
            except Exception:
                pass  # Column may already exist
            try:
                cursor.execute("ALTER TABLE sales ADD COLUMN form_of_sale TEXT DEFAULT 'B2CS'")
            except Exception:
                pass  # Column may already exist
            try:
                cursor.execute("ALTER TABLE sales ADD COLUMN status TEXT DEFAULT 'Active'")
            except Exception:
                pass  # Column may already exist
            try:
                cursor.execute(
                    "ALTER TABLE sales ADD COLUMN payment_mode TEXT DEFAULT 'Cash'"
                )
            except Exception:
                pass  # Column may already exist
            try:
                cursor.execute("ALTER TABLE sales ADD COLUMN salesman TEXT")
            except sqlite3.OperationalError:
                pass  # Column may already exist
            self._migrate_sales_type_bill_of_supply(cursor)
        else:
            # MySQL: use IF NOT EXISTS
            try:
                cursor.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS amount_received REAL DEFAULT 0.0")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS form_of_sale TEXT DEFAULT 'B2CS'")
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'Active'")
            except Exception:
                pass
            try:
                cursor.execute(
                    "ALTER TABLE sales ADD COLUMN IF NOT EXISTS payment_mode TEXT DEFAULT 'Cash'"
                )
            except Exception:
                pass
            try:
                cursor.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS salesman TEXT")
            except Exception:
                pass

    def _migrate_sales_type_bill_of_supply(self, cursor):
        """Rebuild SQLite sales tables so sales_type accepts Bill of Supply."""
        if not self._is_sqlite():
            return

        try:
            cursor.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'sales'")
            row = cursor.fetchone()
            sales_sql = row[0] if row else ""
            if "Bill of Supply" in sales_sql:
                return

            print("Migrating sales.sales_type to allow Bill of Supply...")
            timestamp_default = self._get_timestamp_default()
            pk_autoinc = self._get_primary_key_autoincrement()

            cursor.execute("PRAGMA table_info(sales)")
            sales_columns = {col[1] for col in cursor.fetchall()}
            if not sales_columns:
                return

            cursor.execute("PRAGMA table_info(sales_items)")
            item_columns = {col[1] for col in cursor.fetchall()}

            cursor.execute("PRAGMA foreign_keys = OFF")
            cursor.execute("ALTER TABLE sales RENAME TO sales_type_old")
            cursor.execute(f"""
                CREATE TABLE sales (
                    id {pk_autoinc},
                    company_id INTEGER NOT NULL,
                    invoice_number TEXT NOT NULL,
                    invoice_date DATE NOT NULL,
                    party_id INTEGER NOT NULL,
                    sales_type TEXT DEFAULT 'Sales' CHECK (sales_type IN ('Sales', 'Credit Sales', 'Return', 'Bill of Supply')),
                    bill_series TEXT,
                    nature TEXT,
                    due_date DATE,
                    address TEXT,
                    gstin TEXT,
                    state TEXT,
                    sales_rate TEXT DEFAULT 'Exclusive',
                    narration TEXT,
                    sub_total REAL DEFAULT 0.0,
                    discount_total REAL DEFAULT 0.0,
                    tax_total REAL DEFAULT 0.0,
                    round_off REAL DEFAULT 0.0,
                    grand_total REAL DEFAULT 0.0,
                    amount_received REAL DEFAULT 0.0,
                    form_of_sale TEXT DEFAULT 'B2CS',
                    payment_mode TEXT DEFAULT 'Cash',
                    status TEXT DEFAULT 'Active',
                    created_at TIMESTAMP DEFAULT {timestamp_default},
                    updated_at TIMESTAMP DEFAULT {timestamp_default},
                    FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                    FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE CASCADE,
                    UNIQUE(company_id, invoice_number)
                )
            """)

            sales_copy_columns = [
                ("id", "id"),
                ("company_id", "company_id"),
                ("invoice_number", "invoice_number"),
                ("invoice_date", "invoice_date"),
                ("party_id", "party_id"),
                ("sales_type", "sales_type"),
                ("bill_series", "bill_series"),
                ("nature", "nature"),
                ("due_date", "due_date"),
                ("address", "address"),
                ("gstin", "gstin"),
                ("state", "state"),
                ("sales_rate", "sales_rate"),
                ("narration", "narration"),
                ("sub_total", "sub_total"),
                ("discount_total", "discount_total"),
                ("tax_total", "tax_total"),
                ("round_off", "round_off"),
                ("grand_total", "grand_total"),
                ("amount_received", "amount_received"),
                ("form_of_sale", "form_of_sale"),
                ("payment_mode", "payment_mode"),
                ("status", "status"),
                ("created_at", "created_at"),
                ("updated_at", "updated_at"),
            ]
            sales_defaults = {
                "amount_received": "0.0",
                "form_of_sale": "'B2CS'",
                "payment_mode": "'Cash'",
                "status": "'Active'",
                "created_at": "CURRENT_TIMESTAMP",
                "updated_at": "CURRENT_TIMESTAMP",
            }
            insert_cols = [target for target, _source in sales_copy_columns]
            select_exprs = [
                source if source in sales_columns else sales_defaults.get(target, "NULL")
                for target, source in sales_copy_columns
            ]
            cursor.execute(f"""
                INSERT INTO sales ({", ".join(insert_cols)})
                SELECT {", ".join(select_exprs)}
                FROM sales_type_old
            """)
            cursor.execute("DROP TABLE sales_type_old")

            if item_columns:
                cursor.execute("ALTER TABLE sales_items RENAME TO sales_items_type_old")
                self._create_sales_items_table_with_current_columns(cursor)
                item_copy_columns = [
                    ("id", "id", "NULL"),
                    ("sale_id", "sale_id", "NULL"),
                    ("product_id", "product_id", "NULL"),
                    ("sl_no", "sl_no", "0"),
                    ("hsn", "hsn", "NULL"),
                    ("tax_percent", "tax_percent", "0.0"),
                    ("unit", "unit", "NULL"),
                    ("rate", "rate", "0.0"),
                    ("quantity", "quantity", "0.0"),
                    ("gross_value", "gross_value", "0.0"),
                    ("discount", "discount", "0.0"),
                    ("net_value", "net_value", "0.0"),
                    ("tax_amount", "tax_amount", "0.0"),
                    ("grand_total", "grand_total", "0.0"),
                    ("created_at", "created_at", "CURRENT_TIMESTAMP"),
                    ("cgst", "cgst", "0.0"),
                    ("sgst", "sgst", "0.0"),
                    ("igst", "igst", "0.0"),
                    ("cess", "cess", "0.0"),
                    ("cgst_amount", "cgst_amount", "0.0"),
                    ("sgst_amount", "sgst_amount", "0.0"),
                    ("igst_amount", "igst_amount", "0.0"),
                    ("cess_amount", "cess_amount", "0.0"),
                    ("cost_price", "cost_price", "0.0"),
                    ("cost_value", "cost_value", "0.0"),
                ]
                item_insert_cols = [target for target, _source, _default in item_copy_columns]
                item_select_exprs = [
                    source if source in item_columns else default
                    for _target, source, default in item_copy_columns
                ]
                cursor.execute(f"""
                    INSERT INTO sales_items ({", ".join(item_insert_cols)})
                    SELECT {", ".join(item_select_exprs)}
                    FROM sales_items_type_old
                """)
                cursor.execute("DROP TABLE sales_items_type_old")

            cursor.execute("PRAGMA foreign_keys = ON")
            self._create_index_if_missing(cursor, 'sales', 'idx_sales_invoice_search', 'company_id, invoice_date, invoice_number')
            self._create_index_if_missing(cursor, 'sales_items', 'idx_sales_items_sale_id', 'sale_id')
            self._create_index_if_missing(cursor, 'sales_items', 'idx_sales_items_product_id', 'product_id')
            print("sales.sales_type Bill of Supply migration complete.")
        except Exception as e:
            try:
                cursor.execute("PRAGMA foreign_keys = ON")
            except Exception:
                pass
            print(f"sales.sales_type Bill of Supply migration error: {e}")

    def _create_sales_items_table_with_current_columns(self, cursor):
        """Create sales_items with the full current column set for table rebuilds."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        cursor.execute(f"""
            CREATE TABLE sales_items (
                id {pk_autoinc},
                sale_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                sl_no INTEGER NOT NULL,
                hsn TEXT,
                tax_percent REAL DEFAULT 0.0,
                unit TEXT,
                rate REAL DEFAULT 0.0,
                quantity REAL DEFAULT 0.0,
                gross_value REAL DEFAULT 0.0,
                discount REAL DEFAULT 0.0,
                net_value REAL DEFAULT 0.0,
                tax_amount REAL DEFAULT 0.0,
                grand_total REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                cgst REAL DEFAULT 0.0,
                sgst REAL DEFAULT 0.0,
                igst REAL DEFAULT 0.0,
                cess REAL DEFAULT 0.0,
                cgst_amount REAL DEFAULT 0.0,
                sgst_amount REAL DEFAULT 0.0,
                igst_amount REAL DEFAULT 0.0,
                cess_amount REAL DEFAULT 0.0,
                cost_price REAL DEFAULT 0.0,
                cost_value REAL DEFAULT 0.0,
                FOREIGN KEY (sale_id) REFERENCES sales (id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
            )
        """)
    
    def _create_sales_items_table(self, cursor):
        """Create sales_items table for sales line items."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
        hsn_type = self._get_text_type(50)
        unit_type = self._get_text_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS sales_items (
                id {pk_autoinc},
                sale_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                sl_no INTEGER NOT NULL,
                hsn {hsn_type},
                tax_percent REAL DEFAULT 0.0,
                unit {unit_type},
                rate REAL DEFAULT 0.0,
                quantity REAL DEFAULT 0.0,
                gross_value REAL DEFAULT 0.0,
                discount REAL DEFAULT 0.0,
                net_value REAL DEFAULT 0.0,
                tax_amount REAL DEFAULT 0.0,
                grand_total REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (sale_id) REFERENCES sales (id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
            )
        """)
    
    def _create_purchases_table(self, cursor):
        """Create purchases table for purchase header information."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
        purchase_number_type = self._get_text_type(100)
        purchase_type_type = self._get_text_type(50)
        bill_series_type = self._get_text_type(50)
        nature_type = self._get_text_type(50)
        gstin_type = self._get_text_type(15)
        state_type = self._get_text_type(100)
        purchase_rate_type = self._get_text_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS purchases (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                purchase_number {purchase_number_type} NOT NULL,
                purchase_date DATE NOT NULL,
                party_id INTEGER NOT NULL,
                purchase_type {purchase_type_type} DEFAULT 'Cash' CHECK (purchase_type IN ('Cash', 'Credit')),
                bill_series {bill_series_type},
                nature {nature_type},
                due_date DATE,
                address TEXT,
                gstin {gstin_type},
                state {state_type},
                supplier_invoice_no {purchase_number_type},
                purchase_rate {purchase_rate_type} DEFAULT 'Exclusive',
                narration TEXT,
                sub_total REAL DEFAULT 0.0,
                discount_total REAL DEFAULT 0.0,
                tax_total REAL DEFAULT 0.0,
                freight REAL DEFAULT 0.0,
                purchase_expense REAL DEFAULT 0.0,
                round_off REAL DEFAULT 0.0,
                grand_total REAL DEFAULT 0.0,
                amount_paid REAL DEFAULT 0.0,
                status VARCHAR(20) DEFAULT 'Active',
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE CASCADE,
                UNIQUE(company_id, purchase_number)
            )
        """)

        # Create indexes for performance and MySQL compatibility
        try:
            self._create_index_if_missing(cursor, 'purchases', 'idx_purchases_company_id', 'company_id')
            self._create_index_if_missing(cursor, 'purchases', 'idx_purchases_purchase_no', 'purchase_number')
            self._create_index_if_missing(cursor, 'purchases', 'idx_purchases_party_id', 'party_id')
            self._create_index_if_missing(cursor, 'purchases', 'idx_purchases_date', 'purchase_date')
        except Exception as e:
            # Index creation may fail if already exists or not supported
            print(f"Note: Index creation failed (may already exist): {e}")

    def _migrate_purchases_table(self, cursor):
        """Migrate purchases table to add missing columns safely."""
        missing_columns = (
            ("status", "TEXT DEFAULT 'Active'", "VARCHAR(20) DEFAULT 'Active'"),
            ("supplier_invoice_no", "TEXT", "VARCHAR(100)"),
            ("freight", "REAL DEFAULT 0.0", "DOUBLE DEFAULT 0.0"),
            ("purchase_expense", "REAL DEFAULT 0.0", "DOUBLE DEFAULT 0.0"),
        )
        if self.db_type == "sqlite":
            for column_name, sqlite_type, _mysql_type in missing_columns:
                try:
                    cursor.execute(f"ALTER TABLE purchases ADD COLUMN {column_name} {sqlite_type}")
                except Exception:
                    pass  # Column may already exist
        else:
            for column_name, _sqlite_type, mysql_type in missing_columns:
                try:
                    cursor.execute(f"ALTER TABLE purchases ADD COLUMN IF NOT EXISTS {column_name} {mysql_type}")
                except Exception:
                    pass

    def _migrate_return_status_columns(self, cursor):
        """Migrate return header tables to add status columns safely."""
        targets = (
            ("sales_returns", "TEXT"),
            ("purchase_returns", "TEXT"),
        )
        if self.db_type == "sqlite":
            for table_name, column_type in targets:
                try:
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN status {column_type} DEFAULT 'Active'")
                except Exception:
                    pass  # Column may already exist
        else:
            for table_name, _column_type in targets:
                try:
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'Active'")
                except Exception:
                    pass

    def _create_ledger_accounts_table(self, cursor):
        """Create ledger accounts table for double-entry accounting."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
        account_name_type = self._get_text_type(255)
        account_type_type = self._get_text_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS ledger_accounts (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                account_name {account_name_type} NOT NULL,
                account_code VARCHAR(50),
                account_type {account_type_type} NOT NULL CHECK (account_type IN ('party', 'cash_bank', 'income', 'expense', 'tax_liability', 'capital', 'stock')),
                group_name VARCHAR(100),
                opening_balance REAL DEFAULT 0.0,
                opening_balance_type VARCHAR(10) DEFAULT 'Dr' CHECK (opening_balance_type IN ('Dr', 'Cr')),
                is_system INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                UNIQUE(company_id, account_name)
            )
        """)

        # Create indexes for performance
        try:
            self._create_index_if_missing(cursor, 'ledger_accounts', 'idx_ledger_accounts_company_id', 'company_id')
            self._create_index_if_missing(cursor, 'ledger_accounts', 'idx_ledger_accounts_account_name', 'account_name')
            self._create_index_if_missing(cursor, 'ledger_accounts', 'idx_ledger_accounts_account_type', 'account_type')
        except Exception as e:
            print(f"Note: Ledger accounts index creation failed (may already exist): {e}")

    def _create_stock_adjustments_table(self, cursor):
        """Create stock_adjustments header table."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        varchar_100 = self._get_varchar_type(100)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS stock_adjustments (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                voucher_no {varchar_100} NOT NULL,
                voucher_date DATE NOT NULL,
                narration TEXT,
                total_increase_value REAL DEFAULT 0.0,
                total_decrease_value REAL DEFAULT 0.0,
                net_adjustment REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                UNIQUE(company_id, voucher_no)
            )
        """)
        self._create_index_if_missing(cursor, 'stock_adjustments', 'idx_stock_adjustments_company_date', 'company_id, voucher_date')

    def _create_stock_adjustment_items_table(self, cursor):
        """Create stock_adjustment_items table."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        varchar_100 = self._get_varchar_type(100)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS stock_adjustment_items (
                id {pk_autoinc},
                adjustment_id INTEGER NOT NULL,
                sl_no INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                barcode {varchar_100},
                system_qty REAL DEFAULT 0.0,
                physical_qty REAL DEFAULT 0.0,
                difference_qty REAL DEFAULT 0.0,
                rate REAL DEFAULT 0.0,
                value REAL DEFAULT 0.0,
                reason TEXT,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (adjustment_id) REFERENCES stock_adjustments (id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
            )
        """)

    def _create_stock_draft_session_table(self, cursor):
        """Create stock_draft_session table for multi-day stock audit sessions."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        varchar_100 = self._get_varchar_type(100)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS stock_draft_session (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                item_code {varchar_100},
                item_name TEXT NOT NULL,
                computer_qty REAL DEFAULT 0.0,
                physical_qty REAL DEFAULT 0.0,
                purchase_rate REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (item_id) REFERENCES products (id) ON DELETE CASCADE
            )
        """)
        self._create_index_if_missing(cursor, 'stock_draft_session', 'idx_stock_draft_session_company', 'company_id')
        self._create_index_if_missing(cursor, 'stock_draft_session', 'idx_stock_draft_session_company_item', 'company_id, item_id')

    def _create_ledger_entries_table(self, cursor):
        """Create ledger_entries table for double-entry accounting transactions."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
        voucher_type_type = self._get_text_type(50)
        voucher_no_type = self._get_text_type(100)
        reference_type_type = self._get_text_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS ledger_entries (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                voucher_type {voucher_type_type} NOT NULL,
                voucher_id INTEGER NOT NULL,
                voucher_no {voucher_no_type},
                voucher_date DATE NOT NULL,
                account_id INTEGER NOT NULL,
                contra_account_id INTEGER,
                narration TEXT,
                debit REAL DEFAULT 0.0,
                credit REAL DEFAULT 0.0,
                running_balance REAL DEFAULT 0.0,
                reference_type {reference_type_type},
                reference_id INTEGER,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES ledger_accounts (id) ON DELETE CASCADE
            )
        """)

        # Create indexes for performance
        try:
            self._create_index_if_missing(cursor, 'ledger_entries', 'idx_ledger_entries_company_id', 'company_id')
            self._create_index_if_missing(cursor, 'ledger_entries', 'idx_ledger_entries_voucher_date', 'voucher_date')
            self._create_index_if_missing(cursor, 'ledger_entries', 'idx_ledger_entries_voucher_type', 'voucher_type')
            self._create_index_if_missing(cursor, 'ledger_entries', 'idx_ledger_entries_voucher_id', 'voucher_id')
            self._create_index_if_missing(cursor, 'ledger_entries', 'idx_ledger_entries_account_id', 'account_id')
            self._create_index_if_missing(cursor, 'ledger_entries', 'idx_ledger_entries_reference_id', 'reference_id')
        except Exception as e:
            print(f"Note: Ledger entries index creation failed (may already exist): {e}")
    
    def _create_purchase_items_table(self, cursor):
        """Create purchase_items table for purchase line items."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
        hsn_type = self._get_text_type(50)
        unit_type = self._get_text_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS purchase_items (
                id {pk_autoinc},
                purchase_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                sl_no INTEGER NOT NULL,
                hsn {hsn_type},
                tax_percent REAL DEFAULT 0.0,
                unit {unit_type},
                rate REAL DEFAULT 0.0,
                quantity REAL DEFAULT 0.0,
                gross_value REAL DEFAULT 0.0,
                discount REAL DEFAULT 0.0,
                net_value REAL DEFAULT 0.0,
                tax_amount REAL DEFAULT 0.0,
                grand_total REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (purchase_id) REFERENCES purchases (id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
            )
        """)
    
    def _create_sales_returns_table(self, cursor):
        """Create sales_returns table for sales return header information."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
        return_no_type = self._get_text_type(100)
        original_bill_no_type = self._get_text_type(100)
        return_type_type = self._get_text_type(50)
        nature_type = self._get_text_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS sales_returns (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                return_no {return_no_type} NOT NULL,
                return_date DATE NOT NULL,
                original_bill_id INTEGER,
                original_bill_no {original_bill_no_type},
                party_id INTEGER,
                return_type {return_type_type} DEFAULT 'Cash' CHECK (return_type IN ('Cash', 'Credit')),
                nature {nature_type},
                narration TEXT,
                sub_total REAL DEFAULT 0.0,
                discount_total REAL DEFAULT 0.0,
                tax_total REAL DEFAULT 0.0,
                round_off REAL DEFAULT 0.0,
                grand_total REAL DEFAULT 0.0,
                amount_refunded_or_adjusted REAL DEFAULT 0.0,
                balance_adjustment REAL DEFAULT 0.0,
                status VARCHAR(20) DEFAULT 'Active',
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE CASCADE,
                UNIQUE(company_id, return_no)
            )
        """)

    def _create_sales_return_items_table(self, cursor):
        """Create sales_return_items table for sales return line items."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
        hsn_type = self._get_text_type(50)
        unit_type = self._get_text_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS sales_return_items (
                id {pk_autoinc},
                sales_return_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                sl_no INTEGER NOT NULL,
                hsn {hsn_type},
                cgst REAL DEFAULT 0.0,
                sgst REAL DEFAULT 0.0,
                igst REAL DEFAULT 0.0,
                cess REAL DEFAULT 0.0,
                tax_percent REAL DEFAULT 0.0,
                unit {unit_type},
                rate REAL DEFAULT 0.0,
                quantity REAL DEFAULT 0.0,
                gross_value REAL DEFAULT 0.0,
                discount REAL DEFAULT 0.0,
                net_value REAL DEFAULT 0.0,
                tax_amount REAL DEFAULT 0.0,
                grand_total REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (sales_return_id) REFERENCES sales_returns (id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
            )
        """)
    
    def _create_purchase_returns_table(self, cursor):
        """Create purchase_returns table for purchase return header information."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
        return_no_type = self._get_text_type(100)
        original_purchase_no_type = self._get_text_type(100)
        return_type_type = self._get_text_type(50)
        nature_type = self._get_text_type(50)
        supplier_invoice_no_type = self._get_text_type(100)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS purchase_returns (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                return_no {return_no_type} NOT NULL,
                return_date DATE NOT NULL,
                original_purchase_id INTEGER,
                original_purchase_no {original_purchase_no_type},
                party_id INTEGER NOT NULL,
                return_type {return_type_type} DEFAULT 'Cash' CHECK (return_type IN ('Cash', 'Credit')),
                nature {nature_type},
                supplier_invoice_no {supplier_invoice_no_type},
                narration TEXT,
                sub_total REAL DEFAULT 0.0,
                discount_total REAL DEFAULT 0.0,
                tax_total REAL DEFAULT 0.0,
                round_off REAL DEFAULT 0.0,
                grand_total REAL DEFAULT 0.0,
                amount_received_or_adjusted REAL DEFAULT 0.0,
                balance_adjustment REAL DEFAULT 0.0,
                status VARCHAR(20) DEFAULT 'Active',
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE CASCADE,
                UNIQUE(company_id, return_no)
            )
        """)

    def _create_purchase_return_items_table(self, cursor):
        """Create purchase_return_items table for purchase return line items."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
        hsn_type = self._get_text_type(50)
        unit_type = self._get_text_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS purchase_return_items (
                id {pk_autoinc},
                purchase_return_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                sl_no INTEGER NOT NULL,
                hsn {hsn_type},
                cgst REAL DEFAULT 0.0,
                sgst REAL DEFAULT 0.0,
                igst REAL DEFAULT 0.0,
                cess REAL DEFAULT 0.0,
                tax_percent REAL DEFAULT 0.0,
                unit {unit_type},
                rate REAL DEFAULT 0.0,
                quantity REAL DEFAULT 0.0,
                gross_value REAL DEFAULT 0.0,
                discount REAL DEFAULT 0.0,
                net_value REAL DEFAULT 0.0,
                tax_amount REAL DEFAULT 0.0,
                grand_total REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (purchase_return_id) REFERENCES purchase_returns (id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
            )
        """)
        # Create indexes for purchase_return_items
        self._create_index_if_missing(cursor, 'purchase_return_items', 'idx_purchase_return_items_return_id', 'purchase_return_id')
        self._create_index_if_missing(cursor, 'purchase_return_items', 'idx_purchase_return_items_product_id', 'product_id')

    def _create_purchase_return_indexes(self, cursor):
        """Create indexes for purchase_returns table if they don't exist."""
        self._create_index_if_missing(cursor, 'purchase_returns', 'idx_purchase_returns_company_id', 'company_id')
        self._create_index_if_missing(cursor, 'purchase_returns', 'idx_purchase_returns_return_no', 'return_no')
        self._create_index_if_missing(cursor, 'purchase_returns', 'idx_purchase_returns_return_date', 'return_date')
        self._create_index_if_missing(cursor, 'purchase_returns', 'idx_purchase_returns_party_id', 'party_id')
        self._create_index_if_missing(cursor, 'purchase_returns', 'idx_purchase_returns_company_return', 'company_id, return_no')

    def _create_cash_receipts_table(self, cursor):
        """Create cash_receipts table for cash receipt vouchers."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        voucher_no_type = self._get_voucher_no_type()
        date_type = self._get_date_type()
        account_name_type = self._get_account_name_type()
        narration_type = self._get_narration_type()
        
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS cash_receipts (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                voucher_no {voucher_no_type} NOT NULL,
                receipt_no {voucher_no_type} NOT NULL,
                voucher_date {date_type} NOT NULL,
                received_from_account_id INTEGER NOT NULL,
                cash_account_id INTEGER NOT NULL,
                party_id INTEGER,
                amount REAL NOT NULL,
                towards_acc TEXT,
                remark TEXT,
                narration {narration_type},
                payment_mode VARCHAR(50) DEFAULT 'Cash',
                reference_no TEXT,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (received_from_account_id) REFERENCES ledger_accounts (id) ON DELETE RESTRICT,
                FOREIGN KEY (cash_account_id) REFERENCES ledger_accounts (id) ON DELETE RESTRICT,
                FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE SET NULL,
                UNIQUE(company_id, voucher_no)
            )
        """)
        # Create indexes for cash_receipts
        self._create_index_if_missing(cursor, 'cash_receipts', 'idx_cash_receipts_company_id', 'company_id')
        self._create_index_if_missing(cursor, 'cash_receipts', 'idx_cash_receipts_voucher_no', 'voucher_no')
        self._create_index_if_missing(cursor, 'cash_receipts', 'idx_cash_receipts_receipt_no', 'receipt_no')
        self._create_index_if_missing(cursor, 'cash_receipts', 'idx_cash_receipts_voucher_date', 'voucher_date')
        self._create_index_if_missing(cursor, 'cash_receipts', 'idx_cash_receipts_company_voucher', 'company_id, voucher_no')
        self._create_unique_index_if_no_duplicates(
            cursor,
            'cash_receipts',
            'uq_cash_receipts_company_voucher',
            'company_id, voucher_no',
            """
                SELECT company_id, voucher_no, COUNT(*) AS duplicate_count
                FROM cash_receipts
                GROUP BY company_id, voucher_no
                HAVING COUNT(*) > 1
                LIMIT 1
            """
        )

    def _create_cash_payments_table(self, cursor):
        """Create cash_payments table for cash payment vouchers."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        voucher_no_type = self._get_voucher_no_type()
        date_type = self._get_date_type()
        account_name_type = self._get_account_name_type()
        narration_type = self._get_narration_type()
        
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS cash_payments (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                voucher_no {voucher_no_type} NOT NULL,
                payment_no {voucher_no_type} NOT NULL,
                voucher_date {date_type} NOT NULL,
                paid_to_account_id INTEGER NOT NULL,
                cash_account_id INTEGER NOT NULL,
                party_id INTEGER,
                amount REAL NOT NULL,
                towards_acc TEXT,
                remark TEXT,
                narration {narration_type},
                payment_mode VARCHAR(50) DEFAULT 'Cash',
                reference_no TEXT,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (paid_to_account_id) REFERENCES ledger_accounts (id) ON DELETE RESTRICT,
                FOREIGN KEY (cash_account_id) REFERENCES ledger_accounts (id) ON DELETE RESTRICT,
                FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE SET NULL,
                UNIQUE(company_id, voucher_no)
            )
        """)
        # Create indexes for cash_payments
        self._create_index_if_missing(cursor, 'cash_payments', 'idx_cash_payments_company_id', 'company_id')
        self._create_index_if_missing(cursor, 'cash_payments', 'idx_cash_payments_voucher_no', 'voucher_no')
        self._create_index_if_missing(cursor, 'cash_payments', 'idx_cash_payments_payment_no', 'payment_no')
        self._create_index_if_missing(cursor, 'cash_payments', 'idx_cash_payments_voucher_date', 'voucher_date')
        self._create_index_if_missing(cursor, 'cash_payments', 'idx_cash_payments_company_voucher', 'company_id, voucher_no')
        self._create_unique_index_if_no_duplicates(
            cursor,
            'cash_payments',
            'uq_cash_payments_company_voucher',
            'company_id, voucher_no',
            """
                SELECT company_id, voucher_no, COUNT(*) AS duplicate_count
                FROM cash_payments
                GROUP BY company_id, voucher_no
                HAVING COUNT(*) > 1
                LIMIT 1
            """
        )

    def _create_cash_receipt_items_table(self, cursor):
        """Create cash_receipt_items table for multi-row cash receipt vouchers."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        narration_type = self._get_narration_type()
        
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS cash_receipt_items (
                id {pk_autoinc},
                receipt_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                party_id INTEGER,
                account_kind VARCHAR(50),
                towards_voucher_no TEXT,
                amount REAL NOT NULL,
                discount REAL DEFAULT 0.0,
                narration {narration_type},
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (receipt_id) REFERENCES cash_receipts (id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES ledger_accounts (id) ON DELETE RESTRICT,
                FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE SET NULL
            )
        """)
        # Create indexes for cash_receipt_items
        self._create_index_if_missing(cursor, 'cash_receipt_items', 'idx_cash_receipt_items_receipt_id', 'receipt_id')
        self._create_index_if_missing(cursor, 'cash_receipt_items', 'idx_cash_receipt_items_account_id', 'account_id')
        self._create_index_if_missing(cursor, 'cash_receipt_items', 'idx_cash_receipt_items_party_id', 'party_id')

    def _create_cash_payment_items_table(self, cursor):
        """Create cash_payment_items table for multi-row cash payment vouchers."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        narration_type = self._get_narration_type()
        
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS cash_payment_items (
                id {pk_autoinc},
                payment_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                party_id INTEGER,
                account_kind VARCHAR(50),
                towards_voucher_no TEXT,
                amount REAL NOT NULL,
                narration {narration_type},
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (payment_id) REFERENCES cash_payments (id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES ledger_accounts (id) ON DELETE RESTRICT,
                FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE SET NULL
            )
        """)
        # Create indexes for cash_payment_items
        self._create_index_if_missing(cursor, 'cash_payment_items', 'idx_cash_payment_items_payment_id', 'payment_id')
        self._create_index_if_missing(cursor, 'cash_payment_items', 'idx_cash_payment_items_account_id', 'account_id')
        self._create_index_if_missing(cursor, 'cash_payment_items', 'idx_cash_payment_items_party_id', 'party_id')

    def _create_bank_receipts_table(self, cursor):
        """Create bank_receipts table for bank receipt vouchers."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        voucher_no_type = self._get_voucher_no_type()
        date_type = self._get_date_type()
        account_name_type = self._get_account_name_type()
        narration_type = self._get_narration_type()
        
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS bank_receipts (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                voucher_no {voucher_no_type} NOT NULL,
                voucher_date {date_type} NOT NULL,
                received_from_account_id INTEGER NOT NULL,
                bank_account_id INTEGER NOT NULL,
                party_id INTEGER,
                amount REAL NOT NULL,
                remark TEXT,
                narration {narration_type},
                reference_no TEXT,
                cheque_no TEXT,
                utr_no TEXT,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (received_from_account_id) REFERENCES ledger_accounts (id) ON DELETE RESTRICT,
                FOREIGN KEY (bank_account_id) REFERENCES bank_accounts (id) ON DELETE RESTRICT,
                FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE SET NULL
            )
        """)
        # Create indexes for bank_receipts
        self._create_index_if_missing(cursor, 'bank_receipts', 'idx_bank_receipts_company_id', 'company_id')
        self._create_index_if_missing(cursor, 'bank_receipts', 'idx_bank_receipts_voucher_no', 'voucher_no')
        self._create_index_if_missing(cursor, 'bank_receipts', 'idx_bank_receipts_voucher_date', 'voucher_date')
        self._create_index_if_missing(cursor, 'bank_receipts', 'idx_bank_receipts_bank_account', 'bank_account_id')
        self._create_index_if_missing(cursor, 'bank_receipts', 'idx_bank_receipts_company_voucher', 'company_id, voucher_no')

    def _create_bank_payments_table(self, cursor):
        """Create bank_payments table for bank payment vouchers."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        voucher_no_type = self._get_voucher_no_type()
        date_type = self._get_date_type()
        account_name_type = self._get_account_name_type()
        narration_type = self._get_narration_type()
        
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS bank_payments (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                voucher_no {voucher_no_type} NOT NULL,
                voucher_date {date_type} NOT NULL,
                paid_to_account_id INTEGER NOT NULL,
                bank_account_id INTEGER NOT NULL,
                party_id INTEGER,
                amount REAL NOT NULL,
                remark TEXT,
                narration {narration_type},
                reference_no TEXT,
                cheque_no TEXT,
                utr_no TEXT,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (paid_to_account_id) REFERENCES ledger_accounts (id) ON DELETE RESTRICT,
                FOREIGN KEY (bank_account_id) REFERENCES bank_accounts (id) ON DELETE RESTRICT,
                FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE SET NULL
            )
        """)
        # Create indexes for bank_payments
        self._create_index_if_missing(cursor, 'bank_payments', 'idx_bank_payments_company_id', 'company_id')
        self._create_index_if_missing(cursor, 'bank_payments', 'idx_bank_payments_voucher_no', 'voucher_no')
        self._create_index_if_missing(cursor, 'bank_payments', 'idx_bank_payments_voucher_date', 'voucher_date')
        self._create_index_if_missing(cursor, 'bank_payments', 'idx_bank_payments_bank_account', 'bank_account_id')
        self._create_index_if_missing(cursor, 'bank_payments', 'idx_bank_payments_company_voucher', 'company_id, voucher_no')

    def _create_journal_vouchers_table(self, cursor):
        """Create journal_vouchers table for journal entry vouchers."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        voucher_no_type = self._get_voucher_no_type()
        date_type = self._get_date_type()
        narration_type = self._get_narration_type()
        
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS journal_vouchers (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                voucher_no {voucher_no_type} NOT NULL,
                voucher_date {date_type} NOT NULL,
                remark TEXT,
                narration {narration_type},
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                UNIQUE(company_id, voucher_no)
            )
        """)
        # Create indexes for journal_vouchers
        self._create_index_if_missing(cursor, 'journal_vouchers', 'idx_journal_vouchers_company_id', 'company_id')
        self._create_index_if_missing(cursor, 'journal_vouchers', 'idx_journal_vouchers_voucher_no', 'voucher_no')
        self._create_index_if_missing(cursor, 'journal_vouchers', 'idx_journal_vouchers_voucher_date', 'voucher_date')
        self._create_index_if_missing(cursor, 'journal_vouchers', 'idx_journal_vouchers_company_voucher', 'company_id, voucher_no')
        self._create_unique_index_if_no_duplicates(
            cursor,
            'journal_vouchers',
            'uq_journal_vouchers_company_voucher',
            'company_id, voucher_no',
            """
                SELECT company_id, voucher_no, COUNT(*) AS duplicate_count
                FROM journal_vouchers
                GROUP BY company_id, voucher_no
                HAVING COUNT(*) > 1
                LIMIT 1
            """
        )

    def _create_journal_voucher_lines_table(self, cursor):
        """Create journal_voucher_lines table for journal entry line items."""
        pk_autoinc = self._get_primary_key_autoincrement()
        pk_autoinc2 = self._get_primary_key_autoincrement_2()
        
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS journal_voucher_lines (
                id {pk_autoinc},
                journal_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                debit REAL DEFAULT 0.0,
                credit REAL DEFAULT 0.0,
                narration TEXT,
                sl_no INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (journal_id) REFERENCES journal_vouchers (id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES ledger_accounts (id) ON DELETE RESTRICT
            )
        """)
        # Create indexes for journal_voucher_lines
        self._create_index_if_missing(cursor, 'journal_voucher_lines', 'idx_journal_voucher_lines_journal_id', 'journal_id')
        self._create_index_if_missing(cursor, 'journal_voucher_lines', 'idx_journal_voucher_lines_account_id', 'account_id')
        self._create_index_if_missing(cursor, 'journal_voucher_lines', 'idx_journal_voucher_lines_journal_account', 'journal_id, account_id')

    def _create_quotation_master_table(self, cursor):
        """Create quotation_master table for quotation header information."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        quotation_no_type = self._get_text_type(100)
        quotation_type_type = self._get_text_type(50)
        nature_type = self._get_text_type(50)
        gstin_type = self._get_text_type(15)
        state_type = self._get_text_type(100)
        status_type = self._get_text_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS quotation_master (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                quotation_no {quotation_no_type} NOT NULL,
                quotation_date DATE NOT NULL,
                party_id INTEGER,
                customer_name TEXT,
                mobile TEXT,
                gstin {gstin_type},
                state {state_type},
                address TEXT,
                nature {nature_type},
                quotation_type {quotation_type_type} DEFAULT 'Standard',
                status {status_type} DEFAULT 'Pending' CHECK (status IN ('Draft', 'Sent', 'Pending', 'Accepted', 'Rejected', 'Converted', 'Cancelled')),
                valid_until DATE,
                narration TEXT,
                sub_total REAL DEFAULT 0.0,
                discount_total REAL DEFAULT 0.0,
                tax_total REAL DEFAULT 0.0,
                cgst_total REAL DEFAULT 0.0,
                sgst_total REAL DEFAULT 0.0,
                igst_total REAL DEFAULT 0.0,
                cess_total REAL DEFAULT 0.0,
                freight REAL DEFAULT 0.0,
                round_off REAL DEFAULT 0.0,
                grand_total REAL DEFAULT 0.0,
                converted_sale_id INTEGER,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE SET NULL,
                FOREIGN KEY (converted_sale_id) REFERENCES sales (id) ON DELETE SET NULL,
                UNIQUE(company_id, quotation_no)
            )
        """)
        # Create indexes for quotation_master
        self._create_index_if_missing(cursor, 'quotation_master', 'idx_quotation_master_company', 'company_id')
        self._create_index_if_missing(cursor, 'quotation_master', 'idx_quotation_master_company_no', 'company_id, quotation_no')
        self._create_index_if_missing(cursor, 'quotation_master', 'idx_quotation_master_company_date', 'company_id, quotation_date')
        self._create_index_if_missing(cursor, 'quotation_master', 'idx_quotation_master_party', 'party_id')
        self._create_index_if_missing(cursor, 'quotation_master', 'idx_quotation_master_status', 'status')

    def _rebuild_quotation_items_if_obsolete_fk(self, cursor, obsolete_targets: tuple) -> bool:
        """Rebuild quotation_items when FK metadata points to obsolete tables."""
        if not self._is_sqlite() or not self._check_table_exists(cursor, "quotation_items"):
            return False

        targets = self._get_sqlite_foreign_key_targets(cursor, "quotation_items")
        if not any(target in obsolete_targets for target in targets):
            return False

        print("Rebuilding quotation_items to remove obsolete FK metadata...")
        self._drop_sqlite_table_if_exists(cursor, "quotation_items_fk_old")
        cursor.execute("PRAGMA table_info(quotation_items)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        copy_columns = [
            "id",
            "quotation_id",
            "product_id",
            "sl_no",
            "hsn",
            "tax_percent",
            "unit",
            "rate",
            "quantity",
            "gross_value",
            "discount",
            "net_value",
            "cgst",
            "sgst",
            "igst",
            "cess",
            "tax_amount",
            "grand_total",
            "created_at",
        ]
        insert_columns = [
            column for column in copy_columns if column in existing_columns
        ]

        cursor.execute("ALTER TABLE quotation_items RENAME TO quotation_items_fk_old")
        self._create_quotation_items_table(cursor)
        if insert_columns:
            quoted_columns = [
                self._quote_sqlite_identifier(column)
                for column in insert_columns
            ]
            column_sql = ", ".join(quoted_columns)
            cursor.execute(f"""
                INSERT INTO quotation_items ({column_sql})
                SELECT {column_sql}
                FROM quotation_items_fk_old
            """)
        self._drop_sqlite_table_if_exists(cursor, "quotation_items_fk_old")
        print("quotation_items FK metadata repair complete.")
        return True

    def _migrate_quotation_master_sales_fk(self, cursor):
        """Repair quotation schema FK metadata that points to obsolete tables."""
        if not self._is_sqlite():
            return

        obsolete_targets = ("sales_type_old", "quotation_master_fk_old")
        foreign_keys_were_enabled = True
        legacy_alter_table_was_enabled = False

        try:
            connection = getattr(cursor, "connection", None)
            if connection is not None and connection.in_transaction:
                connection.commit()

            self._cleanup_legacy_sales_type_sqlite_objects(cursor)

            cursor.execute("PRAGMA foreign_keys")
            foreign_keys_were_enabled = bool(cursor.fetchone()[0])
            cursor.execute("PRAGMA legacy_alter_table")
            legacy_alter_table_was_enabled = bool(cursor.fetchone()[0])

            cursor.execute("PRAGMA foreign_keys = OFF")
            cursor.execute("PRAGMA legacy_alter_table = ON")

            self._rebuild_quotation_items_if_obsolete_fk(cursor, obsolete_targets)

            if not self._check_table_exists(cursor, "quotation_master"):
                if self._check_table_exists(cursor, "quotation_master_fk_old"):
                    print("Restoring quotation_master from leftover migration table...")
                    cursor.execute(
                        "ALTER TABLE quotation_master_fk_old RENAME TO quotation_master"
                    )
                else:
                    self._restore_sqlite_rebuild_pragmas(
                        cursor,
                        foreign_keys_were_enabled,
                        legacy_alter_table_was_enabled,
                    )
                    return

            quoted_table = self._quote_sqlite_identifier("quotation_master")
            cursor.execute(f"PRAGMA foreign_key_list({quoted_table})")
            foreign_keys = cursor.fetchall()
            fk_targets = [
                row["table"] if isinstance(row, sqlite3.Row) else row[2]
                for row in foreign_keys
            ]
            must_rebuild_master = any(
                target in obsolete_targets for target in fk_targets
            )

            if must_rebuild_master:
                print("Migrating quotation_master converted_sale_id FK to sales...")
                self._drop_sqlite_table_if_exists(cursor, "quotation_master_fk_old")
                cursor.execute("PRAGMA table_info(quotation_master)")
                existing_columns = {row[1] for row in cursor.fetchall()}
                copy_columns = [
                    "id",
                    "company_id",
                    "quotation_no",
                    "quotation_date",
                    "party_id",
                    "customer_name",
                    "mobile",
                    "gstin",
                    "state",
                    "address",
                    "nature",
                    "quotation_type",
                    "status",
                    "valid_until",
                    "narration",
                    "sub_total",
                    "discount_total",
                    "tax_total",
                    "cgst_total",
                    "sgst_total",
                    "igst_total",
                    "cess_total",
                    "freight",
                    "round_off",
                    "grand_total",
                    "converted_sale_id",
                    "created_at",
                    "updated_at",
                ]
                insert_columns = [
                    column for column in copy_columns if column in existing_columns
                ]

                cursor.execute(
                    "ALTER TABLE quotation_master RENAME TO quotation_master_fk_old"
                )
                self._create_quotation_master_table(cursor)

                if insert_columns:
                    quoted_columns = [
                        self._quote_sqlite_identifier(column)
                        for column in insert_columns
                    ]
                    column_sql = ", ".join(quoted_columns)
                    cursor.execute(f"""
                        INSERT INTO quotation_master ({column_sql})
                        SELECT {column_sql}
                        FROM quotation_master_fk_old
                    """)

                self._drop_sqlite_table_if_exists(cursor, "quotation_master_fk_old")
                print("quotation_master converted_sale_id FK migration complete.")

            if self._check_table_exists(cursor, "quotation_master"):
                self._drop_sqlite_table_if_exists(cursor, "quotation_master_fk_old")
            self._create_index_if_missing(cursor, 'quotation_master', 'idx_quotation_master_company', 'company_id')
            self._create_index_if_missing(cursor, 'quotation_master', 'idx_quotation_master_company_no', 'company_id, quotation_no')
            self._create_index_if_missing(cursor, 'quotation_master', 'idx_quotation_master_company_date', 'company_id, quotation_date')
            self._create_index_if_missing(cursor, 'quotation_master', 'idx_quotation_master_party', 'party_id')
            self._create_index_if_missing(cursor, 'quotation_master', 'idx_quotation_master_status', 'status')

            broken_tables = self._get_sqlite_tables_referencing_targets(
                cursor,
                obsolete_targets,
            )
            if broken_tables:
                print(
                    "Remaining obsolete SQLite FK references after quotation "
                    f"repair: {', '.join(broken_tables)}"
                )

            self._restore_sqlite_rebuild_pragmas(
                cursor,
                foreign_keys_were_enabled,
                legacy_alter_table_was_enabled,
            )
        except sqlite3.Error as e:
            try:
                self._restore_sqlite_rebuild_pragmas(
                    cursor,
                    foreign_keys_were_enabled,
                    legacy_alter_table_was_enabled,
                )
            except sqlite3.Error:
                pass
            print(f"quotation_master sales FK migration error: {e}")

    def _create_quotations_table(self, cursor):
        """Create quotations table for informational quotation documents."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        quotation_no_type = self._get_text_type(100)
        quotation_type_type = self._get_text_type(50)
        nature_type = self._get_text_type(50)
        gstin_type = self._get_text_type(15)
        state_type = self._get_text_type(100)
        status_type = self._get_text_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS quotations (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                quotation_no {quotation_no_type} NOT NULL,
                quotation_date DATE NOT NULL,
                party_id INTEGER,
                customer_name TEXT,
                mobile TEXT,
                gstin {gstin_type},
                state {state_type},
                address TEXT,
                nature {nature_type},
                quotation_type {quotation_type_type} DEFAULT 'Standard',
                status {status_type} DEFAULT 'Pending',
                valid_until DATE,
                narration TEXT,
                sub_total REAL DEFAULT 0.0,
                discount_total REAL DEFAULT 0.0,
                tax_total REAL DEFAULT 0.0,
                cgst_total REAL DEFAULT 0.0,
                sgst_total REAL DEFAULT 0.0,
                igst_total REAL DEFAULT 0.0,
                cess_total REAL DEFAULT 0.0,
                freight REAL DEFAULT 0.0,
                round_off REAL DEFAULT 0.0,
                grand_total REAL DEFAULT 0.0,
                converted_sale_id INTEGER,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE SET NULL,
                UNIQUE(company_id, quotation_no)
            )
        """)
        self._create_index_if_missing(cursor, 'quotations', 'idx_quotations_company', 'company_id')
        self._create_index_if_missing(cursor, 'quotations', 'idx_quotations_company_no', 'company_id, quotation_no')
        self._create_index_if_missing(cursor, 'quotations', 'idx_quotations_company_date', 'company_id, quotation_date')
        self._create_index_if_missing(cursor, 'quotations', 'idx_quotations_party', 'party_id')
        self._create_index_if_missing(cursor, 'quotations', 'idx_quotations_status', 'status')

    def _create_quotation_items_table(self, cursor):
        """Create quotation_items table for quotation line items."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        hsn_type = self._get_text_type(50)
        unit_type = self._get_text_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS quotation_items (
                id {pk_autoinc},
                quotation_id INTEGER NOT NULL,
                product_id INTEGER,
                sl_no INTEGER NOT NULL,
                product_name TEXT,
                barcode TEXT,
                hsn {hsn_type},
                tax_percent REAL DEFAULT 0.0,
                unit {unit_type},
                rate REAL DEFAULT 0.0,
                quantity REAL DEFAULT 0.0,
                gross_value REAL DEFAULT 0.0,
                discount REAL DEFAULT 0.0,
                net_value REAL DEFAULT 0.0,
                cgst REAL DEFAULT 0.0,
                sgst REAL DEFAULT 0.0,
                igst REAL DEFAULT 0.0,
                cess REAL DEFAULT 0.0,
                tax_amount REAL DEFAULT 0.0,
                grand_total REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (quotation_id) REFERENCES quotations (id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE SET NULL
            )
        """)
        # Create indexes for quotation_items
        self._create_index_if_missing(cursor, 'quotation_items', 'idx_quotation_items_quotation', 'quotation_id')
        self._create_index_if_missing(cursor, 'quotation_items', 'idx_quotation_items_product', 'product_id')

    def _create_purchase_orders_table(self, cursor):
        """Create purchase_orders table (tracking only; no stock/ledger impact)."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        po_number_type = self._get_text_type(100)
        status_type = self._get_text_type(50)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                po_number {po_number_type} NOT NULL,
                date TEXT NOT NULL,
                creditor_name TEXT NOT NULL,
                grand_total REAL DEFAULT 0.0,
                status {status_type} DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                UNIQUE(company_id, po_number)
            )
        """)
        self._create_index_if_missing(
            cursor, 'purchase_orders', 'idx_purchase_orders_company', 'company_id'
        )
        self._create_index_if_missing(
            cursor, 'purchase_orders', 'idx_purchase_orders_company_date', 'company_id, date'
        )
        self._create_index_if_missing(
            cursor, 'purchase_orders', 'idx_purchase_orders_status', 'status'
        )

    def _create_purchase_order_items_table(self, cursor):
        """Create purchase_order_items line table linked to purchase_orders."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS purchase_order_items (
                id {pk_autoinc},
                po_id INTEGER NOT NULL,
                barcode TEXT,
                product_name TEXT,
                qty REAL DEFAULT 0.0,
                rate REAL DEFAULT 0.0,
                discount REAL DEFAULT 0.0,
                tax_amount REAL DEFAULT 0.0,
                net_amount REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (po_id) REFERENCES purchase_orders (id) ON DELETE CASCADE
            )
        """)
        self._create_index_if_missing(
            cursor, 'purchase_order_items', 'idx_purchase_order_items_po', 'po_id'
        )

    def _migrate_products_table(self, cursor):
        """Migrate products table to remove old global barcode uniqueness constraints (SQLite only)."""
        # Skip migration for MySQL (fresh install)
        if not self._is_sqlite():
            return
        
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
                pk_autoinc = self._get_primary_key_autoincrement()
                varchar_255 = self._get_varchar_type(255)
                varchar_100 = self._get_varchar_type(100)
                varchar_50 = self._get_varchar_type(50)
                cursor.execute(f"""
                    CREATE TABLE products (
                        id {pk_autoinc},
                        company_id INTEGER NOT NULL,
                        name {varchar_255} NOT NULL,
                        barcode {varchar_100},
                        hsn {varchar_50},
                        unit {varchar_50} DEFAULT 'pcs',
                        category {varchar_100},
                        color {varchar_50},
                        size {varchar_50},
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
                self._create_index_if_missing(cursor, 'products', 'idx_products_company_barcode', 'company_id, barcode', unique=True)
                print("Created company-specific unique index on products (company_id, barcode)")

                print("Products table migration completed successfully")

            # Ensure company-specific unique index exists on sales (company_id, invoice_number)
            self._create_index_if_missing(cursor, 'sales', 'idx_sales_company_invoice_number', 'company_id, invoice_number', unique=True)

        except Exception as e:
            print(f"Sales table migration error: {e}")
            raise

    def _migrate_stock_movements_table(self, cursor):
        """Migrate stock_movements table to add comprehensive stock tracking columns (SQLite only)."""
        if not self._is_sqlite():
            return
        
        try:
            cursor.execute("PRAGMA table_info(stock_movements)")
            columns = [row[1] for row in cursor.fetchall()]

            # Add comprehensive stock tracking columns for audit-ready stock report
            required_columns = [
                ('movement_date', 'TEXT'),
                ('voucher_type', 'TEXT'),
                ('voucher_no', 'TEXT'),
                ('narration', 'TEXT'),
                ('qty_in', 'REAL DEFAULT 0.0'),
                ('qty_out', 'REAL DEFAULT 0.0'),
                ('rate', 'REAL DEFAULT 0.0'),
                ('value_in', 'REAL DEFAULT 0.0'),
                ('value_out', 'REAL DEFAULT 0.0'),
                ('balance_qty', 'REAL DEFAULT 0.0'),
                ('balance_value', 'REAL DEFAULT 0.0')
            ]

            for field_name, field_type in required_columns:
                if field_name not in columns:
                    cursor.execute(f"ALTER TABLE stock_movements ADD COLUMN {field_name} {field_type}")
                    print(f"Added {field_name} column to stock_movements table")

            # Note: updated_at column not added via ALTER TABLE due to SQLite limitation
            # It will be added when the table is recreated in fresh install

            # Create indexes for performance with large datasets
            indexes = [
                ('idx_stock_movements_company_id', 'company_id'),
                ('idx_stock_movements_product_id', 'product_id'),
                ('idx_stock_movements_movement_date', 'movement_date'),
                ('idx_stock_movements_voucher_type', 'voucher_type'),
                ('idx_stock_movements_voucher_no', 'voucher_no'),
                ('idx_stock_movements_product_date', 'product_id, movement_date'),
                ('idx_stock_movements_company_date', 'company_id, movement_date')
            ]

            for index_name, index_cols in indexes:
                self._create_index_if_missing(cursor, 'stock_movements', index_name, index_cols)
                print(f"Created index {index_name}")

        except Exception as e:
            print(f"Stock movements table migration error: {e}")
            raise

    def _migrate_stock_draft_session_table(self, cursor):
        """Migrate stock_draft_session table to remove UNIQUE constraint for multi-bin support (SQLite only)."""
        if not self._is_sqlite():
            return

        try:
            # Check if table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_draft_session'")
            if not cursor.fetchone():
                return  # Table doesn't exist, no migration needed

            # Check if UNIQUE constraint exists by trying to insert duplicate
            # If it fails, we need to migrate
            cursor.execute("PRAGMA table_info(stock_draft_session)")
            columns = [row[1] for row in cursor.fetchall()]

            # SQLite doesn't support dropping constraints directly
            # We need to recreate the table without the UNIQUE constraint
            print("Migrating stock_draft_session table to remove UNIQUE constraint...")

            # Create new table without UNIQUE constraint
            pk_autoinc = self._get_primary_key_autoincrement()
            timestamp_default = self._get_timestamp_default()
            varchar_100 = self._get_varchar_type(100)

            # Remove only the orphaned rebuild table from an interrupted migration.
            cursor.execute("DROP TABLE IF EXISTS stock_draft_session_new")

            cursor.execute(f"""
                CREATE TABLE stock_draft_session_new (
                    id {pk_autoinc},
                    company_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    item_code {varchar_100},
                    item_name TEXT NOT NULL,
                    computer_qty REAL DEFAULT 0.0,
                    physical_qty REAL DEFAULT 0.0,
                    purchase_rate REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT {timestamp_default},
                    updated_at TIMESTAMP DEFAULT {timestamp_default},
                    FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                    FOREIGN KEY (item_id) REFERENCES products (id) ON DELETE CASCADE
                )
            """)

            # Copy data from old table to new table
            cursor.execute("""
                INSERT INTO stock_draft_session_new
                (id, company_id, item_id, item_code, item_name, computer_qty, physical_qty, purchase_rate, created_at, updated_at)
                SELECT id, company_id, item_id, item_code, item_name, computer_qty, physical_qty, purchase_rate, created_at, updated_at
                FROM stock_draft_session
            """)

            # Drop old table
            cursor.execute("DROP TABLE stock_draft_session")

            # Rename new table to old name
            cursor.execute("ALTER TABLE stock_draft_session_new RENAME TO stock_draft_session")

            # Recreate indexes
            self._create_index_if_missing(cursor, 'stock_draft_session', 'idx_stock_draft_session_company', 'company_id')
            self._create_index_if_missing(cursor, 'stock_draft_session', 'idx_stock_draft_session_company_item', 'company_id, item_id')

            print("Successfully migrated stock_draft_session table to remove UNIQUE constraint")

        except Exception as e:
            print(f"Stock draft session table migration error: {e}")
            # Don't raise - allow app to continue even if migration fails

    def _migrate_database(self, cursor):
        """Migrate existing database to add missing columns (SQLite only)."""
        # Skip migration for MySQL (fresh install)
        if not self._is_sqlite():
            return

        try:
            self._cleanup_legacy_sales_type_sqlite_objects(cursor)

            # Check if products table needs migration for barcode uniqueness
            self._migrate_products_table(cursor)

            # Migrate sales table to add missing columns (e.g. amount_received)
            self._migrate_sales_table(cursor)

            # Migrate purchases table to add missing columns (e.g. status)
            self._migrate_purchases_table(cursor)

            # Migrate return header tables to add missing columns (e.g. status)
            self._migrate_return_status_columns(cursor)

            # Migrate stock_movements table to add comprehensive stock tracking columns
            self._migrate_stock_movements_table(cursor)

            # Migrate stock_draft_session table to remove UNIQUE constraint for multi-bin support
            self._migrate_stock_draft_session_table(cursor)

            # Check if logo_path column exists in companies table
            cursor.execute("PRAGMA table_info(companies)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'logo_path' not in columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN logo_path TEXT")
                print("Added logo_path column to companies table")

            if 'signature_path' not in columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN signature_path TEXT")
                print("Added signature_path column to companies table")
            
            if 'print_phone' not in columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN print_phone BOOLEAN DEFAULT 1")
                print("Added print_phone column to companies table")
            
            if 'print_email' not in columns:
                cursor.execute("ALTER TABLE companies ADD COLUMN print_email BOOLEAN DEFAULT 1")
                print("Added print_email column to companies table")
            
            self._ensure_company_columns(cursor)
                
            # Add towards_acc column to cash_receipts table
            cursor.execute("PRAGMA table_info(cash_receipts)")
            cash_receipts_columns = [row[1] for row in cursor.fetchall()]
            if 'towards_acc' not in cash_receipts_columns:
                cursor.execute("ALTER TABLE cash_receipts ADD COLUMN towards_acc TEXT")
                print("Added towards_acc column to cash_receipts table")

            # Add total_amount and total_discount columns to cash_receipts table for multi-row support
            cursor.execute("PRAGMA table_info(cash_receipts)")
            cash_receipts_columns = [row[1] for row in cursor.fetchall()]
            if 'total_amount' not in cash_receipts_columns:
                cursor.execute("ALTER TABLE cash_receipts ADD COLUMN total_amount REAL DEFAULT 0.0")
                print("Added total_amount column to cash_receipts table")
            if 'total_discount' not in cash_receipts_columns:
                cursor.execute("ALTER TABLE cash_receipts ADD COLUMN total_discount REAL DEFAULT 0.0")
                print("Added total_discount column to cash_receipts table")

            # Add towards_acc column to cash_payments table
            cursor.execute("PRAGMA table_info(cash_payments)")
            cash_payments_columns = [row[1] for row in cursor.fetchall()]
            if 'towards_acc' not in cash_payments_columns:
                cursor.execute("ALTER TABLE cash_payments ADD COLUMN towards_acc TEXT")
                print("Added towards_acc column to cash_payments table")

            # Add cost columns to sales_items table for historical profit calculation
            cursor.execute("PRAGMA table_info(sales_items)")
            sales_items_columns = [row[1] for row in cursor.fetchall()]
            if 'cost_price' not in sales_items_columns:
                cursor.execute("ALTER TABLE sales_items ADD COLUMN cost_price REAL DEFAULT 0.0")
                print("Added cost_price column to sales_items table")
            if 'cost_value' not in sales_items_columns:
                cursor.execute("ALTER TABLE sales_items ADD COLUMN cost_value REAL DEFAULT 0.0")
                print("Added cost_value column to sales_items table")

            # Add total_amount column to cash_payments table for multi-row support
            cursor.execute("PRAGMA table_info(cash_payments)")
            cash_payments_columns = [row[1] for row in cursor.fetchall()]
            if 'total_amount' not in cash_payments_columns:
                cursor.execute("ALTER TABLE cash_payments ADD COLUMN total_amount REAL DEFAULT 0.0")
                print("Added total_amount column to cash_payments table")

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

            # Check if state column exists in parties table
            cursor.execute("PRAGMA table_info(parties)")
            party_columns = [row[1] for row in cursor.fetchall()]

            if 'state' not in party_columns:
                cursor.execute("ALTER TABLE parties ADD COLUMN state TEXT")
                print("Added state column to parties table")
                
                # Add company-specific unique constraint for barcode
                self._create_index_if_missing(cursor, 'products', 'idx_products_company_barcode', 'company_id, barcode', unique=True)
                print("Added company-specific unique index on products (company_id, barcode)")
                
            # Check if accounts table needs company_id column
            cursor.execute("PRAGMA table_info(accounts)")
            account_columns = [row[1] for row in cursor.fetchall()]
            
            if 'company_id' not in account_columns:
                cursor.execute("ALTER TABLE accounts ADD COLUMN company_id INTEGER NOT NULL DEFAULT 1")
                # Add unique constraint for company_id, name
                self._create_index_if_missing(cursor, 'accounts', 'idx_accounts_company_name', 'company_id, name', unique=True)
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
                self._create_index_if_missing(cursor, 'categories', 'idx_categories_company_name', 'company_id, name', unique=True)
                print("Added company_id column to categories table")

            # Migrate sales_returns.party_id to allow NULL (Cash returns need no party)
            self._migrate_sales_returns_party_nullable(cursor)

            # Create indexes for purchase_returns table
            self._create_purchase_return_indexes(cursor)

            # Migrate sales_items table to add split GST columns
            self._migrate_sales_items_split_gst(cursor)

            # Migrate purchase_items table to add split GST columns
            self._migrate_purchase_items_split_gst(cursor)

            # Migrate sales_return_items table to add split GST amount columns
            self._migrate_sales_return_items_split_gst_amounts(cursor)

            # Migrate purchase_return_items table to add split GST amount columns
            self._migrate_purchase_return_items_split_gst_amounts(cursor)

            # Migrate return items tables to add missing unit column
            self._migrate_return_items_add_unit(cursor)

            # Create performance indexes for faster bill navigation and loading
            self._create_performance_indexes(cursor)

            # Add ledger_account_id to parties table for party-ledger linkage
            self._migrate_parties_ledger_account_id(cursor)
            self._migrate_parties_party_code(cursor)

            # Link bank master rows to individual ledger accounts
            self._migrate_bank_accounts_ledger_account_id(cursor)

            self._migrate_quotation_tables(cursor)
            self._migrate_quotation_master_sales_fk(cursor)

            self._migrate_purchase_order_tables(cursor)

            self._migrate_pdc_table(cursor)

            self._migrate_credit_debit_notes_table(cursor)

            # Add compound ledger indexes for performance
            self._create_ledger_compound_indexes(cursor)

            # Normalize legacy system account flags so UI filters can hide them.
            self._migrate_system_account_flags(cursor)

            # Party opening balance is posted as OB-PARTY vouchers; clear duplicate column values.
            self._migrate_party_opening_balance_double_count(cursor)

        except Exception as e:
            print(f"Database migration error: {e}")

    def _migrate_parties_ledger_account_id(self, cursor):
        """Add ledger_account_id column to parties table if missing (SQLite only)."""
        if not self._is_sqlite():
            return
        try:
            cursor.execute("PRAGMA table_info(parties)")
            cols = [row[1] for row in cursor.fetchall()]
            if 'ledger_account_id' not in cols:
                cursor.execute("ALTER TABLE parties ADD COLUMN ledger_account_id INTEGER")
        except Exception as e:
            print(f"Note: parties ledger_account_id migration: {e}")

    def _migrate_parties_party_code(self, cursor):
        """Add party_code column and index to parties if missing."""
        if not self._is_sqlite():
            return
        try:
            cursor.execute("PRAGMA table_info(parties)")
            cols = [row[1] for row in cursor.fetchall()]
            if 'party_code' not in cols:
                cursor.execute("ALTER TABLE parties ADD COLUMN party_code TEXT")
            self._create_index_if_missing(cursor, 'parties', 'idx_parties_company_code', 'company_id, party_code')
        except Exception as e:
            print(f"Note: parties party_code migration: {e}")

    def _migrate_bank_accounts_ledger_account_id(self, cursor):
        """Add ledger_account_id column to bank_accounts for per-bank ledger linkage."""
        try:
            if self._is_sqlite():
                cursor.execute("PRAGMA table_info(bank_accounts)")
                cols = [row[1] for row in cursor.fetchall()]
                if 'ledger_account_id' not in cols:
                    cursor.execute("ALTER TABLE bank_accounts ADD COLUMN ledger_account_id INTEGER")
            else:
                cursor.execute(
                    "ALTER TABLE bank_accounts ADD COLUMN IF NOT EXISTS ledger_account_id INTEGER"
                )
            self._create_index_if_missing(
                cursor, 'bank_accounts', 'idx_bank_accounts_ledger_account_id', 'ledger_account_id'
            )
        except Exception as e:
            print(f"Note: bank_accounts ledger_account_id migration: {e}")

    def _migrate_party_opening_balance_double_count(self, cursor):
        """Clear ledger_accounts.opening_balance when an OB-PARTY voucher already exists."""
        try:
            cursor.execute(
                """
                UPDATE ledger_accounts
                SET opening_balance = 0.0
                WHERE account_type = 'party'
                  AND COALESCE(opening_balance, 0) <> 0
                  AND id IN (
                      SELECT account_id
                      FROM ledger_entries
                      WHERE voucher_type = 'Opening Balance'
                        AND voucher_no LIKE 'OB-PARTY-%'
                  )
                """
            )
            repaired = cursor.rowcount if cursor.rowcount is not None else 0
            if repaired:
                print(f"Repaired {repaired} party ledger account(s) with duplicate opening balance")
        except Exception as e:
            print(f"Note: party opening balance repair migration: {e}")

    def _create_ledger_compound_indexes(self, cursor):
        """Create compound indexes on ledger tables for performance."""
        self._create_index_if_missing(cursor, 'ledger_accounts', 'idx_la_company_name', 'company_id, account_name')
        self._create_index_if_missing(cursor, 'ledger_accounts', 'idx_la_company_type', 'company_id, account_type')
        self._create_index_if_missing(cursor, 'ledger_entries', 'idx_le_company_account_date', 'company_id, account_id, voucher_date')
        self._create_index_if_missing(cursor, 'ledger_entries', 'idx_le_company_vtype_vid', 'company_id, voucher_type, voucher_id')
        self._create_index_if_missing(cursor, 'ledger_entries', 'idx_le_company_vno', 'company_id, voucher_no')

    def _migrate_system_account_flags(self, cursor):
        """Mark known default ledger accounts as system accounts in legacy data."""
        system_account_names = (
            'Cash Account',
            'Bank Account',
            'Sundry Debtors',
            'Sundry Creditors',
            'Stock Account',
            'Sales Account',
            'Purchase Account',
            'Sales Return Account',
            'Purchase Return Account',
            'Output CGST',
            'Output SGST',
            'Output IGST',
            'Output CESS',
            'Input CGST',
            'Input SGST',
            'Input IGST',
            'Input CESS',
            'GST Payable',
            'GST Receivable',
            'GST Paid',
            'GST Collected',
            'CESS Paid',
            'CESS Collected',
            'Round Off',
            'Profit and Loss Account',
            'Opening Stock',
            'Closing Stock',
            'Capital Account',
            'Drawings',
            'Suspense Account',
            'Stock Adjustment Loss',
            'Stock Adjustment Gain',
        )
        try:
            ph = self._get_placeholder()
            query = f"""
                UPDATE ledger_accounts
                SET is_system = 1
                WHERE account_name = {ph}
                  AND COALESCE(is_system, 0) <> 1
            """
            for account_name in system_account_names:
                cursor.execute(query, (account_name,))
        except Exception as e:
            print(f"Note: system account flag migration skipped: {e}")

    def _migrate_quotation_tables(self, cursor):
        """Create quotation tables if missing (for existing databases)."""
        if not self._is_sqlite():
            return
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='quotations'")
            if not cursor.fetchone():
                self._create_quotations_table(cursor)
                print("Created quotations table")

            # Check if quotation_master table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='quotation_master'")
            if not cursor.fetchone():
                # Table doesn't exist, create it
                self._create_quotation_master_table(cursor)
                self._create_quotation_items_table(cursor)
                print("Created quotation_master and quotation_items tables")
        except Exception as e:
            print(f"Note: quotation tables migration: {e}")

    def _migrate_purchase_order_tables(self, cursor):
        """Create purchase order tables if missing (for existing databases)."""
        if not self._is_sqlite():
            return
        try:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='purchase_orders'"
            )
            if not cursor.fetchone():
                self._create_purchase_orders_table(cursor)
                self._create_purchase_order_items_table(cursor)
                print("Created purchase_orders and purchase_order_items tables")
        except Exception as e:
            print(f"Note: purchase order tables migration: {e}")

    def _create_pdc_register_table(self, cursor):
        """Create pdc_register table for Post Dated Cheque management."""
        pk_autoinc = self._get_primary_key_autoincrement()
        timestamp_default = self._get_timestamp_default()
        # Use VARCHAR for indexed/searchable fields, TEXT for large fields
        transaction_type_type = self._get_text_type(20)
        account_type_type = self._get_text_type(50)
        cheque_number_type = self._get_text_type(50)
        bank_name_type = self._get_text_type(100)
        branch_name_type = self._get_text_type(100)
        status_type = self._get_text_type(20)
        voucher_type_type = self._get_text_type(50)
        
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS pdc_register (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                transaction_type {transaction_type_type} NOT NULL CHECK (transaction_type IN ('RECEIPT', 'ISSUE')),
                account_type {account_type_type} NOT NULL CHECK (account_type IN ('General', 'Sundry Debtors', 'Sundry Creditors', 'Bank')),
                party_id INTEGER,
                account_name {bank_name_type},
                bank_account_id INTEGER,
                bank_name {bank_name_type},
                received_issued_date DATE NOT NULL,
                cheque_date DATE NOT NULL,
                cheque_number {cheque_number_type} NOT NULL,
                cheque_bank_name {bank_name_type},
                branch_name {branch_name_type},
                amount REAL DEFAULT 0.0,
                narration TEXT,
                status {status_type} DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'CLEARED', 'BOUNCED', 'CANCELLED')),
                linked_voucher_id INTEGER,
                linked_voucher_type {voucher_type_type},
                cleared_date DATE,
                bounced_date DATE,
                cancelled_date DATE,
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE SET NULL
            )
        """)
        
        # Create indexes for performance
        self._create_index_if_missing(cursor, 'pdc_register', 'idx_pdc_company', 'company_id')
        self._create_index_if_missing(cursor, 'pdc_register', 'idx_pdc_type', 'transaction_type')
        self._create_index_if_missing(cursor, 'pdc_register', 'idx_pdc_cheque_date', 'cheque_date')
        self._create_index_if_missing(cursor, 'pdc_register', 'idx_pdc_status', 'status')
        self._create_index_if_missing(cursor, 'pdc_register', 'idx_pdc_party', 'party_id')
        self._create_index_if_missing(cursor, 'pdc_register', 'idx_pdc_bank_account', 'bank_account_id')
        self._create_index_if_missing(cursor, 'pdc_register', 'idx_pdc_cheque_number', 'cheque_number')

    def _migrate_pdc_table(self, cursor):
        """Create pdc_register table if missing (for existing databases)."""
        if not self._is_sqlite():
            return
        try:
            # Check if pdc_register table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pdc_register'")
            if not cursor.fetchone():
                # Table doesn't exist, create it
                self._create_pdc_register_table(cursor)
                print("Created pdc_register table")
        except Exception as e:
            print(f"Note: pdc table migration: {e}")

    def _create_credit_debit_notes_table(self, cursor):
        """Create credit_debit_notes table with indexes."""
        pk_autoinc = "INTEGER PRIMARY KEY AUTOINCREMENT" if self._is_sqlite() else "INT AUTO_INCREMENT PRIMARY KEY"
        transaction_type_type = "TEXT" if self._is_sqlite() else "VARCHAR(20)"
        party_type_type = "TEXT" if self._is_sqlite() else "VARCHAR(20)"
        status_type = "TEXT" if self._is_sqlite() else "VARCHAR(20)"
        timestamp_default = "CURRENT_TIMESTAMP" if self._is_sqlite() else "CURRENT_TIMESTAMP"
        bank_name_type = "TEXT" if self._is_sqlite() else "VARCHAR(255)"
        cheque_number_type = "TEXT" if self._is_sqlite() else "VARCHAR(100)"
        branch_name_type = "TEXT" if self._is_sqlite() else "VARCHAR(255)"

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS credit_debit_notes (
                id {pk_autoinc},
                company_id INTEGER NOT NULL,
                serial_no {bank_name_type} NOT NULL,
                note_type {transaction_type_type} NOT NULL CHECK (note_type IN ('Credit Note', 'Debit Note')),
                note_date DATE NOT NULL,
                party_type {party_type_type} NOT NULL CHECK (party_type IN ('Debtor', 'Creditor')),
                party_id INTEGER,
                party_name {bank_name_type},
                reason {bank_name_type} NOT NULL,
                goods_description TEXT,
                quantity REAL DEFAULT 0.0,
                related_bill_no {cheque_number_type},
                related_bill_date DATE,
                return_document_details TEXT,
                amount REAL DEFAULT 0.0,
                related_tax REAL DEFAULT 0.0,
                total REAL DEFAULT 0.0,
                remarks TEXT,
                status {status_type} DEFAULT 'Saved' CHECK (status IN ('Saved', 'Cancelled')),
                created_at TIMESTAMP DEFAULT {timestamp_default},
                updated_at TIMESTAMP DEFAULT {timestamp_default},
                FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                FOREIGN KEY (party_id) REFERENCES parties (id) ON DELETE SET NULL
            )
        """)

        # Create indexes for performance
        self._create_index_if_missing(cursor, 'credit_debit_notes', 'idx_cdn_company', 'company_id')
        self._create_index_if_missing(cursor, 'credit_debit_notes', 'idx_cdn_serial', 'serial_no')
        self._create_index_if_missing(cursor, 'credit_debit_notes', 'idx_cdn_date', 'note_date')
        self._create_index_if_missing(cursor, 'credit_debit_notes', 'idx_cdn_party', 'party_id')
        self._create_index_if_missing(cursor, 'credit_debit_notes', 'idx_cdn_type', 'note_type')

    def _migrate_credit_debit_notes_table(self, cursor):
        """Create credit_debit_notes table if missing (for existing databases)."""
        if not self._is_sqlite():
            return
        try:
            # Check if credit_debit_notes table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='credit_debit_notes'")
            if not cursor.fetchone():
                # Table doesn't exist, create it
                self._create_credit_debit_notes_table(cursor)
                print("Created credit_debit_notes table")
        except Exception as e:
            print(f"Note: credit_debit_notes table migration: {e}")

    def _migrate_sales_items_split_gst(self, cursor):
        """Add split GST columns to sales_items table (SQLite only)."""
        if not self._is_sqlite():
            return
        try:
            cursor.execute("PRAGMA table_info(sales_items)")
            columns = [row[1] for row in cursor.fetchall()]
            
            required_fields = [
                ('cgst', 'REAL DEFAULT 0.0'),
                ('sgst', 'REAL DEFAULT 0.0'),
                ('igst', 'REAL DEFAULT 0.0'),
                ('cess', 'REAL DEFAULT 0.0'),
                ('cgst_amount', 'REAL DEFAULT 0.0'),
                ('sgst_amount', 'REAL DEFAULT 0.0'),
                ('igst_amount', 'REAL DEFAULT 0.0'),
                ('cess_amount', 'REAL DEFAULT 0.0'),
            ]
            
            for field_name, field_type in required_fields:
                if field_name not in columns:
                    cursor.execute(f"ALTER TABLE sales_items ADD COLUMN {field_name} {field_type}")
                    print(f"Added {field_name} column to sales_items table")
                    
        except Exception as e:
            print(f"Sales items split GST migration error: {e}")

    def _migrate_purchase_items_split_gst(self, cursor):
        """Add split GST columns to purchase_items table (SQLite only)."""
        if not self._is_sqlite():
            return
        try:
            cursor.execute("PRAGMA table_info(purchase_items)")
            columns = [row[1] for row in cursor.fetchall()]
            
            required_fields = [
                ('cgst', 'REAL DEFAULT 0.0'),
                ('sgst', 'REAL DEFAULT 0.0'),
                ('igst', 'REAL DEFAULT 0.0'),
                ('cess', 'REAL DEFAULT 0.0'),
                ('cgst_amount', 'REAL DEFAULT 0.0'),
                ('sgst_amount', 'REAL DEFAULT 0.0'),
                ('igst_amount', 'REAL DEFAULT 0.0'),
                ('cess_amount', 'REAL DEFAULT 0.0'),
            ]
            
            for field_name, field_type in required_fields:
                if field_name not in columns:
                    cursor.execute(f"ALTER TABLE purchase_items ADD COLUMN {field_name} {field_type}")
                    print(f"Added {field_name} column to purchase_items table")
                    
        except Exception as e:
            print(f"Purchase items split GST migration error: {e}")

    def _migrate_sales_return_items_split_gst_amounts(self, cursor):
        """Add split GST amount columns to sales_return_items table (SQLite only)."""
        if not self._is_sqlite():
            return
        try:
            cursor.execute("PRAGMA table_info(sales_return_items)")
            columns = [row[1] for row in cursor.fetchall()]
            
            required_fields = [
                ('cgst_amount', 'REAL DEFAULT 0.0'),
                ('sgst_amount', 'REAL DEFAULT 0.0'),
                ('igst_amount', 'REAL DEFAULT 0.0'),
                ('cess_amount', 'REAL DEFAULT 0.0'),
            ]
            
            for field_name, field_type in required_fields:
                if field_name not in columns:
                    cursor.execute(f"ALTER TABLE sales_return_items ADD COLUMN {field_name} {field_type}")
                    print(f"Added {field_name} column to sales_return_items table")
                    
        except Exception as e:
            print(f"Sales return items split GST amount migration error: {e}")

    def _migrate_purchase_return_items_split_gst_amounts(self, cursor):
        """Add split GST amount columns to purchase_return_items table (SQLite only)."""
        if not self._is_sqlite():
            return
        try:
            cursor.execute("PRAGMA table_info(purchase_return_items)")
            columns = [row[1] for row in cursor.fetchall()]
            
            required_fields = [
                ('cgst_amount', 'REAL DEFAULT 0.0'),
                ('sgst_amount', 'REAL DEFAULT 0.0'),
                ('igst_amount', 'REAL DEFAULT 0.0'),
                ('cess_amount', 'REAL DEFAULT 0.0'),
            ]
            
            for field_name, field_type in required_fields:
                if field_name not in columns:
                    cursor.execute(f"ALTER TABLE purchase_return_items ADD COLUMN {field_name} {field_type}")
                    print(f"Added {field_name} column to purchase_return_items table")
                    
        except Exception as e:
            print(f"Purchase return items split GST amount migration error: {e}")

    def _migrate_return_items_add_unit(self, cursor):
        """Add unit column to sales_return_items and purchase_return_items tables (SQLite only).

        This column was missing from the original schema, causing INSERT errors.
        """
        if not self._is_sqlite():
            return
        try:
            # Check and add unit column to sales_return_items
            cursor.execute("PRAGMA table_info(sales_return_items)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'unit' not in columns:
                cursor.execute("ALTER TABLE sales_return_items ADD COLUMN unit TEXT")
                print("Added unit column to sales_return_items table")

            # Check and add unit column to purchase_return_items
            cursor.execute("PRAGMA table_info(purchase_return_items)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'unit' not in columns:
                cursor.execute("ALTER TABLE purchase_return_items ADD COLUMN unit TEXT")
                print("Added unit column to purchase_return_items table")
        except Exception as e:
            print(f"Return items unit column migration error: {e}")

    def _migrate_sales_returns_party_nullable(self, cursor):
        """Recreate sales_returns table so party_id allows NULL (needed for Cash returns) (SQLite only)."""
        if not self._is_sqlite():
            return
        try:
            cursor.execute("PRAGMA table_info(sales_returns)")
            cols = cursor.fetchall()
            if not cols:
                return  # table doesn't exist yet, schema creation handles it
            # Check if party_id is currently NOT NULL
            party_col = next((c for c in cols if c[1] == 'party_id'), None)
            if party_col is None:
                return
            # col[3] is the 'notnull' flag in SQLite PRAGMA table_info
            if party_col[3] == 0:
                return  # already nullable, nothing to do
            print("Migrating sales_returns.party_id to allow NULL...")
            cursor.execute("ALTER TABLE sales_returns RENAME TO sales_returns_old")
            pk_autoinc = self._get_primary_key_autoincrement()
            timestamp_default = self._get_timestamp_default()
            cursor.execute(f"""
                CREATE TABLE sales_returns (
                    id {pk_autoinc},
                    company_id INTEGER NOT NULL,
                    return_no TEXT NOT NULL,
                    return_date DATE NOT NULL,
                    original_bill_id INTEGER,
                    original_bill_no TEXT,
                    party_id INTEGER,
                    return_type TEXT DEFAULT 'Cash' CHECK (return_type IN ('Cash', 'Credit')),
                    nature TEXT,
                    narration TEXT,
                    sub_total REAL DEFAULT 0.0,
                    discount_total REAL DEFAULT 0.0,
                    tax_total REAL DEFAULT 0.0,
                    round_off REAL DEFAULT 0.0,
                    grand_total REAL DEFAULT 0.0,
                    amount_refunded_or_adjusted REAL DEFAULT 0.0,
                    balance_adjustment REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'Active',
                    created_at TIMESTAMP DEFAULT {timestamp_default},
                    updated_at TIMESTAMP DEFAULT {timestamp_default},
                    FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
                    UNIQUE(company_id, return_no)
                )
            """)
            cursor.execute("""
                INSERT INTO sales_returns
                SELECT id, company_id, return_no, return_date, original_bill_id, original_bill_no,
                       party_id, return_type, nature, narration, sub_total, discount_total,
                       tax_total, round_off, grand_total, amount_refunded_or_adjusted,
                       balance_adjustment, COALESCE(status, 'Active'), created_at, updated_at
                FROM sales_returns_old
            """)
            cursor.execute("DROP TABLE sales_returns_old")
            self._create_index_if_missing(cursor, 'sales_returns', 'idx_sales_returns_company_return_no', 'company_id, return_no')
            self._create_index_if_missing(cursor, 'sales_returns', 'idx_sales_returns_company_return_date', 'company_id, return_date')
            # SQLite auto-updates FK references in child tables to point to the renamed table.
            # Recreate sales_return_items so its FK points back to new sales_returns.
            cursor.execute("ALTER TABLE sales_return_items RENAME TO sales_return_items_fk_old")
            pk_autoinc2 = self._get_primary_key_autoincrement()
            ts2 = self._get_timestamp_default()
            cursor.execute(f"""
                CREATE TABLE sales_return_items (
                    id {pk_autoinc2},
                    sales_return_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    sl_no INTEGER NOT NULL,
                    hsn TEXT,
                    cgst REAL DEFAULT 0.0,
                    sgst REAL DEFAULT 0.0,
                    igst REAL DEFAULT 0.0,
                    cess REAL DEFAULT 0.0,
                    tax_percent REAL DEFAULT 0.0,
                    rate REAL DEFAULT 0.0,
                    quantity REAL DEFAULT 0.0,
                    gross_value REAL DEFAULT 0.0,
                    discount REAL DEFAULT 0.0,
                    net_value REAL DEFAULT 0.0,
                    tax_amount REAL DEFAULT 0.0,
                    grand_total REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT {ts2},
                    FOREIGN KEY (sales_return_id) REFERENCES sales_returns (id) ON DELETE CASCADE,
                    FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
                )
            """)
            cursor.execute("INSERT INTO sales_return_items SELECT * FROM sales_return_items_fk_old")
            cursor.execute("DROP TABLE sales_return_items_fk_old")
            self._create_index_if_missing(cursor, 'sales_return_items', 'idx_sales_return_items_product_id', 'product_id')
            print("sales_returns.party_id migration complete.")
        except Exception as e:
            print(f"sales_returns party_id migration error: {e}")

    def _create_performance_indexes(self, cursor):
        """Create performance-critical indexes for faster bill operations.

        These indexes significantly speed up:
        - Bill navigation (previous/next)
        - Bill loading (sale items lookup)
        - Bill deletion (cascade operations)
        - Stock report generation
        """
        indexes = [
            # Sales items - critical for loading bills quickly
            ("idx_sales_items_sale_id", "sales_items", "sale_id"),
            ("idx_sales_items_product_id", "sales_items", "product_id"),

            # Purchase items - critical for loading purchase bills
            ("idx_purchase_items_purchase_id", "purchase_items", "purchase_id"),
            ("idx_purchase_items_product_id", "purchase_items", "product_id"),

            # Sales navigation - for fast previous/next bill lookups
            ("idx_sales_company_id", "sales", "company_id"),
            ("idx_sales_company_id_id", "sales", "company_id, id"),

            # Purchase navigation
            ("idx_purchases_company_id", "purchases", "company_id"),
            ("idx_purchases_company_id_id", "purchases", "company_id, id"),

            # Stock movements - for faster stock balance calculations
            ("idx_stock_movements_company_product", "stock_movements", "company_id, product_id"),
            ("idx_stock_movements_reference", "stock_movements", "reference_type, reference_id"),

            # Sales returns
            ("idx_sales_return_items_return_id", "sales_return_items", "sales_return_id"),

            # Purchase returns
            ("idx_purchase_return_items_return_id", "purchase_return_items", "purchase_return_id"),
        ]

        created_count = 0
        for index_name, table, columns in indexes:
            try:
                self._create_index_if_missing(cursor, table, index_name, columns)
                created_count += 1
            except Exception as e:
                print(f"Note: Index {index_name} creation skipped: {e}")

        if created_count > 0:
            print(f"Created {created_count} performance indexes")

    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results."""
        try:
            conn = self.connect()
            with closing(conn.cursor()) as cursor:
                cursor.execute(query, params)

                # Handle different cursor result formats
                if self.db_type == "sqlite":
                    results = [dict(row) for row in cursor.fetchall()]
                else:
                    # MySQL: convert to dict using cursor.description
                    columns = [column[0] for column in cursor.description]
                    results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            return results
        except sqlite3.Error as e:
            print(f"Database Error: {e}")
            print(f"Query execution error: {e}")
            raise
        except Exception as e:
            print(f"Query execution error: {e}")
            return []
        finally:
            self.disconnect()
    
    def execute_update(self, query: str, params: tuple = ()) -> bool:
        """Execute an INSERT, UPDATE, or DELETE query."""
        conn = None
        try:
            conn = self.connect()
            with closing(conn.cursor()) as cursor:
                cursor.execute(query, params)
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Database Error: {e}")
            try:
                if conn:
                    conn.rollback()
            except sqlite3.Error as rollback_error:
                print(f"Database Error: {rollback_error}")
                print(f"Rollback error: {rollback_error}")
            print(f"Update execution error: {e}")
            raise  # Re-raise to allow caller to handle the error
        except Exception as e:
            print(f"Update execution error: {e}")
            raise  # Re-raise to allow caller to handle the error
        finally:
            self.disconnect()

    def get_settings(self, company_id: int) -> Dict[str, str]:
        """Return company settings with hardcoded defaults overlaid first."""
        try:
            from bizora_core.settings_logic import get_settings
            return get_settings(self, company_id)
        except Exception as e:
            print(f"Company settings check error: {e}")
            return {}

    def save_setting(self, company_id: int, key: str, value: Any) -> bool:
        """Persist one company setting without changing global defaults."""
        try:
            from bizora_core.settings_logic import save_setting
            return save_setting(self, company_id, key, value)
        except Exception as e:
            print(f"Company setting save error: {e}")
            return False

    def is_cash_tender_enabled(self, company_id: Optional[int] = None) -> bool:
        """Return True when Cash Tender tracking is enabled for a company."""
        try:
            from bizora_core.settings_logic import resolve_company_id
            resolved_company_id = resolve_company_id(company_id)
            if not resolved_company_id:
                return True
            settings = self.get_settings(resolved_company_id)
            return settings.get("enable_cash_tender", "1") == "1"
        except Exception as e:
            print(f"Cash Tender setting check error: {e}")
            return True

    def set_cash_tender_enabled(
        self,
        enabled: bool,
        company_id: Optional[int] = None,
    ) -> bool:
        """Persist whether Cash Tender opens for the selected company."""
        try:
            from bizora_core.settings_logic import resolve_company_id
            resolved_company_id = resolve_company_id(company_id)
            if not resolved_company_id:
                return False
            setting_value = "1" if enabled else "0"
            return self.save_setting(
                resolved_company_id,
                "enable_cash_tender",
                setting_value,
            )
        except Exception as e:
            print(f"Cash Tender setting save error: {e}")
            return False

    def save_cash_tender(
        self,
        bill_no: str,
        bill_amount: float,
        cash_received: float,
        balance_returned: float,
        payment_mode: str = "Cash",
    ) -> bool:
        """Store Cash Tender history without posting to ledgers or trial balance."""
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO cash_tender_history (
                bill_no, bill_amount, cash_received, balance_returned,
                payment_mode
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
        """
        params = (
            bill_no,
            bill_amount,
            cash_received,
            balance_returned,
            (payment_mode or "Cash").strip() or "Cash",
        )
        try:
            return self.execute_update(query, params)
        except Exception as e:
            print(f"Cash Tender save error: {e}")
            return False

    def get_cash_tender_history(self) -> List[Dict[str, Any]]:
        """Return Cash Tender history rows for the read-only audit view."""
        ph = self._get_placeholder()
        query = f"""
            SELECT bill_no, bill_amount, cash_received,
                   balance_returned, payment_mode, created_at
            FROM cash_tender_history
            WHERE id >= {ph}
            ORDER BY id DESC
        """
        try:
            return self.execute_query(query, (0,))
        except Exception as e:
            print(f"Cash Tender history load error: {e}")
            return []
    
    def backup_database(self, backup_path: Optional[str] = None) -> bool:
        """Create a backup of the database (SQLite only)."""
        # Backup is only supported for SQLite
        if self.db_type != "sqlite":
            print("Backup is only supported for SQLite backend")
            return False
        
        if backup_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Anchor the backup folder to BASE_DIR (never the working
            # directory) and strip any directory/drive component that may
            # ever appear in the configured backup dir name.
            backup_dir = os.path.join(
                BASE_DIR, os.path.basename(DATABASE_BACKUP_DIR) or "backups"
            )
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, f"backup_{timestamp}.db")
        
        try:
            with closing(sqlite3.connect(self.db_path, timeout=30.0)) as source:
                source.execute("PRAGMA journal_mode = DELETE;")
                with closing(sqlite3.connect(backup_path, timeout=30.0)) as backup:
                    # Keep journal handling consistent with the main connection so no
                    # -wal/-shm sidecar files are ever produced by backup runs.
                    backup.execute("PRAGMA journal_mode = DELETE;")
                    source.backup(backup)
            print(f"Database backed up to: {backup_path}")
            return True
        except Exception as e:
            print(f"Backup error: {e}")
            return False
    
    def company_name_exists(self, business_name: str) -> bool:
        """Check if a company name already exists (case-insensitive, ignoring leading/trailing spaces)."""
        normalized_name = business_name.strip().lower()
        ph = self._get_placeholder()
        query = f"SELECT COUNT(*) as count FROM companies WHERE LOWER(TRIM(business_name)) = {ph}"
        result = self.execute_query(query, (normalized_name,))
        return result[0]['count'] > 0 if result else False
    
    def create_company(self, company_data: Dict[str, Any]) -> bool:
        """Create a new company record and optionally set it as active."""
        conn = None
        try:
            conn = self.connect()
            cursor = conn.cursor()

            visibility = (company_data.get("visibility") or "normal").strip().lower()
            if visibility not in ("normal", "secret"):
                visibility = "normal"
            activate_on_create = company_data.get("activate_on_create")
            if activate_on_create is None:
                activate_on_create = visibility == "normal"

            if activate_on_create:
                cursor.execute("UPDATE companies SET is_active = 0")

            placeholder = self._get_placeholder()
            self._ensure_company_print_columns(cursor)
            self._ensure_company_columns(cursor)
            is_active_value = 1 if activate_on_create else 0
            has_visibility = self._check_column_exists(cursor, "companies", "visibility")
            visibility_clause = f", visibility" if has_visibility else ""
            visibility_value = f", {placeholder}" if has_visibility else ""
            query = f"""
                INSERT INTO companies (
                    business_name, phone_number, gstin, gst_type, email, business_type,
                    business_category, address, state, pincode, logo_path, signature_path,
                    print_phone, print_gstin, print_email, print_business_type, print_business_category,
                    print_address, print_state, print_pincode, print_logo, print_signature,
                    financial_year, is_active{visibility_clause}
                ) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}{visibility_value})
            """
            params = (
                company_data.get('business_name'),
                company_data.get('phone_number'),
                company_data.get('gstin'),
                company_data.get('gst_type', 'Regular') or 'Regular',
                company_data.get('email'),
                company_data.get('business_type'),
                company_data.get('business_category'),
                company_data.get('address'),
                company_data.get('state'),
                company_data.get('pincode'),
                company_data.get('logo_path'),
                company_data.get('signature_path'),
                int(company_data.get('print_phone', 1)),
                int(company_data.get('print_gstin', 1)),
                int(company_data.get('print_email', 1)),
                int(company_data.get('print_business_type', 1)),
                int(company_data.get('print_business_category', 1)),
                int(company_data.get('print_address', 1)),
                int(company_data.get('print_state', 1)),
                int(company_data.get('print_pincode', 1)),
                int(company_data.get('print_logo', 1)),
                int(company_data.get('print_signature', 1)),
                company_data.get('financial_year'),
                is_active_value,
            )
            if has_visibility:
                params = (*params, visibility)
            cursor.execute(query, params)
            company_id = cursor.lastrowid
            if self._check_column_exists(cursor, "companies", "db_path"):
                cursor.execute(
                    f"UPDATE companies SET db_path = {placeholder} WHERE id = {placeholder}",
                    (self.db_path, company_id),
                )
            
            conn.commit()
            self.disconnect()
            ensure_company_users_table(self.db_path, company_id)
            return True
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            if conn:
                try:
                    conn.rollback()
                except sqlite3.Error as rollback_error:
                    print(f"Database error: {rollback_error}")
                    print(f"Rollback error: {rollback_error}")
            print(f"Error creating company: {e}")
            return False
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except sqlite3.Error as rollback_error:
                    print(f"Database error: {rollback_error}")
                    print(f"Rollback error: {rollback_error}")
            print(f"Error creating company: {e}")
            return False
        finally:
            self.disconnect()
    
    def get_all_companies(self, visibility: str | None = None) -> List[Dict[str, Any]]:
        """Get companies, optionally filtered to one visibility pool."""
        ph = self._get_placeholder()
        query = """
            SELECT
                id, business_name, phone_number, gstin, gst_type, email, db_path,
                business_type, business_category, address, state, pincode,
                logo_path, signature_path, print_phone, print_gstin,
                print_email, print_business_type, print_business_category,
                print_address, print_state, print_pincode, print_logo,
                print_signature, financial_year, is_active, created_at, updated_at,
                COALESCE(visibility, 'normal') AS visibility
            FROM companies
        """
        params: tuple = ()
        if visibility:
            query += f" WHERE COALESCE(visibility, 'normal') = {ph}"
            params = (visibility.strip().lower(),)
        query += " ORDER BY business_name"
        return self.execute_query(query, params)

    def get_company_by_id(self, company_id: int) -> Optional[Dict[str, Any]]:
        """Get a single company by ID."""
        ph = self._get_placeholder()
        query = f"""
            SELECT
                id, business_name, phone_number, gstin, gst_type, email, db_path,
                business_type, business_category, address, state, pincode,
                logo_path, signature_path, print_phone, print_gstin,
                print_email, print_business_type, print_business_category,
                print_address, print_state, print_pincode, print_logo,
                print_signature, financial_year, is_active, created_at, updated_at,
                COALESCE(visibility, 'normal') AS visibility
            FROM companies
            WHERE id = {ph}
        """
        result = self.execute_query(query, (company_id,))
        return result[0] if result else None
    
    def get_active_company(self, visibility: str | None = None) -> Optional[Dict[str, Any]]:
        """Get the currently active company, optionally filtered by visibility pool."""
        ph = self._get_placeholder()
        query = """
            SELECT
                id, business_name, phone_number, gstin, gst_type, email, db_path,
                business_type, business_category, address, state, pincode,
                logo_path, signature_path, print_phone, print_gstin,
                print_email, print_business_type, print_business_category,
                print_address, print_state, print_pincode, print_logo,
                print_signature, financial_year, is_active, created_at, updated_at,
                COALESCE(visibility, 'normal') AS visibility
            FROM companies
            WHERE is_active = 1
        """
        params: tuple = ()
        if visibility:
            query += f" AND COALESCE(visibility, 'normal') = {ph}"
            params = (visibility.strip().lower(),)
        query += " LIMIT 1"
        result = self.execute_query(query, params)
        return result[0] if result else None
    
    def set_active_company(self, company_id: int) -> bool:
        """Set a company as active (deactivate all others first)."""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            # Deactivate all companies
            cursor.execute("UPDATE companies SET is_active = 0")
            
            # Activate the specified company
            placeholder = self._get_placeholder()
            cursor.execute(f"UPDATE companies SET is_active = 1 WHERE id = {placeholder}", (company_id,))
            
            conn.commit()
            self.disconnect()
            return True
        except Exception as e:
            print(f"Error setting active company: {e}")
            return False
    
    def update_company(self, company_id: int, company_data: Dict[str, Any]) -> bool:
        """Update an existing company record."""
        try:
            conn = self.connect()
            cursor = conn.cursor()
            
            # Update company
            placeholder = self._get_placeholder()
            timestamp_default = self._get_timestamp_default()
            self._ensure_company_print_columns(cursor)
            self._ensure_company_columns(cursor)
            query = f"""
                UPDATE companies SET 
                    business_name = {placeholder}, phone_number = {placeholder}, gstin = {placeholder}, gst_type = {placeholder}, email = {placeholder}, 
                    business_type = {placeholder}, business_category = {placeholder}, address = {placeholder}, 
                    state = {placeholder}, pincode = {placeholder}, logo_path = {placeholder}, signature_path = {placeholder},
                    print_phone = COALESCE({placeholder}, print_phone),
                    print_gstin = COALESCE({placeholder}, print_gstin),
                    print_email = COALESCE({placeholder}, print_email),
                    print_business_type = COALESCE({placeholder}, print_business_type),
                    print_business_category = COALESCE({placeholder}, print_business_category),
                    print_address = COALESCE({placeholder}, print_address),
                    print_state = COALESCE({placeholder}, print_state),
                    print_pincode = COALESCE({placeholder}, print_pincode),
                    print_logo = COALESCE({placeholder}, print_logo),
                    print_signature = COALESCE({placeholder}, print_signature),
                    financial_year = COALESCE({placeholder}, financial_year),
                    updated_at = {timestamp_default}
                WHERE id = {placeholder}
            """
            params = (
                company_data.get('business_name'),
                company_data.get('phone_number'),
                company_data.get('gstin'),
                company_data.get('gst_type', 'Regular') or 'Regular',
                company_data.get('email'),
                company_data.get('business_type'),
                company_data.get('business_category'),
                company_data.get('address'),
                company_data.get('state'),
                company_data.get('pincode'),
                company_data.get('logo_path'),
                company_data.get('signature_path'),
                int(company_data['print_phone']) if 'print_phone' in company_data else None,
                int(company_data['print_gstin']) if 'print_gstin' in company_data else None,
                int(company_data['print_email']) if 'print_email' in company_data else None,
                int(company_data['print_business_type']) if 'print_business_type' in company_data else None,
                int(company_data['print_business_category']) if 'print_business_category' in company_data else None,
                int(company_data['print_address']) if 'print_address' in company_data else None,
                int(company_data['print_state']) if 'print_state' in company_data else None,
                int(company_data['print_pincode']) if 'print_pincode' in company_data else None,
                int(company_data['print_logo']) if 'print_logo' in company_data else None,
                int(company_data['print_signature']) if 'print_signature' in company_data else None,
                company_data.get('financial_year'),
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
        ph = self._get_placeholder()
        query = f"SELECT COUNT(*) as count FROM companies WHERE LOWER(TRIM(business_name)) = {ph} AND id != {ph}"
        result = self.execute_query(query, (normalized_name, exclude_id))
        return result[0]['count'] > 0 if result else False
    
    def delete_company(self, company_id: int) -> bool:
        """Delete a company and all company-scoped data in one transaction."""
        conn = None
        try:
            self.last_error_message = None
            conn = self.connect()
            cursor = conn.cursor()
            placeholder = self._get_placeholder()

            if self._is_sqlite():
                self._cleanup_legacy_sales_type_sqlite_objects(cursor)
                self._migrate_quotation_master_sales_fk(cursor)
                conn.commit()
                cursor.execute("BEGIN")
            else:
                cursor.execute("START TRANSACTION")

            def delete_if_exists(table_name: str, where_clause: str,
                                 params: tuple) -> None:
                """Delete from a known schema table only when it exists."""
                if self._check_table_exists(cursor, table_name):
                    cursor.execute(
                        f"DELETE FROM {table_name} WHERE {where_clause}",
                        params
                    )

            # Child rows are removed first because several use RESTRICT links.
            child_deletes = (
                (
                    "cash_receipt_items",
                    f"""
                    receipt_id IN (
                        SELECT id FROM cash_receipts
                        WHERE company_id = {placeholder}
                    )
                    """,
                ),
                (
                    "cash_payment_items",
                    f"""
                    payment_id IN (
                        SELECT id FROM cash_payments
                        WHERE company_id = {placeholder}
                    )
                    """,
                ),
                (
                    "journal_voucher_lines",
                    f"""
                    journal_id IN (
                        SELECT id FROM journal_vouchers
                        WHERE company_id = {placeholder}
                    )
                    """,
                ),
                (
                    "stock_adjustment_items",
                    f"""
                    adjustment_id IN (
                        SELECT id FROM stock_adjustments
                        WHERE company_id = {placeholder}
                    )
                    """,
                ),
                (
                    "purchase_order_items",
                    f"""
                    po_id IN (
                        SELECT id FROM purchase_orders
                        WHERE company_id = {placeholder}
                    )
                    """,
                ),
                (
                    "quotation_items",
                    f"""
                    quotation_id IN (
                        SELECT id FROM quotations
                        WHERE company_id = {placeholder}
                    )
                    """,
                ),
                (
                    "sales_items",
                    f"""
                    sale_id IN (
                        SELECT id FROM sales
                        WHERE company_id = {placeholder}
                    )
                    """,
                ),
                (
                    "purchase_items",
                    f"""
                    purchase_id IN (
                        SELECT id FROM purchases
                        WHERE company_id = {placeholder}
                    )
                    """,
                ),
                (
                    "sales_return_items",
                    f"""
                    sales_return_id IN (
                        SELECT id FROM sales_returns
                        WHERE company_id = {placeholder}
                    )
                    """,
                ),
                (
                    "purchase_return_items",
                    f"""
                    purchase_return_id IN (
                        SELECT id FROM purchase_returns
                        WHERE company_id = {placeholder}
                    )
                    """,
                ),
            )
            for table_name, where_clause in child_deletes:
                delete_if_exists(table_name, where_clause, (company_id,))

            company_scoped_tables = (
                "ledger_entries",
                "stock_movements",
                "stock_draft_session",
                "audit_logs",
                "company_settings",
                "print_settings",
                "pdc_register",
                "credit_debit_notes",
                "quotation_master",
                "quotations",
                "purchase_orders",
                "stock_adjustments",
                "sales_returns",
                "purchase_returns",
                "sales",
                "purchases",
                "cash_receipts",
                "cash_payments",
                "bank_receipts",
                "bank_payments",
                "journal_vouchers",
                "bank_accounts",
                "ledger_accounts",
                "transactions",
                "categories",
                "accounts",
                "products",
                "parties",
            )
            for table_name in company_scoped_tables:
                delete_if_exists(
                    table_name,
                    f"company_id = {placeholder}",
                    (company_id,)
                )

            cursor.execute(f"DELETE FROM companies WHERE id = {placeholder}", (company_id,))
            
            conn.commit()
            self.disconnect()
            return True
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            self.last_error_message = f"DB Error: {e}"
            print(f"DB Error: {e}")
            return False
        except Exception as e:
            if conn:
                conn.rollback()
            self.last_error_message = f"Error deleting company: {e}"
            print(f"Error deleting company: {e}")
            return False
    
    def get_accounts(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all accounts for a specific company."""
        query = """
            SELECT id, name, type, balance, currency, description, created_at, updated_at
            FROM accounts 
            WHERE company_id = {ph}
            ORDER BY name
        """
        ph = self._get_placeholder()
        query = f"""
            SELECT a.id, a.name, a.type, a.balance, a.currency, a.description
            FROM accounts 
            WHERE company_id = {ph}
            ORDER BY name
        """
        return self.execute_query(query, (company_id,))
    
    def create_account(self, company_id: int, name: str, account_type: str, 
                    balance: float = 0.0, currency: str = 'USD', 
                    description: str = None) -> bool:
        """Create a new account for a specific company."""
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO accounts (company_id, name, type, balance, currency, description)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        return self.execute_update(query, (company_id, name, account_type, balance, currency, description))
    
    def update_account(self, account_id: int, name: str, account_type: str,
                    balance: float, currency: str, description: str) -> bool:
        """Update an existing account."""
        ph = self._get_placeholder()
        query = f"""
            UPDATE accounts 
            SET name = {ph},
                type = {ph},
                balance = {ph},
                currency = {ph},
                description = {ph},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph}
        """
        return self.execute_update(query, (name, account_type, balance, currency, description, account_id))
    
    def delete_account(self, account_id: int) -> bool:
        """Delete an account."""
        ph = self._get_placeholder()
        query = f"DELETE FROM accounts WHERE id = {ph}"
        return self.execute_update(query, (account_id,))
    
    def get_setting(self, key: str) -> Optional[str]:
        """Get a setting value."""
        ph = self._get_placeholder()
        query = f"SELECT value FROM settings WHERE key = {ph}"
        result = self.execute_query(query, (key,))
        return result[0]['value'] if result else None
    
    def get_transactions_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all transactions for a specific company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT t.id, t.date, t.account_id, a.name as account_name, t.amount, t.type,
                   t.description, t.category_id, c.name as category_name, t.created_at
            FROM transactions t
            LEFT JOIN accounts a ON t.account_id = a.id
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.company_id = {ph}
            ORDER BY t.date DESC, t.created_at DESC
        """
        return self.execute_query(query, (company_id,))
    
    def create_transaction(self, company_id: int, account_id: int, amount: float,
                         transaction_type: str, description: str = None, 
                         date: str = None, category_id: int = None) -> bool:
        """Create a new transaction for a specific company."""
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO transactions (company_id, account_id, amount, type, description, date, category_id)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        return self.execute_update(query, (company_id, account_id, amount, transaction_type, description, date, category_id))
    
    def get_categories(self, company_id: int, category_type: str = None) -> List[Dict[str, Any]]:
        """Get all categories for a specific company."""
        ph = self._get_placeholder()
        if category_type:
            query = f"""
                SELECT id, name, type, color, description, created_at
                FROM categories 
                WHERE company_id = {ph} AND type = {ph}
                ORDER BY name
            """
            return self.execute_query(query, (company_id, category_type))
        else:
            query = f"""
                SELECT id, name, type, color, description, created_at
                FROM categories 
                WHERE company_id = {ph}
                ORDER BY name
            """
            return self.execute_query(query, (company_id,))
    
    def create_category(self, company_id: int, name: str, category_type: str,
                       color: str = '#2196F3', description: str = None) -> bool:
        """Create a new category for a specific company."""
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO categories (company_id, name, type, color, description)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph})
        """
        return self.execute_update(query, (company_id, name, category_type, color, description))
    
    def set_setting(self, key: str, value: str) -> bool:
        """Set a setting value using backend-safe INSERT OR REPLACE."""
        ph = self._get_placeholder()
        if self._is_sqlite():
            query = f"INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ({ph}, {ph}, CURRENT_TIMESTAMP)"
        else:
            query = f"""
                INSERT INTO settings (key, value, updated_at)
                VALUES ({ph}, {ph}, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE value = {ph}, updated_at = CURRENT_TIMESTAMP
            """
        if self._is_mysql():
            return self.execute_update(query, (key, value, value))
        return self.execute_update(query, (key, value))
    
    # Product-specific methods
    
    def get_products_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all products for a specific company, ordered by barcode.

        Returns calculated stock balance from movements instead of products.quantity.
        """
        ph = self._get_placeholder()
        query = f"""
            SELECT p.id, p.name, p.barcode, p.hsn, p.color, p.size, p.unit, p.category,
                   p.purchase_rate, p.sale_price, p.wholesale_rate, p.mrp,
                   p.cgst, p.sgst, p.igst, p.cess, p.reorder_level,
                   COALESCE(
                       (SELECT SUM(sm.quantity)
                       FROM stock_movements sm
                       WHERE sm.company_id = p.company_id
                         AND sm.product_id = p.id
                         AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')),
                       0.0
                   ) as quantity
            FROM products p
            WHERE p.company_id = {ph}
            ORDER BY
                CASE
                    WHEN p.barcode IS NULL OR p.barcode = '' THEN 1
                    ELSE 0
                END,
                CAST(p.barcode AS INTEGER)
        """
        return self.execute_query(query, (company_id,))

    def search_products_limited(self, company_id: int, search_term: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search products by name or barcode with a result limit.

        Safe for very large product catalogs. Uses SQL LIKE for prefix and
        contains matching, with an early LIMIT to avoid loading everything.
        """
        if not search_term:
            return []
        starts_pattern = f"{search_term}%"
        ph = self._get_placeholder()
        query = f"""
            SELECT p.id, p.name, p.barcode, p.hsn, p.color, p.size, p.unit, p.category,
                   p.purchase_rate, p.sale_price, p.wholesale_rate, p.mrp,
                   p.cgst, p.sgst, p.igst, p.cess, p.reorder_level,
                   COALESCE(
                       (SELECT SUM(sm.quantity)
                       FROM stock_movements sm
                       WHERE sm.company_id = p.company_id
                         AND sm.product_id = p.id
                         AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')),
                       0.0
                   ) as quantity
            FROM products p
            WHERE p.company_id = {ph}
              AND (
                    LOWER(p.name) LIKE LOWER({ph})
                 OR LOWER(COALESCE(p.barcode, '')) LIKE LOWER({ph})
                 OR LOWER(COALESCE(p.category, '')) LIKE LOWER({ph})
              )
            ORDER BY
              CASE WHEN LOWER(p.name) LIKE LOWER({ph}) THEN 0 ELSE 1 END,
              p.name
            LIMIT {ph}
        """
        return self.execute_query(query, (company_id, starts_pattern, starts_pattern, starts_pattern, starts_pattern, limit))

    def get_product_count(self, company_id: int) -> int:
        """Get total product count for a company (lightweight query)."""
        ph = self._get_placeholder()
        query = f"SELECT COUNT(*) as count FROM products WHERE company_id = {ph}"
        result = self.execute_query(query, (company_id,))
        return result[0]['count'] if result else 0

    def get_product_by_exact_name(self, company_id: int, name: str) -> Optional[Dict[str, Any]]:
        """Get product by exact name match (case-insensitive)."""
        ph = self._get_placeholder()
        query = f"""
            SELECT p.id, p.name, p.barcode, p.hsn, p.color, p.size, p.unit, p.category,
                   p.purchase_rate, p.sale_price, p.wholesale_rate, p.mrp,
                   p.cgst, p.sgst, p.igst, p.cess, p.reorder_level,
                   COALESCE(
                       (SELECT SUM(sm.quantity)
                       FROM stock_movements sm
                       WHERE sm.company_id = p.company_id
                         AND sm.product_id = p.id
                         AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')),
                       0.0
                   ) as quantity
            FROM products p
            WHERE p.company_id = {ph} AND LOWER(p.name) = LOWER({ph})
        """
        result = self.execute_query(query, (company_id, name))
        return result[0] if result else None

    def get_product_by_id(self, company_id: int, product_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific product by ID for a company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT id, name, barcode, hsn, color, size, unit, category,
                   purchase_rate, sale_price, wholesale_rate, mrp,
                   cgst, sgst, igst, cess, reorder_level,
                   description, quantity, auto_barcode
            FROM products
            WHERE company_id = {ph} AND id = {ph}
        """
        result = self.execute_query(query, (company_id, product_id))
        return result[0] if result else None

    def get_product_by_barcode(self, company_id: int, barcode: str) -> Optional[Dict[str, Any]]:
        """Get a specific product by barcode for a company (exact match)."""
        ph = self._get_placeholder()
        query = f"""
            SELECT id, name, barcode, hsn, color, size, unit, category,
                   purchase_rate, sale_price, wholesale_rate, mrp,
                   cgst, sgst, igst, cess, reorder_level,
                   description, quantity, auto_barcode
            FROM products
            WHERE company_id = {ph} AND barcode = {ph}
        """
        result = self.execute_query(query, (company_id, barcode))
        return result[0] if result else None
    
    def insert_product(self, company_id: int, product_data: Dict[str, Any]) -> int:
        """Insert a new product for a company and return the product ID."""
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO products (
                company_id, name, barcode, hsn, color, size, unit, category,
                purchase_rate, sale_price, wholesale_rate, mrp,
                cgst, sgst, igst, cess, reorder_level,
                description, quantity, auto_barcode
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        params = (
            company_id,
            product_data.get('name'),
            product_data.get('barcode'),
            product_data.get('hsn'),
            product_data.get('color'),
            product_data.get('size'),
            product_data.get('unit', 'pcs'),
            product_data.get('category'),
            product_data.get('purchase_rate', 0.0),
            product_data.get('sale_price', 0.0),
            product_data.get('wholesale_rate', 0.0),
            product_data.get('mrp', 0.0),
            product_data.get('cgst', 0.0),
            product_data.get('sgst', 0.0),
            product_data.get('igst', 0.0),
            product_data.get('cess', 0.0),
            product_data.get('reorder_level', 0.0),
            product_data.get('description'),
            product_data.get('quantity', 0.0),
            1 if product_data.get('auto_barcode', True) else 0
        )
        try:
            conn = self.connect()
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            product_id = self._get_last_insert_id(cursor)
            return product_id
        except Exception as e:
            print(f"Insert product error: {e}")
            raise
        finally:
            self.disconnect()
    
    def update_product(self, company_id: int, product_id: int, product_data: Dict[str, Any]) -> bool:
        """Update an existing product for a company."""
        ph = self._get_placeholder()
        query = f"""
            UPDATE products
            SET name = {ph},
                barcode = {ph},
                hsn = {ph},
                color = {ph},
                size = {ph},
                unit = {ph},
                category = {ph},
                purchase_rate = {ph},
                sale_price = {ph},
                wholesale_rate = {ph},
                mrp = {ph},
                cgst = {ph},
                sgst = {ph},
                igst = {ph},
                cess = {ph},
                reorder_level = {ph},
                description = {ph},
                quantity = {ph},
                auto_barcode = {ph}
            WHERE id = {ph} AND company_id = {ph}
        """
        params = (
            product_data.get('name'),
            product_data.get('barcode'),
            product_data.get('hsn'),
            product_data.get('color'),
            product_data.get('size'),
            product_data.get('unit', 'pcs'),
            product_data.get('category'),
            product_data.get('purchase_rate', 0.0),
            product_data.get('sale_price', 0.0),
            product_data.get('wholesale_rate', 0.0),
            product_data.get('mrp', 0.0),
            product_data.get('cgst', 0.0),
            product_data.get('sgst', 0.0),
            product_data.get('igst', 0.0),
            product_data.get('cess', 0.0),
            product_data.get('reorder_level', 0.0),
            product_data.get('description'),
            product_data.get('quantity', 0.0),
            1 if product_data.get('auto_barcode', True) else 0,
            product_id,
            company_id
        )
        return self.execute_update(query, params)
    
    def delete_product(self, company_id: int, product_id: int) -> bool:
        """Delete a product for a company."""
        ph = self._get_placeholder()
        query = f"DELETE FROM products WHERE id = {ph} AND company_id = {ph}"
        return self.execute_update(query, (product_id, company_id))
    
    def barcode_exists(self, company_id: int, barcode: str, exclude_product_id: Optional[int] = None) -> bool:
        """Check if a barcode exists for a company (excluding a specific product if editing)."""
        ph = self._get_placeholder()
        if exclude_product_id:
            query = f"SELECT id FROM products WHERE barcode = {ph} AND company_id = {ph} AND id != {ph}"
            result = self.execute_query(query, (barcode, company_id, exclude_product_id))
        else:
            query = f"SELECT id FROM products WHERE barcode = {ph} AND company_id = {ph}"
            result = self.execute_query(query, (barcode, company_id))
        return len(result) > 0
    
    def get_existing_barcodes(self, company_id: int, exclude_product_id: Optional[int] = None) -> List[int]:
        """Get all existing numeric barcodes for a company."""
        ph = self._get_placeholder()
        if exclude_product_id:
            query = f"""
                SELECT barcode FROM products 
                WHERE company_id = {ph} AND id != {ph} AND barcode IS NOT NULL AND barcode != ''
            """
            result = self.execute_query(query, (company_id, exclude_product_id))
        else:
            query = f"""
                SELECT barcode FROM products 
                WHERE company_id = {ph} AND barcode IS NOT NULL AND barcode != ''
            """
            result = self.execute_query(query, (company_id,))
        
        existing_barcodes = []
        for row in result:
            if row['barcode']:
                try:
                    existing_barcodes.append(int(row['barcode']))
                except (ValueError, TypeError):
                    pass
        
        return existing_barcodes
    
    def get_max_numeric_barcode(self, company_id: int) -> Optional[int]:
        """Get the maximum numeric barcode for a company."""
        cast_integer = self._get_cast_integer()
        ph = self._get_placeholder()
        query = f"""
            SELECT MAX(CAST(barcode {cast_integer})) as max_barcode
            FROM products 
            WHERE company_id = {ph} AND barcode IS NOT NULL AND barcode != ''
        """
        result = self.execute_query(query, (company_id,))
        if result and result[0]['max_barcode']:
            return int(result[0]['max_barcode'])
        return None

    def get_max_auto_barcode(self, company_id: int,
                             exclude_product_id: Optional[int] = None) -> Optional[int]:
        """Return the highest system auto-generated numeric barcode for a company.

        Only barcodes created by the auto sequence (auto_barcode = 1) feed the
        baseline seed, so a manually keyed high value never pushes the counter
        upward. Returns None when no auto barcode exists yet.
        """
        cast_integer = self._get_cast_integer()
        ph = self._get_placeholder()
        if exclude_product_id:
            query = f"""
                SELECT MAX(CAST(barcode {cast_integer})) AS max_auto
                FROM products
                WHERE company_id = {ph} AND id != {ph}
                  AND auto_barcode = 1 AND barcode IS NOT NULL AND barcode != ''
            """
            result = self.execute_query(query, (company_id, exclude_product_id))
        else:
            query = f"""
                SELECT MAX(CAST(barcode {cast_integer})) AS max_auto
                FROM products
                WHERE company_id = {ph}
                  AND auto_barcode = 1 AND barcode IS NOT NULL AND barcode != ''
            """
            result = self.execute_query(query, (company_id,))
        if result and result[0]['max_auto']:
            return int(result[0]['max_auto'])
        return None

    # Party-specific methods
    
    def get_parties_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all parties for a specific company, ordered by name."""
        ph = self._get_placeholder()
        query = f"""
            SELECT id, name, party_type, opening_balance, mobile_number,
                   email, gstin, credit_limit, contact_person, address, notes, state, party_code
            FROM parties
            WHERE company_id = {ph}
            ORDER BY name
        """
        return self.execute_query(query, (company_id,))
    
    def get_party_by_id(self, company_id: int, party_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific party by ID for a company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT id, name, party_type, opening_balance, mobile_number,
                   email, gstin, credit_limit, contact_person, address, notes, state, party_code
            FROM parties
            WHERE company_id = {ph} AND id = {ph}
        """
        result = self.execute_query(query, (company_id, party_id))
        return result[0] if result else None

    def get_party_balance(self, company_id: int, party_id: int) -> float:
        """Return current balance for a party = opening_balance + sum of outstanding credit sales."""
        try:
            # Get party opening_balance
            party = self.get_party_by_id(company_id, party_id)
            opening_balance = float(party.get('opening_balance', 0.0)) if party else 0.0

            # Sum outstanding amounts from all credit sales for this party
            ph = self._get_placeholder()
            query = f"""
                SELECT COALESCE(SUM(grand_total - amount_received), 0.0) as outstanding
                FROM sales
                WHERE company_id = {ph} AND party_id = {ph} AND sales_type = 'Credit Sales'
                  AND COALESCE(status, 'Active') <> 'Voided'
            """
            result = self.execute_query(query, (company_id, party_id))
            outstanding = float(result[0].get('outstanding', 0.0)) if result else 0.0
            return opening_balance + outstanding
        except Exception:
            return 0.0
    
    def insert_party(self, company_id: int, party_data: Dict[str, Any]) -> Optional[int]:
        """Insert a new party for a company. Returns the new party ID or None on failure."""
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO parties (
                company_id, name, party_code, party_type, opening_balance, mobile_number,
                email, gstin, state, credit_limit, contact_person, address, notes
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        params = (
            company_id,
            party_data.get('name'),
            party_data.get('party_code'),
            party_data.get('party_type'),
            party_data.get('opening_balance', 0.0),
            party_data.get('mobile_number'),
            party_data.get('email'),
            party_data.get('gstin'),
            party_data.get('state'),
            party_data.get('credit_limit', 0.0),
            party_data.get('contact_person'),
            party_data.get('address'),
            party_data.get('notes')
        )
        self.execute_update(query, params)
        # Look up by UNIQUE(company_id, name) to get the new ID
        ph = self._get_placeholder()
        result = self.execute_query(
            f"SELECT id FROM parties WHERE company_id = {ph} AND name = {ph} ORDER BY id DESC LIMIT 1",
            (company_id, party_data.get('name'))
        )
        return result[0]['id'] if result else None
    
    def update_party(self, company_id: int, party_id: int, party_data: Dict[str, Any]) -> bool:
        """Update an existing party for a company."""
        ph = self._get_placeholder()
        query = f"""
            UPDATE parties
            SET name = {ph},
                party_code = {ph},
                party_type = {ph},
                opening_balance = {ph},
                mobile_number = {ph},
                email = {ph},
                gstin = {ph},
                state = {ph},
                credit_limit = {ph},
                contact_person = {ph},
                address = {ph},
                notes = {ph},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph} AND company_id = {ph}
        """
        params = (
            party_data.get('name'),
            party_data.get('party_code'),
            party_data.get('party_type'),
            party_data.get('opening_balance', 0.0),
            party_data.get('mobile_number'),
            party_data.get('email'),
            party_data.get('gstin'),
            party_data.get('state'),
            party_data.get('credit_limit', 0.0),
            party_data.get('contact_person'),
            party_data.get('address'),
            party_data.get('notes'),
            party_id,
            company_id
        )
        return self.execute_update(query, params)
    
    def delete_party(self, company_id: int, party_id: int) -> bool:
        """Delete a party for a company."""
        ph = self._get_placeholder()
        query = f"DELETE FROM parties WHERE id = {ph} AND company_id = {ph}"
        return self.execute_update(query, (party_id, company_id))
    
    def party_name_exists(self, company_id: int, party_name: str, exclude_party_id: Optional[int] = None,
                          party_type: Optional[str] = None) -> bool:
        """Check if a party name exists for a company, optionally within one party type."""
        ph = self._get_placeholder()
        type_clause = f" AND party_type = {ph}" if party_type else ""
        if exclude_party_id:
            query = (
                f"SELECT id FROM parties WHERE LOWER(TRIM(name)) = LOWER(TRIM({ph})) "
                f"AND company_id = {ph}{type_clause} AND id != {ph}"
            )
            params = [party_name, company_id]
            if party_type:
                params.append(party_type)
            params.append(exclude_party_id)
            result = self.execute_query(query, tuple(params))
        else:
            query = (
                f"SELECT id FROM parties WHERE LOWER(TRIM(name)) = LOWER(TRIM({ph})) "
                f"AND company_id = {ph}{type_clause}"
            )
            params = [party_name, company_id]
            if party_type:
                params.append(party_type)
            result = self.execute_query(query, tuple(params))
        return len(result) > 0

    def party_code_exists(self, company_id: int, party_code: str, exclude_party_id: Optional[int] = None) -> bool:
        """Check if a party code exists for a company."""
        ph = self._get_placeholder()
        if exclude_party_id:
            query = f"SELECT id FROM parties WHERE UPPER(TRIM(party_code)) = UPPER(TRIM({ph})) AND company_id = {ph} AND id != {ph}"
            result = self.execute_query(query, (party_code, company_id, exclude_party_id))
        else:
            query = f"SELECT id FROM parties WHERE UPPER(TRIM(party_code)) = UPPER(TRIM({ph})) AND company_id = {ph}"
            result = self.execute_query(query, (party_code, company_id))
        return len(result) > 0

    # Purchase-specific methods

    def get_next_purchase_number(self, company_id: int, series: str = "") -> str:
        """Get the next auto-incrementing purchase number for a company."""
        try:
            from bizora_core.invoice_numbering import get_invoice_prefix, get_next_voucher_number

            prefix = series if series else get_invoice_prefix(self, company_id)
            if series:
                return self._get_next_prefixed_number(company_id, "purchases", "purchase_number", prefix)
            return get_next_voucher_number(self, company_id, "purchase")
        except Exception:
            return "001"

    def _get_next_prefixed_number(
        self,
        company_id: int,
        table_name: str,
        column_name: str,
        prefix: str,
    ) -> str:
        """Legacy helper for explicit series strings on purchase numbering."""
        from bizora_core.invoice_numbering import format_voucher_number, get_max_voucher_sequence

        voucher_type = {
            "purchases": "purchase",
            "sales": "sales",
            "sales_returns": "sales_return",
            "purchase_returns": "purchase_return",
            "quotations": "quotation",
        }.get(table_name, "purchase")
        next_sequence = get_max_voucher_sequence(self, company_id, voucher_type, prefix) + 1
        return format_voucher_number(prefix, next_sequence)

    def get_next_po_number(self, company_id: int) -> str:
        """Return the next formatted purchase order number for a company."""
        try:
            from bizora_core.invoice_numbering import get_next_voucher_number

            return get_next_voucher_number(self, company_id, "purchase_order")
        except Exception:
            return "001"

    def get_po_nav_ids(self, company_id: int) -> List[int]:
        """Return purchase order ids in chronological order for navigation."""
        ph = self._get_placeholder()
        try:
            rows = self.execute_query(
                f"""
                SELECT id
                FROM purchase_orders
                WHERE company_id = {ph}
                ORDER BY id
                """,
                (company_id,),
            ) or []
            return [
                int(row.get("id") if isinstance(row, dict) else row[0])
                for row in rows
                if (row.get("id") if isinstance(row, dict) else row[0])
            ]
        except Exception:
            return []

    def get_next_sale_number(self, company_id: int, series: str = "") -> str:
        """Get the next auto-incrementing invoice number for a company."""
        try:
            from bizora_core.invoice_numbering import get_next_voucher_number

            return get_next_voucher_number(self, company_id, "sales")
        except Exception:
            return "001"

    def get_next_voucher_number(self, company_id: int, voucher_type: str) -> str:
        """Return the next formatted voucher number for a supported entry module."""
        from bizora_core.invoice_numbering import get_next_voucher_number

        return get_next_voucher_number(self, company_id, voucher_type)

    def get_next_stock_adjustment_number(self, company_id: int, series: str = "") -> str:
        """Get the next auto-incrementing stock adjustment number for a company.
        Handles STK-YYYYMMDD-XXX format where XXX is a 3-digit sequence.
        Movement type: 'stock_adjustment' (standardized).
        """
        from datetime import datetime
        ph = self._get_placeholder()
        today = datetime.now().strftime("%Y%m%d")
        
        # Stock Adjustment uses STK-YYYYMMDD-XXX format
        # Find the max sequence number for today's date
        query = f"""
            SELECT MAX(CAST(SUBSTR(voucher_no, -3) AS INTEGER)) as max_num
            FROM stock_adjustments
            WHERE company_id = {ph} AND voucher_no LIKE {ph}
        """
        pattern = f"STK-{today}-%"
        result = self.execute_query(query, (company_id, pattern))
        
        if result and result[0]['max_num']:
            next_num = result[0]['max_num'] + 1
        else:
            next_num = 1
        
        return f"STK-{today}-{next_num:03d}"

    def save_stock_adjustment(self, header_data: Dict[str, Any], items_data: List[Dict[str, Any]]) -> int:
        """Save a new stock adjustment with items.
        Returns the adjustment_id.
        Uses placeholder-safe queries for MySQL compatibility.
        """
        ph = self._get_placeholder()
        
        # Save header
        header_query = f"""
            INSERT INTO stock_adjustments (
                company_id, voucher_no, voucher_date, narration,
                total_increase_value, total_decrease_value, net_adjustment
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        header_params = (
            header_data['company_id'],
            header_data['voucher_no'],
            header_data['voucher_date'],
            header_data.get('narration', ''),
            header_data.get('total_increase_value', 0),
            header_data.get('total_decrease_value', 0),
            header_data.get('net_adjustment', 0)
        )
        
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(header_query, header_params)
        adjustment_id = cursor.lastrowid
        
        # Save items
        item_query = f"""
            INSERT INTO stock_adjustment_items (
                adjustment_id, sl_no, product_id, barcode,
                system_qty, physical_qty, difference_qty, rate, value, reason
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        
        for item in items_data:
            item_params = (
                adjustment_id,
                item['sl_no'],
                item['product_id'],
                item.get('barcode', ''),
                item.get('system_qty', 0),
                item.get('physical_qty', 0),
                item.get('difference_qty', 0),
                item.get('rate', 0),
                item.get('value', 0),
                item.get('reason', '')
            )
            cursor.execute(item_query, item_params)
        
        conn.commit()
        conn.close()
        
        return adjustment_id

    def update_stock_adjustment(self, adjustment_id: int, header_data: Dict[str, Any], items_data: List[Dict[str, Any]]) -> bool:
        """Update an existing stock adjustment with items.
        Uses placeholder-safe queries for MySQL compatibility.
        """
        ph = self._get_placeholder()
        
        conn = self.connect()
        cursor = conn.cursor()
        
        # Update header
        header_query = f"""
            UPDATE stock_adjustments SET
                voucher_no = {ph},
                voucher_date = {ph},
                narration = {ph},
                total_increase_value = {ph},
                total_decrease_value = {ph},
                net_adjustment = {ph},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph}
        """
        header_params = (
            header_data['voucher_no'],
            header_data['voucher_date'],
            header_data.get('narration', ''),
            header_data.get('total_increase_value', 0),
            header_data.get('total_decrease_value', 0),
            header_data.get('net_adjustment', 0),
            adjustment_id
        )
        cursor.execute(header_query, header_params)
        
        # Delete old items
        delete_items_query = f"DELETE FROM stock_adjustment_items WHERE adjustment_id = {ph}"
        cursor.execute(delete_items_query, (adjustment_id,))
        
        # Insert new items
        item_query = f"""
            INSERT INTO stock_adjustment_items (
                adjustment_id, sl_no, product_id, barcode,
                system_qty, physical_qty, difference_qty, rate, value, reason
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        
        for item in items_data:
            item_params = (
                adjustment_id,
                item['sl_no'],
                item['product_id'],
                item.get('barcode', ''),
                item.get('system_qty', 0),
                item.get('physical_qty', 0),
                item.get('difference_qty', 0),
                item.get('rate', 0),
                item.get('value', 0),
                item.get('reason', '')
            )
            cursor.execute(item_query, item_params)
        
        conn.commit()
        conn.close()
        
        return True

    def delete_stock_adjustment(self, adjustment_id: int) -> bool:
        """Delete a stock adjustment (cascade deletes items).
        Uses placeholder-safe queries for MySQL compatibility.
        """
        ph = self._get_placeholder()
        
        conn = self.connect()
        cursor = conn.cursor()
        
        query = f"DELETE FROM stock_adjustments WHERE id = {ph}"
        cursor.execute(query, (adjustment_id,))
        
        conn.commit()
        conn.close()
        
        return True

    def get_stock_adjustment_by_id(self, adjustment_id: int) -> Dict[str, Any]:
        """Get a stock adjustment by ID.
        Uses placeholder-safe queries for MySQL compatibility.
        """
        ph = self._get_placeholder()
        
        query = f"""
            SELECT id, company_id, voucher_no, voucher_date, narration,
                   total_increase_value, total_decrease_value, net_adjustment,
                   created_at, updated_at
            FROM stock_adjustments
            WHERE id = {ph}
        """
        
        result = self.execute_query(query, (adjustment_id,))
        
        if result:
            return result[0]
        return None

    def get_stock_adjustment_items(self, adjustment_id: int) -> List[Dict[str, Any]]:
        """Get all items for a stock adjustment.
        Uses placeholder-safe queries for MySQL compatibility.
        """
        ph = self._get_placeholder()
        
        query = f"""
            SELECT id, adjustment_id, sl_no, product_id, barcode,
                   system_qty, physical_qty, difference_qty, rate, value, reason
            FROM stock_adjustment_items
            WHERE adjustment_id = {ph}
            ORDER BY sl_no
        """
        
        return self.execute_query(query, (adjustment_id,))

    def get_stock_draft_session_items(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all items in the stock draft session for a company."""
        ph = self._get_placeholder()

        query = f"""
            SELECT id, company_id, item_id, item_code, item_name,
                   computer_qty, physical_qty, purchase_rate
            FROM stock_draft_session
            WHERE company_id = {ph}
            ORDER BY created_at
        """

        return self.execute_query(query, (company_id,))

    def add_stock_draft_item(self, company_id: int, item_id: int, item_code: str,
                            item_name: str, computer_qty: float, purchase_rate: float) -> Dict[str, Any]:
        """Add or update an item in the stock draft session (aggregates existing)."""
        ph = self._get_placeholder()

        # Check if item exists
        check_query = f"""
            SELECT id FROM stock_draft_session
            WHERE company_id = {ph} AND item_id = {ph}
        """
        existing = self.execute_query(check_query, (company_id, item_id))

        if existing:
            # Update existing
            query = f"""
                UPDATE stock_draft_session
                SET item_code = {ph}, item_name = {ph}, computer_qty = {ph},
                    purchase_rate = {ph}, updated_at = CURRENT_TIMESTAMP
                WHERE company_id = {ph} AND item_id = {ph}
            """
            self.execute_update(query, (item_code, item_name, computer_qty, purchase_rate, company_id, item_id))
        else:
            # Insert new
            query = f"""
                INSERT INTO stock_draft_session (company_id, item_id, item_code, item_name, computer_qty, physical_qty, purchase_rate)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """
            self.execute_update(query, (company_id, item_id, item_code, item_name, computer_qty, computer_qty, purchase_rate))

        return {'success': True}

    def update_stock_draft_physical_qty(self, company_id: int, item_id: int, physical_qty: float) -> Dict[str, Any]:
        """Update the physical quantity for an item in the draft session."""
        ph = self._get_placeholder()

        query = f"""
            UPDATE stock_draft_session
            SET physical_qty = {ph}, updated_at = CURRENT_TIMESTAMP
            WHERE company_id = {ph} AND item_id = {ph}
        """

        self.execute_update(query, (physical_qty, company_id, item_id))

        return {'success': True}

    def delete_stock_draft_item(self, row_id: int) -> Dict[str, Any]:
        """Delete an item from the stock draft session by row id."""
        ph = self._get_placeholder()

        query = f"""
            DELETE FROM stock_draft_session
            WHERE id = {ph}
        """

        self.execute_update(query, (row_id,))

        return {'success': True}

    def clear_stock_draft_session(self, company_id: int) -> Dict[str, Any]:
        """Clear all items from the stock draft session for a company."""
        ph = self._get_placeholder()

        query = f"""
            DELETE FROM stock_draft_session
            WHERE company_id = {ph}
        """

        self.execute_update(query, (company_id,))

        return {'success': True}

    def get_stock_adjustment_ids_by_company(self, company_id: int) -> List[int]:
        """Get all stock adjustment IDs for a company (optimized for navigation).
        Uses placeholder-safe queries for MySQL compatibility.
        """
        ph = self._get_placeholder()
        
        query = f"""
            SELECT id FROM stock_adjustments
            WHERE company_id = {ph}
            ORDER BY voucher_date DESC, id DESC
        """
        
        results = self.execute_query(query, (company_id,))
        return [r['id'] for r in results]

    def get_stock_adjustments_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all stock adjustments for a company.
        Uses placeholder-safe queries for MySQL compatibility.
        """
        ph = self._get_placeholder()
        
        query = f"""
            SELECT id, company_id, voucher_no, voucher_date, narration,
                   total_increase_value, total_decrease_value, net_adjustment,
                   created_at, updated_at
            FROM stock_adjustments
            WHERE company_id = {ph}
            ORDER BY voucher_date DESC, id DESC
        """
        
        return self.execute_query(query, (company_id,))

    def get_purchases_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all purchases for a specific company, ordered by date desc."""
        ph = self._get_placeholder()
        query = f"""
            SELECT id, purchase_number, purchase_date, party_id, purchase_type,
                   bill_series, nature, due_date, address, gstin, state,
                   narration, sub_total, discount_total, tax_total, round_off,
                   grand_total, amount_paid, COALESCE(status, 'Active') AS status, created_at
            FROM purchases
            WHERE company_id = {ph}
            ORDER BY purchase_date DESC, id DESC
        """
        return self.execute_query(query, (company_id,))

    def get_purchase_ids_by_company(self, company_id: int) -> List[int]:
        """Get only purchase IDs for a specific company - optimized for navigation.

        This is much faster than get_purchases_by_company() for prev/next navigation
        because it doesn't return full rows.
        """
        ph = self._get_placeholder()
        query = f"""
            SELECT id FROM purchases
            WHERE company_id = {ph}
            ORDER BY id ASC
        """
        results = self.execute_query(query, (company_id,))
        return [r['id'] for r in results if r.get('id') is not None]

    def get_purchase_by_id(self, company_id: int, purchase_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific purchase by ID for a company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT id, purchase_number, purchase_date, party_id, purchase_type,
                   bill_series, nature, due_date, address, gstin, state,
                   narration, sub_total, discount_total, tax_total, round_off,
                   grand_total, amount_paid, COALESCE(status, 'Active') AS status, created_at
            FROM purchases
            WHERE company_id = {ph} AND id = {ph}
        """
        result = self.execute_query(query, (company_id, purchase_id))
        return result[0] if result else None

    def get_purchases_for_gst_report(self, company_id: int, from_date: str, to_date: str, search: str = "") -> List[Dict[str, Any]]:
        """Get active purchases and debit notes for GST purchase reporting.

        Purchase returns are emitted as negative Debit Note rows so ITC totals
        reconcile with net supplier liability. Taxable value remains the item
        net-value sum; invoice value comes from the voucher header grand total.
        """
        ph = self._get_placeholder()
        purchase_search_clause = ""
        return_search_clause = ""
        params = [company_id, from_date, to_date]

        if search:
            purchase_search_clause = (
                f"AND (p.purchase_number LIKE {ph} OR p.supplier_invoice_no LIKE {ph} "
                f"OR pr.name LIKE {ph} OR pr.gstin LIKE {ph})"
            )
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
            params.append(f"%{search}%")

        params.extend([company_id, from_date, to_date])
        if search:
            return_search_clause = (
                f"AND (pur.return_no LIKE {ph} OR pur.supplier_invoice_no LIKE {ph} "
                f"OR pr.name LIKE {ph} OR pr.gstin LIKE {ph})"
            )
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])

        query = f"""
            SELECT report_rows.id, report_rows.voucher_type, report_rows.document_type,
                   report_rows.purchase_number, report_rows.supplier_invoice_no,
                   report_rows.purchase_date, report_rows.party_id, report_rows.party_name,
                   report_rows.supplier_gstin, report_rows.supplier_state,
                   report_rows.purchase_type, report_rows.bill_series, report_rows.nature,
                   report_rows.due_date, report_rows.address, report_rows.bill_gstin,
                   report_rows.bill_state, report_rows.narration, report_rows.sub_total,
                   report_rows.discount_total, report_rows.tax_total, report_rows.freight,
                   report_rows.purchase_expense, report_rows.round_off,
                   report_rows.footer_adjustment, report_rows.grand_total,
                   report_rows.amount_paid, report_rows.taxable_value, report_rows.cgst,
                   report_rows.sgst, report_rows.igst, report_rows.cess,
                   report_rows.item_tax_total
            FROM (
                SELECT
                    p.id AS id,
                    'purchase' AS voucher_type,
                    'Purchase' AS document_type,
                    p.purchase_number AS purchase_number,
                    p.supplier_invoice_no AS supplier_invoice_no,
                    p.purchase_date AS purchase_date,
                    p.party_id AS party_id,
                    pr.name AS party_name,
                    pr.gstin AS supplier_gstin,
                    pr.state AS supplier_state,
                    p.purchase_type AS purchase_type,
                    p.bill_series AS bill_series,
                    p.nature AS nature,
                    p.due_date AS due_date,
                    p.address AS address,
                    p.gstin AS bill_gstin,
                    p.state AS bill_state,
                    p.narration AS narration,
                    COALESCE(p.sub_total, 0) AS sub_total,
                    COALESCE(p.discount_total, 0) AS discount_total,
                    COALESCE(p.tax_total, 0) AS tax_total,
                    COALESCE(p.freight, 0) AS freight,
                    COALESCE(p.purchase_expense, 0) AS purchase_expense,
                    COALESCE(p.round_off, 0) AS round_off,
                    COALESCE(p.grand_total, 0)
                        - COALESCE(item_totals.taxable_value, 0)
                        - COALESCE(item_totals.cgst, 0)
                        - COALESCE(item_totals.sgst, 0)
                        - COALESCE(item_totals.igst, 0)
                        - COALESCE(item_totals.cess, 0) AS footer_adjustment,
                    COALESCE(p.grand_total, 0) AS grand_total,
                    COALESCE(p.amount_paid, 0) AS amount_paid,
                    COALESCE(item_totals.taxable_value, 0) AS taxable_value,
                    COALESCE(item_totals.cgst, 0) AS cgst,
                    COALESCE(item_totals.sgst, 0) AS sgst,
                    COALESCE(item_totals.igst, 0) AS igst,
                    COALESCE(item_totals.cess, 0) AS cess,
                    COALESCE(item_totals.item_tax_total, 0) AS item_tax_total
                FROM purchases p
                LEFT JOIN parties pr ON p.party_id = pr.id
                LEFT JOIN (
                    SELECT purchase_id,
                           SUM(COALESCE(net_value, 0)) AS taxable_value,
                           SUM(COALESCE(cgst_amount, 0)) AS cgst,
                           SUM(COALESCE(sgst_amount, 0)) AS sgst,
                           SUM(COALESCE(igst_amount, 0)) AS igst,
                           SUM(COALESCE(cess_amount, 0)) AS cess,
                           SUM(COALESCE(tax_amount, 0)) AS item_tax_total
                    FROM purchase_items
                    GROUP BY purchase_id
                ) item_totals ON p.id = item_totals.purchase_id
                WHERE p.company_id = {ph}
                  AND p.purchase_date BETWEEN {ph} AND {ph}
                  AND UPPER(COALESCE(p.status, 'Active')) IN ('ACTIVE', 'POSTED', 'FINALIZED', 'FINALISED')
                  AND UPPER(COALESCE(p.status, 'Active')) NOT IN ('DRAFT', 'ESTIMATE', 'VOIDED')
                  {purchase_search_clause}
                UNION ALL
                SELECT
                    pur.id AS id,
                    'purchase_return' AS voucher_type,
                    'Debit Note' AS document_type,
                    pur.return_no AS purchase_number,
                    pur.supplier_invoice_no AS supplier_invoice_no,
                    pur.return_date AS purchase_date,
                    pur.party_id AS party_id,
                    pr.name AS party_name,
                    pr.gstin AS supplier_gstin,
                    pr.state AS supplier_state,
                    pur.return_type AS purchase_type,
                    '' AS bill_series,
                    pur.nature AS nature,
                    NULL AS due_date,
                    '' AS address,
                    pr.gstin AS bill_gstin,
                    pr.state AS bill_state,
                    pur.narration AS narration,
                    -COALESCE(pur.sub_total, 0) AS sub_total,
                    -COALESCE(pur.discount_total, 0) AS discount_total,
                    -COALESCE(pur.tax_total, 0) AS tax_total,
                    0 AS freight,
                    0 AS purchase_expense,
                    -COALESCE(pur.round_off, 0) AS round_off,
                    -COALESCE(pur.grand_total, 0)
                        + COALESCE(return_totals.taxable_value, 0)
                        + COALESCE(return_totals.cgst, 0)
                        + COALESCE(return_totals.sgst, 0)
                        + COALESCE(return_totals.igst, 0)
                        + COALESCE(return_totals.cess, 0) AS footer_adjustment,
                    -COALESCE(pur.grand_total, 0) AS grand_total,
                    -COALESCE(pur.amount_received_or_adjusted, 0) AS amount_paid,
                    -COALESCE(return_totals.taxable_value, 0) AS taxable_value,
                    -COALESCE(return_totals.cgst, 0) AS cgst,
                    -COALESCE(return_totals.sgst, 0) AS sgst,
                    -COALESCE(return_totals.igst, 0) AS igst,
                    -COALESCE(return_totals.cess, 0) AS cess,
                    -COALESCE(return_totals.item_tax_total, 0) AS item_tax_total
                FROM purchase_returns pur
                LEFT JOIN parties pr ON pur.party_id = pr.id
                LEFT JOIN (
                    SELECT purchase_return_id,
                           SUM(COALESCE(net_value, 0)) AS taxable_value,
                           SUM(COALESCE(cgst_amount, 0)) AS cgst,
                           SUM(COALESCE(sgst_amount, 0)) AS sgst,
                           SUM(COALESCE(igst_amount, 0)) AS igst,
                           SUM(COALESCE(cess_amount, 0)) AS cess,
                           SUM(COALESCE(tax_amount, 0)) AS item_tax_total
                    FROM purchase_return_items
                    GROUP BY purchase_return_id
                ) return_totals ON pur.id = return_totals.purchase_return_id
                WHERE pur.company_id = {ph}
                  AND pur.return_date BETWEEN {ph} AND {ph}
                  AND UPPER(COALESCE(pur.status, 'Active')) IN ('ACTIVE', 'POSTED', 'FINALIZED', 'FINALISED')
                  AND UPPER(COALESCE(pur.status, 'Active')) NOT IN ('DRAFT', 'ESTIMATE', 'VOIDED')
                  {return_search_clause}
            ) report_rows
            ORDER BY report_rows.purchase_date DESC, report_rows.id DESC
        """
        rows = self.execute_query(query, params)
        for row in rows:
            if not row.get('tax_total') and row.get('item_tax_total'):
                row['tax_total'] = row.get('item_tax_total')
            row['gstin'] = row.get('supplier_gstin') or row.get('bill_gstin') or ''
            row['state'] = row.get('supplier_state') or row.get('bill_state') or ''
        return rows

    def get_purchase_items(self, purchase_id: int) -> List[Dict[str, Any]]:
        """Get all items for a specific purchase, ordered by sl_no."""
        ph = self._get_placeholder()
        query = f"""
            SELECT id, product_id, sl_no, hsn, tax_percent, unit, rate, quantity,
                   gross_value, discount, net_value, tax_amount, grand_total,
                   cgst, sgst, igst, cess, cgst_amount, sgst_amount, igst_amount, cess_amount
            FROM purchase_items
            WHERE purchase_id = {ph}
            ORDER BY sl_no
        """
        return self.execute_query(query, (purchase_id,))

    def purchase_number_exists(self, company_id: int, purchase_number: str, exclude_purchase_id: Optional[int] = None) -> bool:
        """Check if a purchase number exists for a company (excluding a specific purchase if editing)."""
        ph = self._get_placeholder()
        if exclude_purchase_id:
            query = f"SELECT id FROM purchases WHERE purchase_number = {ph} AND company_id = {ph} AND id != {ph}"
            result = self.execute_query(query, (purchase_number, company_id, exclude_purchase_id))
        else:
            query = f"SELECT id FROM purchases WHERE purchase_number = {ph} AND company_id = {ph}"
            result = self.execute_query(query, (purchase_number, company_id))
        return len(result) > 0

    def save_purchase(self, company_id: int, purchase_data: Dict[str, Any], purchase_items: List[Dict[str, Any]], conn=None, cursor=None) -> Optional[int]:
        """Save a new purchase with its items. Returns purchase_id on success, None on failure.
        
        Args:
            company_id: Company ID
            purchase_data: Purchase header data
            purchase_items: List of purchase items
            conn: Optional external connection for atomic transactions
            cursor: Optional external cursor for atomic transactions
        
        If conn/cursor provided, uses them and does NOT commit/rollback.
        If not provided, creates own connection and commits/rolls back internally.
        """
        own_connection = False
        if conn is None or cursor is None:
            conn = self.connect()
            cursor = conn.cursor()
            own_connection = True
        
        try:
            # Insert purchase header
            timestamp_default = self._get_timestamp_default()
            ph = self._get_placeholder()
            query = f"""
                INSERT INTO purchases (
                    company_id, purchase_number, purchase_date, party_id, purchase_type,
                    bill_series, nature, due_date, address, gstin, state,
                supplier_invoice_no, narration, sub_total, discount_total, tax_total,
                freight, purchase_expense, round_off, grand_total, amount_paid,
                created_at, updated_at
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {timestamp_default}, {timestamp_default})
            """
            params = (
                company_id,
                purchase_data.get('purchase_number'),
                purchase_data.get('purchase_date'),
                purchase_data.get('party_id'),
                purchase_data.get('purchase_type', 'Cash'),
                purchase_data.get('bill_series'),
                purchase_data.get('nature'),
                purchase_data.get('due_date'),
                purchase_data.get('address'),
                purchase_data.get('gstin'),
                purchase_data.get('state'),
                purchase_data.get('supplier_invoice_no'),
                purchase_data.get('narration'),
                purchase_data.get('sub_total', 0.0),
                purchase_data.get('discount_total', 0.0),
                purchase_data.get('tax_total', 0.0),
                purchase_data.get('freight', 0.0),
                purchase_data.get('purchase_expense', 0.0),
                purchase_data.get('round_off', 0.0),
                purchase_data.get('grand_total', 0.0),
                purchase_data.get('amount_paid', 0.0)
            )
            cursor.execute(query, params)
            purchase_id = self._get_last_insert_id(cursor)

            # Insert purchase items with split GST columns
            for item in purchase_items:
                ph = self._get_placeholder()
                query = f"""
                    INSERT INTO purchase_items (
                        purchase_id, product_id, sl_no, hsn, tax_percent, unit, rate, quantity,
                        gross_value, discount, net_value, tax_amount, grand_total, created_at,
                        cgst, sgst, igst, cess, cgst_amount, sgst_amount, igst_amount, cess_amount
                    ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {timestamp_default}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                """
                params = (
                    purchase_id,
                    item.get('product_id'),
                    item.get('sl_no'),
                    item.get('hsn'),
                    item.get('tax_percent', 0.0),
                    item.get('unit'),
                    item.get('rate', 0.0),
                    item.get('quantity', 0.0),
                    item.get('gross_value', 0.0),
                    item.get('discount', 0.0),
                    item.get('net_value', 0.0),
                    item.get('tax_amount', 0.0),
                    item.get('grand_total', 0.0),
                    item.get('cgst', 0.0),
                    item.get('sgst', 0.0),
                    item.get('igst', 0.0),
                    item.get('cess', 0.0),
                    item.get('cgst_amount', 0.0),
                    item.get('sgst_amount', 0.0),
                    item.get('igst_amount', 0.0),
                    item.get('cess_amount', 0.0)
                )
                cursor.execute(query, params)

            # Create stock movements for purchase (stock increases)
            for item in purchase_items:
                ph = self._get_placeholder()
                query = f"""
                    INSERT INTO stock_movements (
                        company_id, product_id, movement_type, quantity, reference_type, reference_id, notes, created_at
                    ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {timestamp_default})
                """
                params = (
                    company_id,
                    item.get('product_id'),
                    'purchase',
                    item.get('quantity', 0.0),
                    'purchase',
                    purchase_id,
                    f"Purchase {purchase_data.get('purchase_number')}"
                )
                cursor.execute(query, params)

            # Update product quantities (for backward compatibility with stock_display)
            for item in purchase_items:
                ph = self._get_placeholder()
                query = f"""
                    UPDATE products
                    SET quantity = COALESCE(quantity, 0) + {ph},
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = {ph} AND company_id = {ph}
                """
                cursor.execute(query, (item.get('quantity', 0.0), item.get('product_id'), company_id))

            # Only commit if we own the connection
            if own_connection:
                conn.commit()
                self.disconnect()
            
            return purchase_id
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            if own_connection and conn:
                try:
                    conn.rollback()
                except sqlite3.Error as rollback_error:
                    print(f"Database error: {rollback_error}")
                    print(f"Rollback error: {rollback_error}")
                self.disconnect()
            print(f"Error saving purchase: {e}")
            raise
        except Exception as e:
            if own_connection and conn:
                try:
                    conn.rollback()
                except sqlite3.Error as rollback_error:
                    print(f"Database error: {rollback_error}")
                    print(f"Rollback error: {rollback_error}")
                self.disconnect()
            print(f"Error saving purchase: {e}")
            raise

    def update_purchase(self, company_id: int, purchase_id: int, purchase_data: Dict[str, Any],
                        conn=None, cursor=None) -> bool:
        """Update the header fields of an existing purchase.

        Items and stock movements are managed separately by purchase_logic
        using delete_purchase_items_by_purchase / insert_purchase_item /
        adjust_purchase_stock_movements.
        """
        ph = self._get_placeholder()
        query = f"""
            UPDATE purchases
            SET purchase_number = {ph},
                purchase_date = {ph},
                party_id = {ph},
                purchase_type = {ph},
                bill_series = {ph},
                nature = {ph},
                due_date = {ph},
                address = {ph},
                gstin = {ph},
                state = {ph},
                supplier_invoice_no = {ph},
                narration = {ph},
                sub_total = {ph},
                discount_total = {ph},
                tax_total = {ph},
                freight = {ph},
                purchase_expense = {ph},
                round_off = {ph},
                grand_total = {ph},
                amount_paid = {ph},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph} AND company_id = {ph}
        """
        params = (
            purchase_data.get('purchase_number'),
            purchase_data.get('purchase_date'),
            purchase_data.get('party_id'),
            purchase_data.get('purchase_type', 'Cash'),
            purchase_data.get('bill_series'),
            purchase_data.get('nature'),
            purchase_data.get('due_date'),
            purchase_data.get('address'),
            purchase_data.get('gstin'),
            purchase_data.get('state'),
            purchase_data.get('supplier_invoice_no'),
            purchase_data.get('narration'),
            purchase_data.get('sub_total', 0.0),
            purchase_data.get('discount_total', 0.0),
            purchase_data.get('tax_total', 0.0),
            purchase_data.get('freight', 0.0),
            purchase_data.get('purchase_expense', 0.0),
            purchase_data.get('round_off', 0.0),
            purchase_data.get('grand_total', 0.0),
            purchase_data.get('amount_paid', 0.0),
            purchase_id,
            company_id
        )
        if cursor is not None:
            cursor.execute(query, params)
            return cursor.rowcount != 0
        return self.execute_update(query, params)

    def delete_purchase(self, company_id: int, purchase_id: int, conn=None, cursor=None) -> bool:
        """Delete a purchase and its items. Returns True on success.

        Stock movements are cleaned up by purchase_logic before this is called
        (via reverse_purchase_stock_movements). This method only deletes the
        purchase header and items (cascade).
        """
        ph = self._get_placeholder()
        query = f"DELETE FROM purchases WHERE id = {ph} AND company_id = {ph}"
        if cursor is not None:
            cursor.execute(query, (purchase_id, company_id))
            return cursor.rowcount != 0
        return self.execute_update(query, (purchase_id, company_id))

    def get_purchase_nav_ids(self, company_id: int) -> List[int]:
        """Get all purchase IDs for navigation, ordered by date desc."""
        ph = self._get_placeholder()
        query = f"""
            SELECT id FROM purchases
            WHERE company_id = {ph}
            ORDER BY purchase_date DESC, id DESC
        """
        result = self.execute_query(query, (company_id,))
        return [row['id'] for row in result]

    # Stock movement methods for stock tracking foundation

    def delete_stock_movements_by_reference(self, reference_type: str, reference_id: int) -> bool:
        """Delete all stock movements for a given reference (purchase, sale, purchase_return, etc.)."""
        ph = self._get_placeholder()
        query = f"DELETE FROM stock_movements WHERE reference_type = {ph} AND reference_id = {ph}"
        return self.execute_update(query, (reference_type, reference_id))

    def set_product_quantity_cache(self, company_id: int, product_id: int, quantity: float) -> bool:
        """Update products.quantity cache directly (authoritative value is stock_movements)."""
        ph = self._get_placeholder()
        query = f"""
            UPDATE products SET quantity = {ph}, updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph} AND company_id = {ph}
        """
        return self.execute_update(query, (quantity, product_id, company_id))

    def batch_sync_product_quantities(self, company_id: int, product_ids: List[int]) -> None:
        """Recalculate and cache products.quantity for each product from stock_movements."""
        if not product_ids:
            return
        for product_id in product_ids:
            balance = self.get_stock_balance_from_movements(company_id, product_id)
            self.set_product_quantity_cache(company_id, product_id, balance)

    def adjust_product_quantity(self, company_id: int, product_id: int, delta: float) -> bool:
        """Increment (delta > 0) or decrement (delta < 0) the on-hand stock
        stored on the products table for a given product.

        Used to keep `products.quantity` in sync with sale/purchase events so
        the stock_display in Sales Entry shows the live on-hand value.
        """
        ph = self._get_placeholder()
        query = f"""
            UPDATE products
            SET quantity = COALESCE(quantity, 0) + {ph},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph} AND company_id = {ph}
        """
        return self.execute_update(query, (delta, product_id, company_id))

    def create_stock_movement(self, company_id: int, product_id: int, movement_type: str,
                            quantity: float, reference_type: Optional[str] = None,
                            reference_id: Optional[int] = None, notes: Optional[str] = None,
                            voucher_type: Optional[str] = None) -> bool:
        """Create a new stock movement entry."""
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO stock_movements (
                company_id, product_id, movement_type, quantity, reference_type, reference_id, notes, voucher_type
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        params = (company_id, product_id, movement_type, quantity, reference_type, reference_id, notes, voucher_type)
        return self.execute_update(query, params)

    def create_stock_movement_with_cursor(self, cursor, company_id: int, product_id: int, movement_type: str,
                                        quantity: float, reference_type: Optional[str] = None,
                                        reference_id: Optional[int] = None, notes: Optional[str] = None,
                                        voucher_type: Optional[str] = None):
        """Create a new stock movement entry using an existing cursor (to avoid nested connections)."""
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO stock_movements (
                company_id, product_id, movement_type, quantity, reference_type, reference_id, notes, voucher_type
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        params = (company_id, product_id, movement_type, quantity, reference_type, reference_id, notes, voucher_type)
        cursor.execute(query, params)
    
    def get_stock_movements_by_product(self, company_id: int, product_id: int) -> List[Dict[str, Any]]:
        """Get all stock movements for a specific product."""
        ph = self._get_placeholder()
        query = f"""
            SELECT id, company_id, product_id, movement_type, quantity, reference_type, reference_id, notes, created_at
            FROM stock_movements
            WHERE company_id = {ph} AND product_id = {ph}
              AND COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')
            ORDER BY created_at DESC
        """
        return self.execute_query(query, (company_id, product_id))
    
    def get_stock_movements_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all stock movements for a specific company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT id, company_id, product_id, movement_type, quantity, reference_type, reference_id, notes, created_at
            FROM stock_movements
            WHERE company_id = {ph}
              AND COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')
            ORDER BY created_at DESC
        """
        return self.execute_query(query, (company_id,))
    
    def get_stock_balance_from_movements(self, company_id: int, product_id: int) -> float:
        """Get the current stock balance for a product from stock movements."""
        ph = self._get_placeholder()
        query = f"""
            SELECT COALESCE(SUM(quantity), 0) as balance
            FROM stock_movements
            WHERE company_id = {ph} AND product_id = {ph}
              AND COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')
        """
        result = self.execute_query(query, (company_id, product_id))
        return float(result[0]['balance']) if result and result[0]['balance'] else 0.0

    def get_stock_balances_for_products(self, company_id: int, product_ids: List[int]) -> Dict[int, float]:
        """Get stock balances for multiple products in a single query.

        Much faster than calling get_stock_balance_from_movements() for each product
        when updating stock after a sale/purchase with multiple items.

        Args:
            company_id: Company ID
            product_ids: List of product IDs to get balances for

        Returns:
            Dictionary mapping product_id to stock balance
        """
        if not product_ids:
            return {}

        # Build placeholders for IN clause
        ph = self._get_placeholder()
        placeholders = ",".join([ph] * len(product_ids))
        query = f"""
            SELECT
                product_id,
                COALESCE(SUM(quantity), 0) as balance
            FROM stock_movements
            WHERE company_id = {ph} AND product_id IN ({placeholders})
              AND COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')
            GROUP BY product_id
        """
        params = [company_id] + list(product_ids)
        results = self.execute_query(query, tuple(params))
        return {r['product_id']: float(r['balance']) if r['balance'] else 0.0 for r in results}

    # Stock Report Methods

    def get_stock_summary_count(self, company_id: int, filters: Dict[str, Any] = None) -> int:
        """Get total count of products for stock summary pagination."""
        filters = filters or {}
        search_text = filters.get('search_text')
        category = filters.get('category')

        ph = self._get_placeholder()
        query = f"""
            SELECT COUNT(*) as count
            FROM products p
            WHERE p.company_id = {ph}
        """
        params = [company_id]

        if search_text:
            query += f" AND (LOWER(p.name) LIKE LOWER({ph}) OR LOWER(p.barcode) LIKE LOWER({ph}))"
            search_pattern = f"%{search_text}%"
            params.extend([search_pattern, search_pattern])

        if category:
            query += f" AND p.category = {ph}"
            params.append(category)

        result = self.execute_query(query, params)
        return result[0]['count'] if result else 0

    def get_stock_summary(self, company_id: int, filters: Dict[str, Any] = None,
                         limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get product-wise stock summary with pagination.
        
        Uses signed stock_movements.quantity as authoritative source.
        Rewritten to use single LEFT JOIN subquery to fix parameter order bug.
        """
        filters = filters or {}
        search_text = filters.get('search_text')
        category = filters.get('category')
        date_from = filters.get('date_from')
        date_to = filters.get('date_to')

        ph = self._get_placeholder()
        
        # Build date filter clauses for movement subquery
        # Use DATE() function to ensure same-day movements are included
        movement_date_filter = ""
        movement_date_params = []
        if date_from:
            movement_date_filter += f" AND DATE(COALESCE(sm.movement_date, sm.created_at)) >= DATE({ph})"
            movement_date_params.append(date_from)
        if date_to:
            movement_date_filter += f" AND DATE(COALESCE(sm.movement_date, sm.created_at)) <= DATE({ph})"
            movement_date_params.append(date_to)

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
                    SUM(CASE WHEN movement_type = 'purchase' THEN quantity ELSE 0 END) as purchase_qty,
                    SUM(CASE WHEN movement_type = 'sale' THEN quantity ELSE 0 END) as sales_qty,
                    SUM(CASE
                        WHEN voucher_type = 'sales_return' OR movement_type = 'sales_return'
                        THEN quantity ELSE 0
                    END) as sales_return_qty,
                    SUM(CASE
                        WHEN voucher_type = 'purchase_return' OR movement_type = 'purchase_return'
                        THEN quantity ELSE 0
                    END) as purchase_return_qty,
                    SUM(CASE
                        WHEN movement_type IN ('adjustment', 'stock_adjustment')
                        THEN quantity
                        ELSE 0
                    END) as adjustment_qty,
                    COALESCE(SUM(quantity), 0) as closing_qty,
                    MAX(COALESCE(created_at, movement_date)) as last_movement_date
                FROM stock_movements sm
                WHERE sm.company_id = {ph}
                AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')
                {movement_date_filter}
                GROUP BY product_id
            ) ms ON ms.product_id = p.id
            WHERE p.company_id = {ph}
        """

        # Parameter order: movement subquery company_id, movement date params, products company_id
        params = [company_id]
        params.extend(movement_date_params)
        params.append(company_id)

        if search_text:
            query += f" AND (LOWER(p.name) LIKE LOWER({ph}) OR LOWER(p.barcode) LIKE LOWER({ph}))"
            search_pattern = f"%{search_text}%"
            params.extend([search_pattern, search_pattern])

        if category:
            query += f" AND p.category = {ph}"
            params.append(category)

        query += f" ORDER BY p.name LIMIT {ph} OFFSET {ph}"
        params.extend([limit, offset])

        # DEBUG: Inspect actual stock_movements data
        try:
            debug_query = f"""
                SELECT movement_type, product_id, quantity, voucher_no
                FROM stock_movements
                WHERE company_id = {ph}
                  AND COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')
                ORDER BY id DESC
                LIMIT 20
            """
            debug_rows = self.execute_query(debug_query, (company_id,))
            print(f"[DEBUG STOCK REPORT] SAMPLE STOCK MOVEMENTS (last 20):")
            for row in debug_rows:
                print(f"  Type: {row.get('movement_type')}, Qty: {row.get('quantity')}, Product: {row.get('product_id')}, Voucher: {row.get('voucher_no')}")

            # DEBUG: Get unique movement types
            unique_types_query = f"""
                SELECT DISTINCT movement_type
                FROM stock_movements
                WHERE company_id = {ph}
                  AND COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')
            """
            unique_types = self.execute_query(unique_types_query, (company_id,))
            print(f"[DEBUG STOCK REPORT] UNIQUE MOVEMENT TYPES = {[mt.get('movement_type') for mt in unique_types]}")

            # DEBUG: Check Shirt example if exists
            shirt_query = f"""
                SELECT p.name, sm.movement_type, sm.quantity, sm.voucher_no
                FROM stock_movements sm
                JOIN products p ON p.id = sm.product_id
                WHERE sm.company_id = {ph}
                  AND LOWER(p.name) LIKE '%shirt%'
                  AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')
                ORDER BY sm.id DESC
            """
            shirt_rows = self.execute_query(shirt_query, (company_id,))
            if shirt_rows:
                print(f"[DEBUG STOCK REPORT] SHIRT MOVEMENTS:")
                for row in shirt_rows:
                    print(f"  Type: {row.get('movement_type')}, Qty: {row.get('quantity')}, Voucher: {row.get('voucher_no')}")
        except Exception as e:
            print(f"[DEBUG STOCK REPORT] Error inspecting stock_movements: {e}")

        result = self.execute_query(query, params)

        # DEBUG: Print sample calculations for validation
        if result:
            print(f"[DEBUG STOCK REPORT] Sample row calculations:")
            for i, row in enumerate(result[:5]):  # Print first 5 rows
                print(f"  Row {i}: {row.get('name')} - Opening: {row.get('opening_qty')}, Purchase: {row.get('purchase_qty')}, Sales: {row.get('sales_qty')}, Sales Return: {row.get('sales_return_qty')}, Purchase Return: {row.get('purchase_return_qty')}, Adjustment: {row.get('adjustment_qty')}, Closing: {row.get('closing_qty')}")
                # Calculate expected closing manually for validation
                expected_closing = (row.get('opening_qty') or 0) + (row.get('purchase_qty') or 0) - (row.get('sales_qty') or 0) + (row.get('sales_return_qty') or 0) + (row.get('purchase_return_qty') or 0) + (row.get('adjustment_qty') or 0)
                print(f"    Expected (manual calc): {expected_closing:.2f}, Actual (SUM quantity): {row.get('closing_qty'):.2f}")

        return result

    def get_stock_ledger_count(self, company_id: int, product_id: int,
                               date_from: str = None, date_to: str = None) -> int:
        """Get total count of stock movements for ledger pagination."""
        ph = self._get_placeholder()
        query = f"""
            SELECT COUNT(*) as count
            FROM stock_movements
            WHERE company_id = {ph} AND product_id = {ph}
              AND COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')
        """
        params = [company_id, product_id]

        if date_from:
            query += f" AND COALESCE(movement_date, created_at) >= {ph}"
            params.append(date_from)
        if date_to:
            query += f" AND COALESCE(movement_date, created_at) <= {ph}"
            params.append(date_to)

        result = self.execute_query(query, params)
        return result[0]['count'] if result else 0

    def get_stock_ledger(self, company_id: int, product_id: int,
                        date_from: str = None, date_to: str = None,
                        limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get movement-wise stock ledger for a specific product."""
        ph = self._get_placeholder()
        query = f"""
            SELECT
                id,
                COALESCE(movement_date, created_at) as movement_date,
                movement_type,
                voucher_type,
                voucher_no,
                notes as narration,
                CASE WHEN quantity > 0 THEN quantity ELSE 0 END as qty_in,
                CASE WHEN quantity < 0 THEN -quantity ELSE 0 END as qty_out,
                COALESCE(rate, 0) as rate,
                COALESCE(value_in, 0) as value_in,
                COALESCE(value_out, 0) as value_out,
                COALESCE(balance_qty, 0) as balance_qty,
                COALESCE(balance_value, 0) as balance_value
            FROM stock_movements
            WHERE company_id = {ph} AND product_id = {ph}
              AND COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')
        """
        params = [company_id, product_id]

        if date_from:
            query += f" AND COALESCE(movement_date, created_at) >= {ph}"
            params.append(date_from)
        if date_to:
            query += f" AND COALESCE(movement_date, created_at) <= {ph}"
            params.append(date_to)

        query += f" ORDER BY COALESCE(movement_date, created_at) ASC LIMIT {ph} OFFSET {ph}"
        params.extend([limit, offset])

        return self.execute_query(query, params)

    def get_negative_stock_count(self, company_id: int, filters: Dict[str, Any] = None) -> int:
        """Get count of products with negative stock."""
        filters = filters or {}
        search_text = filters.get('search_text')

        ph = self._get_placeholder()
        query = f"""
            SELECT COUNT(*) as count
            FROM products p
            WHERE p.company_id = {ph}
              AND COALESCE(
                  (SELECT SUM(sm.quantity)
                  FROM stock_movements sm
                  WHERE sm.company_id = p.company_id
                    AND sm.product_id = p.id
                    AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')),
                  0.0
              ) < 0
        """
        params = [company_id]

        if search_text:
            query += f" AND (LOWER(p.name) LIKE LOWER({ph}) OR LOWER(p.barcode) LIKE LOWER({ph}))"
            search_pattern = f"%{search_text}%"
            params.extend([search_pattern, search_pattern])

        result = self.execute_query(query, params)
        return result[0]['count'] if result else 0

    def get_negative_stock(self, company_id: int, filters: Dict[str, Any] = None,
                           limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get products with negative stock."""
        filters = filters or {}
        search_text = filters.get('search_text')

        ph = self._get_placeholder()
        query = f"""
            SELECT
                p.id,
                p.name,
                p.barcode,
                p.category,
                p.unit,
                COALESCE(
                    (SELECT SUM(sm.quantity)
                    FROM stock_movements sm
                    WHERE sm.company_id = p.company_id
                      AND sm.product_id = p.id
                      AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')),
                    0.0
                ) as closing_qty,
                p.purchase_rate,
                p.sale_price
            FROM products p
            WHERE p.company_id = {ph}
              AND COALESCE(
                  (SELECT SUM(sm.quantity)
                  FROM stock_movements sm
                  WHERE sm.company_id = p.company_id
                    AND sm.product_id = p.id
                    AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')),
                  0.0
              ) < 0
        """
        params = [company_id]

        if search_text:
            query += f" AND (LOWER(p.name) LIKE LOWER({ph}) OR LOWER(p.barcode) LIKE LOWER({ph}))"
            search_pattern = f"%{search_text}%"
            params.extend([search_pattern, search_pattern])

        query += f" ORDER BY p.name LIMIT {ph} OFFSET {ph}"
        params.extend([limit, offset])

        return self.execute_query(query, params)

    def get_low_stock_count(self, company_id: int, filters: Dict[str, Any] = None) -> int:
        """Get count of products below reorder level."""
        filters = filters or {}
        search_text = filters.get('search_text')

        ph = self._get_placeholder()
        query = f"""
            SELECT COUNT(*) as count
            FROM products p
            WHERE p.company_id = {ph}
              AND p.reorder_level > 0
              AND COALESCE(
                  (SELECT SUM(sm.quantity)
                  FROM stock_movements sm
                  WHERE sm.company_id = p.company_id
                    AND sm.product_id = p.id
                    AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')),
                  0.0
              ) <= p.reorder_level
        """
        params = [company_id]

        if search_text:
            query += f" AND (LOWER(p.name) LIKE LOWER({ph}) OR LOWER(p.barcode) LIKE LOWER({ph}))"
            search_pattern = f"%{search_text}%"
            params.extend([search_pattern, search_pattern])

        result = self.execute_query(query, params)
        return result[0]['count'] if result else 0

    def get_low_stock(self, company_id: int, filters: Dict[str, Any] = None,
                      limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get products below reorder level."""
        filters = filters or {}
        search_text = filters.get('search_text')

        ph = self._get_placeholder()
        query = f"""
            SELECT
                p.id,
                p.name,
                p.barcode,
                p.category,
                p.unit,
                p.reorder_level,
                COALESCE(
                    (SELECT SUM(sm.quantity)
                    FROM stock_movements sm
                    WHERE sm.company_id = p.company_id
                      AND sm.product_id = p.id
                      AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')),
                    0.0
                ) as closing_qty,
                p.purchase_rate,
                p.sale_price
            FROM products p
            WHERE p.company_id = {ph}
              AND p.reorder_level > 0
              AND COALESCE(
                  (SELECT SUM(sm.quantity)
                  FROM stock_movements sm
                  WHERE sm.company_id = p.company_id
                    AND sm.product_id = p.id
                    AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')),
                  0.0
              ) <= p.reorder_level
        """
        params = [company_id]

        if search_text:
            query += f" AND (LOWER(p.name) LIKE LOWER({ph}) OR LOWER(p.barcode) LIKE LOWER({ph}))"
            search_pattern = f"%{search_text}%"
            params.extend([search_pattern, search_pattern])

        query += f" ORDER BY p.name LIMIT {ph} OFFSET {ph}"
        params.extend([limit, offset])

        return self.execute_query(query, params)

    def get_zero_stock_count(self, company_id: int, filters: Dict[str, Any] = None) -> int:
        """Get count of products with zero stock."""
        filters = filters or {}
        search_text = filters.get('search_text')

        ph = self._get_placeholder()
        query = f"""
            SELECT COUNT(*) as count
            FROM products p
            WHERE p.company_id = {ph}
              AND COALESCE(
                  (SELECT SUM(sm.quantity)
                  FROM stock_movements sm
                  WHERE sm.company_id = p.company_id
                    AND sm.product_id = p.id
                    AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')),
                  0.0
              ) = 0
        """
        params = [company_id]

        if search_text:
            query += f" AND (LOWER(p.name) LIKE LOWER({ph}) OR LOWER(p.barcode) LIKE LOWER({ph}))"
            search_pattern = f"%{search_text}%"
            params.extend([search_pattern, search_pattern])

        result = self.execute_query(query, params)
        return result[0]['count'] if result else 0

    def get_zero_stock(self, company_id: int, filters: Dict[str, Any] = None,
                      limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get products with zero stock."""
        filters = filters or {}
        search_text = filters.get('search_text')

        ph = self._get_placeholder()
        query = f"""
            SELECT
                p.id,
                p.name,
                p.barcode,
                p.category,
                p.unit,
                COALESCE(
                    (SELECT SUM(sm.quantity)
                    FROM stock_movements sm
                    WHERE sm.company_id = p.company_id
                      AND sm.product_id = p.id
                      AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')),
                    0.0
                ) as closing_qty,
                p.purchase_rate,
                p.sale_price
            FROM products p
            WHERE p.company_id = {ph}
              AND COALESCE(
                  (SELECT SUM(sm.quantity)
                  FROM stock_movements sm
                  WHERE sm.company_id = p.company_id
                    AND sm.product_id = p.id
                    AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')),
                  0.0
              ) = 0
        """
        params = [company_id]

        if search_text:
            query += f" AND (LOWER(p.name) LIKE LOWER({ph}) OR LOWER(p.barcode) LIKE LOWER({ph}))"
            search_pattern = f"%{search_text}%"
            params.extend([search_pattern, search_pattern])

        query += f" ORDER BY p.name LIMIT {ph} OFFSET {ph}"
        params.extend([limit, offset])

        return self.execute_query(query, params)

    def get_fast_moving_products(self, company_id: int, date_from: str, date_to: str,
                                 limit: int = 50) -> List[Dict[str, Any]]:
        """Get fast-moving products based on sales volume (future-ready)."""
        # Placeholder for future implementation
        return []

    def get_slow_moving_products(self, company_id: int, date_from: str, date_to: str,
                                 limit: int = 50) -> List[Dict[str, Any]]:
        """Get slow-moving products based on sales volume (future-ready)."""
        # Placeholder for future implementation
        return []

    def get_stock_value(self, company_id: int, filters: Dict[str, Any] = None) -> float:
        """Get total stock valuation."""
        filters = filters or {}
        search_text = filters.get('search_text')

        ph = self._get_placeholder()
        query = f"""
            SELECT
                SUM(
                    COALESCE(
                        (SELECT SUM(sm.quantity)
                        FROM stock_movements sm
                        WHERE sm.company_id = p.company_id
                          AND sm.product_id = p.id
                          AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')),
                        0.0
                    ) * COALESCE(p.purchase_rate, 0)
                ) as total_value
            FROM products p
            WHERE p.company_id = {ph}
        """
        params = [company_id]

        if search_text:
            query += f" AND (LOWER(p.name) LIKE LOWER({ph}) OR LOWER(p.barcode) LIKE LOWER({ph}))"
            search_pattern = f"%{search_text}%"
            params.extend([search_pattern, search_pattern])

        result = self.execute_query(query, params)
        return float(result[0]['total_value']) if result and result[0]['total_value'] else 0.0

    def get_stock_summary_stats(self, company_id: int, filters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Get summary statistics for stock report dashboard."""
        filters = filters or {}

        # Get total products count
        total_products = self.get_product_count(company_id)

        # Get total stock qty
        ph = self._get_placeholder()
        query = f"""
            SELECT
                SUM(COALESCE(
                    (SELECT SUM(sm.quantity)
                    FROM stock_movements sm
                    WHERE sm.company_id = p.company_id
                      AND sm.product_id = p.id
                      AND COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')),
                    0.0
                )) as total_qty
            FROM products p
            WHERE p.company_id = {ph}
        """
        result = self.execute_query(query, (company_id,))
        total_qty = float(result[0]['total_qty']) if result and result[0]['total_qty'] else 0.0

        # Get total stock value
        total_value = self.get_stock_value(company_id, filters)

        # Get negative stock count
        negative_count = self.get_negative_stock_count(company_id, filters)

        # Get zero stock count
        zero_count = self.get_zero_stock_count(company_id, filters)

        return {
            'total_products': total_products,
            'total_qty': total_qty,
            'total_value': total_value,
            'negative_count': negative_count,
            'zero_count': zero_count
        }

    def rebuild_stock_balances(self, company_id: int) -> bool:
        """Rebuild stock balances from movements (audit/support method)."""
        try:
            conn = self._connect()
            cursor = conn.cursor()
            ph = self._get_placeholder()

            # Get all products for the company
            cursor.execute(f"SELECT id FROM products WHERE company_id = {ph}", (company_id,))
            product_ids = [row[0] for row in cursor.fetchall()]

            # Recalculate balance for each product
            for product_id in product_ids:
                balance = self.get_stock_balance_from_movements(company_id, product_id)

                # Update all movements with running balance
                query = f"""
                    SELECT id, movement_type, quantity, COALESCE(movement_date, created_at) as movement_date
                    FROM stock_movements
                    WHERE company_id = {ph} AND product_id = {ph}
                      AND COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')
                    ORDER BY COALESCE(movement_date, created_at) ASC
                """
                cursor.execute(query, (company_id, product_id))
                movements = cursor.fetchall()

                running_balance = 0.0
                for movement in movements:
                    movement_id = movement[0]
                    movement_type = movement[1]
                    quantity = movement[2]

                    running_balance += quantity

                    # Update balance_qty
                    cursor.execute(
                        f"UPDATE stock_movements SET balance_qty = {ph} WHERE id = {ph}",
                        (running_balance, movement_id)
                    )

            conn.commit()
            return True
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Error rebuilding stock balances: {e}")
            return False
        finally:
            self.disconnect()

    # Sales methods for Sales Entry module

    def get_salesmen(self) -> List[Dict[str, Any]]:
        """Return all salesmen ordered by name."""
        query = """
            SELECT id, name
            FROM salesmen
            ORDER BY name
        """
        return self.execute_query(query)

    def insert_salesman(self, name: str) -> Optional[int]:
        """Insert a salesman name and return its id."""
        cleaned_name = str(name or "").strip()
        if not cleaned_name:
            return None

        ph = self._get_placeholder()
        try:
            self.execute_update(
                f"INSERT INTO salesmen (name) VALUES ({ph})",
                (cleaned_name,),
            )
        except Exception as exc:
            print(f"Error inserting salesman: {exc}")
            existing = self.execute_query(
                f"SELECT id FROM salesmen WHERE name = {ph}",
                (cleaned_name,),
            )
            return existing[0]["id"] if existing else None

        result = self.execute_query(
            f"SELECT id FROM salesmen WHERE name = {ph}",
            (cleaned_name,),
        )
        return result[0]["id"] if result else None

    def insert_sale(self, company_id: int, sale_data: Dict[str, Any], conn=None, cursor=None) -> int:
        """Insert a new sale for a company and return the sale ID."""
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO sales (
                company_id, invoice_number, invoice_date, party_id, sales_type,
                bill_series, nature, due_date, address, gstin, state,
                sales_rate, narration, salesman, sub_total, discount_total, tax_total,
                round_off, grand_total, amount_received, payment_mode
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        params = (
            company_id,
            sale_data.get('invoice_number'),
            sale_data.get('invoice_date'),
            sale_data.get('party_id'),
            sale_data.get('sales_type', 'Sales'),
            sale_data.get('bill_series'),
            sale_data.get('nature'),
            sale_data.get('due_date'),
            sale_data.get('address'),
            sale_data.get('gstin'),
            sale_data.get('state'),
            sale_data.get('sales_rate', 'Exclusive'),
            sale_data.get('narration'),
            sale_data.get('salesman'),
            sale_data.get('sub_total', 0.0),
            sale_data.get('discount_total', 0.0),
            sale_data.get('tax_total', 0.0),
            sale_data.get('round_off', 0.0),
            sale_data.get('grand_total', 0.0),
            sale_data.get('amount_received', 0.0),
            sale_data.get('payment_mode', 'Cash'),
        )
        if cursor is not None:
            cursor.execute(query, params)
            return self._get_last_insert_id(cursor)

        self.execute_update(query, params)

        # NOTE: execute_update closes the connection in `finally`, so SQLite's
        # last_insert_rowid() on a fresh connection returns 0. Look up the id
        # via the UNIQUE(company_id, invoice_number) index instead — this works
        # correctly for both SQLite and MySQL.
        ph = self._get_placeholder()
        lookup_query = f"SELECT id FROM sales WHERE company_id = {ph} AND invoice_number = {ph}"
        result = self.execute_query(
            lookup_query,
            (company_id, sale_data.get('invoice_number'))
        )
        return result[0]['id'] if result else None

    def update_sale(self, company_id: int, sale_id: int, sale_data: Dict[str, Any],
                    conn=None, cursor=None) -> bool:
        """Update the header fields of an existing sale."""
        ph = self._get_placeholder()
        query = f"""
            UPDATE sales
            SET invoice_number = {ph},
                invoice_date = {ph},
                party_id = {ph},
                sales_type = {ph},
                bill_series = {ph},
                nature = {ph},
                due_date = {ph},
                address = {ph},
                gstin = {ph},
                state = {ph},
                sales_rate = {ph},
                narration = {ph},
                salesman = {ph},
                sub_total = {ph},
                discount_total = {ph},
                tax_total = {ph},
                round_off = {ph},
                grand_total = {ph},
                amount_received = {ph},
                payment_mode = {ph},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph} AND company_id = {ph}
        """
        params = (
            sale_data.get('invoice_number'),
            sale_data.get('invoice_date'),
            sale_data.get('party_id'),
            sale_data.get('sales_type', 'Sales'),
            sale_data.get('bill_series'),
            sale_data.get('nature'),
            sale_data.get('due_date'),
            sale_data.get('address'),
            sale_data.get('gstin'),
            sale_data.get('state'),
            sale_data.get('sales_rate', 'Exclusive'),
            sale_data.get('narration'),
            sale_data.get('salesman'),
            sale_data.get('sub_total', 0.0),
            sale_data.get('discount_total', 0.0),
            sale_data.get('tax_total', 0.0),
            sale_data.get('round_off', 0.0),
            sale_data.get('grand_total', 0.0),
            sale_data.get('amount_received', 0.0),
            sale_data.get('payment_mode', 'Cash'),
            sale_id,
            company_id,
        )
        if cursor is not None:
            cursor.execute(query, params)
            return cursor.rowcount != 0
        return self.execute_update(query, params)

    def delete_sale_items_by_sale(self, sale_id: int, conn=None, cursor=None) -> bool:
        """Delete all line items for a given sale id."""
        ph = self._get_placeholder()
        query = f"DELETE FROM sales_items WHERE sale_id = {ph}"
        if cursor is not None:
            cursor.execute(query, (sale_id,))
            return True
        return self.execute_update(query, (sale_id,))

    def delete_stock_movements_by_reference(self, reference_type: str, reference_id: int,
                                            conn=None, cursor=None) -> bool:
        """Delete stock movements tied to a reference (e.g. a sale)."""
        ph = self._get_placeholder()
        query = f"DELETE FROM stock_movements WHERE reference_type = {ph} AND reference_id = {ph}"
        if cursor is not None:
            cursor.execute(query, (reference_type, reference_id))
            return True
        return self.execute_update(query, (reference_type, reference_id))

    def set_product_quantity_cache(self, company_id: int, product_id: int, quantity: float) -> bool:
        """Set products.quantity as a display cache from movement balance.

        This is NOT the authoritative stock source — use get_stock_balance_from_movements()
        for authoritative values. This only syncs the cache column.
        """
        ph = self._get_placeholder()
        query = f"""
            UPDATE products
            SET quantity = {ph}, updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph} AND company_id = {ph}
        """
        return self.execute_update(query, (quantity, product_id, company_id))

    def batch_sync_product_quantities(self, company_id: int, product_ids: List[int],
                                      conn=None, cursor=None) -> bool:
        """Sync products.quantity cache for multiple products in 2 queries.

        1 query to get all balances, then 1 UPDATE per product via executemany.
        Much faster than N calls to sync_product_quantity_from_movements().

        Args:
            company_id: Company ID
            product_ids: List of product IDs to sync

        Returns:
            True if successful
        """
        if not product_ids:
            return True
        try:
            ph = self._get_placeholder()
            if cursor is not None:
                placeholders = ", ".join([ph] * len(product_ids))
                cursor.execute(
                    f"""
                    SELECT product_id, COALESCE(SUM(quantity), 0.0) AS balance
                    FROM stock_movements
                    WHERE company_id = {ph}
                      AND product_id IN ({placeholders})
                      AND COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')
                    GROUP BY product_id
                    """,
                    tuple([company_id] + list(product_ids))
                )
                balances = {int(row[0]): float(row[1] or 0.0) for row in cursor.fetchall()}
            else:
                # Single query to get all balances
                balances = self.get_stock_balances_for_products(company_id, product_ids)
            if not balances:
                return True
            # Batch update using executemany
            owns_connection = cursor is None
            if owns_connection:
                conn = self.connect()
                cursor = conn.cursor()
            update_data = [
                (balances.get(pid, 0.0), pid, company_id)
                for pid in product_ids
                if pid in balances
            ]
            cursor.executemany(
                f"UPDATE products SET quantity = {ph}, updated_at = CURRENT_TIMESTAMP WHERE id = {ph} AND company_id = {ph}",
                update_data
            )
            if owns_connection:
                conn.commit()
            return True
        except Exception as e:
            print(f"Error in batch_sync_product_quantities: {e}")
            return False

    def delete_purchase_items_by_purchase(self, purchase_id: int, conn=None, cursor=None) -> bool:
        """Delete all line items for a given purchase id."""
        ph = self._get_placeholder()
        query = f"DELETE FROM purchase_items WHERE purchase_id = {ph}"
        if cursor is not None:
            cursor.execute(query, (purchase_id,))
            return True
        return self.execute_update(query, (purchase_id,))

    def insert_purchase_item(self, purchase_id: int, item_data: Dict[str, Any],
                             conn=None, cursor=None) -> bool:
        """Insert a purchase item for a purchase."""
        timestamp_default = self._get_timestamp_default()
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO purchase_items (
                purchase_id, product_id, sl_no, hsn, tax_percent, unit, rate, quantity,
                gross_value, discount, net_value, tax_amount, grand_total, created_at,
                cgst, sgst, igst, cess, cgst_amount, sgst_amount, igst_amount, cess_amount
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {timestamp_default}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        params = (
            purchase_id,
            item_data.get('product_id'),
            item_data.get('sl_no'),
            item_data.get('hsn'),
            item_data.get('tax_percent', 0.0),
            item_data.get('unit'),
            item_data.get('rate', 0.0),
            item_data.get('quantity', 0.0),
            item_data.get('gross_value', 0.0),
            item_data.get('discount', 0.0),
            item_data.get('net_value', 0.0),
            item_data.get('tax_amount', 0.0),
            item_data.get('grand_total', 0.0),
            item_data.get('cgst', 0.0),
            item_data.get('sgst', 0.0),
            item_data.get('igst', 0.0),
            item_data.get('cess', 0.0),
            item_data.get('cgst_amount', 0.0),
            item_data.get('sgst_amount', 0.0),
            item_data.get('igst_amount', 0.0),
            item_data.get('cess_amount', 0.0)
        )
        if cursor is not None:
            cursor.execute(query, params)
            return True
        return self.execute_update(query, params)

    def insert_sale_item(self, sale_id: int, item_data: Dict[str, Any],
                         conn=None, cursor=None) -> int:
        """Insert a sale item for a sale."""
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO sales_items (
                sale_id, product_id, sl_no, hsn, tax_percent, unit, rate,
                quantity, gross_value, discount, net_value, tax_amount, grand_total,
                cgst, sgst, igst, cess, cgst_amount, sgst_amount, igst_amount, cess_amount,
                cost_price, cost_value
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        params = (
            sale_id,
            item_data.get('product_id'),
            item_data.get('sl_no'),
            item_data.get('hsn'),
            item_data.get('tax_percent', 0.0),
            item_data.get('unit'),
            item_data.get('rate', 0.0),
            item_data.get('quantity', 0.0),
            item_data.get('gross_value', 0.0),
            item_data.get('discount', 0.0),
            item_data.get('net_value', 0.0),
            item_data.get('tax_amount', 0.0),
            item_data.get('grand_total', 0.0),
            item_data.get('cgst', 0.0),
            item_data.get('sgst', 0.0),
            item_data.get('igst', 0.0),
            item_data.get('cess', 0.0),
            item_data.get('cgst_amount', 0.0),
            item_data.get('sgst_amount', 0.0),
            item_data.get('igst_amount', 0.0),
            item_data.get('cess_amount', 0.0),
            item_data.get('cost_price', 0.0),
            item_data.get('cost_value', 0.0)
        )
        if cursor is not None:
            cursor.execute(query, params)
            return self._get_last_insert_id(cursor)
        return self.execute_update(query, params)

    def get_sales_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all sales for a specific company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT s.id, s.invoice_number, s.invoice_date, s.party_id, p.name as party_name,
                   s.sales_type, s.bill_series, s.nature, s.due_date, s.sales_rate,
                   s.sub_total, s.discount_total, s.tax_total, s.round_off, s.grand_total,
                   s.amount_received, COALESCE(s.status, 'Active') AS status, s.created_at
            FROM sales s
            LEFT JOIN parties p ON s.party_id = p.id
            WHERE s.company_id = {ph}
            ORDER BY s.invoice_date DESC, s.id DESC
        """
        return self.execute_query(query, (company_id,))

    def get_sales_by_party(self, company_id: int, party_id: int) -> List[Dict[str, Any]]:
        """Get all sales for a specific party."""
        ph = self._get_placeholder()
        query = f"""
            SELECT s.id, s.invoice_number, s.invoice_date, s.party_id, p.name as party_name,
                   s.sales_type, s.bill_series, s.nature, s.due_date, s.sales_rate,
                   s.sub_total, s.discount_total, s.tax_total, s.round_off, s.grand_total,
                   s.amount_received, COALESCE(s.status, 'Active') AS status, s.created_at
            FROM sales s
            LEFT JOIN parties p ON s.party_id = p.id
            WHERE s.company_id = {ph} AND s.party_id = {ph}
            ORDER BY s.invoice_date DESC, s.id DESC
        """
        return self.execute_query(query, (company_id, party_id))

    def get_vouchers_before_date(
        self,
        company_id: int,
        party_id: int,
        voucher_type: str,
        voucher_id: Optional[int] = None,
        voucher_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all vouchers for a party before a specific voucher date/id.

        This is used for balance calculation to exclude current and future vouchers.

        Args:
            company_id: Company ID
            party_id: Party ID
            voucher_type: Type of current voucher ('sales', 'purchase', 'sales_return', 'purchase_return')
            voucher_id: ID of current voucher (to exclude)
            voucher_date: Date of current voucher (for date-based exclusion)

        Returns:
            List of vouchers with voucher_type, voucher_date, voucher_id, grand_total, amount_received/amount_paid
        """
        vouchers = []

        ph = self._get_placeholder()
        # Get sales before current voucher
        if voucher_type in ['sales', 'sales_return']:
            sales_query = f"""
                SELECT 'sales' as voucher_type, s.id as voucher_id, s.invoice_date as voucher_date,
                       s.grand_total, s.amount_received AS amount_received,
                       s.amount_received AS amount_received_or_paid
                FROM sales s
                WHERE s.company_id = {ph} AND s.party_id = {ph}
                  AND COALESCE(s.status, 'Active') <> 'Voided'
            """
            params = [company_id, party_id]

            # Add date filter if provided
            if voucher_date:
                sales_query += f" AND s.invoice_date < {ph}"
                params.append(voucher_date)
            elif voucher_id:
                # If no date but has ID, use ID ordering
                sales_query += f" AND s.id < {ph}"
                params.append(voucher_id)

            sales_query += " ORDER BY s.invoice_date ASC, s.id ASC"
            sales = self.execute_query(sales_query, tuple(params))
            vouchers.extend(sales)

        # Get purchases before current voucher
        if voucher_type in ['purchase', 'purchase_return']:
            purchase_query = f"""
                SELECT 'purchase' as voucher_type, p.id as voucher_id, p.purchase_date as voucher_date,
                       p.grand_total, p.amount_paid AS amount_paid,
                       p.amount_paid AS amount_received_or_paid
                FROM purchases p
                WHERE p.company_id = {ph} AND p.party_id = {ph}
                  AND COALESCE(p.status, 'Active') <> 'Voided'
            """
            params = [company_id, party_id]

            # Add date filter if provided
            if voucher_date:
                purchase_query += f" AND p.purchase_date < {ph}"
                params.append(voucher_date)
            elif voucher_id:
                # If no date but has ID, use ID ordering
                purchase_query += f" AND p.id < {ph}"
                params.append(voucher_id)

            purchase_query += " ORDER BY p.purchase_date ASC, p.id ASC"
            purchases = self.execute_query(purchase_query, tuple(params))
            vouchers.extend(purchases)

        # Get sales returns before current voucher
        if voucher_type == 'sales_return':
            sales_return_query = f"""
                SELECT 'sales_return' as voucher_type, sr.id as voucher_id, sr.return_date as voucher_date,
                       sr.grand_total, sr.amount_refunded_or_adjusted AS amount_received,
                       sr.amount_refunded_or_adjusted AS amount_received_or_paid
                FROM sales_returns sr
                WHERE sr.company_id = {ph} AND sr.party_id = {ph}
                  AND COALESCE(sr.status, 'Active') <> 'Voided'
            """
            params = [company_id, party_id]

            # Add date filter if provided
            if voucher_date:
                sales_return_query += f" AND sr.return_date < {ph}"
                params.append(voucher_date)
            elif voucher_id:
                # If no date but has ID, use ID ordering
                sales_return_query += f" AND sr.id < {ph}"
                params.append(voucher_id)

            sales_return_query += " ORDER BY sr.return_date ASC, sr.id ASC"
            sales_returns = self.execute_query(sales_return_query, tuple(params))
            vouchers.extend(sales_returns)

        # Get purchase returns before current voucher
        if voucher_type == 'purchase_return':
            purchase_return_query = f"""
                SELECT 'purchase_return' as voucher_type, pr.id as voucher_id, pr.return_date as voucher_date,
                       pr.grand_total, pr.amount_received_or_adjusted AS amount_paid,
                       pr.amount_received_or_adjusted AS amount_received_or_paid
                FROM purchase_returns pr
                WHERE pr.company_id = {ph} AND pr.party_id = {ph}
                  AND COALESCE(pr.status, 'Active') <> 'Voided'
            """
            params = [company_id, party_id]

            # Add date filter if provided
            if voucher_date:
                purchase_return_query += f" AND pr.return_date < {ph}"
                params.append(voucher_date)
            elif voucher_id:
                # If no date but has ID, use ID ordering
                purchase_return_query += f" AND pr.id < {ph}"
                params.append(voucher_id)

            purchase_return_query += " ORDER BY pr.return_date ASC, pr.id ASC"
            purchase_returns = self.execute_query(purchase_return_query, tuple(params))
            vouchers.extend(purchase_returns)

        return vouchers

    def get_sale_ids_by_company(self, company_id: int) -> List[int]:
        """Get only sale IDs for a specific company - optimized for navigation.

        This is much faster than get_sales_by_company() for prev/next navigation
        because it doesn't JOIN with parties or return full rows.
        """
        ph = self._get_placeholder()
        query = f"""
            SELECT id FROM sales
            WHERE company_id = {ph}
            ORDER BY id ASC
        """
        results = self.execute_query(query, (company_id,))
        return [r['id'] for r in results if r.get('id') is not None]

    def get_sale_by_id(self, company_id: int, sale_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific sale by ID for a company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT s.id, s.invoice_number, s.invoice_date, s.party_id, p.name as party_name,
                   p.mobile_number, p.address, p.gstin, s.sales_type, s.bill_series, s.nature,
                   s.due_date, s.address, s.gstin, s.state, s.sales_rate, s.narration, s.salesman,
                   s.form_of_sale,
                   s.sub_total, s.discount_total, s.tax_total, s.round_off, s.grand_total,
                   s.amount_received, COALESCE(s.payment_mode, 'Cash') AS payment_mode,
                   COALESCE(s.status, 'Active') AS status
            FROM sales s
            LEFT JOIN parties p ON s.party_id = p.id
            WHERE s.company_id = {ph} AND s.id = {ph}
        """
        result = self.execute_query(query, (company_id, sale_id))
        return result[0] if result else None

    def get_sales_for_gst_report(self, company_id: int, from_date: str, to_date: str, search: str = "") -> List[Dict[str, Any]]:
        """Get sales data for GST report with tax breakdown.

        Returns one row per sales invoice with explicit party aliases and aggregated
        item GST amount fields. The aliases prevent duplicate field-name collisions
        and keep GST Sales Report classification stable.
        """
        ph = self._get_placeholder()
        search_clause = ""
        params = [company_id, from_date, to_date]

        if search:
            search_clause = f"AND (s.invoice_number LIKE {ph} OR p.name LIKE {ph} OR p.gstin LIKE {ph})"
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

        query = f"""
            SELECT
                s.id, s.invoice_number, s.invoice_date, s.party_id, p.name as party_name,
                p.gstin as party_gstin, p.state as party_state,
                s.sales_type, s.bill_series, s.nature, s.due_date,
                s.address, s.gstin as bill_gstin, s.state as bill_state, s.sales_rate, s.narration, s.form_of_sale,
                s.sub_total, s.discount_total, s.tax_total, s.round_off, s.grand_total,
                s.amount_received,
                COALESCE(SUM(si.net_value), 0) as taxable_value,
                COALESCE(SUM(si.cgst_amount), 0) as cgst,
                COALESCE(SUM(si.sgst_amount), 0) as sgst,
                COALESCE(SUM(si.igst_amount), 0) as igst,
                COALESCE(SUM(si.cess_amount), 0) as cess,
                COALESCE(SUM(si.tax_amount), 0) as item_tax_total
            FROM sales s
            LEFT JOIN parties p ON s.party_id = p.id
            LEFT JOIN sales_items si ON s.id = si.sale_id
            WHERE s.company_id = {ph}
              AND s.invoice_date BETWEEN {ph} AND {ph}
              AND COALESCE(s.status, 'Active') <> 'Voided'
              {search_clause}
            GROUP BY s.id
            ORDER BY s.invoice_date DESC, s.id DESC
        """
        rows = self.execute_query(query, params)
        for row in rows:
            if not row.get('tax_total') and row.get('item_tax_total'):
                row['tax_total'] = row.get('item_tax_total')
            row['gstin'] = row.get('party_gstin') or row.get('bill_gstin') or ''
            row['state'] = row.get('party_state') or row.get('bill_state') or ''
        return rows

    def get_sale_items(self, sale_id: int) -> List[Dict[str, Any]]:
        """Get all items for a specific sale."""
        ph = self._get_placeholder()
        query = f"""
            SELECT si.id, si.sale_id, si.product_id, pr.name as product_name, pr.barcode,
                   si.sl_no, si.hsn, si.tax_percent, si.unit, si.rate,
                   si.quantity, si.gross_value, si.discount, si.net_value, si.tax_amount, si.grand_total,
                   si.cgst, si.sgst, si.igst, si.cess, si.cgst_amount, si.sgst_amount, si.igst_amount, si.cess_amount
            FROM sales_items si
            LEFT JOIN products pr ON si.product_id = pr.id
            WHERE si.sale_id = {ph}
            ORDER BY si.sl_no
        """
        return self.execute_query(query, (sale_id,))

    def invoice_number_exists(self, company_id: int, invoice_number: str, exclude_sale_id: Optional[int] = None) -> bool:
        """Check if an invoice number exists for a company (excluding a specific sale if editing)."""
        ph = self._get_placeholder()
        if exclude_sale_id:
            query = f"SELECT id FROM sales WHERE invoice_number = {ph} AND company_id = {ph} AND id != {ph}"
            result = self.execute_query(query, (invoice_number, company_id, exclude_sale_id))
        else:
            query = f"SELECT id FROM sales WHERE invoice_number = {ph} AND company_id = {ph}"
            result = self.execute_query(query, (invoice_number, company_id))
        return len(result) > 0

    # Sales Return methods
    def insert_sales_return(self, company_id: int, sales_return_data: Dict[str, Any]) -> int:
        """Insert a new sales return for a company and return the sales_return ID."""
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO sales_returns (
                company_id, return_no, return_date, original_bill_id, original_bill_no, party_id,
                return_type, nature, narration, sub_total, discount_total, tax_total,
                round_off, grand_total, amount_refunded_or_adjusted, balance_adjustment
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        params = (
            company_id,
            sales_return_data.get('return_no'),
            sales_return_data.get('return_date'),
            sales_return_data.get('original_bill_id'),
            sales_return_data.get('original_bill_no'),
            sales_return_data.get('party_id'),
            sales_return_data.get('return_type', 'Cash'),
            sales_return_data.get('nature'),
            sales_return_data.get('narration'),
            sales_return_data.get('sub_total', 0.0),
            sales_return_data.get('discount_total', 0.0),
            sales_return_data.get('tax_total', 0.0),
            sales_return_data.get('round_off', 0.0),
            sales_return_data.get('grand_total', 0.0),
            sales_return_data.get('amount_refunded_or_adjusted', 0.0),
            sales_return_data.get('balance_adjustment', 0.0)
        )
        self.execute_update(query, params)
        ph = self._get_placeholder()
        result = self.execute_query(
            f"SELECT id FROM sales_returns WHERE company_id = {ph} AND return_no = {ph}",
            (company_id, sales_return_data.get('return_no'))
        )
        return result[0]['id'] if result else None

    def insert_sales_return_item(self, sales_return_id: int, item_data: Dict[str, Any]) -> bool:
        """Insert a sales return item for a sales return."""
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO sales_return_items (
                sales_return_id, product_id, sl_no, hsn, cgst, sgst, igst, cess,
                tax_percent, unit, rate, quantity, gross_value, discount, net_value, tax_amount, grand_total,
                cgst_amount, sgst_amount, igst_amount, cess_amount
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        params = (
            sales_return_id,
            item_data.get('product_id'),
            item_data.get('sl_no'),
            item_data.get('hsn'),
            item_data.get('cgst', 0.0),
            item_data.get('sgst', 0.0),
            item_data.get('igst', 0.0),
            item_data.get('cess', 0.0),
            item_data.get('tax_percent', 0.0),
            item_data.get('unit', ''),  # Added missing unit column
            item_data.get('rate', 0.0),
            item_data.get('quantity', 0.0),
            item_data.get('gross_value', 0.0),
            item_data.get('discount', 0.0),
            item_data.get('net_value', 0.0),
            item_data.get('tax_amount', 0.0),
            item_data.get('grand_total', 0.0),
            item_data.get('cgst_amount', 0.0),
            item_data.get('sgst_amount', 0.0),
            item_data.get('igst_amount', 0.0),
            item_data.get('cess_amount', 0.0)
        )
        return self.execute_update(query, params)

    def get_sales_returns_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all sales returns for a specific company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT sr.id, sr.return_no, sr.return_date, sr.party_id, p.name as party_name,
                   sr.return_type, sr.nature, sr.original_bill_no, sr.narration,
                   sr.sub_total, sr.discount_total, sr.tax_total, sr.round_off, sr.grand_total,
                   sr.amount_refunded_or_adjusted, sr.balance_adjustment, sr.created_at
            FROM sales_returns sr
            LEFT JOIN parties p ON sr.party_id = p.id
            WHERE sr.company_id = {ph}
            ORDER BY sr.return_date DESC, sr.id DESC
        """
        return self.execute_query(query, (company_id,))

    def get_sales_return_by_id(self, company_id: int, sales_return_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific sales return by ID for a company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT sr.id, sr.return_no, sr.return_date, sr.party_id, p.name as party_name,
                   p.mobile_number, p.address, p.gstin, p.state,
                   sr.return_type, sr.nature, sr.original_bill_id, sr.original_bill_no, sr.narration,
                   sr.sub_total, sr.discount_total, sr.tax_total, sr.round_off, sr.grand_total,
                   sr.amount_refunded_or_adjusted, sr.balance_adjustment
            FROM sales_returns sr
            LEFT JOIN parties p ON sr.party_id = p.id
            WHERE sr.company_id = {ph} AND sr.id = {ph}
        """
        result = self.execute_query(query, (company_id, sales_return_id))
        return result[0] if result else None

    def get_sales_return_by_return_no(self, company_id: int, return_no: str) -> Optional[Dict[str, Any]]:
        """Get a specific sales return by return number for a company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT sr.id, sr.return_no, sr.return_date, sr.party_id
            FROM sales_returns sr
            WHERE sr.company_id = {ph} AND sr.return_no = {ph}
        """
        result = self.execute_query(query, (company_id, return_no))
        return result[0] if result else None

    def get_sales_return_items(self, sales_return_id: int) -> List[Dict[str, Any]]:
        """Get all items for a specific sales return."""
        ph = self._get_placeholder()
        query = f"""
            SELECT sri.id, sri.sales_return_id, sri.product_id, pr.name as product_name, pr.barcode,
                   sri.sl_no, sri.hsn, sri.cgst, sri.sgst, sri.igst, sri.cess, sri.tax_percent,
                   sri.unit, sri.rate, sri.quantity, sri.gross_value, sri.discount, sri.net_value,
                   sri.tax_amount, sri.grand_total, sri.cgst_amount, sri.sgst_amount, sri.igst_amount, sri.cess_amount
            FROM sales_return_items sri
            LEFT JOIN products pr ON sri.product_id = pr.id
            WHERE sri.sales_return_id = {ph}
            ORDER BY sri.sl_no
        """
        return self.execute_query(query, (sales_return_id,))

    def update_sales_return(self, sales_return_id: int, sales_return_data: Dict[str, Any]) -> bool:
        """Update an existing sales return."""
        ph = self._get_placeholder()
        query = f"""
            UPDATE sales_returns SET
                return_no = {ph},
                return_date = {ph},
                original_bill_id = {ph},
                original_bill_no = {ph},
                party_id = {ph},
                return_type = {ph},
                nature = {ph},
                narration = {ph},
                sub_total = {ph},
                discount_total = {ph},
                tax_total = {ph},
                round_off = {ph},
                grand_total = {ph},
                amount_refunded_or_adjusted = {ph},
                balance_adjustment = {ph},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph}
        """
        params = (
            sales_return_data.get('return_no'),
            sales_return_data.get('return_date'),
            sales_return_data.get('original_bill_id'),
            sales_return_data.get('original_bill_no'),
            sales_return_data.get('party_id'),
            sales_return_data.get('return_type'),
            sales_return_data.get('nature'),
            sales_return_data.get('narration'),
            sales_return_data.get('sub_total', 0.0),
            sales_return_data.get('discount_total', 0.0),
            sales_return_data.get('tax_total', 0.0),
            sales_return_data.get('round_off', 0.0),
            sales_return_data.get('grand_total', 0.0),
            sales_return_data.get('amount_refunded_or_adjusted', 0.0),
            sales_return_data.get('balance_adjustment', 0.0),
            sales_return_id
        )
        return self.execute_update(query, params)

    def delete_sales_return(self, sales_return_id: int) -> bool:
        """Delete a sales return."""
        ph = self._get_placeholder()
        query = f"DELETE FROM sales_returns WHERE id = {ph}"
        return self.execute_update(query, (sales_return_id,))

    def delete_sales_return_items(self, sales_return_id: int) -> bool:
        """Delete all line items for a given sales return id."""
        ph = self._get_placeholder()
        query = f"DELETE FROM sales_return_items WHERE sales_return_id = {ph}"
        return self.execute_update(query, (sales_return_id,))

    def get_last_sales_return_no(self, company_id: int) -> Optional[str]:
        """Get the last sales return number for a company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT return_no FROM sales_returns
            WHERE company_id = {ph}
            ORDER BY id DESC
            LIMIT 1
        """
        result = self.execute_query(query, (company_id,))
        return result[0]['return_no'] if result else None

    # Purchase Return methods
    def insert_purchase_return(self, company_id: int, purchase_return_data: Dict[str, Any]) -> int:
        """Insert a new purchase return for a company and return the purchase_return ID."""
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO purchase_returns (
                company_id, return_no, return_date, original_purchase_id, original_purchase_no, party_id,
                return_type, nature, supplier_invoice_no, narration, sub_total, discount_total, tax_total,
                round_off, grand_total, amount_received_or_adjusted, balance_adjustment
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        params = (
            company_id,
            purchase_return_data.get('return_no'),
            purchase_return_data.get('return_date'),
            purchase_return_data.get('original_purchase_id'),
            purchase_return_data.get('original_purchase_no'),
            purchase_return_data.get('party_id'),
            purchase_return_data.get('return_type', 'Cash'),
            purchase_return_data.get('nature'),
            purchase_return_data.get('supplier_invoice_no'),
            purchase_return_data.get('narration'),
            purchase_return_data.get('sub_total', 0.0),
            purchase_return_data.get('discount_total', 0.0),
            purchase_return_data.get('tax_total', 0.0),
            purchase_return_data.get('round_off', 0.0),
            purchase_return_data.get('grand_total', 0.0),
            purchase_return_data.get('amount_received_or_adjusted', 0.0),
            purchase_return_data.get('balance_adjustment', 0.0)
        )
        self.execute_update(query, params)
        ph = self._get_placeholder()
        result = self.execute_query(
            f"SELECT id FROM purchase_returns WHERE company_id = {ph} AND return_no = {ph}",
            (company_id, purchase_return_data.get('return_no'))
        )
        return result[0]['id'] if result else None

    def insert_purchase_return_item(self, purchase_return_id: int, item_data: Dict[str, Any]) -> bool:
        """Insert a purchase return item for a purchase return."""
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO purchase_return_items (
                purchase_return_id, product_id, sl_no, hsn, cgst, sgst, igst, cess,
                tax_percent, unit, rate, quantity, gross_value, discount, net_value, tax_amount, grand_total,
                cgst_amount, sgst_amount, igst_amount, cess_amount
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        params = (
            purchase_return_id,
            item_data.get('product_id'),
            item_data.get('sl_no'),
            item_data.get('hsn'),
            item_data.get('cgst', 0.0),
            item_data.get('sgst', 0.0),
            item_data.get('igst', 0.0),
            item_data.get('cess', 0.0),
            item_data.get('tax_percent', 0.0),
            item_data.get('unit', ''),  # Added missing unit column
            item_data.get('rate', 0.0),
            item_data.get('quantity', 0.0),
            item_data.get('gross_value', 0.0),
            item_data.get('discount', 0.0),
            item_data.get('net_value', 0.0),
            item_data.get('tax_amount', 0.0),
            item_data.get('grand_total', 0.0),
            item_data.get('cgst_amount', 0.0),
            item_data.get('sgst_amount', 0.0),
            item_data.get('igst_amount', 0.0),
            item_data.get('cess_amount', 0.0)
        )
        return self.execute_update(query, params)

    def get_purchase_returns_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all purchase returns for a specific company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT pr.id, pr.return_no, pr.return_date, pr.party_id, p.name as party_name,
                   pr.return_type, pr.nature, pr.original_purchase_no, pr.supplier_invoice_no, pr.narration,
                   pr.sub_total, pr.discount_total, pr.tax_total, pr.round_off, pr.grand_total,
                   pr.amount_received_or_adjusted, pr.balance_adjustment, pr.created_at
            FROM purchase_returns pr
            LEFT JOIN parties p ON pr.party_id = p.id
            WHERE pr.company_id = {ph}
            ORDER BY pr.return_date DESC, pr.id DESC
        """
        return self.execute_query(query, (company_id,))

    def get_purchase_return_by_id(self, company_id: int, purchase_return_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific purchase return by ID for a company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT pr.id, pr.return_no, pr.return_date, pr.party_id, p.name as party_name,
                   p.mobile_number, p.address, p.gstin, p.state,
                   pr.return_type, pr.nature, pr.original_purchase_id, pr.original_purchase_no,
                   pr.supplier_invoice_no, pr.narration,
                   pr.sub_total, pr.discount_total, pr.tax_total, pr.round_off, pr.grand_total,
                   pr.amount_received_or_adjusted, pr.balance_adjustment
            FROM purchase_returns pr
            LEFT JOIN parties p ON pr.party_id = p.id
            WHERE pr.company_id = {ph} AND pr.id = {ph}
        """
        result = self.execute_query(query, (company_id, purchase_return_id))
        return result[0] if result else None

    def get_purchase_return_by_return_no(self, company_id: int, return_no: str) -> Optional[Dict[str, Any]]:
        """Get a specific purchase return by return number for a company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT pr.id, pr.return_no, pr.return_date, pr.party_id
            FROM purchase_returns pr
            WHERE pr.company_id = {ph} AND pr.return_no = {ph}
        """
        result = self.execute_query(query, (company_id, return_no))
        return result[0] if result else None

    def get_purchase_return_items(self, purchase_return_id: int) -> List[Dict[str, Any]]:
        """Get all items for a specific purchase return."""
        ph = self._get_placeholder()
        query = f"""
            SELECT pri.id, pri.purchase_return_id, pri.product_id, pr.name as product_name, pr.barcode,
                   pri.sl_no, pri.hsn, pri.cgst, pri.sgst, pri.igst, pri.cess, pri.tax_percent,
                   pri.unit, pri.rate, pri.quantity, pri.gross_value, pri.discount, pri.net_value,
                   pri.tax_amount, pri.grand_total, pri.cgst_amount, pri.sgst_amount, pri.igst_amount, pri.cess_amount
            FROM purchase_return_items pri
            LEFT JOIN products pr ON pri.product_id = pr.id
            WHERE pri.purchase_return_id = {ph}
            ORDER BY pri.sl_no
        """
        return self.execute_query(query, (purchase_return_id,))

    def update_purchase_return(self, purchase_return_id: int, purchase_return_data: Dict[str, Any]) -> bool:
        """Update an existing purchase return."""
        ph = self._get_placeholder()
        query = f"""
            UPDATE purchase_returns SET
                return_no = {ph},
                return_date = {ph},
                original_purchase_id = {ph},
                original_purchase_no = {ph},
                party_id = {ph},
                return_type = {ph},
                nature = {ph},
                supplier_invoice_no = {ph},
                narration = {ph},
                sub_total = {ph},
                discount_total = {ph},
                tax_total = {ph},
                round_off = {ph},
                grand_total = {ph},
                amount_received_or_adjusted = {ph},
                balance_adjustment = {ph},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph}
        """
        params = (
            purchase_return_data.get('return_no'),
            purchase_return_data.get('return_date'),
            purchase_return_data.get('original_purchase_id'),
            purchase_return_data.get('original_purchase_no'),
            purchase_return_data.get('party_id'),
            purchase_return_data.get('return_type'),
            purchase_return_data.get('nature'),
            purchase_return_data.get('supplier_invoice_no'),
            purchase_return_data.get('narration'),
            purchase_return_data.get('sub_total', 0.0),
            purchase_return_data.get('discount_total', 0.0),
            purchase_return_data.get('tax_total', 0.0),
            purchase_return_data.get('round_off', 0.0),
            purchase_return_data.get('grand_total', 0.0),
            purchase_return_data.get('amount_received_or_adjusted', 0.0),
            purchase_return_data.get('balance_adjustment', 0.0),
            purchase_return_id
        )
        return self.execute_update(query, params)

    def delete_purchase_return(self, purchase_return_id: int) -> bool:
        """Delete a purchase return."""
        ph = self._get_placeholder()
        query = f"DELETE FROM purchase_returns WHERE id = {ph}"
        return self.execute_update(query, (purchase_return_id,))

    def delete_purchase_return_items(self, purchase_return_id: int) -> bool:
        """Delete all line items for a given purchase return id."""
        ph = self._get_placeholder()
        query = f"DELETE FROM purchase_return_items WHERE purchase_return_id = {ph}"
        return self.execute_update(query, (purchase_return_id,))

    def get_last_purchase_return_no(self, company_id: int) -> Optional[str]:
        """Get the last purchase return number for a company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT return_no FROM purchase_returns
            WHERE company_id = {ph}
            ORDER BY id DESC
            LIMIT 1
        """
        result = self.execute_query(query, (company_id,))
        return result[0]['return_no'] if result else None

    # Bank account methods
    
    def get_bank_accounts_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all bank accounts for a specific company, ordered by account name."""
        ph = self._get_placeholder()
        query = f"""
            SELECT id, company_id, account_name, bank_name, account_number, ifsc_code,
                   branch_name, opening_balance, notes, ledger_account_id, created_at, updated_at
            FROM bank_accounts
            WHERE company_id = {ph}
            ORDER BY account_name
        """
        return self.execute_query(query, (company_id,))
    
    def get_bank_account_by_id(self, company_id: int, bank_account_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific bank account by ID for a company."""
        ph = self._get_placeholder()
        query = f"""
            SELECT id, company_id, account_name, bank_name, account_number, ifsc_code,
                   branch_name, opening_balance, notes, ledger_account_id, created_at, updated_at
            FROM bank_accounts
            WHERE company_id = {ph} AND id = {ph}
        """
        result = self.execute_query(query, (company_id, bank_account_id))
        return result[0] if result else None
    
    def create_bank_account(self, company_id: int, bank_account_data: Dict[str, Any]) -> bool:
        """Insert a new bank account for a company."""
        return self.insert_bank_account(company_id, bank_account_data) is not None

    def insert_bank_account(self, company_id: int, bank_account_data: Dict[str, Any]) -> Optional[int]:
        """Insert a new bank account and return the generated bank_accounts.id."""
        ph = self._get_placeholder()
        query = f"""
            INSERT INTO bank_accounts (
                company_id, account_name, bank_name, account_number, ifsc_code,
                branch_name, opening_balance, notes
            ) VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        """
        params = (
            company_id,
            bank_account_data.get('account_name'),
            bank_account_data.get('bank_name'),
            bank_account_data.get('account_number'),
            bank_account_data.get('ifsc_code'),
            bank_account_data.get('branch_name'),
            bank_account_data.get('opening_balance', 0.0),
            bank_account_data.get('notes')
        )
        conn = None
        try:
            conn = self.connect()
            cursor = conn.cursor()
            cursor.execute(query, params)
            bank_id = self._get_last_insert_id(cursor)
            conn.commit()
            return int(bank_id) if bank_id else None
        except Exception as e:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"Bank account insert error: {e}")
            return None
        finally:
            self.disconnect()
    
    def update_bank_account(self, company_id: int, bank_account_id: int, bank_account_data: Dict[str, Any]) -> bool:
        """Update an existing bank account for a company."""
        ph = self._get_placeholder()
        query = f"""
            UPDATE bank_accounts
            SET account_name = {ph},
                bank_name = {ph},
                account_number = {ph},
                ifsc_code = {ph},
                branch_name = {ph},
                opening_balance = {ph},
                notes = {ph},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph} AND company_id = {ph}
        """
        params = (
            bank_account_data.get('account_name'),
            bank_account_data.get('bank_name'),
            bank_account_data.get('account_number'),
            bank_account_data.get('ifsc_code'),
            bank_account_data.get('branch_name'),
            bank_account_data.get('opening_balance', 0.0),
            bank_account_data.get('notes'),
            bank_account_id,
            company_id
        )
        return self.execute_update(query, params)

    def update_bank_account_ledger_link(self, company_id: int, bank_account_id: int, ledger_account_id: int) -> bool:
        """Persist the ledger account linked to a bank master row."""
        ph = self._get_placeholder()
        query = f"""
            UPDATE bank_accounts
            SET ledger_account_id = {ph}, updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph} AND company_id = {ph}
        """
        return self.execute_update(query, (ledger_account_id, bank_account_id, company_id))

    def delete_bank_account(self, company_id: int, bank_account_id: int) -> bool:
        """Delete a bank account for a company."""
        ph = self._get_placeholder()
        query = f"DELETE FROM bank_accounts WHERE id = {ph} AND company_id = {ph}"
        return self.execute_update(query, (bank_account_id, company_id))
    
    def bank_account_name_exists(self, company_id: int, account_name: str, exclude_bank_account_id: Optional[int] = None) -> bool:
        """Check if a bank account name exists for a company (excluding a specific account if editing)."""
        ph = self._get_placeholder()
        if exclude_bank_account_id:
            query = f"SELECT id FROM bank_accounts WHERE account_name = {ph} AND company_id = {ph} AND id != {ph}"
            result = self.execute_query(query, (account_name, company_id, exclude_bank_account_id))
        else:
            query = f"SELECT id FROM bank_accounts WHERE account_name = {ph} AND company_id = {ph}"
            result = self.execute_query(query, (account_name, company_id))
        return len(result) > 0
