"""
Party Balance Engine Module
Handles party balance calculations for all billing modules (Sales, Purchase, Sales Return, Purchase Return).
Uses international accounting standard for Opening Balance, Previous Balance, and Closing Balance.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime


class PartyBalanceEngine:
    """Balance calculation engine for party ledger operations."""

    def __init__(self, db):
        """Initialize balance engine with database instance."""
        self.db = db

    def get_party_opening_balance(self, company_id: int, party_id: int) -> float:
        """
        Get party opening balance from party master.

        Args:
            company_id: Company ID
            party_id: Party ID

        Returns:
            Opening balance from parties.opening_balance
        """
        try:
            party = self.db.get_party_by_id(company_id, party_id)
            if party:
                return float(party.get('opening_balance', 0.0))
            return 0.0
        except Exception:
            return 0.0

    def get_party_balance_before_voucher(
        self,
        company_id: int,
        party_id: int,
        voucher_type: str,
        voucher_id: Optional[int] = None,
        voucher_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate party balance before a specific voucher.

        This function calculates the balance BEFORE the current voucher by:
        - Starting with party opening balance
        - Adding/subtracting effects of all vouchers BEFORE current voucher
        - Excluding current voucher by ID
        - Excluding future vouchers (after current voucher date/id)

        Args:
            company_id: Company ID
            party_id: Party ID
            voucher_type: Type of current voucher ('sales', 'purchase', 'sales_return', 'purchase_return')
            voucher_id: ID of current voucher (to exclude when editing/viewing)
            voucher_date: Date of current voucher (for date-based exclusion)

        Returns:
            Dict with:
                opening_balance: Party master opening balance
                previous_balance: Balance before current voucher
                breakdown: Detailed breakdown by voucher type
        """
        try:
            # Get party opening balance
            opening_balance = self.get_party_opening_balance(company_id, party_id)

            # Get all vouchers for this party before current voucher
            vouchers = self.db.get_vouchers_before_date(
                company_id, party_id, voucher_type, voucher_id, voucher_date
            )

            # Calculate effects based on voucher type
            sales_effect = 0.0
            purchase_effect = 0.0
            sales_return_effect = 0.0
            purchase_return_effect = 0.0
            receipt_effect = 0.0
            payment_effect = 0.0

            for voucher in vouchers:
                v_type = voucher.get('voucher_type')
                v_date = voucher.get('voucher_date')
                v_id = voucher.get('voucher_id')

                # Skip if this is the current voucher (by ID)
                if voucher_id and v_id == voucher_id:
                    continue

                # Calculate effect based on voucher type
                if v_type == 'sales':
                    # Sales credit unpaid effect: +
                    # Sales amount received effect: -
                    grand_total = float(voucher.get('grand_total', 0.0))
                    amount_received = float(voucher.get('amount_received', 0.0))
                    unpaid = grand_total - amount_received
                    if unpaid > 0:
                        sales_effect += unpaid

                elif v_type == 'purchase':
                    # Purchase credit unpaid/payable effect: +
                    # Purchase amount paid effect: -
                    grand_total = float(voucher.get('grand_total', 0.0))
                    amount_paid = float(voucher.get('amount_paid', 0.0))
                    unpaid = grand_total - amount_paid
                    if unpaid > 0:
                        purchase_effect += unpaid

                elif v_type == 'sales_return':
                    # Sales return reduces debitor/customer receivable: -
                    grand_total = float(voucher.get('grand_total', 0.0))
                    amount_received = float(voucher.get('amount_received', 0.0))
                    unpaid = grand_total - amount_received
                    if unpaid > 0:
                        sales_return_effect -= unpaid

                elif v_type == 'purchase_return':
                    # Purchase return reduces creditor payable: -
                    grand_total = float(voucher.get('grand_total', 0.0))
                    amount_paid = float(voucher.get('amount_paid', 0.0))
                    unpaid = grand_total - amount_paid
                    if unpaid > 0:
                        purchase_return_effect -= unpaid

            # Calculate previous balance
            previous_balance = (
                opening_balance
                + sales_effect
                + purchase_effect
                + sales_return_effect
                + purchase_return_effect
                + receipt_effect
                + payment_effect
            )

            return {
                'opening_balance': opening_balance,
                'previous_balance': previous_balance,
                'breakdown': {
                    'sales_effect': sales_effect,
                    'purchase_effect': purchase_effect,
                    'sales_return_effect': sales_return_effect,
                    'purchase_return_effect': purchase_return_effect,
                    'receipt_effect': receipt_effect,
                    'payment_effect': payment_effect
                }
            }
        except Exception as e:
            # On error, return safe defaults
            return {
                'opening_balance': 0.0,
                'previous_balance': 0.0,
                'breakdown': {
                    'sales_effect': 0.0,
                    'purchase_effect': 0.0,
                    'sales_return_effect': 0.0,
                    'purchase_return_effect': 0.0,
                    'receipt_effect': 0.0,
                    'payment_effect': 0.0
                }
            }

    def calculate_closing_balance(
        self,
        previous_balance: float,
        current_amount: float,
        amount_received_or_paid: float,
        voucher_type: str
    ) -> float:
        """
        Calculate closing balance based on voucher type.

        Args:
            previous_balance: Balance before current voucher
            current_amount: Current voucher net amount
            amount_received_or_paid: Amount received (sales) or paid (purchase)
            voucher_type: Type of voucher ('sales', 'purchase', 'sales_return', 'purchase_return')

        Returns:
            Closing balance
        """
        try:
            if voucher_type == 'sales':
                # Closing Balance = Previous Balance + Net Amount - Amount Received
                return previous_balance + current_amount - amount_received_or_paid

            elif voucher_type == 'purchase':
                # Closing Payable = Previous Balance + Purchase Net Amount - Amount Paid
                return previous_balance + current_amount - amount_received_or_paid

            elif voucher_type == 'sales_return':
                # Closing Balance = Previous Balance - Return Net Amount
                return previous_balance - current_amount

            elif voucher_type == 'purchase_return':
                # Closing Payable = Previous Balance - Return Net Amount
                return previous_balance - current_amount

            else:
                # Default: add current amount
                return previous_balance + current_amount
        except Exception:
            return previous_balance
