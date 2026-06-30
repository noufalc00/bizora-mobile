"""
Credit / Debit Note business logic.
Memo-only first version: saves notes without ledger or stock posting.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from db import Database


class CreditDebitNoteLogic:
    """Database and validation layer for Credit / Debit Notes."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.ensure_tables()

    def ensure_tables(self) -> None:
        pk = self.db._get_primary_key_autoincrement()
        ts = self.db._get_timestamp_default()
        self.db.execute_update(f"""
            CREATE TABLE IF NOT EXISTS credit_debit_notes (
                id {pk},
                company_id INTEGER NOT NULL,
                serial_no TEXT,
                note_type TEXT NOT NULL,
                note_date DATE NOT NULL,
                party_type TEXT NOT NULL,
                party_id INTEGER,
                party_name TEXT,
                reason TEXT,
                goods_description TEXT,
                quantity REAL DEFAULT 0.0,
                related_bill_no TEXT,
                related_bill_date DATE,
                return_date DATE,
                return_document_details TEXT,
                amount REAL DEFAULT 0.0,
                related_tax REAL DEFAULT 0.0,
                total REAL DEFAULT 0.0,
                remarks TEXT,
                status TEXT DEFAULT 'Saved',
                created_at TIMESTAMP DEFAULT {ts},
                updated_at TIMESTAMP DEFAULT {ts}
            )
        """)
        self._ensure_columns()
        self.db.execute_update("CREATE INDEX IF NOT EXISTS idx_cdn_company ON credit_debit_notes(company_id)")
        self.db.execute_update("CREATE INDEX IF NOT EXISTS idx_cdn_serial ON credit_debit_notes(company_id, serial_no)")
        self.db.execute_update("CREATE INDEX IF NOT EXISTS idx_cdn_date ON credit_debit_notes(company_id, note_date)")
        self.db.execute_update("CREATE INDEX IF NOT EXISTS idx_cdn_party ON credit_debit_notes(company_id, party_id)")
        self.db.execute_update("CREATE INDEX IF NOT EXISTS idx_cdn_type ON credit_debit_notes(company_id, note_type)")

    def _ensure_columns(self) -> None:
        if self.db.db_type != "sqlite":
            return
        existing = {row.get("name") for row in self.db.execute_query("PRAGMA table_info(credit_debit_notes)")}
        required = {
            "return_date": "DATE",
            "status": "TEXT DEFAULT 'Saved'",
            "updated_at": "TIMESTAMP",
        }
        for col, col_type in required.items():
            if col not in existing:
                self.db.execute_update(f"ALTER TABLE credit_debit_notes ADD COLUMN {col} {col_type}")

    def _next_serial_no(self, company_id: int) -> str:
        ph = self.db._get_placeholder()
        rows = self.db.execute_query(
            f"SELECT serial_no FROM credit_debit_notes WHERE company_id={ph} ORDER BY id DESC LIMIT 1",
            (company_id,),
        )
        if not rows or not rows[0].get("serial_no"):
            return "CDN-001"
        raw = str(rows[0].get("serial_no", ""))
        try:
            num = int(raw.split("-")[-1]) + 1
        except Exception:
            num = len(self.db.execute_query(f"SELECT id FROM credit_debit_notes WHERE company_id={ph}", (company_id,))) + 1
        return f"CDN-{num:03d}"

    def get_parties_by_type(self, company_id: int, party_type: str) -> List[Dict[str, Any]]:
        ph = self.db._get_placeholder()
        normalized = (party_type or "").strip().lower()
        if normalized in ("debtor", "debitor", "sundry debtors"):
            types = ("Debitor", "Both")
        else:
            types = ("Creditor", "Both")
        return self.db.execute_query(
            f"""
            SELECT id, name, gstin, address AS state, party_type
            FROM parties
            WHERE company_id={ph} AND party_type IN ({ph}, {ph})
            ORDER BY name COLLATE NOCASE
            """,
            (company_id, types[0], types[1]),
        )

    def create_note(self, data: Dict[str, Any]) -> str:
        company_id = int(data["company_id"])
        serial_no = data.get("serial_no") or self._next_serial_no(company_id)
        amount = self._to_float(data.get("amount"))
        tax = self._to_float(data.get("related_tax"))
        total = amount + tax
        ph = self.db._get_placeholder()
        self.db.execute_update(
            f"""
            INSERT INTO credit_debit_notes (
                company_id, serial_no, note_type, note_date, party_type, party_id, party_name,
                reason, goods_description, quantity, related_bill_no, related_bill_date,
                return_date, return_document_details, amount, related_tax, total, remarks, updated_at
            ) VALUES ({','.join([ph] * 19)})
            """,
            (
                company_id,
                serial_no,
                data.get("note_type", "Credit Note"),
                data.get("note_date"),
                data.get("party_type", "Debtor"),
                data.get("party_id"),
                data.get("party_name", ""),
                data.get("reason", ""),
                data.get("goods_description", ""),
                self._to_float(data.get("quantity")),
                data.get("related_bill_no", ""),
                data.get("related_bill_date"),
                data.get("return_date"),
                data.get("return_document_details", ""),
                amount,
                tax,
                total,
                data.get("remarks", ""),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        return serial_no

    def update_note(self, note_id: int, data: Dict[str, Any]) -> bool:
        amount = self._to_float(data.get("amount"))
        tax = self._to_float(data.get("related_tax"))
        total = amount + tax
        ph = self.db._get_placeholder()
        return self.db.execute_update(
            f"""
            UPDATE credit_debit_notes SET
                note_type={ph}, note_date={ph}, party_type={ph}, party_id={ph}, party_name={ph},
                reason={ph}, goods_description={ph}, quantity={ph}, related_bill_no={ph},
                related_bill_date={ph}, return_date={ph}, return_document_details={ph},
                amount={ph}, related_tax={ph}, total={ph}, remarks={ph}, updated_at={ph}
            WHERE id={ph}
            """,
            (
                data.get("note_type", "Credit Note"),
                data.get("note_date"),
                data.get("party_type", "Debtor"),
                data.get("party_id"),
                data.get("party_name", ""),
                data.get("reason", ""),
                data.get("goods_description", ""),
                self._to_float(data.get("quantity")),
                data.get("related_bill_no", ""),
                data.get("related_bill_date"),
                data.get("return_date"),
                data.get("return_document_details", ""),
                amount,
                tax,
                total,
                data.get("remarks", ""),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                note_id,
            ),
        )

    def delete_note(self, note_id: int) -> bool:
        ph = self.db._get_placeholder()
        return self.db.execute_update(f"DELETE FROM credit_debit_notes WHERE id={ph}", (note_id,))

    def get_note_by_id(self, note_id: int) -> Optional[Dict[str, Any]]:
        ph = self.db._get_placeholder()
        rows = self.db.execute_query(f"SELECT * FROM credit_debit_notes WHERE id={ph}", (note_id,))
        return rows[0] if rows else None

    def get_previous_note(self, company_id: int, current_id: int, note_type: str) -> Optional[Dict[str, Any]]:
        ph = self.db._get_placeholder()
        rows = self.db.execute_query(
            f"""
            SELECT * FROM credit_debit_notes
            WHERE company_id={ph} AND note_type={ph} AND id < {ph}
            ORDER BY id DESC LIMIT 1
            """,
            (company_id, note_type, current_id),
        )
        return rows[0] if rows else None

    def get_next_note(self, company_id: int, current_id: int, note_type: str) -> Optional[Dict[str, Any]]:
        ph = self.db._get_placeholder()
        rows = self.db.execute_query(
            f"""
            SELECT * FROM credit_debit_notes
            WHERE company_id={ph} AND note_type={ph} AND id > {ph}
            ORDER BY id ASC LIMIT 1
            """,
            (company_id, note_type, current_id),
        )
        return rows[0] if rows else None

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            if value is None or value == "":
                return 0.0
            return float(str(value).replace(",", ""))
        except Exception:
            return 0.0
