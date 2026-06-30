"""
Year-end financial processing using the split-database method.

Clones a company database, purges transactional history, carries forward
ledger and stock balances, locks the old database, and registers the new
financial year in the master company registry.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from contextlib import closing
from typing import Any, Dict, List, Optional, Tuple

from utils.backup_manager import execute_backup

BALANCE_SHEET_ACCOUNT_TYPES = (
    "party",
    "cash_bank",
    "capital",
    "tax_liability",
    "stock",
)

EXCLUDED_VOUCHER_TYPES = (
    "quotation",
    "estimate",
    "quote",
    "Quotation",
    "Estimate",
    "Quote",
)

EXCLUDED_STOCK_VOUCHER_TYPES = ("quotation", "estimate", "draft")

CAPITAL_ACCOUNT_NAMES = (
    "Capital Account",
    "Owner's Capital",
    "Owners Capital",
    "Retained Earnings",
)


def process_financial_year(
    old_db_path: str,
    new_db_path: str,
    new_company_name: str,
    backup_dir: str,
    master_db_path: str,
) -> Tuple[bool, str]:
    """
    Process year-end closing by cloning the company database and carrying balances forward.

    Returns:
        (True, "Success") on completion, or (False, error_message) on failure.
    """
    new_db_created = False
    try:
        old_db_path = os.path.abspath(old_db_path)
        new_db_path = os.path.abspath(new_db_path)
        master_db_path = os.path.abspath(master_db_path)

        if not os.path.isfile(old_db_path):
            return False, "Source database not found"
        if not new_company_name.strip():
            return False, "New company name is required"
        if os.path.exists(new_db_path):
            return False, f"Target database already exists: {new_db_path}"

        with closing(_connect(old_db_path)) as old_conn:
            company_id, company_name, source_company_row = _get_active_company_context(old_conn)
            if not company_id:
                return False, "No active company found in source database"

            ledger_closings = _calculate_ledger_closing_balances(old_conn, company_id)
            net_profit = _calculate_net_profit(old_conn, company_id)
            stock_closings = _calculate_stock_closing_balances(old_conn, company_id)

        backup_ok, _backup_result = execute_backup(old_db_path, backup_dir, company_name)
        if not backup_ok:
            return False, "Backup failed"

        target_parent = os.path.dirname(new_db_path)
        if target_parent:
            os.makedirs(target_parent, exist_ok=True)

        shutil.copy2(old_db_path, new_db_path)
        new_db_created = True

        with closing(_connect(new_db_path)) as new_conn:
            _purge_transactions(new_conn, company_id)
            _inject_opening_balances(
                new_conn,
                company_id,
                ledger_closings,
                net_profit,
                stock_closings,
            )
            _update_company_identity(new_conn, company_id, new_company_name, new_db_path)
            new_conn.commit()

        with closing(_connect(old_db_path)) as old_conn:
            _lock_database(old_conn)
            old_conn.commit()

        with closing(_connect(master_db_path)) as master_conn:
            _register_new_company(
                master_conn,
                source_company_row,
                new_company_name,
                new_db_path,
            )
            master_conn.commit()

        return True, "Success"
    except Exception as error:
        if new_db_created and os.path.exists(new_db_path):
            try:
                os.remove(new_db_path)
            except OSError:
                pass
        return False, str(error)


def _connect(db_path: str) -> sqlite3.Connection:
    """Open a hardened SQLite connection."""
    connection = sqlite3.connect(db_path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000;")
    connection.execute("PRAGMA journal_mode = DELETE;")
    connection.execute("PRAGMA synchronous = NORMAL;")
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    cursor = connection.cursor()
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _column_exists(connection: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    cursor = connection.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def _delete_if_exists(
    connection: sqlite3.Connection,
    table_name: str,
    where_clause: str,
    params: Tuple[Any, ...],
) -> None:
    if not _table_exists(connection, table_name):
        return
    connection.execute(f"DELETE FROM {table_name} WHERE {where_clause}", params)


def _get_active_company_context(
    connection: sqlite3.Connection,
) -> Tuple[Optional[int], str, Dict[str, Any]]:
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT
            id, business_name, phone_number, gstin, gst_type, email, db_path,
            business_type, business_category, address, state, pincode,
            logo_path, signature_path, print_phone, print_gstin, print_email,
            print_business_type, print_business_category, print_address,
            print_state, print_pincode, print_logo, print_signature, is_active
        FROM companies
        WHERE is_active = 1
        ORDER BY id
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    if not row:
        return None, "", {}

    company_row = dict(row)
    return (
        int(company_row["id"]),
        str(company_row.get("business_name") or "company"),
        company_row,
    )


def _signed_opening_balance(opening_balance: Any, opening_balance_type: Any) -> float:
    amount = float(opening_balance or 0.0)
    balance_type = str(opening_balance_type or "Dr").strip().lower()
    if balance_type.startswith("cr"):
        return -amount
    return amount


def _signed_to_opening_parts(signed_balance: float) -> Tuple[float, str]:
    if signed_balance >= 0:
        return round(abs(signed_balance), 2), "Dr"
    return round(abs(signed_balance), 2), "Cr"


def _calculate_ledger_closing_balances(
    connection: sqlite3.Connection,
    company_id: int,
) -> Dict[int, Dict[str, Any]]:
    excluded = ", ".join(f"'{value}'" for value in EXCLUDED_VOUCHER_TYPES)
    cursor = connection.cursor()
    cursor.execute(
        f"""
        SELECT
            la.id,
            la.account_name,
            la.account_type,
            la.opening_balance,
            la.opening_balance_type,
            COALESCE(SUM(le.debit), 0) AS total_debit,
            COALESCE(SUM(le.credit), 0) AS total_credit
        FROM ledger_accounts la
        LEFT JOIN ledger_entries le
            ON la.id = le.account_id
           AND le.company_id = la.company_id
           AND le.voucher_type NOT IN ({excluded})
        WHERE la.company_id = ?
          AND la.is_active = 1
        GROUP BY
            la.id,
            la.account_name,
            la.account_type,
            la.opening_balance,
            la.opening_balance_type
        """,
        (company_id,),
    )

    closings: Dict[int, Dict[str, Any]] = {}
    for row in cursor.fetchall():
        signed_balance = _signed_opening_balance(
            row["opening_balance"],
            row["opening_balance_type"],
        )
        signed_balance += float(row["total_debit"] or 0.0) - float(row["total_credit"] or 0.0)
        closings[int(row["id"])] = {
            "account_name": row["account_name"],
            "account_type": row["account_type"],
            "signed_balance": round(signed_balance, 2),
        }
    return closings


def _calculate_net_profit(connection: sqlite3.Connection, company_id: int) -> float:
    excluded = ", ".join(f"'{value}'" for value in EXCLUDED_VOUCHER_TYPES)
    cursor = connection.cursor()
    cursor.execute(
        f"""
        SELECT
            la.account_type,
            COALESCE(SUM(le.debit), 0) AS total_debit,
            COALESCE(SUM(le.credit), 0) AS total_credit
        FROM ledger_accounts la
        LEFT JOIN ledger_entries le
            ON la.id = le.account_id
           AND le.company_id = la.company_id
           AND le.voucher_type NOT IN ({excluded})
        WHERE la.company_id = ?
          AND la.is_active = 1
          AND la.account_type IN ('income', 'expense')
        GROUP BY la.id, la.account_type
        """,
        (company_id,),
    )

    net_profit = 0.0
    for row in cursor.fetchall():
        debit = float(row["total_debit"] or 0.0)
        credit = float(row["total_credit"] or 0.0)
        if row["account_type"] == "income":
            net_profit += credit - debit
        else:
            net_profit -= debit - credit
    return round(net_profit, 2)


def _calculate_stock_closing_balances(
    connection: sqlite3.Connection,
    company_id: int,
) -> Dict[int, float]:
    if not _table_exists(connection, "stock_movements"):
        return {}

    excluded = ", ".join(f"'{value}'" for value in EXCLUDED_STOCK_VOUCHER_TYPES)
    voucher_filter = ""
    if _column_exists(connection, "stock_movements", "voucher_type"):
        voucher_filter = f"AND COALESCE(voucher_type, '') NOT IN ({excluded})"

    cursor = connection.cursor()
    cursor.execute(
        f"""
        SELECT
            product_id,
            COALESCE(SUM(quantity), 0) AS closing_qty
        FROM stock_movements
        WHERE company_id = ?
          {voucher_filter}
        GROUP BY product_id
        """,
        (company_id,),
    )
    return {
        int(row["product_id"]): round(float(row["closing_qty"] or 0.0), 4)
        for row in cursor.fetchall()
    }


def _purge_transactions(connection: sqlite3.Connection, company_id: int) -> None:
    """Delete transactional history while preserving master records."""
    child_deletes = (
        (
            "cash_receipt_items",
            "receipt_id IN (SELECT id FROM cash_receipts WHERE company_id = ?)",
        ),
        (
            "cash_payment_items",
            "payment_id IN (SELECT id FROM cash_payments WHERE company_id = ?)",
        ),
        (
            "journal_voucher_lines",
            "journal_id IN (SELECT id FROM journal_vouchers WHERE company_id = ?)",
        ),
        (
            "stock_adjustment_items",
            "adjustment_id IN (SELECT id FROM stock_adjustments WHERE company_id = ?)",
        ),
        (
            "purchase_order_items",
            "po_id IN (SELECT id FROM purchase_orders WHERE company_id = ?)",
        ),
        (
            "quotation_items",
            "quotation_id IN (SELECT id FROM quotations WHERE company_id = ?)",
        ),
        (
            "sales_items",
            "sale_id IN (SELECT id FROM sales WHERE company_id = ?)",
        ),
        (
            "purchase_items",
            "purchase_id IN (SELECT id FROM purchases WHERE company_id = ?)",
        ),
        (
            "sales_return_items",
            "sales_return_id IN (SELECT id FROM sales_returns WHERE company_id = ?)",
        ),
        (
            "purchase_return_items",
            "purchase_return_id IN (SELECT id FROM purchase_returns WHERE company_id = ?)",
        ),
    )
    for table_name, where_clause in child_deletes:
        _delete_if_exists(connection, table_name, where_clause, (company_id,))

    company_scoped_tables = (
        "ledger_entries",
        "stock_movements",
        "stock_draft_session",
        "audit_logs",
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
        "cash_tender_history",
        "transactions",
    )
    for table_name in company_scoped_tables:
        _delete_if_exists(
            connection,
            table_name,
            "company_id = ?",
            (company_id,),
        )


def _find_capital_account_id(
    connection: sqlite3.Connection,
    company_id: int,
) -> Optional[int]:
    cursor = connection.cursor()
    placeholders = ", ".join("?" for _ in CAPITAL_ACCOUNT_NAMES)
    cursor.execute(
        f"""
        SELECT id
        FROM ledger_accounts
        WHERE company_id = ?
          AND account_type = 'capital'
          AND account_name IN ({placeholders})
        ORDER BY is_system DESC, id
        LIMIT 1
        """,
        (company_id, *CAPITAL_ACCOUNT_NAMES),
    )
    row = cursor.fetchone()
    if row:
        return int(row["id"])

    cursor.execute(
        """
        SELECT id
        FROM ledger_accounts
        WHERE company_id = ?
          AND account_type = 'capital'
        ORDER BY is_system DESC, id
        LIMIT 1
        """,
        (company_id,),
    )
    row = cursor.fetchone()
    return int(row["id"]) if row else None


def _inject_opening_balances(
    connection: sqlite3.Connection,
    company_id: int,
    ledger_closings: Dict[int, Dict[str, Any]],
    net_profit: float,
    stock_closings: Dict[int, float],
) -> None:
    cursor = connection.cursor()
    cursor.execute(
        """
        UPDATE ledger_accounts
        SET opening_balance = 0.0,
            opening_balance_type = 'Dr'
        WHERE company_id = ?
        """,
        (company_id,),
    )

    carried_balances: Dict[int, float] = {}
    for account_id, account_data in ledger_closings.items():
        if account_data["account_type"] not in BALANCE_SHEET_ACCOUNT_TYPES:
            continue
        carried_balances[account_id] = float(account_data["signed_balance"])

    capital_account_id = _find_capital_account_id(connection, company_id)
    if capital_account_id is not None and net_profit:
        carried_balances[capital_account_id] = round(
            carried_balances.get(capital_account_id, 0.0) - net_profit,
            2,
        )

    for account_id, signed_balance in carried_balances.items():
        opening_amount, opening_type = _signed_to_opening_parts(signed_balance)
        cursor.execute(
            """
            UPDATE ledger_accounts
            SET opening_balance = ?,
                opening_balance_type = ?
            WHERE id = ?
              AND company_id = ?
            """,
            (opening_amount, opening_type, account_id, company_id),
        )

    if _table_exists(connection, "parties"):
        cursor.execute(
            """
            UPDATE parties
            SET opening_balance = (
                SELECT la.opening_balance
                FROM ledger_accounts la
                WHERE la.company_id = parties.company_id
                  AND la.account_type = 'party'
                  AND la.account_name = parties.name
                LIMIT 1
            )
            WHERE company_id = ?
              AND EXISTS (
                SELECT 1
                FROM ledger_accounts la
                WHERE la.company_id = parties.company_id
                  AND la.account_type = 'party'
                  AND la.account_name = parties.name
              )
            """,
            (company_id,),
        )

    if _table_exists(connection, "bank_accounts"):
        cursor.execute(
            """
            UPDATE bank_accounts
            SET opening_balance = (
                SELECT la.opening_balance
                FROM ledger_accounts la
                WHERE la.company_id = bank_accounts.company_id
                  AND la.account_type = 'cash_bank'
                  AND la.account_name = bank_accounts.account_name
                LIMIT 1
            )
            WHERE company_id = ?
              AND EXISTS (
                SELECT 1
                FROM ledger_accounts la
                WHERE la.company_id = bank_accounts.company_id
                  AND la.account_type = 'cash_bank'
                  AND la.account_name = bank_accounts.account_name
              )
            """,
            (company_id,),
        )

    if _table_exists(connection, "products"):
        cursor.execute(
            "UPDATE products SET quantity = 0.0 WHERE company_id = ?",
            (company_id,),
        )
        for product_id, closing_qty in stock_closings.items():
            cursor.execute(
                """
                UPDATE products
                SET quantity = ?
                WHERE id = ?
                  AND company_id = ?
                """,
                (closing_qty, product_id, company_id),
            )

    if _table_exists(connection, "stock_movements"):
        has_voucher_type = _column_exists(connection, "stock_movements", "voucher_type")
        for product_id, closing_qty in stock_closings.items():
            if closing_qty == 0:
                continue
            if has_voucher_type:
                cursor.execute(
                    """
                    INSERT INTO stock_movements (
                        company_id, product_id, movement_type, quantity,
                        reference_type, reference_id, notes, voucher_type
                    ) VALUES (?, ?, 'opening', ?, 'year_end', 0, ?, 'opening')
                    """,
                    (
                        company_id,
                        product_id,
                        closing_qty,
                        "Year-end opening stock",
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO stock_movements (
                        company_id, product_id, movement_type, quantity,
                        reference_type, reference_id, notes
                    ) VALUES (?, ?, 'opening', ?, 'year_end', 0, ?)
                    """,
                    (
                        company_id,
                        product_id,
                        closing_qty,
                        "Year-end opening stock",
                    ),
                )


