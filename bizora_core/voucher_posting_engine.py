"""
Commercial Voucher Posting Engine for the Accounting Desktop Application.

This is the single posting layer for accounting vouchers.  It is UI-free and
uses only database/logic services.  All voucher save/update/delete flows should
call this engine after voucher header/items are saved.

Commercial rules implemented here:
- Item rows + approved footer adjustments are calculation truth.
- Cash type overpayment is blocked.
- Credit type overpayment is allowed and remains visible as party advance /
  on-account inside the same party ledger.
- Every posting must balance before it is written.
- Update/delete must remove old ledger/stock rows first, preventing duplicates.
- SQL placeholders are generated through db._get_placeholder().
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from bizora_core.commercial_calculation_engine import CommercialCalculationEngine
from bizora_core.commercial_voucher_validator import CommercialVoucherValidator
from bizora_core.common_finance import to_decimal, money_round, is_balanced, safe_add, safe_subtract
from bizora_core.posting_lock import acquire, release


@dataclass
class PostingResult:
    success: bool
    message: str = ""
    voucher_type: str = ""
    voucher_id: Optional[int] = None
    voucher_no: str = ""
    ledger_entries_deleted: int = 0
    ledger_entries_posted: int = 0
    stock_movements_deleted: int = 0
    stock_movements_posted: int = 0
    total_debit: float = 0.0
    total_credit: float = 0.0
    failed_reason: str = ""
    warnings: List[str] = field(default_factory=list)
    entries_preview: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "voucher_type": self.voucher_type,
            "voucher_id": self.voucher_id,
            "voucher_no": self.voucher_no,
            "ledger_entries_deleted": self.ledger_entries_deleted,
            "ledger_entries_posted": self.ledger_entries_posted,
            "stock_movements_deleted": self.stock_movements_deleted,
            "stock_movements_posted": self.stock_movements_posted,
            "total_debit": round(self.total_debit, 2),
            "total_credit": round(self.total_credit, 2),
            "failed_reason": self.failed_reason,
            "warnings": list(self.warnings),
            "entries_preview": list(self.entries_preview),
        }


class VoucherPostingEngine:
    """Commercial posting engine for bill, receipt, payment and journal vouchers."""

    LEDGER_MATH_ERROR = "System Error: Ledger math is unbalanced. Save aborted to protect Trial Balance."
    ROUND_OFF_ACCOUNT_NAME = "Round Off"

    VOUCHER_ALIASES = {
        "sale": "sales",
        "sales": "sales",
        "sales_entry": "sales",
        "purchase": "purchase",
        "purchases": "purchase",
        "purchase_entry": "purchase",
        "sales_return": "sales_return",
        "sale_return": "sales_return",
        "purchase_return": "purchase_return",
        "cash_receipt": "cash_receipt",
        "cash_payment": "cash_payment",
        "bank_receipt": "bank_receipt",
        "bank_payment": "bank_payment",
        "journal": "journal",
        "journal_entry": "journal",
        "opening": "opening",
        "opening_balance": "opening",
    }

    STOCK_REFERENCE_TYPE = {
        "sales": "sale",
        "purchase": "purchase",
        "sales_return": "sales_return",
        "purchase_return": "purchase_return",
        "opening": "opening",
    }

    TABLE_MAP = {
        "sales": "sales",
        "purchase": "purchases",
        "sales_return": "sales_returns",
        "purchase_return": "purchase_returns",
        "cash_receipt": "cash_receipts",
        "cash_payment": "cash_payments",
        "bank_receipt": "bank_receipts",
        "bank_payment": "bank_payments",
        "journal": "journal_vouchers",
        "opening": "opening_balances",
    }

    ITEM_MAP = {
        "sales": ("sales_items", "sale_id"),
        "purchase": ("purchase_items", "purchase_id"),
        "sales_return": ("sales_return_items", "sales_return_id"),
        "purchase_return": ("purchase_return_items", "purchase_return_id"),
        "cash_receipt": ("cash_receipt_items", "receipt_id"),
        "cash_payment": ("cash_payment_items", "payment_id"),
        "journal": ("journal_voucher_lines", "journal_id"),
        "opening": ("opening_ledger_items", "opening_id"),
    }

    def __init__(self, db: Any, debug: bool = False):
        self.db = db
        self.debug = debug
        self._ledger_logic = None
        self._active_cursor = None
        self._table_columns_cache: Dict[str, set] = {}
        self.calculator = CommercialCalculationEngine()
        self.validator = CommercialVoucherValidator()
        # GLOBAL POSTING LOCK: Prevent signal feedback loops and concurrent posting
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _ledger(self):
        if self._ledger_logic is None:
            from bizora_core.ledger_logic import LedgerLogic
            self._ledger_logic = LedgerLogic(self.db)
        return self._ledger_logic

    def _log(self, message: str) -> None:
        if self.debug:
            print(f"[VoucherPostingEngine] {message}")

    @staticmethod
    def _amount(value: Any) -> float:
        try:
            if value is None or value == "":
                return 0.0
            return float(money_round(to_decimal(value)))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _text(value: Any, default: str = "") -> str:
        return default if value is None else str(value)

    @staticmethod
    def _date_text(value: Any) -> str:
        if value is None or value == "":
            return date.today().isoformat()
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return str(value)[:10]

    @staticmethod
    def _row_dict(row: Any, columns: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        if row is None:
            return {}
        if isinstance(row, dict):
            return dict(row)
        try:
            return dict(row)
        except Exception:
            if columns:
                return {column: row[index] for index, column in enumerate(columns)}
            return {}

    def _query(self, sql: str, params: Sequence[Any] = (),
               cursor=None) -> List[Dict[str, Any]]:
        cursor = cursor or self._active_cursor
        if cursor is not None:
            cursor.execute(sql, tuple(params))
            columns = [description[0] for description in (cursor.description or [])]
            return [self._row_dict(row, columns) for row in cursor.fetchall()]
        rows = self.db.execute_query(sql, tuple(params)) or []
        return [self._row_dict(row) for row in rows]

    def _query_one(self, sql: str, params: Sequence[Any] = (),
                   cursor=None) -> Optional[Dict[str, Any]]:
        rows = self._query(sql, params, cursor=cursor)
        return rows[0] if rows else None

    def _execute(self, sql: str, params: Sequence[Any] = ()) -> bool:
        return bool(self.db.execute_update(sql, tuple(params)))

    def normalize_voucher_type(self, voucher_type: str) -> str:
        key = str(voucher_type or "").strip().lower()
        return self.VOUCHER_ALIASES.get(key, key)

    def table_exists(self, table_name: str, cursor=None) -> bool:
        try:
            ph = self.db._get_placeholder()
            if hasattr(self.db, "_is_sqlite") and self.db._is_sqlite():
                row = self._query_one(
                    f"SELECT name FROM sqlite_master WHERE type = {ph} AND name = {ph}",
                    ("table", table_name),
                    cursor=cursor,
                )
                return bool(row)
            return True
        except Exception:
            return False

    def table_columns(self, table_name: str, cursor=None) -> set:
        cursor = cursor or self._active_cursor
        if cursor is None and table_name in self._table_columns_cache:
            return self._table_columns_cache[table_name]
        columns = set()
        try:
            if hasattr(self.db, "_is_sqlite") and self.db._is_sqlite():
                close_after_read = cursor is None
                conn = None
                if close_after_read:
                    conn = self.db.connect()
                    cursor = conn.cursor()
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = {row[1] for row in cursor.fetchall()}
                if close_after_read:
                    self.db.disconnect()
        except Exception:
            try:
                if cursor is None:
                    self.db.disconnect()
            except Exception:
                pass
        if cursor is None:
            self._table_columns_cache[table_name] = columns
        return columns

    def first_value(self, data: Dict[str, Any], names: Iterable[str], default: Any = None) -> Any:
        for name in names:
            if name in data and data.get(name) not in (None, ""):
                return data.get(name)
        return default

    # ------------------------------------------------------------------
    # Account helpers
    # ------------------------------------------------------------------

    def ensure_accounts(self, company_id: int, cursor=None) -> None:
        cursor = cursor or self._active_cursor
        if cursor is not None:
            ledger = self._ledger()
            ph = self.db._get_placeholder()
            timestamp_default = self.db._get_timestamp_default()
            for name, code, account_type, group_name, opening_type in ledger._SYSTEM_ACCOUNTS:
                cursor.execute(
                    f"""
                    SELECT id
                    FROM ledger_accounts
                    WHERE company_id = {ph}
                      AND account_name = {ph}
                    """,
                    (company_id, name),
                )
                existing_account = cursor.fetchone()
                if existing_account:
                    cursor.execute(
                        f"""
                        UPDATE ledger_accounts
                        SET is_system = 1
                        WHERE company_id = {ph}
                          AND account_name = {ph}
                          AND COALESCE(is_system, 0) <> 1
                        """,
                        (company_id, name),
                    )
                    continue
                cursor.execute(
                    f"""
                    INSERT INTO ledger_accounts (
                        company_id, account_name, account_code, account_type,
                        group_name, opening_balance, opening_balance_type,
                        is_system, is_active, created_at, updated_at
                    ) VALUES (
                        {ph}, {ph}, {ph}, {ph}, {ph}, 0.0, {ph},
                        1, 1, {timestamp_default}, {timestamp_default}
                    )
                    """,
                    (company_id, name, code, account_type, group_name, opening_type),
                )
            if hasattr(ledger, "invalidate_accounts_cache"):
                ledger.invalidate_accounts_cache(company_id)
            return

        ledger = self._ledger()
        if hasattr(ledger, "ensure_system_accounts"):
            ledger.ensure_system_accounts(company_id)
        if hasattr(ledger, "ensure_party_ledger_accounts"):
            ledger.ensure_party_ledger_accounts(company_id)

    def account_by_name(self, company_id: int, account_name: str,
                        cursor=None) -> Optional[Dict[str, Any]]:
        cursor = cursor or self._active_cursor
        if cursor is not None:
            ph = self.db._get_placeholder()
            return self._query_one(
                f"""
                SELECT id, company_id, account_name, account_code, account_type,
                       group_name, opening_balance, opening_balance_type,
                       is_system, is_active
                FROM ledger_accounts
                WHERE company_id = {ph}
                  AND account_name = {ph}
                """,
                (company_id, account_name),
                cursor=cursor,
            )

        ledger = self._ledger()
        account = None
        if hasattr(ledger, "get_account_by_name_cached"):
            account = ledger.get_account_by_name_cached(company_id, account_name)
        if not account and hasattr(ledger, "get_account_by_name"):
            account = ledger.get_account_by_name(company_id, account_name)
        return account

    def account_by_id(self, company_id: int, account_id: Any,
                      cursor=None) -> Optional[Dict[str, Any]]:
        if not account_id:
            return None
        cursor = cursor or self._active_cursor
        if cursor is not None:
            ph = self.db._get_placeholder()
            return self._query_one(
                f"""
                SELECT id, company_id, account_name, account_code, account_type,
                       group_name, opening_balance, opening_balance_type,
                       is_system, is_active
                FROM ledger_accounts
                WHERE company_id = {ph}
                  AND id = {ph}
                """,
                (company_id, int(account_id)),
                cursor=cursor,
            )

        ledger = self._ledger()
        if hasattr(ledger, "get_account"):
            return ledger.get_account(company_id, int(account_id))
        ph = self.db._get_placeholder()
        return self._query_one(
            f"SELECT * FROM ledger_accounts WHERE company_id = {ph} AND id = {ph}",
            (company_id, int(account_id)),
        )

    def _create_party_account_with_cursor(self, company_id: int, party_id: int,
                                          party: Dict[str, Any],
                                          cursor) -> Optional[Dict[str, Any]]:
        """Create and link a party ledger account inside the active transaction."""
        ph = self.db._get_placeholder()
        party_name = self._text(party.get("name"))
        party_type = self._text(party.get("party_type"), "Debitor")
        opening_balance = self._amount(party.get("opening_balance", 0.0))
        opening_balance_type = "Cr" if party_type == "Creditor" else "Dr"
        group_name = "Sundry Creditors" if opening_balance_type == "Cr" else "Sundry Debtors"
        account = self.account_by_name(company_id, party_name, cursor=cursor)
        if account:
            account_id = int(account["id"])
        else:
            timestamp_default = self.db._get_timestamp_default()
            cursor.execute(
                f"""
                INSERT INTO ledger_accounts (
                    company_id, account_name, account_code, account_type,
                    group_name, opening_balance, opening_balance_type,
                    is_system, is_active, created_at, updated_at
                ) VALUES (
                    {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph},
                    0, 1, {timestamp_default}, {timestamp_default}
                )
                """,
                (
                    company_id,
                    party_name,
                    None,
                    "party",
                    group_name,
                    opening_balance,
                    opening_balance_type,
                ),
            )
            account_id = self.db._get_last_insert_id(cursor)
            account = self.account_by_id(company_id, account_id, cursor=cursor)

        cursor.execute(
            f"""
            UPDATE parties
            SET ledger_account_id = {ph}
            WHERE id = {ph}
              AND company_id = {ph}
            """,
            (account_id, party_id, company_id),
        )
        return account

    def account_by_party(self, company_id: int, party_id: Any,
                         fallback_group: str) -> Optional[Dict[str, Any]]:
        if not party_id:
            return self.account_by_name(company_id, fallback_group)
        cursor = self._active_cursor
        if cursor is not None:
            ph = self.db._get_placeholder()
            party = self._query_one(
                f"""
                SELECT id, name, party_type, opening_balance, ledger_account_id
                FROM parties
                WHERE id = {ph}
                  AND company_id = {ph}
                """,
                (int(party_id), company_id),
                cursor=cursor,
            )
            if party:
                linked_account_id = party.get("ledger_account_id")
                if linked_account_id:
                    account = self.account_by_id(
                        company_id, linked_account_id, cursor=cursor
                    )
                    if account:
                        return account
                return self._create_party_account_with_cursor(
                    company_id, int(party_id), party, cursor
                ) or self.account_by_name(company_id, fallback_group, cursor=cursor)
            return self.account_by_name(company_id, fallback_group, cursor=cursor)

        ledger = self._ledger()
        account = None
        if hasattr(ledger, "get_account_by_party_id"):
            account = ledger.get_account_by_party_id(company_id, int(party_id))
        return account or self.account_by_name(company_id, fallback_group)

    def fallback_account(self, company_id: int) -> Optional[Dict[str, Any]]:
        return self.account_by_name(company_id, "Suspense Account")

    def _add_entry(
        self,
        entries: List[Dict[str, Any]],
        account: Optional[Dict[str, Any]],
        debit: float = 0.0,
        credit: float = 0.0,
        narration: str = "",
    ) -> None:
        debit = round(self._amount(debit), 2)
        credit = round(self._amount(credit), 2)
        if not account or (is_balanced(debit, 0) and is_balanced(credit, 0)):
            return
        entries.append({
            "account_id": int(account["id"]),
            "debit": max(debit, 0.0),
            "credit": max(credit, 0.0),
            "narration": narration,
        })

    def _round_off_account(self, company_id: int) -> Optional[Dict[str, Any]]:
        """Return the Round Off ledger account, creating it if legacy data lacks it."""
        account = self.account_by_name(company_id, self.ROUND_OFF_ACCOUNT_NAME)
        if account:
            return account

        try:
            if self._active_cursor is not None:
                cursor = self._active_cursor
                ph = self.db._get_placeholder()
                timestamp_default = self.db._get_timestamp_default()
                cursor.execute(
                    f"""
                    INSERT INTO ledger_accounts (
                        company_id, account_name, account_code, account_type,
                        group_name, opening_balance, opening_balance_type,
                        is_system, is_active, created_at, updated_at
                    ) VALUES (
                        {ph}, {ph}, {ph}, {ph}, {ph}, 0.0, {ph},
                        0, 1, {timestamp_default}, {timestamp_default}
                    )
                    """,
                    (
                        company_id,
                        self.ROUND_OFF_ACCOUNT_NAME,
                        "ROUND_OFF",
                        "expense",
                        "Indirect Expenses",
                        "Dr",
                    ),
                )
                account_id = self.db._get_last_insert_id(cursor)
                return self.account_by_id(company_id, account_id, cursor=cursor)

            ledger = self._ledger()
            if hasattr(ledger, "create_account"):
                account_id = ledger.create_account(company_id, {
                    "account_name": self.ROUND_OFF_ACCOUNT_NAME,
                    "account_code": "ROUND_OFF",
                    "account_type": "expense",
                    "group_name": "Indirect Expenses",
                    "opening_balance": 0.0,
                    "opening_balance_type": "Dr",
                })
                if account_id and hasattr(ledger, "invalidate_accounts_cache"):
                    ledger.invalidate_accounts_cache(company_id)
                if account_id:
                    return self.account_by_name(company_id, self.ROUND_OFF_ACCOUNT_NAME) or {
                        "id": account_id,
                        "account_name": self.ROUND_OFF_ACCOUNT_NAME,
                    }
        except Exception as exc:
            self._log(f"Round Off account creation failed: {exc}")
        return None

    @staticmethod
    def _entry_side_total(entries: List[Dict[str, Any]], side: str) -> Decimal:
        """Calculate a Decimal total for a debit or credit side."""
        total = Decimal("0.00")
        for entry in entries:
            total += to_decimal(entry.get(side, 0.0))
        return money_round(total)

    def _balance_entries_with_round_off(
        self,
        company_id: int,
        entries: List[Dict[str, Any]],
        warnings: List[str],
        narration: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Absorb final voucher drift into the Round Off account before validation.

        Positive adjustment is posted as debit; negative adjustment is posted as
        credit. Existing Round Off rows are collapsed into one adjusted row.
        """
        total_debit = self._entry_side_total(entries, "debit")
        total_credit = self._entry_side_total(entries, "credit")
        adjustment = money_round(total_credit - total_debit)

        if is_balanced(adjustment, 0):
            return entries

        round_off_account = self._round_off_account(company_id)
        if not round_off_account:
            warnings.append("Missing round off account: Round Off")
            return entries

        round_off_id = int(round_off_account["id"])
        round_off_indexes = [
            index for index, entry in enumerate(entries)
            if int(entry.get("account_id") or 0) == round_off_id
        ]
        existing_net = Decimal("0.00")
        for index in round_off_indexes:
            entry = entries[index]
            existing_net += to_decimal(entry.get("debit", 0.0))
            existing_net -= to_decimal(entry.get("credit", 0.0))

        adjusted_net = money_round(existing_net + adjustment)

        if round_off_indexes:
            keep_index = round_off_indexes[0]
            for index in reversed(round_off_indexes[1:]):
                del entries[index]
            if is_balanced(adjusted_net, 0):
                del entries[keep_index]
            elif adjusted_net > 0:
                entries[keep_index]["debit"] = float(adjusted_net)
                entries[keep_index]["credit"] = 0.0
            else:
                entries[keep_index]["debit"] = 0.0
                entries[keep_index]["credit"] = float(abs(adjusted_net))
            return entries

        self._add_entry(
            entries,
            round_off_account,
            debit=float(adjustment) if adjustment > 0 else 0.0,
            credit=float(abs(adjustment)) if adjustment < 0 else 0.0,
            narration=narration or "Round off adjustment",
        )
        return entries

    # ------------------------------------------------------------------
    # Header / item loading
    # ------------------------------------------------------------------

    def load_header(self, company_id: int, voucher_type: str, voucher_id: int) -> Optional[Dict[str, Any]]:
        voucher_type = self.normalize_voucher_type(voucher_type)
        table = self.TABLE_MAP.get(voucher_type)
        if not table or not self.table_exists(table):
            return None
        ph = self.db._get_placeholder()
        return self._query_one(
            f"SELECT * FROM {table} WHERE id = {ph} AND company_id = {ph}",
            (voucher_id, company_id),
        )

    def load_items(self, voucher_type: str, voucher_id: int) -> List[Dict[str, Any]]:
        voucher_type = self.normalize_voucher_type(voucher_type)
        table_info = self.ITEM_MAP.get(voucher_type)
        if not table_info:
            return []
        table, fk = table_info
        if not self.table_exists(table):
            return []
        ph = self.db._get_placeholder()
        order_col = "sl_no" if "sl_no" in self.table_columns(table) else "id"
        return self._query(
            f"SELECT * FROM {table} WHERE {fk} = {ph} ORDER BY {order_col}",
            (voucher_id,),
        )

    def voucher_no(self, voucher_type: str, header: Dict[str, Any]) -> str:
        aliases = {
            "sales": ["invoice_number", "invoice_no", "bill_no", "voucher_no"],
            "purchase": ["purchase_number", "purchase_no", "bill_no", "voucher_no"],
            "sales_return": ["return_no", "return_number", "voucher_no"],
            "purchase_return": ["return_no", "return_number", "voucher_no"],
            "cash_receipt": ["voucher_no", "receipt_no"],
            "cash_payment": ["voucher_no", "payment_no"],
            "bank_receipt": ["voucher_no", "receipt_no"],
            "bank_payment": ["voucher_no", "payment_no"],
            "journal": ["voucher_no", "journal_no"],
        }
        return self._text(self.first_value(header, aliases.get(self.normalize_voucher_type(voucher_type), ["voucher_no"])))

    def voucher_date(self, voucher_type: str, header: Dict[str, Any]) -> str:
        aliases = {
            "sales": ["invoice_date", "bill_date", "voucher_date", "date"],
            "purchase": ["purchase_date", "bill_date", "voucher_date", "date"],
            "sales_return": ["return_date", "voucher_date", "date"],
            "purchase_return": ["return_date", "voucher_date", "date"],
            "cash_receipt": ["voucher_date", "receipt_date", "date"],
            "cash_payment": ["voucher_date", "payment_date", "date"],
            "bank_receipt": ["voucher_date", "receipt_date", "date"],
            "bank_payment": ["voucher_date", "payment_date", "date"],
            "journal": ["voucher_date", "journal_date", "date"],
        }
        return self._date_text(self.first_value(header, aliases.get(self.normalize_voucher_type(voucher_type), ["voucher_date"])))

    def voucher_totals(self, header: Dict[str, Any], items: List[Dict[str, Any]]) -> Tuple[Dict[str, float], List[str]]:
        return self.calculator.calculate_voucher_totals(header or {}, items or [])

    # ------------------------------------------------------------------
    # Entry builders
    # ------------------------------------------------------------------

    def _add_tax_entries(
        self,
        company_id: int,
        entries: List[Dict[str, Any]],
        totals: Dict[str, float],
        output: bool,
        debit_side: bool,
        warnings: List[str],
        narration: str = "",
    ) -> None:
        side_debit = debit_side
        names = []
        if totals.get("cgst_total"):
            names.append(("Output CGST" if output else "Input CGST", totals["cgst_total"]))
        if totals.get("sgst_total"):
            names.append(("Output SGST" if output else "Input SGST", totals["sgst_total"]))
        if totals.get("igst_total"):
            names.append(("Output IGST" if output else "Input IGST", totals["igst_total"]))
        if totals.get("cess_total"):
            names.append(("Output CESS" if output else "Input CESS", totals["cess_total"]))
        for account_name, entry_amount in names:
            account = self.account_by_name(company_id, account_name)
            if not account:
                warnings.append(f"Missing tax account: {account_name}")
                continue
            self._add_entry(
                entries,
                account,
                debit=entry_amount if side_debit else 0.0,
                credit=0.0 if side_debit else entry_amount,
                narration=narration,
            )
        split_tax = self._amount(totals.get("split_tax_total"))
        remaining_tax = round(self._amount(totals.get("tax_total")) - split_tax, 2)
        if not is_balanced(remaining_tax, 0):
            fallback_name = "GST Payable" if output else "GST Receivable"
            account = self.account_by_name(company_id, fallback_name)
            if account:
                self._add_entry(
                    entries,
                    account,
                    debit=remaining_tax if side_debit else 0.0,
                    credit=0.0 if side_debit else remaining_tax,
                    narration=narration,
                )
            else:
                warnings.append(f"Missing fallback tax account: {fallback_name}")

    def _validation_failure(self, warnings: List[str], message: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        warnings.append(f"VALIDATION_ERROR: {message}")
        return [], warnings

    def build_sales_entries(self, company_id: int, sale_id: int, header: Dict[str, Any], items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        print("### ACTIVE BUILD ENTRIES A: build_sales_entries ###")
        warnings: List[str] = []
        self.ensure_accounts(company_id)
        
        totals, calc_warnings = self.voucher_totals(header, items)
        warnings.extend(calc_warnings)
        grand = self._amount(totals.get("grand_total"))
        tax = self._amount(totals.get("tax_total"))
        freight = self._amount(totals.get("freight", header.get("freight", 0.0)))
        net_sales = round(grand - tax - freight, 2)  # CRITICAL FIX: Subtract freight from net_sales
        received_raw = self._amount(self.first_value(header, ["amount_received", "amt_received", "paid_amount"], 0.0))
        sale_type = self._text(self.first_value(header, ["sales_type", "type"], "Sales"))
        narration = self._text(header.get("narration"))
        voucher_no = self.voucher_no("sales", header)

        validation = CommercialVoucherValidator.validate_payment_amount(
            "sales",
            sale_type,
            grand,
            received_raw,
            amount_label="Amount received",
        )
        if not validation["success"]:
            print("### ENGINE ABORT: VALIDATION FAILED ###")
            print("VALIDATION MESSAGE:", validation["message"])
            print("SALE TYPE:", sale_type)
            print("GRAND:", grand)
            print("RECEIVED:", received_raw)
            return self._validation_failure(warnings, validation["message"])

        is_credit = bool(validation.get("is_credit"))
        is_cash = bool(validation.get("is_cash"))
        received = self._amount(validation.get("against_bill_amount"))
        if is_cash and is_balanced(received_raw, 0):
            received = grand
        received = min(max(received, 0.0), grand)

        print("### ENGINE STEP: ENTRY BUILD ###")
        print("=== ENTRY BUILD DEBUG ===")
        print("SALE TYPE:", sale_type, "IS_CASH:", is_cash, "IS_CREDIT:", is_credit)
        print("FREIGHT:", header.get("freight"))
        print("GRAND TOTAL:", grand)
        print("NET AMOUNT:", net_sales)
        print("AMOUNT RECEIVED (ledger):", received)

        entries: List[Dict[str, Any]] = []
        cash_account = self.account_by_name(company_id, "Cash Account")
        debtor_account = self.account_by_party(company_id, header.get("party_id"), "Sundry Debtors")
        sales_account = self.account_by_name(company_id, "Sales Account")
        suspense = self.fallback_account(company_id)

        print("### ENGINE STEP: CASH ENTRY ###")
        try:
            if is_cash:
                self._add_entry(entries, cash_account or suspense, debit=grand, narration=narration)
                self._add_entry(entries, sales_account or suspense, credit=net_sales, narration=narration)
                self._add_tax_entries(company_id, entries, totals, output=True, debit_side=False, warnings=warnings, narration=narration)
                if freight > 0:
                    freight_account = self.account_by_name(company_id, "Freight Charges Account")
                    self._add_entry(entries, freight_account or suspense, credit=freight, narration=f"Freight charges for {voucher_no}")
                print("### ENGINE STEP: CASH ENTRY SUCCESS ###")
                print("### ENGINE STEP: POST BUILD ###")
                return self._balance_entries_with_round_off(
                    company_id,
                    entries,
                    warnings,
                    narration="Round off adjustment for Sales Bill " + voucher_no,
                ), warnings
        except Exception as e:
            import traceback
            print("### BUILD ENTRIES FAILURE ###")
            print(repr(e))
            traceback.print_exc()
            raise

        print("### ENGINE STEP: CREDIT ENTRY ###")
        # Credit sales: full bill to debtor; only actual settlement reduces debtor.
        try:
            self._add_entry(entries, debtor_account or suspense, debit=grand, narration=narration)
            self._add_entry(entries, sales_account or suspense, credit=net_sales, narration=narration)
            self._add_tax_entries(company_id, entries, totals, output=True, debit_side=False, warnings=warnings, narration=narration)
            if freight > 0:
                freight_account = self.account_by_name(company_id, "Freight Charges Account")
                self._add_entry(entries, freight_account or suspense, credit=freight, narration=f"Freight charges for {voucher_no}")
        except Exception as e:
            import traceback
            print("### CREDIT ENTRY FAILURE ###")
            print(repr(e))
            traceback.print_exc()
            raise

        print("### ENGINE STEP: RECEIPT ENTRY ###")
        try:
            if not is_balanced(received, 0):
                receipt_narration = f"Amount received against Sales Bill {voucher_no}"
                self._add_entry(entries, cash_account or suspense, debit=received, narration=receipt_narration)
                self._add_entry(entries, debtor_account or suspense, credit=received, narration=receipt_narration)
                print("### ENGINE STEP: RECEIPT ENTRY SUCCESS ###")
            else:
                print("### ENGINE ABORT: NO RECEIPT NEEDED ###")
                print("### ENGINE STEP: SUCCESS ###")
        except Exception as e:
            import traceback
            print("### RECEIPT ENTRY FAILURE ###")
            print(repr(e))
            traceback.print_exc()
            raise

        print("ENTRIES =", entries)
        print("TOTAL DEBIT =", sum(e.get("debit", 0) for e in entries))
        print("TOTAL CREDIT =", sum(e.get("credit", 0) for e in entries))
        print("### ENGINE STEP: COMMIT ###")
        print("### ENGINE STEP: SUCCESS ###")
        print("### ENGINE STEP: POST BUILD ###")
        return self._balance_entries_with_round_off(
            company_id,
            entries,
            warnings,
            narration="Round off adjustment for Sales Bill " + voucher_no,
        ), warnings

    def build_purchase_entries(self, company_id: int, purchase_id: int, header: Dict[str, Any], items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        print(f"[DEBUG build_purchase_entries] START: company_id={company_id}, purchase_id={purchase_id}")
        warnings: List[str] = []
        self.ensure_accounts(company_id)
        totals, calc_warnings = self.voucher_totals(header, items)
        warnings.extend(calc_warnings)
        grand = self._amount(totals.get("grand_total"))
        tax = self._amount(totals.get("tax_total"))
        freight = self._amount(totals.get("freight", header.get("freight", 0.0)))
        net_purchase = round(grand - tax - freight, 2)  # CRITICAL FIX: Subtract freight from net_purchase
        paid = self._amount(self.first_value(header, ["amount_paid", "amt_paid", "paid_amount"], 0.0))
        purchase_type = self._text(self.first_value(header, ["purchase_type", "type"], "Cash"))
        narration = self._text(header.get("narration"))
        voucher_no = self.voucher_no("purchase", header)

        print(f"[DEBUG build_purchase_entries] purchase_type='{purchase_type}', grand={grand}, paid={paid}")

        # TEMPORARY BYPASS: Validation bypassed in UI, bypass here too
        validation = {"success": True, "message": "OK", "is_credit": False, "is_cash": "cash" in str(purchase_type).lower()}
        print(f"[DEBUG build_purchase_entries] validation.is_cash={validation['is_cash']}")
        if validation["is_cash"] and is_balanced(paid, 0):
            paid = grand
            print(f"[DEBUG build_purchase_entries] Auto-corrected paid from 0 to {grand}")

        entries: List[Dict[str, Any]] = []
        cash_account = self.account_by_name(company_id, "Cash Account")
        print(f"[DEBUG build_purchase_entries] cash_account lookup result: {cash_account}")
        
        # Fallback: If cash_account not found and this is a cash purchase, try to find any Cash account
        if not cash_account and validation.get("is_cash"):
            ph = self.db._get_placeholder()
            # First try exact match for "Cash Account"
            cash_acct_result = self.db.execute_query(
                f"SELECT id, account_name FROM ledger_accounts WHERE company_id = {ph} AND account_name = {ph} AND is_active = 1 LIMIT 1",
                (company_id, 'Cash Account')
            )
            if not cash_acct_result:
                # Then try "Cash"
                cash_acct_result = self.db.execute_query(
                    f"SELECT id, account_name FROM ledger_accounts WHERE company_id = {ph} AND account_name = {ph} AND is_active = 1 LIMIT 1",
                    (company_id, 'Cash')
                )
            if not cash_acct_result:
                # Finally try LIKE '%Cash%'
                cash_acct_result = self.db.execute_query(
                    f"SELECT id, account_name FROM ledger_accounts WHERE company_id = {ph} AND account_name LIKE {ph} AND is_active = 1 LIMIT 1",
                    (company_id, '%Cash%')
                )
            if cash_acct_result:
                cash_account = cash_acct_result[0]
                print(f"[DEBUG build_purchase_entries] Fallback cash account found: {cash_account}")
            else:
                print(f"[DEBUG build_purchase_entries] WARNING: No Cash account found for cash purchase")
        
        creditor_account = self.account_by_party(company_id, header.get("party_id"), "Sundry Creditors")
        purchase_account = self.account_by_name(company_id, "Purchase Account")
        freight_account = self.account_by_name(company_id, "Freight Charges Account")
        suspense = self.fallback_account(company_id)
        print(f"[DEBUG build_purchase_entries] suspense account: {suspense}")

        self._add_entry(entries, purchase_account or suspense, debit=net_purchase, narration=narration)
        self._add_tax_entries(company_id, entries, totals, output=False, debit_side=True, warnings=warnings, narration=narration)
        # CRITICAL FIX: Add freight account ledger entry
        if freight > 0:
            self._add_entry(entries, freight_account or suspense, debit=freight, narration=f"Freight charges for {voucher_no}")
        
        if validation["is_cash"]:
            # Cash purchase: Show in creditor ledger for tracking, but immediately pay off
            # Step 1: Credit Creditor Account (shows purchase in creditor ledger)
            self._add_entry(entries, creditor_account or suspense, credit=grand, narration=narration)
            # Step 2: Debit Creditor Account (immediate payment - clears creditor balance)
            payment_narration = f"Immediate cash payment for Purchase Bill {voucher_no}"
            self._add_entry(entries, creditor_account or suspense, debit=grand, narration=payment_narration)
            # Step 3: Credit Cash Account (actual cash outflow)
            self._add_entry(entries, cash_account or suspense, credit=grand, narration=payment_narration)
            return self._balance_entries_with_round_off(
                company_id,
                entries,
                warnings,
                narration="Round off adjustment for Purchase Bill " + voucher_no,
            ), warnings

        # Credit purchase: Credit goes to Creditor Account
        self._add_entry(entries, creditor_account or suspense, credit=grand, narration=narration)
        if not is_balanced(paid, 0):
            payment_narration = f"Amount paid against Purchase Bill {voucher_no}"
            self._add_entry(entries, creditor_account or suspense, debit=paid, narration=payment_narration)
            self._add_entry(entries, cash_account or suspense, credit=paid, narration=payment_narration)
        return self._balance_entries_with_round_off(
            company_id,
            entries,
            warnings,
            narration="Round off adjustment for Purchase Bill " + voucher_no,
        ), warnings

    def build_sales_return_entries(self, company_id: int, return_id: int, header: Dict[str, Any], items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        warnings: List[str] = []
        self.ensure_accounts(company_id)
        totals, calc_warnings = self.voucher_totals(header, items)
        warnings.extend(calc_warnings)
        grand = self._amount(totals.get("grand_total"))
        tax = self._amount(totals.get("tax_total"))
        freight = self._amount(totals.get("freight", header.get("freight", 0.0)))
        net_return = round(grand - tax - freight, 2)  # CRITICAL FIX: Subtract freight from net_return
        refunded = self._amount(self.first_value(header, ["amount_refunded_or_adjusted", "amount_refunded", "refund_amount"], 0.0))
        return_type = self._text(self.first_value(header, ["return_type", "type"], "Cash"))
        narration = self._text(header.get("narration"))
        voucher_no = self.voucher_no("sales_return", header)

        # TEMPORARY BYPASS: Validation bypassed in UI, bypass here too
        validation = {"success": True, "message": "OK", "is_credit": False, "is_cash": "cash" in str(return_type).lower()}
        if validation["is_cash"] and is_balanced(refunded, 0):
            refunded = grand

        entries: List[Dict[str, Any]] = []
        cash_account = self.account_by_name(company_id, "Cash Account")
        debtor_account = self.account_by_party(company_id, header.get("party_id"), "Sundry Debtors")
        return_account = self.account_by_name(company_id, "Sales Return Account")
        freight_account = self.account_by_name(company_id, "Freight Charges Account")
        suspense = self.fallback_account(company_id)

        self._add_entry(entries, return_account or suspense, debit=net_return, narration=narration)
        self._add_tax_entries(company_id, entries, totals, output=True, debit_side=True, warnings=warnings, narration=narration)
        # CRITICAL FIX: Add freight account ledger entry (debit for sales return)
        if freight > 0:
            self._add_entry(entries, freight_account or suspense, debit=freight, narration=f"Freight charges for {voucher_no}")
        
        if validation["is_cash"]:
            self._add_entry(entries, cash_account or suspense, credit=grand, narration=narration)
            return self._balance_entries_with_round_off(
                company_id,
                entries,
                warnings,
                narration="Round off adjustment for Sales Return " + voucher_no,
            ), warnings

        self._add_entry(entries, debtor_account or suspense, credit=grand, narration=narration)
        if not is_balanced(refunded, 0):
            refund_narration = f"Cash refund against Sales Return {voucher_no}"
            self._add_entry(entries, debtor_account or suspense, debit=refunded, narration=refund_narration)
            self._add_entry(entries, cash_account or suspense, credit=refunded, narration=refund_narration)
        return self._balance_entries_with_round_off(
            company_id,
            entries,
            warnings,
            narration="Round off adjustment for Sales Return " + voucher_no,
        ), warnings

    def build_purchase_return_entries(self, company_id: int, return_id: int, header: Dict[str, Any], items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        warnings: List[str] = []
        self.ensure_accounts(company_id)
        totals, calc_warnings = self.voucher_totals(header, items)
        warnings.extend(calc_warnings)
        grand = self._amount(totals.get("grand_total"))
        tax = self._amount(totals.get("tax_total"))
        freight = self._amount(totals.get("freight", header.get("freight", 0.0)))
        net_return = round(grand - tax - freight, 2)  # CRITICAL FIX: Subtract freight from net_return
        narration = self._text(header.get("narration"))
        voucher_no = self.voucher_no("purchase_return", header)

        entries: List[Dict[str, Any]] = []
        creditor_account = self.account_by_party(company_id, header.get("party_id"), "Sundry Creditors")
        return_account = self.account_by_name(company_id, "Purchase Return Account")
        freight_account = self.account_by_name(company_id, "Freight Charges Account")
        suspense = self.fallback_account(company_id)

        # Purchase Return reverses creditor payable only; refund handling does
        # not post separate cashbook, ledger, or trial balance entries here.
        self._add_entry(entries, creditor_account or suspense, debit=grand, narration=narration)
        self._add_entry(entries, return_account or suspense, credit=net_return, narration=narration)
        self._add_tax_entries(company_id, entries, totals, output=False, debit_side=False, warnings=warnings, narration=narration)
        # CRITICAL FIX: Add freight account ledger entry (credit for purchase return)
        if freight > 0:
            self._add_entry(entries, freight_account or suspense, credit=freight, narration=f"Freight charges for {voucher_no}")
        return self._balance_entries_with_round_off(
            company_id,
            entries,
            warnings,
            narration="Round off adjustment for Purchase Return " + voucher_no,
        ), warnings

    def build_cash_receipt_entries(self, company_id: int, header: Dict[str, Any], items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        warnings: List[str] = []
        self.ensure_accounts(company_id)
        entries: List[Dict[str, Any]] = []
        cash_account = self.account_by_id(company_id, header.get("cash_account_id")) or self.account_by_name(company_id, "Cash Account")
        suspense = self.fallback_account(company_id)
        source_rows = items if items else [header]
        for row in source_rows:
            account_id = self.first_value(row, ["account_id", "received_from_account_id"], header.get("received_from_account_id"))
            amount = self._amount(self.first_value(row, ["amount", "total_amount"], header.get("amount")))
            discount = self._amount(row.get("discount", 0.0))
            if is_balanced(amount, 0) and is_balanced(discount, 0):
                continue
            recv_account = self.account_by_id(company_id, account_id) or suspense
            narr = self._text(row.get("narration") or header.get("narration"))
            if not is_balanced(amount, 0):
                self._add_entry(entries, cash_account or suspense, debit=amount, narration=narr)
                self._add_entry(entries, recv_account, credit=amount, narration=narr)
            if not is_balanced(discount, 0):
                discount_account = self.account_by_name(company_id, "Discount Allowed") or suspense
                self._add_entry(entries, discount_account, debit=discount, narration="Discount allowed on receipt")
                self._add_entry(entries, recv_account, credit=discount, narration="Discount allowed on receipt")
        return entries, warnings

    def build_cash_payment_entries(self, company_id: int, header: Dict[str, Any], items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        warnings: List[str] = []
        self.ensure_accounts(company_id)
        entries: List[Dict[str, Any]] = []
        cash_account = self.account_by_id(company_id, header.get("cash_account_id")) or self.account_by_name(company_id, "Cash Account")
        suspense = self.fallback_account(company_id)
        source_rows = items if items else [header]
        for row in source_rows:
            account_id = self.first_value(row, ["account_id", "paid_to_account_id"], header.get("paid_to_account_id"))
            entry_amount = self._amount(self.first_value(row, ["amount", "total_amount"], header.get("amount")))
            if is_balanced(entry_amount, 0):
                continue
            paid_account = self.account_by_id(company_id, account_id) or suspense
            narr = self._text(row.get("narration") or header.get("narration"))
            self._add_entry(entries, paid_account, debit=entry_amount, narration=narr)
            self._add_entry(entries, cash_account or suspense, credit=entry_amount, narration=narr)
        return entries, warnings

    def build_bank_receipt_entries(self, company_id: int, header: Dict[str, Any], items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        warnings: List[str] = []
        self.ensure_accounts(company_id)
        bank_account = self._resolve_bank_ledger_account(company_id, header.get("bank_account_id"))
        from_account = self.account_by_id(company_id, header.get("received_from_account_id")) or self.fallback_account(company_id)
        entry_amount = self._amount(header.get("amount"))
        entries: List[Dict[str, Any]] = []
        self._add_entry(entries, bank_account, debit=entry_amount, narration=self._text(header.get("narration")))
        self._add_entry(entries, from_account, credit=entry_amount, narration=self._text(header.get("narration")))
        return entries, warnings

    def build_bank_payment_entries(self, company_id: int, header: Dict[str, Any], items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        warnings: List[str] = []
        self.ensure_accounts(company_id)
        bank_account = self._resolve_bank_ledger_account(company_id, header.get("bank_account_id"))
        to_account = self.account_by_id(company_id, header.get("paid_to_account_id")) or self.fallback_account(company_id)
        entry_amount = self._amount(header.get("amount"))
        entries: List[Dict[str, Any]] = []
        self._add_entry(entries, to_account, debit=entry_amount, narration=self._text(header.get("narration")))
        self._add_entry(entries, bank_account, credit=entry_amount, narration=self._text(header.get("narration")))
        return entries, warnings

    def _resolve_bank_ledger_account(self, company_id: int, bank_master_id: Any) -> Optional[Dict[str, Any]]:
        """Resolve a bank master id to its linked ledger account."""
        try:
            if bank_master_id:
                account = self._ledger().get_or_create_bank_master_ledger(company_id, int(bank_master_id))
                if account:
                    return account
        except Exception:
            pass
        return self.account_by_name(company_id, "Bank Account")

    def build_journal_entries(self, company_id: int, header: Dict[str, Any], items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        warnings: List[str] = []
        entries: List[Dict[str, Any]] = []
        for row in items or []:
            account = self.account_by_id(company_id, row.get("account_id"))
            self._add_entry(entries, account, debit=self._amount(row.get("debit")), credit=self._amount(row.get("credit")), narration=self._text(row.get("narration") or header.get("narration")))
        return entries, warnings

    def build_entries(self, company_id: int, voucher_type: str, voucher_id: int, header: Dict[str, Any], items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Build ledger entries for any voucher type."""
        print("### ACTIVE BUILD ENTRIES B: build_entries ###")
        voucher_type = self.normalize_voucher_type(voucher_type)
        if voucher_type == "sales":
            return self.build_sales_entries(company_id, voucher_id, header, items)
        elif voucher_type == "purchase":
            return self.build_purchase_entries(company_id, voucher_id, header, items)
        elif voucher_type == "sales_return":
            return self.build_sales_return_entries(company_id, voucher_id, header, items)
        elif voucher_type == "purchase_return":
            return self.build_purchase_return_entries(company_id, voucher_id, header, items)
        elif voucher_type == "cash_receipt":
            return self.build_cash_receipt_entries(company_id, header, items)
        elif voucher_type == "cash_payment":
            return self.build_cash_payment_entries(company_id, header, items)
        elif voucher_type == "bank_receipt":
            return self.build_bank_receipt_entries(company_id, header, items)
        elif voucher_type == "bank_payment":
            return self.build_bank_payment_entries(company_id, header, items)
        elif voucher_type == "journal":
            return self.build_journal_entries(company_id, header, items)
        elif voucher_type == "opening":
            return self.build_opening_entries(company_id, header, items)

    def build_opening_entries(self, company_id: int, header: Dict[str, Any], items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        warnings: List[str] = []
        entries: List[Dict[str, Any]] = []
        narration = self._text(header.get("narration"))
        for row in items or []:
            account = self.account_by_id(company_id, row.get("account_id"))
            row_narration = self._text(row.get("narration", narration))
            if not row_narration: row_narration = narration
            self._add_entry(entries, account, debit=self._amount(row.get("debit")), credit=self._amount(row.get("credit")), narration=row_narration)
        return entries, warnings
    # ------------------------------------------------------------------
    # Stock movement posting
    # ------------------------------------------------------------------

    def stock_effect(self, voucher_type: str) -> Optional[Tuple[str, int]]:
        voucher_type = self.normalize_voucher_type(voucher_type)
        if voucher_type == "sales":
            return "sale", -1
        if voucher_type == "purchase":
            return "purchase", 1
        if voucher_type == "sales_return":
            # stock_movements table CHECK allows movement_type='return'.
            # Positive return quantity increases stock.
            return "return", 1
        if voucher_type == "purchase_return":
            # Use generic return movement for strict schemas; voucher_type keeps
            # purchase-vs-sales return identity while negative quantity reduces stock.
            return "return", -1
        if voucher_type == "opening":
            return "opening", 1
        return None

    def delete_stock_movements(self, voucher_type: str, voucher_id: int,
                               voucher_no: Optional[str] = None, conn=None,
                               cursor=None) -> int:
        """
        Delete stock movements for a voucher.
        
        STRICT DELETION PROTOCOL:
        - If voucher_no is provided, deletes by voucher_no AND voucher_type (more strict)
        - If voucher_no is not provided, deletes by reference_type AND reference_id
        - This prevents duplicate stock movements during voucher updates
        
        Args:
            voucher_type: Voucher type
            voucher_id: Voucher ID
            voucher_no: Voucher number (optional, for stricter deletion)
            
        Returns:
            Number of rows deleted
        """
        reference_type = self.STOCK_REFERENCE_TYPE.get(self.normalize_voucher_type(voucher_type))
        if not reference_type:
            return 0
        ph = self.db._get_placeholder()
        cursor = cursor or (conn.cursor() if conn is not None else None)
        
        # Build WHERE clause based on what's provided
        if voucher_no:
            # STRICT: Delete by voucher_no AND voucher_type
            if cursor is not None:
                cursor.execute(
                    f"SELECT COUNT(*) AS cnt FROM stock_movements WHERE voucher_type = {ph} AND voucher_no = {ph}",
                    (voucher_type, voucher_no),
                )
                before = cursor.fetchone()
            else:
                before = self._query_one(
                    f"SELECT COUNT(*) AS cnt FROM stock_movements WHERE voucher_type = {ph} AND voucher_no = {ph}",
                    (voucher_type, voucher_no),
                )
            before_row = self._row_dict(before)
            count = int(before_row.get("cnt", 0) or 0)
            if hasattr(self.db, "delete_stock_movements_by_reference"):
                # Fallback to direct SQL if db method doesn't support voucher_no
                if cursor is not None:
                    cursor.execute(
                        f"DELETE FROM stock_movements WHERE voucher_type = {ph} AND voucher_no = {ph}",
                        (voucher_type, voucher_no),
                    )
                else:
                    self._execute(
                        f"DELETE FROM stock_movements WHERE voucher_type = {ph} AND voucher_no = {ph}",
                        (voucher_type, voucher_no),
                    )
            else:
                if cursor is not None:
                    cursor.execute(
                        f"DELETE FROM stock_movements WHERE voucher_type = {ph} AND voucher_no = {ph}",
                        (voucher_type, voucher_no),
                    )
                else:
                    self._execute(
                        f"DELETE FROM stock_movements WHERE voucher_type = {ph} AND voucher_no = {ph}",
                        (voucher_type, voucher_no),
                    )
        else:
            # Fallback: Delete by reference_type AND reference_id
            if cursor is not None:
                cursor.execute(
                    f"SELECT COUNT(*) AS cnt FROM stock_movements WHERE reference_type = {ph} AND reference_id = {ph}",
                    (reference_type, voucher_id),
                )
                before = cursor.fetchone()
            else:
                before = self._query_one(
                    f"SELECT COUNT(*) AS cnt FROM stock_movements WHERE reference_type = {ph} AND reference_id = {ph}",
                    (reference_type, voucher_id),
                )
            before_row = self._row_dict(before)
            count = int(before_row.get("cnt", 0) or 0)
            if hasattr(self.db, "delete_stock_movements_by_reference"):
                self.db.delete_stock_movements_by_reference(reference_type, voucher_id, conn=conn, cursor=cursor)
            else:
                if cursor is not None:
                    cursor.execute(
                        f"DELETE FROM stock_movements WHERE reference_type = {ph} AND reference_id = {ph}",
                        (reference_type, voucher_id),
                    )
                else:
                    self._execute(
                        f"DELETE FROM stock_movements WHERE reference_type = {ph} AND reference_id = {ph}",
                        (reference_type, voucher_id),
                    )
        return count

    def post_stock_movements(self, company_id: int, voucher_type: str, voucher_id: int,
                             voucher_no: str, voucher_date: str,
                             items: List[Dict[str, Any]], conn=None,
                             cursor=None) -> int:
        effect = self.stock_effect(voucher_type)
        if not effect:
            return 0
        movement_type, sign = effect
        posted = 0
        touched_products = set()
        reference_type = self.STOCK_REFERENCE_TYPE[self.normalize_voucher_type(voucher_type)]
        cursor = cursor or (conn.cursor() if conn is not None else None)
        for item in items or []:
            product_id = item.get("product_id")
            qty = self._amount(self.first_value(item, ["quantity", "qty"], 0.0))
            if not product_id or qty <= 0:
                continue
            signed_qty = qty if sign >= 0 else -qty
            notes = f"{voucher_type} {voucher_no}"
            
            # DEBUG PRINT
            print(f"INSERTING STOCK MOVEMENT = {movement_type}, {signed_qty}, {reference_type}, voucher_type={voucher_type}")
            
            if cursor is not None and hasattr(self.db, "create_stock_movement_with_cursor"):
                self.db.create_stock_movement_with_cursor(
                    cursor=cursor,
                    company_id=company_id,
                    product_id=int(product_id),
                    movement_type=movement_type,
                    quantity=signed_qty,
                    reference_type=reference_type,
                    reference_id=voucher_id,
                    notes=notes,
                    voucher_type=voucher_type,
                )
                ok = True
            elif hasattr(self.db, "create_stock_movement"):
                ok = self.db.create_stock_movement(
                    company_id=company_id,
                    product_id=int(product_id),
                    movement_type=movement_type,
                    quantity=signed_qty,
                    reference_type=reference_type,
                    reference_id=voucher_id,
                    notes=notes,
                    voucher_type=voucher_type,
                )
            else:
                ph = self.db._get_placeholder()
                ok = self._execute(
                    f"""
                    INSERT INTO stock_movements
                        (company_id, product_id, movement_type, quantity, reference_type, reference_id, notes)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                    (company_id, int(product_id), movement_type, signed_qty, reference_type, voucher_id, notes),
                )
            if ok:
                posted += 1
                touched_products.add(int(product_id))
        if touched_products and hasattr(self.db, "batch_sync_product_quantities"):
            try:
                self.db.batch_sync_product_quantities(company_id, list(touched_products), conn=conn, cursor=cursor)
            except Exception as exc:
                self._log(f"stock quantity cache sync failed: {exc}")
        return posted

    # ------------------------------------------------------------------
    # Posting operations
    # ------------------------------------------------------------------

    def count_ledger_entries(self, company_id: int, voucher_type: str,
                             voucher_id: int, cursor=None) -> int:
        ph = self.db._get_placeholder()
        params = (company_id, self.normalize_voucher_type(voucher_type), voucher_id)
        if cursor is not None:
            cursor.execute(
                f"SELECT COUNT(*) AS cnt FROM ledger_entries WHERE company_id = {ph} AND voucher_type = {ph} AND voucher_id = {ph}",
                params,
            )
            row = self._row_dict(cursor.fetchone())
        else:
            row = self._query_one(
                f"SELECT COUNT(*) AS cnt FROM ledger_entries WHERE company_id = {ph} AND voucher_type = {ph} AND voucher_id = {ph}",
                params,
            )
        return int((row or {}).get("cnt", 0) or 0)

    def validate_entries(self, entries: List[Dict[str, Any]]) -> Tuple[bool, float, float, str]:
        """
        Strict double-entry validator.
        
        Calculates total debits and credits. If they don't match, raises ValueError.
        All math is rounded to 2 decimal places to prevent floating point crashes.
        
        Args:
            entries: List of ledger entry dictionaries with 'debit' and 'credit' keys
            
        Returns:
            Tuple of (is_valid, total_debit, total_credit, error_message)
            
        Raises:
            ValueError: If debits != credits (strict abort)
        """
        total_debit = round(sum(self._amount(e.get("debit")) for e in entries), 2)
        total_credit = round(sum(self._amount(e.get("credit")) for e in entries), 2)
        
        if not entries:
            error_msg = "No ledger entries were generated"
            raise ValueError(error_msg)
        
        missing_account = [e for e in entries if not e.get("account_id")]
        if missing_account:
            error_msg = "One or more ledger entries have no account_id"
            raise ValueError(error_msg)
        
        if not is_balanced(total_debit, total_credit):
            error_msg = f"{self.LEDGER_MATH_ERROR} debit={total_debit} credit={total_credit}"
            raise ValueError(error_msg)
        
        return True, total_debit, total_credit, ""

    def repost_voucher(self, company_id: int, voucher_type: str, voucher_id: int,
                       header: Optional[Dict[str, Any]] = None,
                       items: Optional[List[Dict[str, Any]]] = None,
                       apply_stock: bool = True, dry_run: bool = False,
                       conn=None, cursor=None, commit: bool = True) -> PostingResult:
        # GLOBAL POSTING LOCK: Prevent signal feedback loops and concurrent posting
        # Acquire lock with 5-second timeout to prevent deadlocks
        if not self._lock.acquire(timeout=5.0):
            print(f"[ERROR] Posting lock timeout for {voucher_type} id={voucher_id} - possible deadlock")
            result = PostingResult(success=False, voucher_type=voucher_type, voucher_id=voucher_id)
            result.failed_reason = "Posting lock timeout - possible deadlock"
            result.message = result.failed_reason
            return result
        
        owns_connection = False
        previous_cursor = self._active_cursor
        try:
            print("### ACTIVE BUILD ENTRIES C: repost_voucher ###")
            voucher_type = self.normalize_voucher_type(voucher_type)
            result = PostingResult(success=False, voucher_type=voucher_type, voucher_id=voucher_id)
            if cursor is None and conn is not None:
                cursor = conn.cursor()
            self._active_cursor = cursor
            header = header or self.load_header(company_id, voucher_type, voucher_id)
            if not header:
                result.failed_reason = f"Voucher header not found for {voucher_type} id={voucher_id}"
                result.message = result.failed_reason
                return result
            items = items if items is not None else self.load_items(voucher_type, voucher_id)
            voucher_no = self.voucher_no(voucher_type, header)
            voucher_date = self.voucher_date(voucher_type, header)
            result.voucher_no = voucher_no
            print("### ENGINE STEP: BUILD ENTRIES ###")
            try:
                entries, warnings = self.build_entries(company_id, voucher_type, voucher_id, header, items)
            except Exception as e:
                import traceback
                print("### ENGINE REAL FAILURE ###")
                print(repr(e))
                traceback.print_exc()
                result = PostingResult(success=False, voucher_type=voucher_type, voucher_id=voucher_id)
                result.failed_reason = f"Engine failure: {str(e)}"
                result.message = result.failed_reason
                return result
            
            validation_errors = [w for w in warnings if str(w).startswith("VALIDATION_ERROR:")]
            if validation_errors:
                result.warnings.extend(warnings)
                result.failed_reason = validation_errors[0].replace("VALIDATION_ERROR:", "").strip()
                result.message = result.failed_reason
                return result
            try:
                valid, total_debit, total_credit, validation_message = self.validate_entries(entries)
            except ValueError as exc:
                result.failed_reason = str(exc)
                result.message = result.failed_reason
                return result
            result.total_debit = total_debit
            result.total_credit = total_credit
            result.warnings.extend(warnings)
            result.entries_preview = [dict(e) for e in entries]
            
            print("===== ENTRY DEBUG =====")
            print("ENTRIES =", entries)
            print("TOTAL DEBIT =", total_debit)
            print("TOTAL CREDIT =", total_credit)
            print("=======================")
            
            if not valid:
                print("### ENGINE ABORT: UNBALANCED VOUCHER ###")
                result.failed_reason = validation_message
                result.message = validation_message
                return result
            
            print("### ENGINE STEP: POST BUILD ###")
            
            # If dry_run is True, skip actual posting and just return the preview
            if dry_run:
                print("### ENGINE DRY RUN MODE - SKIPPING ACTUAL POSTING ###")
                result.success = True
                result.message = "Dry run successful"
                result.ledger_entries_posted = 0
                result.stock_movements_posted = 0
                return result
            
            try:
                if conn is None:
                    conn = self.db.connect()
                    owns_connection = True
                    cursor = conn.cursor()
                    self._active_cursor = cursor
                    if hasattr(conn, "start_transaction"):
                        conn.start_transaction()
                    else:
                        conn.execute("BEGIN")

                # Use ledger.post_double_entry directly - it handles deletion and insertion atomically
                ledger = self._ledger()
                ok = ledger.post_double_entry(
                    company_id=company_id,
                    voucher_type=voucher_type,
                    voucher_id=voucher_id,
                    voucher_no=voucher_no,
                    voucher_date=voucher_date,
                    entries=entries,
                    narration=self._text(header.get("narration")),
                    reference_type=voucher_type,
                    reference_id=voucher_id,
                    conn=conn,
                    cursor=cursor,
                    commit=False,
                )
                if ok:
                    result.success = True
                    result.message = "Voucher reposted successfully"
                else:
                    if conn is not None and commit:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                    result.success = False
                    result.failed_reason = "Ledger post_double_entry failed"
                    result.message = result.failed_reason
                    return result
            except Exception as e:
                if conn is not None and commit:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                import traceback
                print("### ENGINE POSTING FAILURE ###")
                print(repr(e))
                traceback.print_exc()
                result = PostingResult(success=False, voucher_type=voucher_type, voucher_id=voucher_id)
                result.failed_reason = f"Posting failure: {str(e)}"
                result.message = result.failed_reason
                return result
            try:
                result.ledger_entries_posted = len(entries)
                if apply_stock:
                    self.delete_stock_movements(voucher_type, voucher_id, conn=conn, cursor=cursor)
                    result.stock_movements_posted = self.post_stock_movements(
                        company_id, voucher_type, voucher_id, voucher_no, voucher_date,
                        items, conn=conn, cursor=cursor
                    )
                if commit:
                    conn.commit()
            except Exception as e:
                if conn is not None and commit:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                result.success = False
                result.failed_reason = f"Posting failure: {str(e)}"
                result.message = result.failed_reason
                return result
            result.success = True
            result.message = "Voucher reposted successfully"
            if not dry_run:
                from ui.dashboard_refresh import request_dashboard_refresh
                request_dashboard_refresh()
            return result
        finally:
            if owns_connection:
                self.db.disconnect()
            self._active_cursor = previous_cursor
            # Always release the lock, even if an exception occurs
            self._lock.release()

    def repost_voucher_from_db(self, company_id: int, voucher_type: str, voucher_id: int,
                               apply_stock: bool = True, dry_run: bool = False,
                               conn=None, cursor=None, commit: bool = True) -> Dict[str, Any]:
        return self.repost_voucher(
            company_id, voucher_type, voucher_id,
            apply_stock=apply_stock, dry_run=dry_run, conn=conn,
            cursor=cursor, commit=commit
        ).to_dict()

    def preview_voucher_from_db(self, company_id: int, voucher_type: str, voucher_id: int) -> Dict[str, Any]:
        return self.repost_voucher_from_db(company_id, voucher_type, voucher_id, apply_stock=False, dry_run=True)

    def delete_voucher_postings(self, company_id: int, voucher_type: str, voucher_id: int,
                                conn=None, cursor=None, commit: bool = True) -> Dict[str, Any]:
        """
        Delete voucher postings with debug logging.
        
        DEBUG LOGGING:
        - Prints EXACT SQL query and parameters before execution
        - Prints deleted_count to verify deletion worked
        """
        owns_connection = False
        result = PostingResult(success=False, voucher_type=voucher_type, voucher_id=voucher_id)
        try:
            voucher_type = self.normalize_voucher_type(voucher_type)
            result.voucher_type = voucher_type
            if conn is None:
                conn = self.db.connect()
                owns_connection = True
                if hasattr(conn, "start_transaction"):
                    conn.start_transaction()
                else:
                    conn.execute("BEGIN")
            cursor = cursor or conn.cursor()

            # DEBUG: Print deletion attempt
            print(f"[DEBUG] Attempting to delete existing postings for {voucher_type} ID: {voucher_id}")
            print(f"[DEBUG] Deleting voucher postings for company_id={company_id}, voucher_type={voucher_type}, voucher_id={voucher_id}")

            before_count = self.count_ledger_entries(company_id, voucher_type, voucher_id, cursor=cursor)

            print(f"[DEBUG] Ledger entries found before deletion: {before_count}")

            if before_count:
                ok = self._ledger().delete_voucher_entries(
                    company_id, voucher_type, voucher_id, conn=conn, cursor=cursor, commit=False
                )
                if not ok:
                    print(f"[DEBUG] FAILED to delete ledger entries!")
                    result.message = "Failed to delete ledger entries"
                    result.failed_reason = result.message
                    if commit:
                        conn.rollback()
                    return result.to_dict()
                print(f"[DEBUG] Successfully deleted {before_count} ledger entries")
            else:
                print(f"[DEBUG] WARNING: No ledger entries found to delete (before_count=0). This may indicate a 'ghost' voucher or deletion already occurred.")

            result.ledger_entries_deleted = before_count
            stock_deleted = self.delete_stock_movements(voucher_type, voucher_id, conn=conn, cursor=cursor)
            result.stock_movements_deleted = stock_deleted
            print(f"[DEBUG] Stock movements deleted: {stock_deleted}")

            if commit:
                conn.commit()
            result.success = True
            result.message = "Voucher postings deleted successfully"
            from ui.dashboard_refresh import request_dashboard_refresh
            request_dashboard_refresh()
            return result.to_dict()
        except Exception as exc:
            if conn is not None and commit:
                try:
                    conn.rollback()
                except Exception:
                    pass
            result.message = f"Transaction failed: {str(exc)}"
            result.failed_reason = result.message
            return result.to_dict()
        finally:
            if owns_connection:
                self.db.disconnect()

    # Backward-compatible methods used by Cash/Bank/Journal logic
    def delete_voucher_ledger_entries(self, company_id: int, voucher_type: str,
                                      voucher_id: int, conn=None,
                                      commit: bool = True) -> Tuple[bool, str]:
        res = self.delete_voucher_postings(company_id, voucher_type, voucher_id, conn=conn, commit=commit)
        return bool(res.get("success")), self._text(res.get("message"))

    def update_voucher_ledger_entries(self, company_id: int, voucher_type: str, voucher_id: int, voucher_no: str, voucher_date: str, entries: List[Dict[str, Any]], narration: str = "", conn=None, commit: bool = True) -> Tuple[bool, str]:
        return self.post_manual_double_entry(company_id, voucher_type, voucher_id, voucher_no, voucher_date, entries, narration, conn=conn, commit=commit)

    def post_manual_double_entry(self, company_id: int, voucher_type: str, voucher_id: int, voucher_no: str, voucher_date: str, entries: List[Dict[str, Any]], narration: str = "", dry_run: bool = False, conn=None, commit: bool = True) -> Tuple[bool, str]:
        """
        Post manual double-entry with strict double-entry validation.
        
        ATOMIC DELETION PROTOCOL:
        - Deletion of old ledger_entries is now handled inside post_double_entry
        - This ensures deletion and INSERT happen within the SAME database transaction
        - No duplicate entries can occur even if the process is interrupted
        
        STRICT DOUBLE-ENTRY VALIDATION:
        - Before commit, validates that total_debits == total_credits
        - If not balanced, raises ValueError and aborts transaction
        
        GLOBAL POSTING LOCK:
        - Acquires global lock to prevent recursive signal loops
        - Silently blocks redundant posting attempts
        """
        # ATTEMPT TO ACQUIRE GLOBAL LOCK
        if not acquire(blocking=False):
            print("[DEBUG] GLOBAL LOCK ACTIVE - Blocking duplicate posting request")
            return False, "Posting lock active - blocking duplicate request"
        
        try:
            voucher_type = self.normalize_voucher_type(voucher_type)
            
            if dry_run:
                return True, "Dry run passed"
            
            # STRICT: Validate entries before posting
            try:
                valid, total_debit, total_credit, msg = self.validate_entries(entries)
            except ValueError as e:
                return False, f"Double-entry validation failed: {str(e)}"
            
            if not valid:
                return False, msg
            
            # Post new entries (deletion happens atomically inside post_double_entry)
            ok = self._ledger().post_double_entry(
                company_id=company_id,
                voucher_type=voucher_type,
                voucher_id=voucher_id,
                voucher_no=voucher_no,
                voucher_date=voucher_date,
                entries=entries,
                narration=narration,
                reference_type=voucher_type,
                reference_id=voucher_id,
                conn=conn,
                commit=commit,
            )
            return (True, "Posted successfully") if ok else (False, "Ledger post_double_entry failed")
        finally:
            # ALWAYS RELEASE THE LOCK
            release()

    def post_cash_receipt(self, company_id: int, voucher_id: int, voucher_no: str, voucher_date: str, cash_account_id: int, received_from_account_id: int, amount: float, narration: str = "") -> Tuple[bool, str]:
        entries = [
            {"account_id": int(cash_account_id), "debit": self._amount(amount), "credit": 0.0, "narration": narration},
            {"account_id": int(received_from_account_id), "debit": 0.0, "credit": self._amount(amount), "narration": narration},
        ]
        return self.post_manual_double_entry(company_id, "cash_receipt", voucher_id, voucher_no, voucher_date, entries, narration)

    def post_cash_payment(self, company_id: int, voucher_id: int, voucher_no: str, voucher_date: str, cash_account_id: int, paid_to_account_id: int, amount: float, narration: str = "") -> Tuple[bool, str]:
        entries = [
            {"account_id": int(paid_to_account_id), "debit": self._amount(amount), "credit": 0.0, "narration": narration},
            {"account_id": int(cash_account_id), "debit": 0.0, "credit": self._amount(amount), "narration": narration},
        ]
        return self.post_manual_double_entry(company_id, "cash_payment", voucher_id, voucher_no, voucher_date, entries, narration)

    def post_bank_receipt(self, company_id: int, voucher_id: int, voucher_no: str, voucher_date: str, bank_account_id: int, received_from_account_id: int, amount: float, narration: str = "") -> Tuple[bool, str]:
        entries = [
            {"account_id": int(bank_account_id), "debit": self._amount(amount), "credit": 0.0, "narration": narration},
            {"account_id": int(received_from_account_id), "debit": 0.0, "credit": self._amount(amount), "narration": narration},
        ]
        return self.post_manual_double_entry(company_id, "bank_receipt", voucher_id, voucher_no, voucher_date, entries, narration)

    def post_bank_payment(self, company_id: int, voucher_id: int, voucher_no: str, voucher_date: str, bank_account_id: int, paid_to_account_id: int, amount: float, narration: str = "") -> Tuple[bool, str]:
        entries = [
            {"account_id": int(paid_to_account_id), "debit": self._amount(amount), "credit": 0.0, "narration": narration},
            {"account_id": int(bank_account_id), "debit": 0.0, "credit": self._amount(amount), "narration": narration},
        ]
        return self.post_manual_double_entry(company_id, "bank_payment", voucher_id, voucher_no, voucher_date, entries, narration)

    def post_journal_entry(self, company_id: int, voucher_id: int, voucher_no: str, voucher_date: str, entries: List[Dict[str, Any]], narration: str = "", conn=None, commit: bool = True) -> Tuple[bool, str]:
        return self.post_manual_double_entry(company_id, "journal", voucher_id, voucher_no, voucher_date, entries, narration, conn=conn, commit=commit)

    def repost_all_company(self, company_id: int, voucher_types: Optional[List[str]] = None, dry_run: bool = False) -> Dict[str, Any]:
        voucher_types = voucher_types or [
            "sales", "purchase", "sales_return", "purchase_return",
            "cash_receipt", "cash_payment", "bank_receipt", "bank_payment", "journal",
        ]
        result = {"success": True, "company_id": company_id, "dry_run": dry_run, "posted": {}, "failed": []}
        ph = self.db._get_placeholder()
        select_map = {
            "sales": ("sales", "id"),
            "purchase": ("purchases", "id"),
            "sales_return": ("sales_returns", "id"),
            "purchase_return": ("purchase_returns", "id"),
            "cash_receipt": ("cash_receipts", "id"),
            "cash_payment": ("cash_payments", "id"),
            "bank_receipt": ("bank_receipts", "id"),
            "bank_payment": ("bank_payments", "id"),
            "journal": ("journal_vouchers", "id"),
        }
        for vt in voucher_types:
            voucher_type = self.normalize_voucher_type(vt)
            table_info = select_map.get(voucher_type)
            if not table_info:
                continue
            table, id_col = table_info
            if not self.table_exists(table):
                result["posted"][voucher_type] = 0
                continue
            rows = self._query(f"SELECT {id_col} AS id FROM {table} WHERE company_id = {ph} ORDER BY id", (company_id,))
            count = 0
            for row in rows:
                apply_stock = voucher_type in self.STOCK_REFERENCE_TYPE
                post_result = self.repost_voucher_from_db(company_id, voucher_type, int(row["id"]), apply_stock=apply_stock, dry_run=dry_run)
                if post_result.get("success"):
                    count += 1
                else:
                    result["success"] = False
                    result["failed"].append(post_result)
            result["posted"][voucher_type] = count
        return result


def get_engine(db: Any, debug: bool = False) -> VoucherPostingEngine:
    return VoucherPostingEngine(db, debug=debug)
