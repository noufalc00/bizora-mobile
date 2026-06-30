"""
PDC Book logic.
Read-only accounting book report queries for unified PDC Issue and Receipt view.
"""

from typing import Any, Dict, List, Optional

from db import Database


def safe_float(value: Any) -> float:
    """Convert common database values to float safely."""
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class PDCBookLogic:
    """Logic for PDC Book - unified view of PDC Issue and Receipt."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()

    def _ph(self) -> str:
        """Get database placeholder."""
        return self.db._get_placeholder()

    def get_pdc_book_data(
        self,
        company_id: int,
        from_date: str,
        to_date: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get unified PDC book data for both Issue and Receipt.

        Args:
            company_id: Company ID
            from_date: From date (YYYY-MM-DD)
            to_date: To date (YYYY-MM-DD)
            filters: Optional dict with filters (transaction_type, status, party_id, bank_account_id, voucher_no)

        Returns:
            List of PDC records with unified fields
        """
        ph = self._ph()
        conditions = [f"pdc.company_id = {ph}"]
        params = [company_id]

        # Date filter uses cheque_date, the PDC maturity/due date.
        conditions.append(f"pdc.cheque_date >= {ph}")
        params.append(from_date)
        conditions.append(f"pdc.cheque_date <= {ph}")
        params.append(to_date)

        if filters:
            if filters.get('transaction_type') and filters['transaction_type'] != 'All':
                conditions.append(f"pdc.transaction_type = {ph}")
                params.append(filters['transaction_type'])
            if filters.get('status') and filters['status'] != 'All':
                conditions.append(f"pdc.status = {ph}")
                params.append(filters['status'])
            if filters.get('party_id'):
                conditions.append(f"pdc.party_id = {ph}")
                params.append(filters['party_id'])
            if filters.get('bank_account_id'):
                conditions.append(f"pdc.bank_account_id = {ph}")
                params.append(filters['bank_account_id'])
            if filters.get('voucher_no'):
                conditions.append(f"pdc.id = {ph}")
                params.append(filters['voucher_no'])

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT
                pdc.id AS voucher_no,
                pdc.received_issued_date AS date,
                pdc.transaction_type AS type,
                COALESCE(p.name, pdc.account_name) AS party,
                COALESCE(ba.account_name, pdc.bank_name) AS bank,
                pdc.cheque_number AS cheque_no,
                pdc.amount,
                pdc.cheque_date AS due_date,
                pdc.status,
                COALESCE(pdc.narration, '') AS narration
            FROM pdc_register pdc
            LEFT JOIN parties p ON pdc.party_id = p.id
            LEFT JOIN bank_accounts ba ON pdc.bank_account_id = ba.id
            WHERE {where_clause}
            ORDER BY pdc.cheque_date ASC, pdc.id ASC
        """

        results = self.db.execute_query(query, tuple(params))

        # DEBUG PRINTS
        print(f"PDC ISSUE COUNT = {len([r for r in results if r.get('type') == 'ISSUE'])}")
        print(f"PDC RECEIPT COUNT = {len([r for r in results if r.get('type') == 'RECEIPT'])}")
        print(f"FILTER TYPE = {filters.get('transaction_type', 'All') if filters else 'All'}")
        print(f"FILTER STATUS = {filters.get('status', 'All') if filters else 'All'}")

        return results

    def get_party_choices(self, company_id: int) -> List[Dict[str, Any]]:
        """Get party list for party filter dropdown."""
        ph = self._ph()
        query = f"""
            SELECT id, name, party_type
            FROM parties
            WHERE company_id = {ph}
            ORDER BY name ASC
        """
        return self.db.execute_query(query, (company_id,))

    def get_bank_choices(self, company_id: int) -> List[Dict[str, Any]]:
        """Get bank account list for bank filter dropdown."""
        ph = self._ph()
        query = f"""
            SELECT id, account_name, bank_name
            FROM bank_accounts
            WHERE company_id = {ph}
            ORDER BY account_name ASC
        """
        return self.db.execute_query(query, (company_id,))