def _ensure_app_settings_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT
        )
        """
    )


def _upsert_app_setting(
    connection: sqlite3.Connection,
    setting_key: str,
    setting_value: str,
) -> None:
    _ensure_app_settings_table(connection)
    connection.execute(
        """
        INSERT OR REPLACE INTO app_settings (setting_key, setting_value)
        VALUES (?, ?)
        """,
        (setting_key, setting_value),
    )


def _update_company_identity(
    connection: sqlite3.Connection,
    company_id: int,
    new_company_name: str,
    new_db_path: str,
) -> None:
    cursor = connection.cursor()
    cursor.execute(
        """
        UPDATE companies
        SET business_name = ?,
            is_active = 1
        WHERE id = ?
        """,
        (new_company_name.strip(), company_id),
    )
    if _column_exists(connection, "companies", "db_path"):
        cursor.execute(
            "UPDATE companies SET db_path = ? WHERE id = ?",
            (new_db_path, company_id),
        )

    _upsert_app_setting(connection, "business_name", new_company_name.strip())
    _upsert_app_setting(connection, "last_active_company_name", new_company_name.strip())
    _upsert_app_setting(connection, "last_active_company_path", new_db_path)


def _lock_database(connection: sqlite3.Connection) -> None:
    _upsert_app_setting(connection, "is_read_only", "true")


def _register_new_company(
    connection: sqlite3.Connection,
    source_company_row: Dict[str, Any],
    new_company_name: str,
    new_db_path: str,
) -> None:
    if not _table_exists(connection, "companies"):
        raise RuntimeError("Master database is missing the companies registry table")

    cursor = connection.cursor()
    if _column_exists(connection, "companies", "db_path"):
        cursor.execute(
            "SELECT id FROM companies WHERE db_path = ? LIMIT 1",
            (new_db_path,),
        )
        if cursor.fetchone():
            raise RuntimeError("The new company database is already registered")

    insert_columns: List[str] = ["business_name", "is_active"]
    insert_values: List[Any] = [new_company_name.strip(), 1]

    copy_fields = (
        "phone_number",
        "gstin",
        "gst_type",
        "email",
        "business_type",
        "business_category",
        "address",
        "state",
        "pincode",
        "logo_path",
        "signature_path",
        "print_phone",
        "print_gstin",
        "print_email",
        "print_business_type",
        "print_business_category",
        "print_address",
        "print_state",
        "print_pincode",
        "print_logo",
        "print_signature",
        "db_path",
    )
    for field_name in copy_fields:
        if not _column_exists(connection, "companies", field_name):
            continue
        insert_columns.append(field_name)
        if field_name == "db_path":
            insert_values.append(new_db_path)
        else:
            insert_values.append(source_company_row.get(field_name))

    placeholders = ", ".join("?" for _ in insert_columns)
    column_sql = ", ".join(insert_columns)
    cursor.execute(
        f"INSERT INTO companies ({column_sql}) VALUES ({placeholders})",
        tuple(insert_values),
    )
