"""
Journal Entry Logic Module.

Handles journal entry voucher operations with double-entry ledger posting.
"""

from typing import Dict, List, Any, Optional

from bizora_core.audit_logic import log_action


class JournalEntryLogic:
    """Logic for journal entry vouchers."""

    VOUCHER_PREFIX = "JV-"

    def __init__(self, db=None):
        """
        Initialize journal entry logic.

        Args:
            db: Database instance (optional, will create default if not provided)
        """
        if db is None:
            from db import Database
            self.db = Database()
        else:
            self.db = db

        self._posting_engine = None
        self._ledger_logic = None

    def _get_posting_engine(self):
        """Lazy load voucher posting engine."""
        if self._posting_engine is None:
            from bizora_core.voucher_posting_engine import VoucherPostingEngine
            self._posting_engine = VoucherPostingEngine(self.db)
        return self._posting_engine

    def _get_ledger_logic(self):
        """Lazy load ledger logic."""
        if self._ledger_logic is None:
            from bizora_core.ledger_logic import LedgerLogic
            self._ledger_logic = LedgerLogic(self.db)
        return self._ledger_logic

    # ============================================================
    # CRUD METHODS
    # ============================================================

    def _begin_transaction(self, conn) -> None:
        """Begin a caller-owned transaction with a write lock where supported."""
        if hasattr(self.db, "_is_sqlite") and self.db._is_sqlite():
            conn.execute("BEGIN IMMEDIATE")
            return
        if hasattr(conn, "start_transaction"):
            conn.start_transaction()

    def _build_journal_ledger_entries(self, lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build ledger posting rows from validated journal lines."""
        return [
            {
                'account_id': line['account_id'],
                'debit': line.get('debit', 0.0),
                'credit': line.get('credit', 0.0),
                'narration': line.get('narration', '')
            }
            for line in lines
        ]

    def _parse_voucher_number(self, voucher_no: str) -> Optional[int]:
        """Return numeric suffix for standard JV voucher numbers."""
        if not voucher_no or not str(voucher_no).startswith(self.VOUCHER_PREFIX):
            return None
        try:
            return int(str(voucher_no).split("-", 1)[1])
        except (IndexError, ValueError):
            return None

    def _format_voucher_no(self, number: int) -> str:
        """Format a standard Journal voucher number."""
        return f"{self.VOUCHER_PREFIX}{number:04d}"

    def _next_voucher_no_for_cursor(self, cursor, company_id: int) -> str:
        """Calculate the next Journal voucher number using the active transaction."""
        ph = self.db._get_placeholder()
        cursor.execute(
            f"""
                SELECT voucher_no
                FROM journal_vouchers
                WHERE company_id = {ph}
            """,
            (company_id,)
        )
        max_number = 0
        for row in cursor.fetchall():
            voucher_no = row["voucher_no"] if hasattr(row, "keys") else row[0]
            parsed = self._parse_voucher_number(voucher_no)
            if parsed and parsed > max_number:
                max_number = parsed
        return self._format_voucher_no(max_number + 1)

    def _voucher_no_exists(self, cursor, company_id: int, voucher_no: str,
                           excluded_journal_id: Optional[int] = None) -> bool:
        """Check voucher number existence inside the active transaction."""
        ph = self.db._get_placeholder()
        query = f"""
            SELECT id
            FROM journal_vouchers
            WHERE company_id = {ph}
              AND voucher_no = {ph}
        """
        params = [company_id, voucher_no]
        if excluded_journal_id is not None:
            query += f" AND id <> {ph}"
            params.append(excluded_journal_id)
        cursor.execute(query, tuple(params))
        return cursor.fetchone() is not None

    def _is_unique_error(self, error: Exception) -> bool:
        """Detect journal voucher uniqueness failures across DB backends."""
        message = str(error).lower()
        return (
            "unique" in message
            or "duplicate" in message
            or "journal_vouchers" in message and "voucher_no" in message
        )

    def save_journal_entry(self, company_id: int, voucher_no: str,
                         voucher_date: str, lines: List[Dict[str, Any]],
                         remark: str, narration: str) -> Dict[str, Any]:
        """Save a new journal entry voucher.

        Args:
            company_id: Company ID
            voucher_no: Voucher number (e.g., JV-0001)
            voucher_date: Voucher date
            lines: List of journal lines with 'account_id', 'debit', 'credit', 'narration', 'sl_no'
            remark: Remark
            narration: Narration

        Returns:
            Dict with success, data, message
        """
        for attempt in range(3):
            conn = None
            try:
                ph = self.db._get_placeholder()
                ts = self.db._get_timestamp_default()
                conn = self.db.connect()
                self._begin_transaction(conn)
                cursor = conn.cursor()

                effective_voucher_no = voucher_no.strip() if voucher_no else ""
                if (
                    not effective_voucher_no
                    or self._voucher_no_exists(cursor, company_id, effective_voucher_no)
                ):
                    effective_voucher_no = self._next_voucher_no_for_cursor(cursor, company_id)

                header_query = f"""
                    INSERT INTO journal_vouchers
                    (company_id, voucher_no, voucher_date, remark, narration, created_at, updated_at)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ts}, {ts})
                """
                cursor.execute(
                    header_query,
                    (company_id, effective_voucher_no, voucher_date, remark, narration)
                )
                journal_id = self.db._get_last_insert_id(cursor)

                if not journal_id:
                    conn.rollback()
                    return {"success": False, "message": "Failed to save journal header"}

                line_query = f"""
                    INSERT INTO journal_voucher_lines
                    (journal_id, account_id, debit, credit, narration, sl_no, created_at)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, CURRENT_TIMESTAMP)
                """
                for i, line in enumerate(lines):
                    cursor.execute(
                        line_query,
                        (
                            journal_id,
                            line.get('account_id'),
                            line.get('debit', 0.0),
                            line.get('credit', 0.0),
                            line.get('narration', ''),
                            line.get('sl_no', i + 1)
                        )
                    )

                posting_engine = self._get_posting_engine()
                success, error_msg = posting_engine.post_journal_entry(
                    company_id=company_id,
                    voucher_id=journal_id,
                    voucher_no=effective_voucher_no,
                    voucher_date=voucher_date,
                    entries=self._build_journal_ledger_entries(lines),
                    narration=narration,
                    conn=conn,
                    commit=False,
                )

                if not success:
                    conn.rollback()
                    return {"success": False, "message": f"Ledger posting failed: {error_msg}"}

                if not log_action(
                    company_id,
                    None,
                    'Journal',
                    'CREATE',
                    effective_voucher_no,
                    f"Created Journal Voucher with {len(lines)} lines.",
                    conn=conn,
                ):
                    raise Exception("Audit logging failed")

                conn.commit()
                return {
                    "success": True,
                    "data": {"id": journal_id, "voucher_no": effective_voucher_no},
                    "message": "Journal entry saved successfully"
                }

            except Exception as e:
                if conn is not None:
                    conn.rollback()
                if self._is_unique_error(e) and attempt < 2:
                    voucher_no = ""
                    continue
                if self._is_unique_error(e):
                    return {
                        "success": False,
                        "message": "Journal voucher number already exists. Please try saving again."
                    }
                return {"success": False, "message": f"Error saving journal entry: {e}"}

    def update_journal_entry(self, journal_id: int, company_id: int, voucher_no: str,
                           voucher_date: str, lines: List[Dict[str, Any]],
                           remark: str, narration: str) -> Dict[str, Any]:
        """Update an existing journal entry voucher.

        Args:
            journal_id: Journal voucher ID
            company_id: Company ID
            voucher_no: Voucher number
            voucher_date: Voucher date
            lines: List of journal lines
            remark: Remark
            narration: Narration

        Returns:
            Dict with success, data, message
        """
        conn = None
        try:
            ph = self.db._get_placeholder()
            ts = self.db._get_timestamp_default()
            conn = self.db.connect()
            self._begin_transaction(conn)
            cursor = conn.cursor()

            effective_voucher_no = voucher_no.strip() if voucher_no else ""
            if self._voucher_no_exists(cursor, company_id, effective_voucher_no, journal_id):
                conn.rollback()
                return {
                    "success": False,
                    "message": "Journal voucher number already exists."
                }

            header_query = f"""
                UPDATE journal_vouchers
                SET voucher_no = {ph}, voucher_date = {ph}, remark = {ph}, narration = {ph}, updated_at = {ts}
                WHERE id = {ph} AND company_id = {ph}
            """
            cursor.execute(
                header_query,
                (effective_voucher_no, voucher_date, remark, narration, journal_id, company_id)
            )

            if cursor.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Journal entry not found"}

            cursor.execute(
                f"DELETE FROM journal_voucher_lines WHERE journal_id = {ph}",
                (journal_id,)
            )

            line_query = f"""
                INSERT INTO journal_voucher_lines
                (journal_id, account_id, debit, credit, narration, sl_no, created_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, CURRENT_TIMESTAMP)
            """
            for i, line in enumerate(lines):
                cursor.execute(
                    line_query,
                    (
                        journal_id,
                        line.get('account_id'),
                        line.get('debit', 0.0),
                        line.get('credit', 0.0),
                        line.get('narration', ''),
                        line.get('sl_no', i + 1)
                    )
                )

            posting_engine = self._get_posting_engine()
            success, error_msg = posting_engine.update_voucher_ledger_entries(
                company_id=company_id,
                voucher_type='journal',
                voucher_id=journal_id,
                voucher_no=effective_voucher_no,
                voucher_date=voucher_date,
                entries=self._build_journal_ledger_entries(lines),
                narration=narration,
                conn=conn,
                commit=False,
            )

            if not success:
                conn.rollback()
                return {"success": False, "message": f"Ledger update failed: {error_msg}"}

            if not log_action(
                company_id,
                None,
                'Journal',
                'UPDATE',
                effective_voucher_no,
                f"Updated Journal Voucher with {len(lines)} lines.",
                conn=conn,
            ):
                raise Exception("Audit logging failed")

            conn.commit()
            return {
                "success": True,
                "data": {"id": journal_id, "voucher_no": effective_voucher_no},
                "message": "Journal entry updated successfully"
            }

        except Exception as e:
            if conn is not None:
                conn.rollback()
            if self._is_unique_error(e):
                return {
                    "success": False,
                    "message": "Journal voucher number already exists."
                }
            return {"success": False, "message": f"Error updating journal entry: {e}"}

    def delete_journal_entry(self, journal_id: int, company_id: int) -> Dict[str, Any]:
        """Delete a journal entry voucher.

        Args:
            journal_id: Journal voucher ID
            company_id: Company ID

        Returns:
            Dict with success, data, message
        """
        conn = None
        try:
            ph = self.db._get_placeholder()
            conn = self.db.connect()
            self._begin_transaction(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT voucher_no
                FROM journal_vouchers
                WHERE id = {ph} AND company_id = {ph}
                """,
                (journal_id, company_id)
            )
            journal_row = cursor.fetchone()
            old_voucher_no = str(journal_id)
            if journal_row:
                old_voucher_no = (
                    journal_row["voucher_no"]
                    if hasattr(journal_row, "keys")
                    else journal_row[0]
                )

            # Delete ledger entries first
            posting_engine = self._get_posting_engine()
            success, error_msg = posting_engine.delete_voucher_ledger_entries(
                company_id=company_id,
                voucher_type='journal',
                voucher_id=journal_id,
                conn=conn,
                commit=False,
            )

            if not success:
                conn.rollback()
                return {"success": False, "message": f"Transaction failed: Ledger deletion failed: {error_msg}"}

            # Delete voucher
            cursor.execute(f"DELETE FROM journal_voucher_lines WHERE journal_id = {ph}", (journal_id,))
            cursor.execute(
                f"DELETE FROM journal_vouchers WHERE id = {ph} AND company_id = {ph}",
                (journal_id, company_id)
            )
            if cursor.rowcount == 0:
                conn.rollback()
                return {"success": False, "message": "Transaction failed: Journal entry not found"}

            if not log_action(
                company_id,
                None,
                'Journal',
                'DELETE',
                old_voucher_no,
                "Deleted Journal Voucher.",
                conn=conn,
            ):
                raise Exception("Audit logging failed")

            conn.commit()
            return {
                "success": True,
                "message": "Journal entry deleted successfully"
            }

        except Exception as e:
            if conn is not None:
                conn.rollback()
            return {"success": False, "message": f"Transaction failed: {e}"}
        finally:
            if conn is not None:
                self.db.disconnect()

    def _delete_journal_entry(self, journal_id: int) -> None:
        """Delete journal entry from database (internal method)."""
        self._delete_journal_lines(journal_id)
        ph = self.db._get_placeholder()
        query = f"DELETE FROM journal_vouchers WHERE id = {ph}"
        self.db.execute_update(query, (journal_id,))

    def _delete_journal_lines(self, journal_id: int) -> None:
        """Delete journal lines (internal method)."""
        ph = self.db._get_placeholder()
        query = f"DELETE FROM journal_voucher_lines WHERE journal_id = {ph}"
        self.db.execute_update(query, (journal_id,))

    # ============================================================
    # QUERY METHODS
    # ============================================================

    def get_journal_entry(self, journal_id: int, company_id: int) -> Optional[Dict[str, Any]]:
        """Get a journal entry by ID with lines.

        Args:
            journal_id: Journal voucher ID
            company_id: Company ID

        Returns:
            Journal entry dict with lines or None
        """
        try:
            ph = self.db._get_placeholder()
            # Get header
            header_query = f"""
                SELECT * FROM journal_vouchers
                WHERE id = {ph} AND company_id = {ph}
            """
            header_result = self.db.execute_query(header_query, (journal_id, company_id))
            if not header_result:
                return None

            header = header_result[0]

            # Get lines
            lines_query = f"""
                SELECT jvl.*, la.account_name
                FROM journal_voucher_lines jvl
                LEFT JOIN ledger_accounts la ON jvl.account_id = la.id
                WHERE jvl.journal_id = {ph}
                ORDER BY jvl.sl_no
            """
            lines_result = self.db.execute_query(lines_query, (journal_id,))

            header['lines'] = lines_result if lines_result else []
            return header

        except Exception as e:
            print(f"Error getting journal entry: {e}")
            return None

    def get_journal_entries(self, company_id: int, from_date: str = None,
                          to_date: str = None) -> List[Dict[str, Any]]:
        """Get journal entries for a company.

        Args:
            company_id: Company ID
            from_date: From date (optional)
            to_date: To date (optional)

        Returns:
            List of journal entry dicts with lines
        """
        try:
            ph = self.db._get_placeholder()
            query = f"""
                SELECT jv.* FROM journal_vouchers jv
                WHERE jv.company_id = {ph}
            """
            params = [company_id]

            if from_date:
                query += f" AND jv.voucher_date >= {ph}"
                params.append(from_date)

            if to_date:
                query += f" AND jv.voucher_date <= {ph}"
                params.append(to_date)

            query += " ORDER BY jv.voucher_date, jv.id"

            headers = self.db.execute_query(query, tuple(params))
            if not headers:
                return []

            # Get lines for each header
            for header in headers:
                lines_query = f"""
                    SELECT jvl.*, la.account_name
                    FROM journal_voucher_lines jvl
                    LEFT JOIN ledger_accounts la ON jvl.account_id = la.id
                    WHERE jvl.journal_id = {ph}
                    ORDER BY jvl.sl_no
                """
                lines_result = self.db.execute_query(lines_query, (header['id'],))
                header['lines'] = lines_result if lines_result else []

            return headers

        except Exception as e:
            print(f"Error getting journal entries: {e}")
            return []

    def get_next_voucher_no(self, company_id: int) -> str:
        """Get next voucher number for journal entry.

        Args:
            company_id: Company ID

        Returns:
            Next voucher number (e.g., JV-0001)
        """
        try:
            ph = self.db._get_placeholder()
            query = f"""
                SELECT voucher_no
                FROM journal_vouchers
                WHERE company_id = {ph}
            """
            result = self.db.execute_query(query, (company_id,))
            max_number = 0
            for row in result or []:
                parsed = self._parse_voucher_number(row.get('voucher_no'))
                if parsed and parsed > max_number:
                    max_number = parsed

            return self._format_voucher_no(max_number + 1)

        except Exception as e:
            print(f"Error getting next voucher no: {e}")
            return "JV-0001"

    def get_non_system_accounts(self, company_id: int) -> List[Dict[str, Any]]:
        """Get active non-system ledger accounts for journal entry dropdowns.

        Args:
            company_id: Company ID

        Returns:
            List of non-system account dicts
        """
        try:
            ph = self.db._get_placeholder()
            query = f"""
                SELECT id, account_name, account_type
                FROM ledger_accounts
                WHERE company_id = {ph}
                  AND is_active = 1
                  AND COALESCE(is_system, 0) = 0
                ORDER BY account_name
            """
            result = self.db.execute_query(query, (company_id,))
            return result if result else []
        except Exception as e:
            print(f"Error getting accounts: {e}")
            return []

    def get_all_accounts(self, company_id: int) -> List[Dict[str, Any]]:
        """Get active non-system ledger accounts for journal entry.

        This compatibility wrapper keeps existing callers on the filtered
        Journal Entry account list rather than exposing system accounts.
        """
        return self.get_non_system_accounts(company_id)
