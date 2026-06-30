"""
Commercial Cash/Bank Voucher Logic.

Shared logic for Cash Receipt, Cash Payment, Bank Receipt, and Bank Payment.
This module intentionally centralizes receipt/payment validation, persistence,
ledger posting, previous/next loading, and discount posting so all four voucher
pages behave consistently.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from db import Database
from bizora_core.audit_logic import log_action
from bizora_core.ledger_logic import LedgerLogic
from bizora_core.voucher_posting_engine import VoucherPostingEngine


class CashBankVoucherLogic:
    """Shared commercial logic for cash/bank receipt/payment vouchers."""

    VOUCHERS = {
        "cash_receipt": {
            "table": "cash_receipts",
            "items_table": "cash_receipt_items",
            "item_fk": "receipt_id",
            "money_field": "cash_account_id",
            "account_field": "received_from_account_id",
            "party_label": "received_from",
            "prefix": "CR",
            "is_receipt": True,
            "money_account_name": "Cash Account",
            "discount_allowed": True,
            "voucher_title": "Cash Receipt",
        },
        "cash_payment": {
            "table": "cash_payments",
            "items_table": "cash_payment_items",
            "item_fk": "payment_id",
            "money_field": "cash_account_id",
            "account_field": "paid_to_account_id",
            "party_label": "paid_to",
            "prefix": "CP",
            "is_receipt": False,
            "money_account_name": "Cash Account",
            "discount_allowed": False,
            "voucher_title": "Cash Payment",
        },
        "bank_receipt": {
            "table": "bank_receipts",
            "items_table": "bank_receipt_items",
            "item_fk": "receipt_id",
            "money_field": "bank_account_id",
            "account_field": "received_from_account_id",
            "party_label": "received_from",
            "prefix": "BR",
            "is_receipt": True,
            "money_account_name": "Bank Account",
            "discount_allowed": True,
            "voucher_title": "Bank Receipt",
        },
        "bank_payment": {
            "table": "bank_payments",
            "items_table": "bank_payment_items",
            "item_fk": "payment_id",
            "money_field": "bank_account_id",
            "account_field": "paid_to_account_id",
            "party_label": "paid_to",
            "prefix": "BP",
            "is_receipt": False,
            "money_account_name": "Bank Account",
            "discount_allowed": False,
            "voucher_title": "Bank Payment",
        },
    }

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.ledger_logic = LedgerLogic(self.db)
        self.posting_engine = VoucherPostingEngine(self.db)

    # ------------------------------------------------------------------
    # Schema helpers
    # ------------------------------------------------------------------
    def _ph(self) -> str:
        return self.db._get_placeholder()

    def _ts(self) -> str:
        return self.db._get_timestamp_default()

    def _connect(self):
        return self.db.connect()

    def _execute_insert(self, query: str, params: tuple) -> Optional[int]:
        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(query, params)
            last_id = self.db._get_last_insert_id(cursor)
            conn.commit()
            return last_id
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            self.db.disconnect()

    def _execute_update_count(self, query: str, params: tuple) -> int:
        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(query, params)
            count = cursor.rowcount if cursor.rowcount is not None else 0
            conn.commit()
            return count
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            self.db.disconnect()

    def _table_exists(self, table_name: str) -> bool:
        ph = self._ph()
        rows = self.db.execute_query(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name={ph}",
            (table_name,),
        )
        return bool(rows)

    def _column_exists(self, table_name: str, column_name: str) -> bool:
        if self.db.db_type != "sqlite":
            return True
        conn = self.db.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            return column_name in [row[1] for row in cursor.fetchall()]
        finally:
            self.db.disconnect()

    def _add_column_if_missing(self, table_name: str, column_name: str, column_def: str) -> None:
        if self.db.db_type != "sqlite":
            return
        if not self._column_exists(table_name, column_name):
            self.db.execute_update(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")

    def _ensure_unique_voucher_index(self, table_name: str, index_name: str) -> None:
        """Create company/voucher unique index unless historical duplicates exist."""
        duplicates = self.db.execute_query(
            f"""
            SELECT company_id, voucher_no, COUNT(id) AS duplicate_count
            FROM {table_name}
            GROUP BY company_id, voucher_no
            HAVING COUNT(id) > 1
            LIMIT 1
            """
        )
        if duplicates:
            print(
                f"Note: Unique index {index_name} skipped because duplicate "
                f"historical {table_name} rows exist."
            )
            return
        try:
            if self.db.db_type == "sqlite":
                self.db.execute_update(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} "
                    f"ON {table_name} (company_id, voucher_no)"
                )
            else:
                self.db.execute_update(
                    f"CREATE UNIQUE INDEX {index_name} "
                    f"ON {table_name} (company_id, voucher_no)"
                )
        except Exception as exc:
            print(f"Note: Unique index creation for {index_name} skipped: {exc}")

    def ensure_schema(self) -> None:
        """Create/migrate voucher tables used by the four voucher pages."""
        pk = self.db._get_primary_key_autoincrement()
        ts = self._ts()
        # Existing installs may already have these tables. Keep CREATE minimal and migrate.
        create_statements = [
            f"""
            CREATE TABLE IF NOT EXISTS cash_receipts (
                id {pk}, company_id INTEGER NOT NULL, voucher_no TEXT NOT NULL,
                receipt_no TEXT, voucher_date TEXT NOT NULL,
                received_from_account_id INTEGER NOT NULL, cash_account_id INTEGER NOT NULL,
                party_id INTEGER, amount REAL DEFAULT 0.0, towards_acc TEXT,
                remark TEXT, narration TEXT, payment_mode TEXT DEFAULT 'Cash', reference_no TEXT,
                total_amount REAL DEFAULT 0.0, total_discount REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT {ts}, updated_at TIMESTAMP DEFAULT {ts},
                UNIQUE(company_id, voucher_no)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS cash_payments (
                id {pk}, company_id INTEGER NOT NULL, voucher_no TEXT NOT NULL,
                payment_no TEXT, voucher_date TEXT NOT NULL,
                paid_to_account_id INTEGER NOT NULL, cash_account_id INTEGER NOT NULL,
                party_id INTEGER, amount REAL DEFAULT 0.0, towards_acc TEXT,
                remark TEXT, narration TEXT, payment_mode TEXT DEFAULT 'Cash', reference_no TEXT,
                total_amount REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT {ts}, updated_at TIMESTAMP DEFAULT {ts},
                UNIQUE(company_id, voucher_no)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS bank_receipts (
                id {pk}, company_id INTEGER NOT NULL, voucher_no TEXT NOT NULL,
                voucher_date TEXT NOT NULL, received_from_account_id INTEGER NOT NULL,
                bank_account_id INTEGER NOT NULL, party_id INTEGER, amount REAL DEFAULT 0.0,
                towards_acc TEXT, remark TEXT, narration TEXT, reference_no TEXT,
                cheque_no TEXT, utr_no TEXT, total_amount REAL DEFAULT 0.0,
                total_discount REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT {ts}, updated_at TIMESTAMP DEFAULT {ts}
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS bank_payments (
                id {pk}, company_id INTEGER NOT NULL, voucher_no TEXT NOT NULL,
                voucher_date TEXT NOT NULL, paid_to_account_id INTEGER NOT NULL,
                bank_account_id INTEGER NOT NULL, party_id INTEGER, amount REAL DEFAULT 0.0,
                towards_acc TEXT, remark TEXT, narration TEXT, reference_no TEXT,
                cheque_no TEXT, utr_no TEXT, total_amount REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT {ts}, updated_at TIMESTAMP DEFAULT {ts}
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS cash_receipt_items (
                id {pk}, receipt_id INTEGER NOT NULL, account_id INTEGER NOT NULL,
                party_id INTEGER, account_kind TEXT, towards_voucher_no TEXT,
                amount REAL DEFAULT 0.0, discount REAL DEFAULT 0.0, narration TEXT,
                created_at TIMESTAMP DEFAULT {ts}, updated_at TIMESTAMP DEFAULT {ts}
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS cash_payment_items (
                id {pk}, payment_id INTEGER NOT NULL, account_id INTEGER NOT NULL,
                party_id INTEGER, account_kind TEXT, towards_voucher_no TEXT,
                amount REAL DEFAULT 0.0, narration TEXT,
                created_at TIMESTAMP DEFAULT {ts}, updated_at TIMESTAMP DEFAULT {ts}
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS bank_receipt_items (
                id {pk}, receipt_id INTEGER NOT NULL, account_id INTEGER NOT NULL,
                party_id INTEGER, account_kind TEXT, towards_voucher_no TEXT,
                amount REAL DEFAULT 0.0, discount REAL DEFAULT 0.0, narration TEXT,
                created_at TIMESTAMP DEFAULT {ts}, updated_at TIMESTAMP DEFAULT {ts}
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS bank_payment_items (
                id {pk}, payment_id INTEGER NOT NULL, account_id INTEGER NOT NULL,
                party_id INTEGER, account_kind TEXT, towards_voucher_no TEXT,
                amount REAL DEFAULT 0.0, narration TEXT,
                created_at TIMESTAMP DEFAULT {ts}, updated_at TIMESTAMP DEFAULT {ts}
            )
            """,
        ]
        for stmt in create_statements:
            self.db.execute_update(stmt)

        # Migrate existing old tables.
        for table in ("cash_receipts", "cash_payments", "bank_receipts", "bank_payments"):
            self._add_column_if_missing(table, "towards_acc", "TEXT")
            self._add_column_if_missing(table, "total_amount", "REAL DEFAULT 0.0")
            self._add_column_if_missing(table, "total_discount", "REAL DEFAULT 0.0")
            self._add_column_if_missing(table, "narration", "TEXT")
            self._add_column_if_missing(table, "remark", "TEXT")
        for table in ("cash_receipt_items", "cash_payment_items", "bank_receipt_items", "bank_payment_items"):
            self._add_column_if_missing(table, "discount", "REAL DEFAULT 0.0")
        self._ensure_unique_voucher_index("cash_receipts", "uq_cash_receipts_company_voucher")
        self._ensure_unique_voucher_index("cash_payments", "uq_cash_payments_company_voucher")

    # ------------------------------------------------------------------
    # Accounts and balances
    # ------------------------------------------------------------------
    def ensure_system_accounts(self, company_id: int) -> None:
        self.ledger_logic.ensure_system_accounts(company_id)
        self.ledger_logic.ensure_bank_master_ledgers(company_id)
        # Ensure Bank Account also exists even when no bank master exists.
        if not self.ledger_logic.get_account_by_name(company_id, "Bank Account"):
            self._create_ledger_account(company_id, "Bank Account", "BANK", "cash_bank", "Cash & Bank", "Dr", system=True)

    def _create_ledger_account(self, company_id: int, name: str, code: str, account_type: str, group_name: str, ob_type: str = "Dr", system: bool = True) -> int:
        ph = self._ph()
        ts = self._ts()
        existing = self.db.execute_query(
            f"SELECT id FROM ledger_accounts WHERE company_id={ph} AND LOWER(account_name)=LOWER({ph})",
            (company_id, name),
        )
        if existing:
            return int(existing[0]["id"])
        return int(self._execute_insert(
            f"""
            INSERT INTO ledger_accounts (company_id, account_name, account_code, account_type,
                group_name, opening_balance, opening_balance_type, is_system, is_active, created_at, updated_at)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, 0.0, {ph}, {ph}, 1, {ts}, {ts})
            """,
            (company_id, name, code, account_type, group_name, ob_type, 1 if system else 0),
        ) or 0)

    def get_money_accounts(self, company_id: int, voucher_type: str) -> List[Dict[str, Any]]:
        self.ensure_system_accounts(company_id)
        cfg = self.VOUCHERS[voucher_type]
        ph = self._ph()
        if voucher_type.startswith("bank"):
            # Bank voucher header tables reference bank_accounts.id, while ledger posting
            # must use the linked ledger account for that bank master row.
            rows = self.db.execute_query(
                f"""
                SELECT id, account_name, bank_name, opening_balance
                FROM bank_accounts
                WHERE company_id={ph}
                ORDER BY account_name
                """,
                (company_id,),
            )
            if not rows:
                bank_id = self._ensure_default_bank_master(company_id)
                rows = self.db.execute_query(
                    f"SELECT id, account_name, bank_name, opening_balance FROM bank_accounts WHERE id={ph}",
                    (bank_id,),
                )
            return [
                {
                    "id": int(r["id"]),
                    "account_name": r.get("account_name") or "Bank Account",
                    "bank_name": r.get("bank_name") or "",
                    "ledger_account_id": self._get_bank_ledger_account_id(company_id, int(r["id"])),
                    "opening_balance": float(r.get("opening_balance") or 0.0),
                    "opening_balance_type": "Dr",
                }
                for r in rows
            ]

        rows = self.db.execute_query(
            f"""
            SELECT id, account_name, account_type, group_name, opening_balance, opening_balance_type
            FROM ledger_accounts
            WHERE company_id={ph} AND is_active=1
              AND LOWER(account_name) LIKE {ph}
            ORDER BY CASE WHEN account_name={ph} THEN 0 ELSE 1 END, account_name
            """,
            (company_id, "%cash%", cfg["money_account_name"]),
        )
        if not rows:
            account_id = self._create_ledger_account(company_id, cfg["money_account_name"], "CASH", "cash_bank", "Cash & Bank")
            rows = self.db.execute_query(
                f"SELECT id, account_name, account_type, group_name, opening_balance, opening_balance_type FROM ledger_accounts WHERE id={ph}",
                (account_id,),
            )
        return rows

    def _get_bank_ledger_account_id(self, company_id: int, bank_master_id: Optional[int] = None) -> int:
        if bank_master_id:
            ledger_id = self.ledger_logic.get_ledger_account_id_for_bank_master(company_id, int(bank_master_id))
            if ledger_id:
                return int(ledger_id)
        acct = self.ledger_logic.get_account_by_name(company_id, "Bank Account")
        if acct:
            return int(acct["id"])
        return self._create_ledger_account(company_id, "Bank Account", "BANK", "cash_bank", "Cash & Bank", "Dr", system=True)

    def _ensure_default_bank_master(self, company_id: int) -> int:
        ph = self._ph()
        ts = self._ts()
        rows = self.db.execute_query(f"SELECT id FROM bank_accounts WHERE company_id={ph} ORDER BY id LIMIT 1", (company_id,))
        if rows:
            return int(rows[0]["id"])
        bank_id = int(self._execute_insert(
            f"""
            INSERT INTO bank_accounts (company_id, account_name, bank_name, account_number, ifsc_code, branch_name, opening_balance, notes, created_at, updated_at)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, 0.0, {ph}, {ts}, {ts})
            """,
            (company_id, "Bank Account", "Default Bank", "", "", "", "Auto-created for Bank Receipt/Payment"),
        ) or 0)
        try:
            self.ledger_logic.get_or_create_bank_master_ledger(company_id, bank_id)
        except Exception:
            pass
        return bank_id

    def get_account_options(
        self,
        company_id: int,
        main_type: str,
        *,
        voucher_type: str = "",
        bill_mode: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return selectable accounts for voucher grid rows."""
        self.ensure_system_accounts(company_id)
        main_type = (main_type or "general").lower()
        if bill_mode:
            cfg = self.VOUCHERS.get(voucher_type, {})
            is_receipt = bool(cfg.get("is_receipt"))
            party_types = ("Debitor", "Both") if is_receipt else ("Creditor", "Both")
            return self._parties_with_outstanding_bills(company_id, party_types, is_receipt)
        if main_type == "debtor":
            return self._party_options(company_id, ("Debitor", "Both"))
        if main_type == "creditor":
            return self._party_options(company_id, ("Creditor", "Both"))
        return self._general_account_options(company_id)

    def _parties_with_outstanding_bills(
        self,
        company_id: int,
        party_types: Tuple[str, ...],
        is_receipt: bool,
    ) -> List[Dict[str, Any]]:
        """Return debtor/creditor parties that still have at least one outstanding bill."""
        options: List[Dict[str, Any]] = []
        for opt in self._party_options(company_id, party_types):
            party_id = opt.get("party_id")
            if not party_id:
                continue
            bills = (
                self.get_outstanding_sales_bills(company_id, int(party_id))
                if is_receipt
                else self.get_outstanding_purchase_bills(company_id, int(party_id))
            )
            if bills:
                options.append(opt)
        return options

    def _sum_receipt_allocations_for_bill(
        self,
        company_id: int,
        party_id: int,
        bill_number: str,
        exclude_voucher_type: str = "",
        exclude_voucher_id: Optional[int] = None,
    ) -> float:
        """Sum cash/bank receipt amounts allocated against a sales bill number."""
        bill_number = str(bill_number or "").strip()
        if not bill_number:
            return 0.0
        ph = self._ph()
        total = 0.0
        sources = (
            ("cash_receipt_items", "receipt_id", "cash_receipts", "cash_receipt"),
            ("bank_receipt_items", "receipt_id", "bank_receipts", "bank_receipt"),
        )
        for items_table, fk_col, header_table, _voucher_key in sources:
            exclude_sql = ""
            params: List[Any] = [company_id, party_id, bill_number.lower()]
            if (
                exclude_voucher_id
                and exclude_voucher_type
                and self.VOUCHERS.get(exclude_voucher_type, {}).get("items_table") == items_table
            ):
                exclude_sql = f" AND h.id <> {ph}"
                params.append(int(exclude_voucher_id))
            rows = self.db.execute_query(
                f"""
                SELECT COALESCE(SUM(i.amount + COALESCE(i.discount, 0)), 0) AS allocated
                FROM {items_table} i
                INNER JOIN {header_table} h ON h.id = i.{fk_col}
                WHERE h.company_id = {ph}
                  AND i.party_id = {ph}
                  AND LOWER(TRIM(i.towards_voucher_no)) = {ph}
                  {exclude_sql}
                """,
                tuple(params),
            )
            total += float(rows[0].get("allocated") or 0.0) if rows else 0.0
        return round(total, 2)

    def _sum_payment_allocations_for_bill(
        self,
        company_id: int,
        party_id: int,
        bill_number: str,
        exclude_voucher_type: str = "",
        exclude_voucher_id: Optional[int] = None,
    ) -> float:
        """Sum cash/bank payment amounts allocated against a purchase bill number."""
        bill_number = str(bill_number or "").strip()
        if not bill_number:
            return 0.0
        ph = self._ph()
        total = 0.0
        sources = (
            ("cash_payment_items", "payment_id", "cash_payments", "cash_payment"),
            ("bank_payment_items", "payment_id", "bank_payments", "bank_payment"),
        )
        for items_table, fk_col, header_table, _voucher_key in sources:
            exclude_sql = ""
            params: List[Any] = [company_id, party_id, bill_number.lower()]
            if (
                exclude_voucher_id
                and exclude_voucher_type
                and self.VOUCHERS.get(exclude_voucher_type, {}).get("items_table") == items_table
            ):
                exclude_sql = f" AND h.id <> {ph}"
                params.append(int(exclude_voucher_id))
            rows = self.db.execute_query(
                f"""
                SELECT COALESCE(SUM(i.amount), 0) AS allocated
                FROM {items_table} i
                INNER JOIN {header_table} h ON h.id = i.{fk_col}
                WHERE h.company_id = {ph}
                  AND i.party_id = {ph}
                  AND LOWER(TRIM(i.towards_voucher_no)) = {ph}
                  {exclude_sql}
                """,
                tuple(params),
            )
            total += float(rows[0].get("allocated") or 0.0) if rows else 0.0
        return round(total, 2)

    def get_outstanding_sales_bills(
        self,
        company_id: int,
        party_id: int,
        exclude_voucher_type: str = "",
        exclude_voucher_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return sales bills with a positive pending balance for bill-wise receipt allocation."""
        ph = self._ph()
        rows = self.db.execute_query(
            f"""
            SELECT id, invoice_number, invoice_date, grand_total, amount_received, sales_type
            FROM sales
            WHERE company_id = {ph}
              AND party_id = {ph}
              AND sales_type <> 'Return'
              AND COALESCE(status, 'Active') <> 'Voided'
            ORDER BY invoice_date, id
            """,
            (company_id, party_id),
        )
        bills: List[Dict[str, Any]] = []
        for row in rows or []:
            bill_number = str(row.get("invoice_number") or "").strip()
            if not bill_number:
                continue
            grand_total = round(float(row.get("grand_total") or 0.0), 2)
            settled = round(float(row.get("amount_received") or 0.0), 2)
            allocated = self._sum_receipt_allocations_for_bill(
                company_id,
                party_id,
                bill_number,
                exclude_voucher_type,
                exclude_voucher_id,
            )
            outstanding = round(grand_total - settled - allocated, 2)
            if outstanding <= 0.004:
                continue
            invoice_date = str(row.get("invoice_date") or "")
            bills.append(
                {
                    "bill_number": bill_number,
                    "display_date": invoice_date,
                    "grand_total": grand_total,
                    "settled": settled + allocated,
                    "outstanding": outstanding,
                    "source_id": int(row.get("id") or 0),
                    "source_type": "sales",
                }
            )
        return bills

    def get_outstanding_purchase_bills(
        self,
        company_id: int,
        party_id: int,
        exclude_voucher_type: str = "",
        exclude_voucher_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return purchase bills with a positive pending balance for bill-wise payment allocation."""
        ph = self._ph()
        rows = self.db.execute_query(
            f"""
            SELECT id, purchase_number, purchase_date, grand_total, amount_paid, purchase_type
            FROM purchases
            WHERE company_id = {ph}
              AND party_id = {ph}
              AND COALESCE(status, 'Active') <> 'Voided'
            ORDER BY purchase_date, id
            """,
            (company_id, party_id),
        )
        bills: List[Dict[str, Any]] = []
        for row in rows or []:
            bill_number = str(row.get("purchase_number") or "").strip()
            if not bill_number:
                continue
            grand_total = round(float(row.get("grand_total") or 0.0), 2)
            settled = round(float(row.get("amount_paid") or 0.0), 2)
            allocated = self._sum_payment_allocations_for_bill(
                company_id,
                party_id,
                bill_number,
                exclude_voucher_type,
                exclude_voucher_id,
            )
            outstanding = round(grand_total - settled - allocated, 2)
            if outstanding <= 0.004:
                continue
            purchase_date = str(row.get("purchase_date") or "")
            bills.append(
                {
                    "bill_number": bill_number,
                    "display_date": purchase_date,
                    "grand_total": grand_total,
                    "settled": settled + allocated,
                    "outstanding": outstanding,
                    "source_id": int(row.get("id") or 0),
                    "source_type": "purchase",
                }
            )
        return bills

    def validate_bill_allocation_items(
        self,
        company_id: int,
        voucher_type: str,
        items: List[Dict[str, Any]],
        voucher_id: Optional[int] = None,
    ) -> Optional[str]:
        """Validate bill-wise allocation rows before save."""
        cfg = self.VOUCHERS.get(voucher_type, {})
        is_receipt = bool(cfg.get("is_receipt"))
        for index, item in enumerate(items, start=1):
            kind = str(item.get("account_kind") or "").lower()
            if kind != "bill":
                continue
            bill_number = str(item.get("towards_voucher_no") or "").strip()
            if not bill_number:
                return f"Row {index}: Please select an outstanding bill."
            party_id = item.get("party_id")
            if not party_id:
                return f"Row {index}: Please select a {'debtor' if is_receipt else 'creditor'} account."
            amount = round(float(item.get("amount") or 0.0), 2)
            bills = (
                self.get_outstanding_sales_bills(
                    company_id,
                    int(party_id),
                    exclude_voucher_type=voucher_type,
                    exclude_voucher_id=voucher_id,
                )
                if is_receipt
                else self.get_outstanding_purchase_bills(
                    company_id,
                    int(party_id),
                    exclude_voucher_type=voucher_type,
                    exclude_voucher_id=voucher_id,
                )
            )
            match = next(
                (
                    bill
                    for bill in bills
                    if str(bill.get("bill_number") or "").strip().lower() == bill_number.lower()
                ),
                None,
            )
            if not match:
                return f"Row {index}: Bill '{bill_number}' is not outstanding for this party."
            outstanding = round(float(match.get("outstanding") or 0.0), 2)
            if amount > outstanding + 0.004:
                return (
                    f"Row {index}: Amount {amount:.2f} exceeds outstanding balance "
                    f"{outstanding:.2f} for bill '{bill_number}'."
                )
        return None

    def _general_account_options(self, company_id: int) -> List[Dict[str, Any]]:
        """Return every selectable general ledger account for receipt/payment rows."""
        self.ensure_system_accounts(company_id)
        if hasattr(self.ledger_logic, "_ensure_extra_general_accounts"):
            self.ledger_logic._ensure_extra_general_accounts(company_id)

        merged_rows: Dict[int, Dict[str, Any]] = {}
        for row in self.ledger_logic.get_general_ledger_accounts(company_id):
            account_id = row.get("id")
            if account_id is not None:
                merged_rows[int(account_id)] = row
        for row in self.ledger_logic.get_account_options_by_type(company_id, "general"):
            account_id = row.get("id")
            if account_id is not None:
                merged_rows[int(account_id)] = row

        options: List[Dict[str, Any]] = []
        for account_id in sorted(merged_rows, key=lambda aid: str(merged_rows[aid].get("account_name") or "").lower()):
            row = merged_rows[account_id]
            account_name = str(row.get("account_name") or "").strip()
            if not account_name:
                continue

            account_type = str(row.get("account_type") or "").strip().lower()
            group_name = str(row.get("group_name") or "").strip().lower()

            if account_type == "party":
                continue
            if group_name in ("sundry debtors", "sundry creditors"):
                continue
            if account_type == "cash_bank":
                continue

            options.append(
                {
                    "id": int(account_id),
                    "label": account_name,
                    "kind": "general",
                    "party_id": None,
                }
            )
        return options

    def _party_options(self, company_id: int, party_types: Tuple[str, ...]) -> List[Dict[str, Any]]:
        ph = self._ph()
        placeholders = ",".join([ph] * len(party_types))
        has_ledger_account_id = self._column_exists("parties", "ledger_account_id")
        ledger_col = ", ledger_account_id" if has_ledger_account_id else ""
        rows = self.db.execute_query(
            f"""
            SELECT id, name, party_type, opening_balance{ledger_col}
            FROM parties
            WHERE company_id={ph} AND party_type IN ({placeholders})
            ORDER BY name
            """,
            (company_id, *party_types),
        )
        options: List[Dict[str, Any]] = []
        for row in rows:
            account_id = row.get("ledger_account_id") if has_ledger_account_id else None
            if not account_id:
                if hasattr(self.ledger_logic, "get_or_create_party_account"):
                    acct = self.ledger_logic.get_or_create_party_account(
                        company_id=company_id,
                        party_id=int(row["id"]),
                        party_name=row["name"],
                        party_type=row["party_type"],
                        opening_balance=float(row.get("opening_balance") or 0.0),
                        opening_balance_type="Cr" if row["party_type"] == "Creditor" else "Dr",
                    )
                    account_id = acct.get("id") if acct else None
                else:
                    acct = self.ledger_logic.get_account_by_name(company_id, row["name"]) if hasattr(self.ledger_logic, "get_account_by_name") else None
                    if acct:
                        account_id = acct.get("id")
                    else:
                        group_name = "Sundry Creditors" if row["party_type"] == "Creditor" else "Sundry Debtors"
                        ob_type = "Cr" if row["party_type"] == "Creditor" else "Dr"
                        account_id = self._create_ledger_account(company_id, row["name"], f"P{row['id']}", "party", group_name, ob_type, system=False)
            if account_id:
                kind = "creditor" if row["party_type"] == "Creditor" else "debtor"
                options.append({"id": int(account_id), "label": row["name"], "kind": kind, "party_id": int(row["id"])})
        return options

    def _get_account_balance_old(self, company_id: int, account_id: int) -> float:
        ph = self._ph()
        rows = self.db.execute_query(
            f"""
            SELECT COALESCE(la.opening_balance, 0) AS opening_balance,
                   COALESCE(la.opening_balance_type, 'Dr') AS opening_balance_type,
                   COALESCE(SUM(le.debit), 0) AS debit,
                   COALESCE(SUM(le.credit), 0) AS credit
            FROM ledger_accounts la
            LEFT JOIN ledger_entries le ON le.company_id=la.company_id AND le.account_id=la.id
            WHERE la.company_id={ph} AND la.id={ph}
            GROUP BY la.id, la.opening_balance, la.opening_balance_type
            """,
            (company_id, account_id),
        )
        if not rows:
            return 0.0
        r = rows[0]
        opening = float(r.get("opening_balance") or 0.0)
        if str(r.get("opening_balance_type") or "Dr").lower() == "cr":
            opening = -opening
        return round(opening + float(r.get("debit") or 0.0) - float(r.get("credit") or 0.0), 2)

    @staticmethod
    def format_balance(value: float) -> str:
        side = "Dr" if value >= 0 else "Cr"
        return f"{abs(float(value)):.2f} {side}"

    def get_account_balance(self, company_id: int, account_id: int) -> float:
        """
        Get account balance using LedgerLogic (SSOT for balance calculations).
        
        Args:
            company_id: Company ID
            account_id: Account ID
            
        Returns:
            Float balance: Positive = Dr balance, Negative = Cr balance
        """
        return self.ledger_logic.calculate_ledger_balance(company_id, account_id)

    def get_next_voucher_no(self, company_id: int, voucher_type: str) -> str:
        cfg = self.VOUCHERS[voucher_type]
        ph = self._ph()
        rows = self.db.execute_query(
            f"""
            SELECT voucher_no
            FROM {cfg['table']}
            WHERE company_id={ph}
            """,
            (company_id,),
        )
        return self._format_next_voucher_no(cfg["prefix"], rows)

    def _next_voucher_no_from_cursor(self, cursor, company_id: int, voucher_type: str) -> str:
        """Return next voucher number using rows visible inside the active transaction."""
        cfg = self.VOUCHERS[voucher_type]
        ph = self._ph()
        cursor.execute(
            f"""
            SELECT voucher_no
            FROM {cfg['table']}
            WHERE company_id={ph}
            """,
            (company_id,),
        )
        return self._format_next_voucher_no(cfg["prefix"], cursor.fetchall())

    def _format_next_voucher_no(self, prefix: str, rows) -> str:
        """Calculate next voucher number from the largest trailing numeric suffix."""
        max_no = 0
        for row in rows or []:
            raw = self._row_value(row, "voucher_no", 0)
            seq_no = self._voucher_sequence_number(raw, prefix)
            if seq_no is not None:
                max_no = max(max_no, seq_no)
        return f"{prefix}-{max_no + 1:04d}"

    @staticmethod
    def _voucher_sequence_number(voucher_no: Any, prefix: str) -> Optional[int]:
        """Extract the trailing numeric suffix from a voucher number."""
        text = str(voucher_no or "").strip()
        if not text:
            return None
        upper_text = text.upper()
        upper_prefix = prefix.upper()
        if not upper_text.startswith(upper_prefix):
            match = re.search(r"(\d+)$", text)
        else:
            match = re.search(r"(\d+)$", text)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _row_value(row: Any, key: str, index: int) -> Any:
        """Read a column from dict-like or tuple-like DB cursor rows."""
        try:
            return row[key]
        except Exception:
            try:
                return row[index]
            except Exception:
                return None

    def _begin_voucher_transaction(self, conn, cursor) -> None:
        """Start a transaction with the strongest portable lock available."""
        if self.db.db_type == "sqlite":
            cursor.execute("BEGIN IMMEDIATE")
            return
        if hasattr(conn, "start_transaction"):
            conn.start_transaction()
            return
        cursor.execute("START TRANSACTION")

    @staticmethod
    def _rollback_quietly(conn) -> None:
        """Rollback a transaction without masking the original error."""
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass

    @staticmethod
    def _is_unique_voucher_error(exc: Exception) -> bool:
        """Return True when the database reports a duplicate voucher number."""
        text = str(exc).lower()
        return (
            "unique constraint" in text
            or "duplicate entry" in text
            or "duplicate key" in text
        ) and "voucher" in text

    # ------------------------------------------------------------------
    # Voucher CRUD
    # ------------------------------------------------------------------
    def list_vouchers(self, company_id: int, voucher_type: str) -> List[Dict[str, Any]]:
        self.ensure_schema()
        cfg = self.VOUCHERS[voucher_type]
        ph = self._ph()
        return self.db.execute_query(
            f"""
            SELECT * FROM {cfg['table']}
            WHERE company_id={ph}
            ORDER BY DATE(voucher_date), id
            """,
            (company_id,),
        )

    def load_voucher(self, company_id: int, voucher_type: str, voucher_id: int) -> Dict[str, Any]:
        self.ensure_schema()
        cfg = self.VOUCHERS[voucher_type]
        ph = self._ph()
        header_rows = self.db.execute_query(
            f"SELECT * FROM {cfg['table']} WHERE company_id={ph} AND id={ph}",
            (company_id, voucher_id),
        )
        if not header_rows:
            return {"success": False, "message": "Voucher not found"}
        item_rows = self.db.execute_query(
            f"SELECT * FROM {cfg['items_table']} WHERE {cfg['item_fk']}={ph} ORDER BY id",
            (voucher_id,),
        )
        # Existing old vouchers may not have item rows. Create a display row from header.
        if not item_rows:
            h = header_rows[0]
            item_rows = [{
                "account_id": h.get(cfg["account_field"]),
                "party_id": h.get("party_id"),
                "account_kind": "",
                "towards_voucher_no": h.get("towards_acc") or "",
                "amount": h.get("amount") or h.get("total_amount") or 0.0,
                "discount": h.get("total_discount") or 0.0,
                "narration": h.get("narration") or "",
            }]
        return {"success": True, "header": header_rows[0], "items": item_rows}

    def delete_voucher(self, company_id: int, voucher_type: str, voucher_id: int) -> Dict[str, Any]:
        self.ensure_schema()
        cfg = self.VOUCHERS[voucher_type]
        ph = self._ph()
        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            self._begin_voucher_transaction(conn, cursor)
            cursor.execute(
                f"""
                SELECT voucher_no
                FROM {cfg['table']}
                WHERE id={ph} AND company_id={ph}
                """,
                (voucher_id, company_id),
            )
            voucher_row = cursor.fetchone()
            old_voucher_no = str(voucher_id)
            if voucher_row:
                old_voucher_no = (
                    voucher_row["voucher_no"]
                    if hasattr(voucher_row, "keys")
                    else voucher_row[0]
                )
            success, error_msg = self.posting_engine.delete_voucher_ledger_entries(
                company_id, voucher_type, voucher_id, conn=conn, commit=False
            )
            if not success:
                self._rollback_quietly(conn)
                return {"success": False, "message": f"Transaction failed: Ledger deletion failed: {error_msg}"}
            cursor.execute(f"DELETE FROM {cfg['items_table']} WHERE {cfg['item_fk']}={ph}", (voucher_id,))
            cursor.execute(f"DELETE FROM {cfg['table']} WHERE id={ph} AND company_id={ph}", (voucher_id, company_id))
            if cursor.rowcount == 0:
                self._rollback_quietly(conn)
                return {"success": False, "message": "Transaction failed: Voucher not found"}
            if not log_action(
                company_id,
                None,
                "Cash/Bank",
                "DELETE",
                old_voucher_no,
                f"Deleted {cfg['voucher_title']} voucher.",
                conn=conn,
            ):
                raise Exception("Audit logging failed")
            conn.commit()
            return {"success": True, "message": "Voucher deleted"}
        except Exception as exc:
            self._rollback_quietly(conn)
            return {"success": False, "message": f"Transaction failed: {str(exc)}"}
        finally:
            if conn is not None:
                self.db.disconnect()

    def save_or_update_voucher(self, company_id: int, voucher_type: str, header: Dict[str, Any], items: List[Dict[str, Any]], voucher_id: Optional[int] = None) -> Dict[str, Any]:
        self.ensure_schema()
        cfg = self.VOUCHERS[voucher_type]
        clean_items = [self._clean_item(it) for it in items if self._clean_item(it).get("account_id") and self._clean_item(it).get("amount") > 0]
        if not clean_items:
            return {"success": False, "message": "Please enter at least one account row with amount."}
        bill_error = self.validate_bill_allocation_items(company_id, voucher_type, clean_items, voucher_id)
        if bill_error:
            return {"success": False, "message": bill_error}
        money_account_id = int(header.get("money_account_id") or 0)
        if not money_account_id:
            return {"success": False, "message": "Please select Cash/Bank account."}
        voucher_no = (header.get("voucher_no") or "").strip()
        auto_number = not voucher_no
        voucher_date = header.get("voucher_date") or datetime.now().strftime("%Y-%m-%d")
        remark = header.get("remark") or ""
        narration = header.get("narration") or remark
        total_amount = round(sum(i["amount"] for i in clean_items), 2)
        total_discount = round(sum(i.get("discount", 0.0) for i in clean_items), 2)
        first = clean_items[0]
        first_account_id = int(first["account_id"])
        first_party_id = first.get("party_id")
        first_towards = first.get("towards_voucher_no") or ""
        self.ensure_system_accounts(company_id)
        if cfg.get("discount_allowed") and total_discount > 0.004:
            self._get_discount_allowed_account(company_id)

        ph = self._ph()
        attempts = 3 if auto_number else 1
        for attempt_no in range(attempts):
            conn = None
            try:
                conn = self.db.connect()
                cursor = conn.cursor()
                self._begin_voucher_transaction(conn, cursor)
                current_voucher_no = voucher_no
                if auto_number:
                    current_voucher_no = self._next_voucher_no_from_cursor(cursor, company_id, voucher_type)

                if voucher_id:
                    current_voucher_id = int(voucher_id)
                    self._update_header_cursor(cursor, voucher_type, current_voucher_id, company_id,
                                               current_voucher_no, voucher_date, first_account_id,
                                               money_account_id, first_party_id, total_amount,
                                               first_towards, remark, narration, total_discount)
                else:
                    current_voucher_id = self._insert_header_cursor(
                        cursor, voucher_type, company_id, current_voucher_no, voucher_date,
                        first_account_id, money_account_id, first_party_id, total_amount,
                        first_towards, remark, narration, total_discount
                    )
                if not current_voucher_id:
                    self._rollback_quietly(conn)
                    return {"success": False, "message": "Failed to save voucher header."}

                # Replace item rows and ledger rows in the same transaction.
                cursor.execute(f"DELETE FROM {cfg['items_table']} WHERE {cfg['item_fk']}={ph}", (current_voucher_id,))
                for item in clean_items:
                    self._insert_item_cursor(cursor, voucher_type, int(current_voucher_id), item)

                success, error = self._post_ledger(
                    company_id, voucher_type, int(current_voucher_id), current_voucher_no,
                    voucher_date, money_account_id, clean_items, narration, conn=conn, commit=False
                )
                if not success:
                    self._rollback_quietly(conn)
                    if "System Error: Ledger math is unbalanced. Save aborted to protect Trial Balance." in str(error):
                        return {
                            "success": False,
                            "message": "System Error: Ledger math is unbalanced. Save aborted to protect Trial Balance.",
                        }
                    return {"success": False, "message": f"Ledger posting failed: {error}"}

                action_type = "UPDATE" if voucher_id else "CREATE"
                action_word = "Updated" if voucher_id else "Created"
                if not log_action(
                    company_id,
                    None,
                    "Cash/Bank",
                    action_type,
                    current_voucher_no,
                    f"{action_word} {cfg['voucher_title']} voucher for {total_amount}.",
                    conn=conn,
                ):
                    raise Exception("Audit logging failed")

                conn.commit()
                from ui.dashboard_refresh import request_dashboard_refresh
                request_dashboard_refresh()
                return {
                    "success": True,
                    "data": {"id": int(current_voucher_id), "voucher_no": current_voucher_no},
                    "message": "Voucher saved",
                }
            except Exception as exc:
                self._rollback_quietly(conn)
                if auto_number and self._is_unique_voucher_error(exc) and attempt_no < attempts - 1:
                    continue
                if self._is_unique_voucher_error(exc):
                    return {
                        "success": False,
                        "message": "Voucher number already exists. Please refresh and try again.",
                    }
                return {"success": False, "message": str(exc)}

    def _insert_header(self, voucher_type: str, company_id: int, voucher_no: str, voucher_date: str,
                       account_id: int, money_account_id: int, party_id: Optional[int], amount: float,
                       towards: str, remark: str, narration: str, discount: float) -> Optional[int]:
        conn = self.db.connect()
        try:
            cursor = conn.cursor()
            row_id = self._insert_header_cursor(
                cursor, voucher_type, company_id, voucher_no, voucher_date, account_id,
                money_account_id, party_id, amount, towards, remark, narration, discount
            )
            conn.commit()
            return row_id
        except Exception:
            conn.rollback()
            raise

    def _insert_header_cursor(self, cursor, voucher_type: str, company_id: int, voucher_no: str,
                              voucher_date: str, account_id: int, money_account_id: int,
                              party_id: Optional[int], amount: float, towards: str,
                              remark: str, narration: str, discount: float) -> Optional[int]:
        cfg = self.VOUCHERS[voucher_type]
        ph = self._ph()
        ts = self._ts()
        money_field = cfg["money_field"]
        account_field = cfg["account_field"]
        table = cfg["table"]
        # receipt_no/payment_no exists only for cash tables; harmless if available.
        columns = self._table_columns(table)
        fields = ["company_id", "voucher_no", "voucher_date", account_field, money_field, "party_id", "amount", "towards_acc", "remark", "narration", "total_amount", "total_discount", "created_at", "updated_at"]
        values = [company_id, voucher_no, voucher_date, account_id, money_account_id, party_id, amount, towards, remark, narration, amount, discount]
        if "receipt_no" in columns:
            fields.insert(2, "receipt_no")
            values.insert(2, voucher_no)
        if "payment_no" in columns:
            fields.insert(2, "payment_no")
            values.insert(2, voucher_no)
        placeholder_text = ", ".join([ph] * (len(fields) - 2) + [ts, ts])
        cursor.execute(
            f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({placeholder_text})",
            tuple(values),
        )
        return self.db._get_last_insert_id(cursor)

    def _update_header(self, voucher_type: str, voucher_id: int, company_id: int, voucher_no: str, voucher_date: str,
                       account_id: int, money_account_id: int, party_id: Optional[int], amount: float,
                       towards: str, remark: str, narration: str, discount: float) -> None:
        conn = self.db.connect()
        try:
            cursor = conn.cursor()
            self._update_header_cursor(
                cursor, voucher_type, voucher_id, company_id, voucher_no, voucher_date,
                account_id, money_account_id, party_id, amount, towards, remark, narration, discount
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _update_header_cursor(self, cursor, voucher_type: str, voucher_id: int, company_id: int,
                              voucher_no: str, voucher_date: str, account_id: int,
                              money_account_id: int, party_id: Optional[int], amount: float,
                              towards: str, remark: str, narration: str, discount: float) -> None:
        cfg = self.VOUCHERS[voucher_type]
        ph = self._ph()
        ts = self._ts()
        table = cfg["table"]
        money_field = cfg["money_field"]
        account_field = cfg["account_field"]
        sets = [
            f"voucher_no={ph}", f"voucher_date={ph}", f"{account_field}={ph}", f"{money_field}={ph}",
            f"party_id={ph}", f"amount={ph}", f"towards_acc={ph}", f"remark={ph}", f"narration={ph}",
            f"total_amount={ph}", f"total_discount={ph}", f"updated_at={ts}",
        ]
        params: List[Any] = [voucher_no, voucher_date, account_id, money_account_id, party_id, amount, towards, remark, narration, amount, discount]
        columns = self._table_columns(table)
        if "receipt_no" in columns:
            sets.insert(1, f"receipt_no={ph}")
            params.insert(1, voucher_no)
        if "payment_no" in columns:
            sets.insert(1, f"payment_no={ph}")
            params.insert(1, voucher_no)
        params.extend([voucher_id, company_id])
        cursor.execute(
            f"UPDATE {table} SET {', '.join(sets)} WHERE id={ph} AND company_id={ph}",
            tuple(params),
        )

    def _table_columns(self, table: str) -> List[str]:
        if self.db.db_type != "sqlite":
            return []
        conn = self.db.connect()
        try:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table})")
            return [r[1] for r in cursor.fetchall()]
        finally:
            self.db.disconnect()

    def _insert_item(self, voucher_type: str, voucher_id: int, item: Dict[str, Any]) -> None:
        conn = self.db.connect()
        try:
            cursor = conn.cursor()
            self._insert_item_cursor(cursor, voucher_type, voucher_id, item)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _insert_item_cursor(self, cursor, voucher_type: str, voucher_id: int, item: Dict[str, Any]) -> None:
        cfg = self.VOUCHERS[voucher_type]
        ph = self._ph()
        ts = self._ts()
        table = cfg["items_table"]
        fk = cfg["item_fk"]
        discount = item.get("discount", 0.0) if cfg.get("discount_allowed") else 0.0
        cursor.execute(
            f"""
            INSERT INTO {table} ({fk}, account_id, party_id, account_kind, towards_voucher_no,
                amount, discount, narration, created_at, updated_at)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ts}, {ts})
            """,
            (voucher_id, item["account_id"], item.get("party_id"), item.get("account_kind") or "",
             item.get("towards_voucher_no") or "", item.get("amount") or 0.0, discount,
             item.get("narration") or ""),
        )

    def _clean_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        try:
            amount = round(float(item.get("amount") or 0.0), 2)
        except Exception:
            amount = 0.0
        try:
            discount = round(float(item.get("discount") or 0.0), 2)
        except Exception:
            discount = 0.0
        account_id = item.get("account_id")
        try:
            account_id = int(account_id) if account_id else None
        except Exception:
            account_id = None
        party_id = item.get("party_id")
        try:
            party_id = int(party_id) if party_id else None
        except Exception:
            party_id = None
        return {
            "account_id": account_id,
            "party_id": party_id,
            "account_kind": item.get("account_kind") or "",
            "towards_voucher_no": item.get("towards_voucher_no") or "",
            "amount": amount,
            "discount": discount,
            "narration": item.get("narration") or "",
        }

    def _post_ledger(self, company_id: int, voucher_type: str, voucher_id: int, voucher_no: str,
                     voucher_date: str, money_account_id: int, items: List[Dict[str, Any]],
                     narration: str, conn=None, commit: bool = True) -> Tuple[bool, str]:
        cfg = self.VOUCHERS[voucher_type]
        is_receipt = bool(cfg["is_receipt"])
        entries: List[Dict[str, Any]] = []
        total_amount = round(sum(i["amount"] for i in items), 2)
        ledger_money_account_id = (
            self._get_bank_ledger_account_id(company_id, money_account_id)
            if voucher_type.startswith("bank") else money_account_id
        )
        base_narration = narration or cfg["voucher_title"]
        if is_receipt:
            # Commercial rule: ledger must keep every transaction separately.
            # Amount receipt and discount are posted as separate debtor/creditor/general ledger rows,
            # so party ledger shows both Cash/Bank Receipt and Discount Allowed instead of one hidden combined credit.
            entries.append({
                "account_id": ledger_money_account_id,
                "debit": total_amount,
                "credit": 0.0,
                "narration": f"{cfg['voucher_title']} {voucher_no}",
            })
            discount_account_id = self._get_discount_allowed_account(company_id) if cfg.get("discount_allowed") else None
            for item in items:
                amount = round(float(item.get("amount") or 0.0), 2)
                discount = round(float(item.get("discount") or 0.0), 2) if cfg.get("discount_allowed") else 0.0
                if amount > 0.004:
                    entries.append({
                        "account_id": int(item["account_id"]),
                        "debit": 0.0,
                        "credit": amount,
                        "narration": f"{cfg['voucher_title']} {voucher_no}",
                    })
                if discount > 0.004 and discount_account_id:
                    entries.append({
                        "account_id": int(discount_account_id),
                        "debit": discount,
                        "credit": 0.0,
                        "narration": f"Discount Allowed {voucher_no}",
                    })
                    entries.append({
                        "account_id": int(item["account_id"]),
                        "debit": 0.0,
                        "credit": discount,
                        "narration": f"Discount Allowed {voucher_no}",
                    })
        else:
            for item in items:
                entries.append({
                    "account_id": int(item["account_id"]),
                    "debit": item["amount"],
                    "credit": 0.0,
                    "narration": f"{cfg['voucher_title']} {voucher_no}",
                })
            entries.append({
                "account_id": ledger_money_account_id,
                "debit": 0.0,
                "credit": total_amount,
                "narration": f"{cfg['voucher_title']} {voucher_no}",
            })
        entries = [e for e in entries if abs(e.get("debit", 0.0)) > 0.004 or abs(e.get("credit", 0.0)) > 0.004]
        return self.posting_engine.post_manual_double_entry(
            company_id=company_id,
            voucher_type=voucher_type,
            voucher_id=voucher_id,
            voucher_no=voucher_no,
            voucher_date=voucher_date,
            entries=entries,
            narration=base_narration,
            conn=conn,
            commit=commit,
        )

    def _get_discount_allowed_account(self, company_id: int) -> int:
        self.ensure_system_accounts(company_id)
        acct = self.ledger_logic.get_account_by_name(company_id, "Discount Allowed") or self.ledger_logic.get_account_by_name(company_id, "Discount Given")
        if acct:
            return int(acct["id"])
        return self._create_ledger_account(company_id, "Discount Allowed", "DISC_ALW", "expense", "Discount", "Dr", system=True)
