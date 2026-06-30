"""
Run desktop DayBookLogic against Supabase-synced ledger data via in-memory SQLite.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import Any, Callable

from bizora_core.day_book_logic import DayBookLogic
from bizora_core.mobile_report_columns import build_slug_table_payload


class _DayBookMemoryDb:
    """Minimal SQLite adapter so DayBookLogic can run without the desktop database file."""

    def __init__(self, connection: sqlite3.Connection):
        self.db_type = "sqlite"
        self.db_path = ":memory:"
        self.mysql_config = None
        self.connection = connection
        self.last_error_message = None

    def connect(self) -> sqlite3.Connection:
        return self.connection

    def disconnect(self) -> None:
        """Keep the in-memory connection open for repeated report queries."""

    def force_disconnect(self) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None

    def _get_placeholder(self) -> str:
        return "?"

    def _is_sqlite(self) -> bool:
        return True

    def execute_query(self, query: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute one SELECT against the in-memory ledger tables."""
        try:
            with closing(self.connection.cursor()) as cursor:
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            print(f"[MOBILE-DAY-BOOK] Query failed: {exc}")
            print(f"[MOBILE-DAY-BOOK] SQL: {query}")
            raise


def _parse_filter_date(value: Any) -> str:
    return str(value or "")[:10]


def _load_memory_db(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
) -> _DayBookMemoryDb:
    """Hydrate in-memory SQLite tables from synced Supabase ledger rows."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE ledger_accounts (
            id INTEGER PRIMARY KEY,
            company_id INTEGER NOT NULL,
            account_name TEXT,
            account_type TEXT,
            group_name TEXT,
            opening_balance REAL DEFAULT 0,
            opening_balance_type TEXT DEFAULT 'Dr',
            is_active INTEGER DEFAULT 1
        );
        CREATE TABLE ledger_entries (
            id INTEGER PRIMARY KEY,
            company_id INTEGER NOT NULL,
            voucher_type TEXT NOT NULL,
            voucher_id INTEGER,
            voucher_no TEXT,
            voucher_date TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            contra_account_id INTEGER,
            narration TEXT,
            debit REAL DEFAULT 0,
            credit REAL DEFAULT 0
        );
        """
    )

    accounts = fetch_table(
        "ledger_accounts",
        company_id,
        select=(
            "id,company_id,account_name,account_type,group_name,"
            "opening_balance,opening_balance_type,is_active"
        ),
        limit=5000,
    )
    entries = fetch_table(
        "ledger_entries",
        company_id,
        select=(
            "id,company_id,voucher_type,voucher_id,voucher_no,voucher_date,"
            "account_id,contra_account_id,narration,debit,credit"
        ),
        limit=50000,
        order_col="voucher_date",
    )

    with closing(connection.cursor()) as cursor:
        cursor.executemany(
            """
            INSERT INTO ledger_accounts (
                id, company_id, account_name, account_type, group_name,
                opening_balance, opening_balance_type, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.get("id"),
                    row.get("company_id", company_id),
                    row.get("account_name", ""),
                    row.get("account_type", ""),
                    row.get("group_name", ""),
                    float(row.get("opening_balance") or 0),
                    row.get("opening_balance_type") or "Dr",
                    1 if str(row.get("is_active", 1)) not in {"0", "false", "False"} else 0,
                )
                for row in accounts
                if row.get("id") is not None
            ],
        )
        cursor.executemany(
            """
            INSERT INTO ledger_entries (
                id, company_id, voucher_type, voucher_id, voucher_no, voucher_date,
                account_id, contra_account_id, narration, debit, credit
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.get("id"),
                    row.get("company_id", company_id),
                    row.get("voucher_type", ""),
                    row.get("voucher_id"),
                    row.get("voucher_no", ""),
                    _parse_filter_date(row.get("voucher_date")),
                    row.get("account_id"),
                    row.get("contra_account_id"),
                    row.get("narration", ""),
                    float(row.get("debit") or 0),
                    float(row.get("credit") or 0),
                )
                for row in entries
                if row.get("id") is not None and row.get("account_id") is not None
            ],
        )
        connection.commit()

    return _DayBookMemoryDb(connection)


DAY_BOOK_SUMMARY_LABELS = {
    "opening_balance": "Opening",
    "day_debit_total": "Receipts (Dr)",
    "day_credit_total": "Payments (Cr)",
    "cash_bank_debit_total": "Cash/Bank Dr",
    "cash_bank_credit_total": "Cash/Bank Cr",
    "closing_balance": "Closing",
}


def run_day_book_from_supabase(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Build Day Book rows using the same logic as the desktop Cash/Bank Day Book."""
    from_date = _parse_filter_date(filters.get("from_date"))
    to_date = _parse_filter_date(filters.get("to_date"))
    summarize_entries = bool(filters.get("summarize_entries", True))
    summarize_debtors = bool(filters.get("summarize_debtors", False))
    summarize_creditors = bool(filters.get("summarize_creditors", False))

    memory_db = _load_memory_db(fetch_table, company_id)
    logic = DayBookLogic(memory_db)

    entries_result = logic.get_day_book_entries(
        company_id,
        from_date,
        to_date,
        summarize_entries=summarize_entries,
        summarize_debtors=summarize_debtors,
        summarize_creditors=summarize_creditors,
    )
    if not entries_result.get("success"):
        return {
            "success": False,
            "message": entries_result.get("message", "Day Book failed."),
            "rows": [],
            "columns": [],
            "data_source": "supabase",
        }

    summary_result = logic.get_day_book_summary(
        company_id,
        from_date,
        to_date,
        summarize_entries=summarize_entries,
        summarize_debtors=summarize_debtors,
        summarize_creditors=summarize_creditors,
    )
    rows = entries_result.get("data") or []
    table_payload = build_slug_table_payload(
        "day-book",
        rows,
        handler="day_book",
        filters=filters,
    )
    memory_db.force_disconnect()

    return {
        "success": True,
        "message": entries_result.get("message", ""),
        "data_source": "supabase",
        "summary": summary_result.get("data") or {},
        "summary_labels": DAY_BOOK_SUMMARY_LABELS,
        **table_payload,
    }
