"""
Party Logic Module
Handles party (debitor/creditor) business logic and validation.
"""

from typing import Dict, Any, List, Optional
from datetime import date
import re

from bizora_core.common_finance import to_decimal, money_round


def normalise_party_code(value) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text.upper()[:7]


class PartyLogic:
    """Business logic for party operations."""

    def __init__(self, db):
        """Initialize party logic with database instance."""
        self.db = db
        self.ledger_logic = None

    def _get_ledger_logic(self):
        """Lazy load ledger_logic."""
        if self.ledger_logic is None:
            from .ledger_logic import LedgerLogic
            self.ledger_logic = LedgerLogic(self.db)
        return self.ledger_logic

    def get_parties(self, company_id: int) -> Dict[str, Any]:
        """
        Get all parties for a company.
        
        Returns:
            Dict with success status, message, and data
        """
        try:
            parties = self.db.get_parties_by_company(company_id)
            return {
                "success": True,
                "message": "Parties retrieved successfully",
                "data": parties
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve parties: {str(e)}",
                "data": []
            }

    def get_party_by_id(self, company_id: int, party_id: int) -> Dict[str, Any]:
        """
        Get a specific party by ID.
        
        Returns:
            Dict with success status, message, and data
        """
        try:
            party = self.db.get_party_by_id(company_id, party_id)
            if party:
                return {
                    "success": True,
                    "message": "Party retrieved successfully",
                    "data": party
                }
            else:
                return {
                    "success": False,
                    "message": "Party not found",
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve party: {str(e)}",
                "data": None
            }

    def validate_party_data(self, party_data: Dict[str, Any], 
                          current_party_id: Optional[int] = None,
                          company_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Validate party data.
        
        Returns:
            Dict with success status and message
        """
        # Check required fields
        if not party_data.get('name', '').strip():
            return {
                "success": False,
                "message": "Party Name is required"
            }

        if not party_data.get('party_type', '').strip():
            return {
                "success": False,
                "message": "Party Type is required"
            }

        # Validate party type
        party_type = party_data.get('party_type', '').strip()
        if party_type not in ['Debitor', 'Creditor', 'Both']:
            return {
                "success": False,
                "message": "Party Type must be Debtor, Creditor, or Both"
            }

        party_code = normalise_party_code(party_data.get('party_code', ''))
        if party_code and company_id:
            exists = self.db.party_code_exists(company_id, party_code, current_party_id)
            if exists:
                return {
                    "success": False,
                    "message": "This Short Code is already assigned to another party! You must manually enter a different unique code to save.",
                    "field": "party_code"
                }

        # Check for duplicate party name if company_id is provided
        if company_id:
            exists = self.db.party_name_exists(
                company_id,
                party_data['name'].strip(),
                current_party_id,
                party_type,
            )
            if exists:
                display_type = "Debtor" if party_type == "Debitor" else party_type
                return {
                    "success": False,
                    "message": f"This Party Name is already saved as a {display_type}! Please use a unique name.",
                    "field": "party_name"
                }

        # Validate numeric fields
        try:
            if party_data.get('opening_balance'):
                to_decimal(party_data['opening_balance'])
            if party_data.get('credit_limit'):
                to_decimal(party_data['credit_limit'])
        except (ValueError, TypeError):
            return {
                "success": False,
                "message": "Please enter valid numeric values for Opening Balance and Credit Limit"
            }

        return {
            "success": True,
            "message": "Party data is valid"
        }

    def normalize_party_data(self, party_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize party data (ensure proper types and defaults).
        
        Returns:
            Normalized party data dict
        """
        normalized = party_data.copy()

        # Ensure numeric fields are Decimals
        numeric_fields = ['opening_balance', 'credit_limit']
        
        for field in numeric_fields:
            value = normalized.get(field)
            if value is None or value == '':
                normalized[field] = float(money_round(to_decimal(0)))
            else:
                try:
                    normalized[field] = float(money_round(to_decimal(value)))
                except (ValueError, TypeError):
                    normalized[field] = float(money_round(to_decimal(0)))

        # Ensure text fields are stripped
        normalized['party_code'] = normalise_party_code(normalized.get('party_code', ''))

        text_fields = ['name', 'mobile_number', 'email', 'gstin', 'state', 'contact_person', 'address', 'notes']
        for field in text_fields:
            if field in normalized and normalized[field]:
                normalized[field] = normalized[field].strip()

        return normalized

    def _sync_opening_balance_entry(self, company_id: int, party_id: int,
                                    account_id: int, party_name: str,
                                    party_type: str, opening_balance: float) -> None:
        """Post one idempotent Opening Balance voucher for the party ledger.

        Party opening balance is stored in parties.opening_balance and posted as an
        OB-PARTY ledger voucher. ledger_accounts.opening_balance must stay 0 so the
        amount is not counted twice in ledger statements and trial balance.
        """
        ll = self._get_ledger_logic()
        voucher_type = "Opening Balance"
        voucher_no = f"OB-PARTY-{party_id}"
        amount = float(money_round(to_decimal(opening_balance or 0.0)))
        ob_type = 'Cr' if party_type == 'Creditor' else 'Dr'

        if amount <= 0:
            ll.delete_voucher_entries(company_id, voucher_type, party_id, voucher_no)
            ll.update_account(company_id, account_id, {
                'opening_balance': 0.0,
                'opening_balance_type': ob_type,
            })
            return

        ll.ensure_system_accounts(company_id)
        capital_account = ll.get_account_by_name_cached(company_id, "Capital Account")
        if not capital_account:
            capital_account = ll.get_account_by_name(company_id, "Capital Account")
        if not capital_account:
            return

        is_creditor = party_type == 'Creditor'
        party_entry = {
            'account_id': account_id,
            'debit': 0.0 if is_creditor else amount,
            'credit': amount if is_creditor else 0.0,
        }
        capital_entry = {
            'account_id': capital_account['id'],
            'debit': amount if is_creditor else 0.0,
            'credit': 0.0 if is_creditor else amount,
        }
        ll.post_double_entry(
            company_id,
            voucher_type,
            party_id,
            voucher_no,
            date.today(),
            [party_entry, capital_entry],
            narration=f"Opening Balance - {party_name}",
            reference_type="party",
            reference_id=party_id,
        )
        ll.update_account(company_id, account_id, {
            'opening_balance': 0.0,
            'opening_balance_type': ob_type,
        })

    def save_party(self, company_id: int, party_data: Dict[str, Any],
                   party_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Save a party (insert or update).

        Returns:
            Dict with success status and message
        """
        try:
            # Normalize data
            normalized_data = self.normalize_party_data(party_data)

            if party_id:
                # Update existing party
                self.db.update_party(company_id, party_id, normalized_data)
                # Sync opening balance on linked ledger account
                try:
                    ll = self._get_ledger_logic()
                    party_name = normalized_data.get('name', '')
                    party_type = normalized_data.get('party_type', 'Debitor')
                    ob = float(money_round(to_decimal(normalized_data.get('opening_balance', 0.0) or 0.0)))
                    ob_type = 'Cr' if party_type == 'Creditor' else 'Dr'
                    ll.ensure_system_accounts(company_id)
                    acct = ll.get_or_create_party_account(
                        company_id, party_id, party_name, party_type, 0.0, ob_type
                    )
                    if acct:
                        ll.update_account(company_id, acct['id'], {
                            'account_name': party_name,
                            'group_name': 'Sundry Creditors' if ob_type == 'Cr' else 'Sundry Debtors',
                            'opening_balance': 0.0,
                            'opening_balance_type': ob_type,
                        })
                        self._sync_opening_balance_entry(
                            company_id, party_id, acct['id'], party_name, party_type, ob
                        )
                        ll.rebuild_running_balances(company_id)
                except Exception as e:
                    print(f"Warning: Party ledger update failed: {e}")
                return {
                    "success": True,
                    "message": "Party updated successfully"
                }
            else:
                # Insert new party
                new_id = self.db.insert_party(company_id, normalized_data)
                # Create linked ledger account
                try:
                    ll = self._get_ledger_logic()
                    ll.ensure_system_accounts(company_id)
                    if new_id:
                        party_name = normalized_data.get('name', '')
                        party_type = normalized_data.get('party_type', 'Debitor')
                        ob = float(money_round(to_decimal(normalized_data.get('opening_balance', 0.0) or 0.0)))
                        ob_type = 'Cr' if party_type == 'Creditor' else 'Dr'
                        acct = ll.get_or_create_party_account(
                            company_id, new_id, party_name, party_type, 0.0, ob_type
                        )
                        if acct:
                            self._sync_opening_balance_entry(
                                company_id, new_id, acct['id'], party_name, party_type, ob
                            )
                            ll.rebuild_running_balances(company_id)
                except Exception as e:
                    print(f"Warning: Party ledger creation failed: {e}")
                return {
                    "success": True,
                    "message": "Party saved successfully"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to save party: {str(e)}"
            }

    def delete_party(self, company_id: int, party_id: int) -> Dict[str, Any]:
        """
        Delete a party.
        
        Returns:
            Dict with success status and message
        """
        try:
            self.db.delete_party(company_id, party_id)
            return {
                "success": True,
                "message": "Party deleted successfully"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to delete party: {str(e)}"
            }

    def filter_parties(self, parties: List[Dict[str, Any]],
                      filter_type: str) -> List[Dict[str, Any]]:
        """
        Filter parties by type.

        Returns:
            Filtered list of parties
        """
        if filter_type == "All":
            return parties

        filtered = []
        for party in parties:
            if party.get('party_type') == filter_type:
                filtered.append(party)

        return filtered

    def get_party_sales_balance(self, company_id: int, party_id: int,
                               exclude_sale_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Calculate party sales balance for opening balance and previous balance calculations.

        Args:
            company_id: Company ID
            party_id: Party ID
            exclude_sale_id: Optional sale ID to exclude (for editing/viewing old bills)

        Returns:
            Dict with:
                opening_balance: Party opening balance from parties table
                previous_sales_total: Total unpaid previous sales (excluding exclude_sale_id)
                previous_received_total: Total previous receipts/returns/adjustments
                previous_balance: opening_balance + previous_sales_total - previous_received_total
        """
        try:
            # Get party opening balance
            party = self.db.get_party_by_id(company_id, party_id)
            if not party:
                return {
                    "opening_balance": 0.0,
                    "previous_sales_total": 0.0,
                    "previous_received_total": 0.0,
                    "previous_balance": 0.0
                }
            opening_balance = float(money_round(to_decimal(party.get('opening_balance', 0.0))))

            # Get all sales for this party (excluding exclude_sale_id if provided)
            sales = self.db.get_sales_by_party(company_id, party_id)
            if not sales:
                sales = []

            previous_sales_total = to_decimal(0)
            for sale in sales:
                sale_id = sale.get('id')
                # Exclude current bill if editing/viewing
                if exclude_sale_id and sale_id == exclude_sale_id:
                    continue
                # Calculate unpaid amount: grand_total - amount_received
                grand_total = to_decimal(sale.get('grand_total', 0.0))
                amount_received = to_decimal(sale.get('amount_received', 0.0))
                unpaid = grand_total - amount_received
                if unpaid > to_decimal(0):
                    previous_sales_total += unpaid

            # Get receipts/returns/adjustments for this party
            # For now, we'll use a simplified approach - in future, this should query ledger entries
            previous_received_total = to_decimal(0)

            # Calculate previous balance
            previous_balance = float(money_round(to_decimal(opening_balance) + previous_sales_total - previous_received_total))

            return {
                "opening_balance": opening_balance,
                "previous_sales_total": previous_sales_total,
                "previous_received_total": previous_received_total,
                "previous_balance": previous_balance
            }
        except Exception as e:
            # On error, return safe defaults
            return {
                "opening_balance": 0.0,
                "previous_sales_total": 0.0,
                "previous_received_total": 0.0,
                "previous_balance": 0.0
            }
