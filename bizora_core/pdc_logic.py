"""
PDC (Post Dated Cheque) Logic Module.
Handles PDC receipt, issue, and register operations with zero-impact pending status.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from db import Database
from bizora_core.ledger_logic import LedgerLogic


class PDCLogic:
    """Logic for Post Dated Cheque management."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.ledger_logic = LedgerLogic(self.db)

    def _execute_insert(self, query: str, params: tuple = ()) -> int:
        """Execute INSERT and return the new row id.

        The project Database class currently exposes execute_query() and
        execute_update(), but not execute_insert().  This local helper keeps
        the PDC module compatible with the existing db.py without modifying
        the shared database layer.
        """
        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            last_id = getattr(cursor, "lastrowid", None)
            if last_id is None:
                # MySQL connectors normally provide lastrowid, but keep a safe
                # fallback for drivers that require SELECT LAST_INSERT_ID().
                if getattr(self.db, "db_type", "sqlite") == "mysql":
                    cursor.execute("SELECT LAST_INSERT_ID()")
                    row = cursor.fetchone()
                    last_id = row[0] if row else 0
                else:
                    cursor.execute("SELECT last_insert_rowid()")
                    row = cursor.fetchone()
                    last_id = row[0] if row else 0
            return int(last_id or 0)
        except Exception:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        finally:
            self.db.disconnect()

    def validate_pdc_data(self, data: Dict) -> Tuple[bool, str]:
        """
        Validate PDC data before save/update.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = [
            'company_id', 'transaction_type', 'account_type',
            'received_issued_date', 'cheque_date', 'cheque_number', 'amount'
        ]
        
        for field in required_fields:
            if field not in data or data[field] is None or data[field] == '':
                return False, f"Missing required field: {field}"
        
        # Validate transaction_type
        if data['transaction_type'] not in ['RECEIPT', 'ISSUE']:
            return False, "Invalid transaction_type. Must be RECEIPT or ISSUE."
        
        # Validate account_type
        if data['account_type'] not in ['General', 'Sundry Debtors', 'Sundry Creditors', 'Bank']:
            return False, "Invalid account_type."
        
        # Validate amount
        try:
            amount = float(data['amount'])
            if amount <= 0:
                return False, "Amount must be greater than 0."
        except (TypeError, ValueError):
            return False, "Invalid amount format."
        
        # Validate dates
        try:
            datetime.strptime(data['received_issued_date'], '%Y-%m-%d')
            datetime.strptime(data['cheque_date'], '%Y-%m-%d')
        except ValueError:
            return False, "Invalid date format. Use YYYY-MM-DD."
        
        # For Sundry Debtors/Creditors/Bank, party_id or bank_account_id should be provided
        account_type = data['account_type']
        if account_type in ['Sundry Debtors', 'Sundry Creditors']:
            if not data.get('party_id'):
                return False, f"party_id required for {account_type}."
        elif account_type == 'Bank':
            if not data.get('bank_account_id'):
                return False, "bank_account_id required for Bank account type."
        
        return True, ""

    def create_pdc(self, data: Dict) -> Optional[int]:
        """
        Create a new PDC entry (zero-impact - no ledger posting).
        
        Args:
            data: Dictionary with PDC details
            
        Returns:
            PDC ID if successful, None otherwise
        """
        # Validate data
        is_valid, error_msg = self.validate_pdc_data(data)
        if not is_valid:
            raise ValueError(error_msg)
        
        ph = self.db._get_placeholder()
        query = f"""
            INSERT INTO pdc_register (
                company_id, transaction_type, account_type, party_id, account_name,
                bank_account_id, bank_name, received_issued_date, cheque_date,
                cheque_number, cheque_bank_name, branch_name, amount, narration, status
            ) VALUES (
                {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}
            )
        """
        
        params = (
            data['company_id'],
            data['transaction_type'],
            data['account_type'],
            data.get('party_id'),
            data.get('account_name', ''),
            data.get('bank_account_id'),
            data.get('bank_name', ''),
            data['received_issued_date'],
            data['cheque_date'],
            data['cheque_number'],
            data.get('cheque_bank_name', ''),
            data.get('branch_name', ''),
            data['amount'],
            data.get('narration', ''),
            data.get('status', 'PENDING')
        )
        
        try:
            pdc_id = self._execute_insert(query, params)
            return pdc_id
        except Exception as e:
            raise Exception(f"Failed to create PDC: {e}")

    def update_pdc(self, pdc_id: int, data: Dict) -> bool:
        """
        Update an existing PDC entry (zero-impact if still pending).
        
        Args:
            pdc_id: PDC ID to update
            data: Dictionary with updated PDC details
            
        Returns:
            True if successful, False otherwise
        """
        # Check if PDC exists and is not cleared
        existing = self.get_pdc_by_id(pdc_id)
        if not existing:
            raise ValueError(f"PDC with ID {pdc_id} not found.")
        
        if existing['status'] == 'CLEARED':
            raise ValueError("Cannot update a CLEARED PDC.")
        
        # Validate data
        is_valid, error_msg = self.validate_pdc_data(data)
        if not is_valid:
            raise ValueError(error_msg)
        
        ph = self.db._get_placeholder()
        query = f"""
            UPDATE pdc_register SET
                transaction_type = {ph},
                account_type = {ph},
                party_id = {ph},
                account_name = {ph},
                bank_account_id = {ph},
                bank_name = {ph},
                received_issued_date = {ph},
                cheque_date = {ph},
                cheque_number = {ph},
                cheque_bank_name = {ph},
                branch_name = {ph},
                amount = {ph},
                narration = {ph},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph}
        """
        
        params = (
            data['transaction_type'],
            data['account_type'],
            data.get('party_id'),
            data.get('account_name', ''),
            data.get('bank_account_id'),
            data.get('bank_name', ''),
            data['received_issued_date'],
            data['cheque_date'],
            data['cheque_number'],
            data.get('cheque_bank_name', ''),
            data.get('branch_name', ''),
            data['amount'],
            data.get('narration', ''),
            pdc_id
        )
        
        try:
            self.db.execute_update(query, params)
            return True
        except Exception as e:
            raise Exception(f"Failed to update PDC: {e}")

    def get_pdc_by_id(self, pdc_id: int) -> Optional[Dict]:
        """Get PDC details by ID."""
        ph = self.db._get_placeholder()
        query = f"""
            SELECT pdc.id,
                   pdc.company_id,
                   pdc.transaction_type,
                   pdc.account_type,
                   pdc.party_id,
                   pdc.account_name,
                   pdc.bank_account_id,
                   pdc.bank_name,
                   pdc.received_issued_date,
                   pdc.cheque_date,
                   pdc.cheque_number,
                   pdc.cheque_bank_name,
                   pdc.branch_name,
                   pdc.amount,
                   pdc.narration,
                   pdc.status,
                   pdc.cleared_date,
                   pdc.bounced_date,
                   pdc.cancelled_date,
                   pdc.linked_voucher_id,
                   pdc.linked_voucher_type,
                   p.name as party_name,
                   ba.account_name as bank_account_name
            FROM pdc_register pdc
            LEFT JOIN parties p ON pdc.party_id = p.id
            LEFT JOIN bank_accounts ba ON pdc.bank_account_id = ba.id
            WHERE pdc.id = {ph}
        """
        results = self.db.execute_query(query, (pdc_id,))
        return results[0] if results else None

    @staticmethod
    def _cursor_row_to_dict(cursor, row) -> Dict:
        """Convert SQLite Row or tuple cursor output into a dictionary."""
        if hasattr(row, "keys"):
            return dict(row)
        columns = [column[0] for column in cursor.description]
        return dict(zip(columns, row))

    def _get_pending_pdc_for_clearance(self, cursor, pdc_id: int) -> Dict:
        """Return a fresh PDC row and enforce clearance/bounce state rules."""
        ph = self.db._get_placeholder()
        query = f"""
            SELECT id, company_id, transaction_type, account_type, party_id,
                   account_name, bank_account_id, bank_name, cheque_number,
                   amount, narration, status, linked_voucher_id,
                   linked_voucher_type
            FROM pdc_register
            WHERE id = {ph}
        """
        cursor.execute(query, (pdc_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"PDC with ID {pdc_id} not found.")

        pdc = self._cursor_row_to_dict(cursor, row)
        status = str(pdc.get("status") or "").upper()
        if status == "CLEARED":
            raise ValueError("PDC is already CLEARED.")
        if status == "BOUNCED":
            raise ValueError("Cannot clear a BOUNCED PDC.")
        if status == "CANCELLED":
            raise ValueError("Cannot clear a CANCELLED PDC.")
        if status != "PENDING":
            raise ValueError(f"Cannot clear a PDC with status {status}.")
        return pdc

    def _get_bank_ledger_account_id(self, company_id: int, bank_master_id: Optional[int] = None) -> int:
        """Return the ledger account used for bank posting."""
        if bank_master_id:
            ledger_id = self.ledger_logic.get_ledger_account_id_for_bank_master(company_id, int(bank_master_id))
            if ledger_id:
                return int(ledger_id)
        if not self.ledger_logic.ensure_system_accounts(company_id):
            raise ValueError("Failed to ensure ledger system accounts.")
        bank_account = self.ledger_logic.get_account_by_name(company_id, "Bank Account")
        if not bank_account:
            raise ValueError("Bank Account ledger is not available.")
        return int(bank_account["id"])

    def _get_pdc_counterparty_account_id(self, pdc: Dict) -> int:
        """Resolve the customer/supplier ledger account for PDC posting."""
        company_id = int(pdc["company_id"])
        party_id = pdc.get("party_id")
        account_type = pdc.get("account_type")

        if account_type in ("Sundry Debtors", "Sundry Creditors"):
            if not party_id:
                raise ValueError(f"party_id required for {account_type} PDC posting.")
            party_account = self.ledger_logic.get_account_by_party_id(company_id, int(party_id))
            if not party_account:
                raise ValueError("Could not resolve party ledger account for PDC posting.")
            return int(party_account["id"])

        if account_type == "General":
            if not party_id:
                raise ValueError("Account selection required for General PDC posting.")
            general_account = self.ledger_logic.get_account(company_id, int(party_id))
            if not general_account:
                raise ValueError("Could not resolve selected ledger account for PDC posting.")
            return int(general_account["id"])

        raise ValueError("PDC clearance posting requires a customer, supplier, or general ledger account.")

    def _get_posted_ledger_entry_id(
        self,
        cursor,
        company_id: int,
        voucher_type: str,
        voucher_id: int,
        voucher_no: str,
    ) -> int:
        """Return the generated ledger entry id for the posted PDC voucher."""
        ph = self.db._get_placeholder()
        cursor.execute(
            f"""
            SELECT MIN(id) AS ledger_entry_id
            FROM ledger_entries
            WHERE company_id = {ph}
              AND voucher_type = {ph}
              AND voucher_id = {ph}
              AND voucher_no = {ph}
            """,
            (company_id, voucher_type, voucher_id, voucher_no),
        )
        row = cursor.fetchone()
        ledger_entry_id = row[0] if row else None
        if not ledger_entry_id:
            raise ValueError("Ledger posting succeeded but no ledger entry id was generated.")
        return int(ledger_entry_id)

    def list_pdc(self, company_id: int, filters: Optional[Dict] = None) -> List[Dict]:
        """
        List PDC entries with optional filters.
        
        Args:
            company_id: Company ID
            filters: Optional dict with filters (from_date, to_date, transaction_type, status, account_type, search)
            
        Returns:
            List of PDC records
        """
        ph = self.db._get_placeholder()
        conditions = [f"pdc.company_id = {ph}"]
        params = [company_id]
        
        if filters:
            if filters.get('from_date'):
                conditions.append(f"pdc.cheque_date >= {ph}")
                params.append(filters['from_date'])
            if filters.get('to_date'):
                conditions.append(f"pdc.cheque_date <= {ph}")
                params.append(filters['to_date'])
            if filters.get('transaction_type') and filters['transaction_type'] != 'All':
                conditions.append(f"pdc.transaction_type = {ph}")
                params.append(filters['transaction_type'])
            if filters.get('status') and filters['status'] != 'All':
                conditions.append(f"pdc.status = {ph}")
                params.append(filters['status'])
            if filters.get('account_type') and filters['account_type'] != 'All':
                conditions.append(f"pdc.account_type = {ph}")
                params.append(filters['account_type'])
            if filters.get('search'):
                conditions.append(f"(pdc.cheque_number LIKE {ph} OR pdc.account_name LIKE {ph} OR pdc.cheque_bank_name LIKE {ph})")
                search_term = f"%{filters['search']}%"
                params.extend([search_term, search_term, search_term])
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT pdc.*, 
                   p.name as party_name,
                   ba.account_name as bank_account_name
            FROM pdc_register pdc
            LEFT JOIN parties p ON pdc.party_id = p.id
            LEFT JOIN bank_accounts ba ON pdc.bank_account_id = ba.id
            WHERE {where_clause}
            ORDER BY pdc.cheque_date DESC, pdc.id DESC
        """
        
        return self.db.execute_query(query, tuple(params))

    def mark_cleared(self, pdc_id: int, clear_bank_account_id: int, cleared_date: str) -> bool:
        """
        Mark a pending PDC as CLEARED and post its ledger impact atomically.
        
        Args:
            pdc_id: PDC ID to clear
            clear_bank_account_id: Bank account where cheque was cleared
            cleared_date: Date of clearance
            
        Returns:
            True if successful, False otherwise
        """
        if not clear_bank_account_id:
            raise ValueError("Bank account is required to clear a PDC.")

        try:
            datetime.strptime(cleared_date, '%Y-%m-%d')
        except ValueError:
            raise ValueError("Invalid cleared_date format. Use YYYY-MM-DD.")

        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            pdc = self._get_pending_pdc_for_clearance(cursor, pdc_id)
            company_id = int(pdc["company_id"])
            bank_ledger_account_id = self._get_bank_ledger_account_id(company_id, clear_bank_account_id)
            counterparty_account_id = self._get_pdc_counterparty_account_id(pdc)
            amount = float(pdc.get("amount") or 0.0)
            if amount <= 0:
                raise ValueError("PDC amount must be greater than zero for ledger posting.")

            transaction_type = str(pdc.get("transaction_type") or "").upper()
            if transaction_type == "RECEIPT":
                voucher_type = "pdc_receipt"
                voucher_no = f"PDC-R-{pdc_id}"
                entries = [
                    {
                        "account_id": bank_ledger_account_id,
                        "contra_account_id": counterparty_account_id,
                        "debit": amount,
                        "credit": 0.0,
                    },
                    {
                        "account_id": counterparty_account_id,
                        "contra_account_id": bank_ledger_account_id,
                        "debit": 0.0,
                        "credit": amount,
                    },
                ]
            elif transaction_type == "ISSUE":
                voucher_type = "pdc_payment"
                voucher_no = f"PDC-I-{pdc_id}"
                entries = [
                    {
                        "account_id": counterparty_account_id,
                        "contra_account_id": bank_ledger_account_id,
                        "debit": amount,
                        "credit": 0.0,
                    },
                    {
                        "account_id": bank_ledger_account_id,
                        "contra_account_id": counterparty_account_id,
                        "debit": 0.0,
                        "credit": amount,
                    },
                ]
            else:
                raise ValueError("Invalid PDC transaction_type for clearance posting.")

            narration = pdc.get("narration") or f"PDC cleared: cheque {pdc.get('cheque_number', '')}"
            posted = self.ledger_logic.post_double_entry(
                company_id=company_id,
                voucher_type=voucher_type,
                voucher_id=pdc_id,
                voucher_no=voucher_no,
                voucher_date=cleared_date,
                entries=entries,
                narration=narration,
                reference_type="pdc",
                reference_id=pdc_id,
                conn=conn,
                commit=False,
            )
            if not posted:
                raise ValueError("Failed to post PDC ledger entries.")

            linked_voucher_id = self._get_posted_ledger_entry_id(
                cursor, company_id, voucher_type, pdc_id, voucher_no
            )

            ph = self.db._get_placeholder()
            cursor.execute(
                f"""
                UPDATE pdc_register SET
                    status = 'CLEARED',
                    bank_account_id = {ph},
                    cleared_date = {ph},
                    linked_voucher_id = {ph},
                    linked_voucher_type = {ph},
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = {ph}
                  AND status = 'PENDING'
                """,
                (clear_bank_account_id, cleared_date, linked_voucher_id, voucher_type, pdc_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("PDC status changed before clearance could be completed.")

            conn.commit()
            return True
        except Exception as e:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise Exception(f"Failed to mark PDC as cleared: {e}")
        finally:
            self.db.disconnect()

    def mark_bounced(self, pdc_id: int, bounced_date: str, reason: str = '') -> bool:
        """
        Mark PDC as BOUNCED (status-only update, no ledger effect).
        
        Args:
            pdc_id: PDC ID to mark as bounced
            bounced_date: Date of bounce
            reason: Optional reason for bounce
            
        Returns:
            True if successful, False otherwise
        """
        ph = self.db._get_placeholder()
        bounce_note = f"Bounced: {reason}" if reason else "Bounced"
        conn = None
        try:
            conn = self.db.connect()
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT id, status, narration
                FROM pdc_register
                WHERE id = {ph}
                """,
                (pdc_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"PDC with ID {pdc_id} not found.")

            existing = self._cursor_row_to_dict(cursor, row)
            status = str(existing.get('status') or '').upper()
            if status == 'CLEARED':
                raise ValueError("Cannot bounce a CLEARED PDC from this screen. Use a separate bounce adjustment journal.")
            if status == 'BOUNCED':
                raise ValueError("PDC is already BOUNCED.")
            if status == 'CANCELLED':
                raise ValueError("Cannot mark a CANCELLED PDC as BOUNCED.")
            if status != 'PENDING':
                raise ValueError(f"Cannot bounce a PDC with status {status}.")

            current_narration = existing.get('narration') or ''
            updated_narration = bounce_note if not current_narration else f"{current_narration} | {bounce_note}"
            cursor.execute(
                f"""
                UPDATE pdc_register SET
                    status = 'BOUNCED',
                    bounced_date = {ph},
                    narration = {ph},
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = {ph}
                  AND status = 'PENDING'
                """,
                (bounced_date, updated_narration, pdc_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("PDC status changed before bounce could be completed.")
            conn.commit()
            return True
        except Exception as e:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise Exception(f"Failed to mark PDC as bounced: {e}")
        finally:
            self.db.disconnect()

    def mark_cancelled(self, pdc_id: int, cancelled_date: str, reason: str = '') -> bool:
        """
        Mark PDC as CANCELLED (status-only update, no ledger effect).
        
        Args:
            pdc_id: PDC ID to cancel
            cancelled_date: Date of cancellation
            reason: Optional reason for cancellation
            
        Returns:
            True if successful, False otherwise
        """
        # Check if PDC exists
        existing = self.get_pdc_by_id(pdc_id)
        if not existing:
            raise ValueError(f"PDC with ID {pdc_id} not found.")
        
        if existing['status'] == 'CANCELLED':
            raise ValueError("PDC is already CANCELLED.")
        
        if existing['status'] == 'CLEARED':
            raise ValueError("Cannot cancel a CLEARED PDC without reversal logic.")
        
        ph = self.db._get_placeholder()
        query = f"""
            UPDATE pdc_register SET
                status = 'CANCELLED',
                cancelled_date = {ph},
                narration = CASE 
                    WHEN narration IS NULL OR narration = '' THEN {ph}
                    ELSE narration || ' | Cancelled: ' || {ph}
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = {ph}
        """
        
        cancel_note = f"Cancelled: {reason}" if reason else "Cancelled"
        
        try:
            self.db.execute_update(query, (cancelled_date, cancel_note, pdc_id))
            return True
        except Exception as e:
            raise Exception(f"Failed to mark PDC as cancelled: {e}")

    def get_due_pdc_alerts(self, company_id: int, current_date: str) -> List[Dict]:
        """
        Get PDCs ready for clearance (cheque_date <= current_date AND status = PENDING).
        
        Args:
            company_id: Company ID
            current_date: Current date in YYYY-MM-DD format
            
        Returns:
            List of due PDCs
        """
        ph = self.db._get_placeholder()
        query = f"""
            SELECT pdc.*, 
                   p.name as party_name,
                   ba.account_name as bank_account_name
            FROM pdc_register pdc
            LEFT JOIN parties p ON pdc.party_id = p.id
            LEFT JOIN bank_accounts ba ON pdc.bank_account_id = ba.id
            WHERE pdc.company_id = {ph}
                AND pdc.cheque_date <= {ph}
                AND pdc.status = 'PENDING'
            ORDER BY pdc.cheque_date ASC
        """
        
        return self.db.execute_query(query, (company_id, current_date))

    def get_pending_pdc_for_party(self, company_id: int, party_id: int) -> List[Dict]:
        """
        Get pending PDCs for a specific party (for Ledger footer note).
        
        Args:
            company_id: Company ID
            party_id: Party ID
            
        Returns:
            List of pending PDCs for the party
        """
        ph = self.db._get_placeholder()
        query = f"""
            SELECT pdc.*,
                   p.name as party_name
            FROM pdc_register pdc
            LEFT JOIN parties p ON pdc.party_id = p.id
            WHERE pdc.company_id = {ph}
                AND pdc.party_id = {ph}
                AND pdc.status = 'PENDING'
            ORDER BY pdc.cheque_date ASC
        """
        
        return self.db.execute_query(query, (company_id, party_id))

    def get_parties_by_type(self, company_id: int, party_type: str) -> List[Dict]:
        """Get parties filtered by type for PDC popup.

        Supports the project spelling `Debitor`, the standard spelling
        `Debtor`, and `Both`, so existing debtor/creditor masters always
        appear in PDC account selection.
        """
        ph = self.db._get_placeholder()

        if party_type in ('Debitor', 'Debtor', 'Sundry Debtors'):
            type_values = ['Debitor', 'Debtor', 'Sundry Debtors', 'Both']
        elif party_type in ('Creditor', 'Sundry Creditors'):
            type_values = ['Creditor', 'Sundry Creditors', 'Both']
        else:
            type_values = [party_type, 'Both']

        placeholders = ", ".join([ph] * len(type_values))
        query = f"""
            SELECT id, name, party_type, gstin, state, mobile_number, opening_balance
            FROM parties
            WHERE company_id = {ph}
              AND party_type IN ({placeholders})
            ORDER BY name ASC
        """
        return self.db.execute_query(query, tuple([company_id] + type_values))

    def get_all_parties(self, company_id: int) -> List[Dict]:
        """Return all parties for PDC popup fallback."""
        ph = self.db._get_placeholder()
        query = f"""
            SELECT id, name, party_type, gstin, state, mobile_number, opening_balance
            FROM parties
            WHERE company_id = {ph}
            ORDER BY name ASC
        """
        return self.db.execute_query(query, (company_id,))

    def get_bank_accounts(self, company_id: int) -> List[Dict]:
        """
        Get bank accounts for the company.
        
        Args:
            company_id: Company ID
            
        Returns:
            List of bank accounts
        """
        ph = self.db._get_placeholder()
        query = f"""
            SELECT id, account_name, bank_name, account_number
            FROM bank_accounts
            WHERE company_id = {ph}
            ORDER BY account_name ASC
        """
        
        return self.db.execute_query(query, (company_id,))

    def get_general_accounts(self, company_id: int) -> List[Dict]:
        """Return general ledger/account options for PDC account popup.

        The app has evolved through multiple account storage versions. Try the
        newer ledger_accounts source first, then safely fall back to accounts.
        Never create duplicate account rows from this report/popup helper.
        """
        ph = self.db._get_placeholder()

        query = f"""
            SELECT id, account_name, account_type
            FROM ledger_accounts
            WHERE company_id = {ph}
              AND account_type IN ('income', 'expense', 'tax_liability', 'capital', 'asset', 'liability', 'general')
            ORDER BY account_name ASC
        """
        try:
            rows = self.db.execute_query(query, (company_id,))
            if rows:
                return rows
        except Exception:
            pass

        fallback = f"""
            SELECT id, name AS account_name, type AS account_type
            FROM accounts
            WHERE company_id = {ph}
            ORDER BY name ASC
        """
        try:
            return self.db.execute_query(fallback, (company_id,))
        except Exception:
            return []

    def get_previous_pdc(self, company_id: int, current_id: int, transaction_type: str) -> Optional[Dict]:
        """
        Get the previous PDC record before current_id for the given transaction_type.

        Args:
            company_id: Company ID
            current_id: Current PDC ID
            transaction_type: 'RECEIPT' or 'ISSUE'

        Returns:
            Previous PDC record or None if no previous record exists
        """
        ph = self.db._get_placeholder()
        query = f"""
            SELECT pdc.*,
                   p.name as party_name,
                   ba.account_name as bank_account_name
            FROM pdc_register pdc
            LEFT JOIN parties p ON pdc.party_id = p.id
            LEFT JOIN bank_accounts ba ON pdc.bank_account_id = ba.id
            WHERE pdc.company_id = {ph}
              AND pdc.transaction_type = {ph}
              AND pdc.id < {ph}
            ORDER BY pdc.id DESC
            LIMIT 1
        """
        results = self.db.execute_query(query, (company_id, transaction_type, current_id))
        return results[0] if results else None

    def get_next_pdc(self, company_id: int, current_id: int, transaction_type: str) -> Optional[Dict]:
        """
        Get the next PDC record after current_id for the given transaction_type.

        Args:
            company_id: Company ID
            current_id: Current PDC ID
            transaction_type: 'RECEIPT' or 'ISSUE'

        Returns:
            Next PDC record or None if no next record exists
        """
        ph = self.db._get_placeholder()
        query = f"""
            SELECT pdc.*,
                   p.name as party_name,
                   ba.account_name as bank_account_name
            FROM pdc_register pdc
            LEFT JOIN parties p ON pdc.party_id = p.id
            LEFT JOIN bank_accounts ba ON pdc.bank_account_id = ba.id
            WHERE pdc.company_id = {ph}
              AND pdc.transaction_type = {ph}
              AND pdc.id > {ph}
            ORDER BY pdc.id ASC
            LIMIT 1
        """
        results = self.db.execute_query(query, (company_id, transaction_type, current_id))
        return results[0] if results else None
