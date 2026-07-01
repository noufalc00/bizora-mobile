"""
In-memory SQLite snapshots of synced Supabase ledger data.

Lets desktop logic classes (LedgerLogic, FinancialReportingEngine) run on
cloud deployments without the full desktop `db` module or hydration bridge.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Any, Callable


class MemoryLedgerDb:
    """Minimal SQLite adapter compatible with desktop logic query helpers."""

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

    def _get_timestamp_default(self) -> str:
        """Match desktop Database timestamp helper for INSERT statements."""
        return datetime.now().isoformat(sep=" ", timespec="seconds")

    def execute_query(self, query: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute one SELECT against the in-memory ledger tables."""
        try:
            with closing(self.connection.cursor()) as cursor:
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            print(f"[MOBILE-MEMORY-DB] Query failed: {exc}")
            print(f"[MOBILE-MEMORY-DB] SQL: {query}")
            raise


def _parse_filter_date(value: Any) -> str:
    return str(value or "")[:10]


from bizora_core.mobile_supabase_party_links import assign_party_ledger_links


def _fetch_parties_for_memory_db(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
    ledger_accounts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fetch parties and backfill ledger_account_id when Supabase omits the column."""
    try:
        parties = fetch_table(
            "parties",
            company_id,
            select="id,company_id,name,party_type,opening_balance,ledger_account_id",
            limit=5000,
        )
    except Exception as exc:
        message = str(exc)
        if "ledger_account_id" not in message:
            raise
        parties = fetch_table(
            "parties",
            company_id,
            select="id,company_id,name,party_type,opening_balance",
            limit=5000,
        )

    return assign_party_ledger_links(parties, ledger_accounts)


def load_ledger_memory_db(
    fetch_table: Callable[..., list[dict[str, Any]]],
    company_id: int,
) -> MemoryLedgerDb:
    """Hydrate ledger_accounts, ledger_entries, and parties from Supabase."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE ledger_accounts (
            id INTEGER PRIMARY KEY,
            company_id INTEGER NOT NULL,
            account_name TEXT,
            account_code TEXT,
            account_type TEXT,
            group_name TEXT,
            opening_balance REAL DEFAULT 0,
            opening_balance_type TEXT DEFAULT 'Dr',
            is_system INTEGER DEFAULT 0,
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
        CREATE TABLE parties (
            id INTEGER PRIMARY KEY,
            company_id INTEGER NOT NULL,
            name TEXT,
            party_type TEXT,
            opening_balance REAL DEFAULT 0,
            ledger_account_id INTEGER
        );
        """
    )

    accounts = fetch_table(
        "ledger_accounts",
        company_id,
        select=(
            "id,company_id,account_name,account_code,account_type,group_name,"
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
    parties = _fetch_parties_for_memory_db(fetch_table, company_id, accounts)

    with closing(connection.cursor()) as cursor:
        cursor.executemany(
            """
            INSERT INTO ledger_accounts (
                id, company_id, account_name, account_code, account_type, group_name,
                opening_balance, opening_balance_type, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.get("id"),
                    row.get("company_id", company_id),
                    row.get("account_name", ""),
                    row.get("account_code", ""),
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
        cursor.executemany(
            """
            INSERT INTO parties (
                id, company_id, name, party_type, opening_balance, ledger_account_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.get("id"),
                    row.get("company_id", company_id),
                    row.get("name", ""),
                    row.get("party_type", ""),
                    float(row.get("opening_balance") or 0),
                    row.get("ledger_account_id"),
                )
                for row in parties
                if row.get("id") is not None
            ],
        )
        connection.commit()

    return MemoryLedgerDb(connection)
