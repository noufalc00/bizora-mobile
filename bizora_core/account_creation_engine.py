"""
Account Creation Engine

Handles creation of ledger accounts and account groups.
MVC Pattern: Engine handles all database operations, UI only collects and displays data.
ANSI SQL compatible for future MySQL migration.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime


class AccountCreationEngine:
    """Engine for creating ledger accounts and account groups."""
    
    def __init__(self, db):
        """
        Initialize account creation engine with database connection.
        
        Args:
            db: Database instance (db.Database)
        """
        self.db = db
    
    def create_ledger_account(
        self,
        company_id: int,
        account_name: str,
        account_type: str,
        group_name: Optional[str] = None,
        opening_balance: float = 0.0,
        opening_balance_type: str = 'Dr',
        account_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new ledger account with opening balance.
        
        Args:
            company_id: Company ID
            account_name: Account name
            account_type: Account type (party, cash_bank, income, expense, tax_liability, capital, stock)
            group_name: Optional group name for categorization
            opening_balance: Opening balance amount
            opening_balance_type: Balance type ('Dr' or 'Cr')
            account_code: Optional account code
            
        Returns:
            Dict with success status and account_id or error message
        """
        try:
            # Validate account_type
            valid_types = ['party', 'cash_bank', 'income', 'expense', 'tax_liability', 'capital', 'stock']
            if account_type not in valid_types:
                return {
                    'success': False,
                    'error': f'Invalid account_type. Must be one of: {", ".join(valid_types)}'
                }
            
            # Validate opening_balance_type
            if opening_balance_type not in ['Dr', 'Cr']:
                return {
                    'success': False,
                    'error': 'Invalid opening_balance_type. Must be "Dr" or "Cr"'
                }
            
            ph = self.db._get_placeholder()
            
            # Check if account already exists
            check_query = f"""
                SELECT id FROM ledger_accounts 
                WHERE company_id = {ph} AND account_name = {ph}
            """
            existing = self.db.execute_query(check_query, (company_id, account_name))
            
            if existing:
                return {
                    'success': False,
                    'error': f'Account "{account_name}" already exists for this company'
                }
            
            # Insert new ledger account with transactional safety
            insert_query = f"""
                INSERT INTO ledger_accounts (
                    company_id, account_name, account_code, account_type, 
                    group_name, opening_balance, opening_balance_type, 
                    is_system, is_active, created_at, updated_at
                ) VALUES (
                    {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, 0, 1, 
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """
            
            self.db.execute_update(insert_query, (
                company_id, account_name, account_code, account_type,
                group_name, opening_balance, opening_balance_type
            ))
            
            # Get the newly created account ID
            account_id = self.db.execute_query(
                f"SELECT last_insert_rowid() as id",
                ()
            )[0]['id']
            
            return {
                'success': True,
                'account_id': account_id,
                'message': f'Account "{account_name}" created successfully'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Database error: {str(e)}'
            }
    
    def get_account_groups(self, company_id: int) -> List[Dict[str, Any]]:
        """
        Get all unique group names for a company.
        
        Args:
            company_id: Company ID
            
        Returns:
            List of unique group names
        """
        try:
            ph = self.db._get_placeholder()
            query = f"""
                SELECT DISTINCT group_name 
                FROM ledger_accounts 
                WHERE company_id = {ph} 
                  AND group_name IS NOT NULL 
                  AND group_name != ''
                ORDER BY group_name
            """
            result = self.db.execute_query(query, (company_id,))
            return [{'group_name': row['group_name']} for row in result]
        except Exception as e:
            print(f"Error fetching account groups: {e}")
            return []
    
    def get_all_accounts(self, company_id: int) -> List[Dict[str, Any]]:
        """
        Get all ledger accounts for a company.
        
        Args:
            company_id: Company ID
            
        Returns:
            List of account dictionaries
        """
        try:
            ph = self.db._get_placeholder()
            query = f"""
                SELECT id, account_name, account_code, account_type, group_name,
                       opening_balance, opening_balance_type, is_active, is_system
                FROM ledger_accounts 
                WHERE company_id = {ph}
                ORDER BY account_type, account_name
            """
            result = self.db.execute_query(query, (company_id,))
            return [dict(row) for row in result]
        except Exception as e:
            print(f"Error fetching accounts: {e}")
            return []
    
    def get_primary_account_types(self) -> List[str]:
        """
        Get the primary account types for grouping.
        
        Returns:
            List of primary account types
        """
        return [
            'party',
            'cash_bank',
            'income',
            'expense',
            'tax_liability',
            'capital',
            'stock'
        ]
    
    def get_primary_account_type_display_names(self) -> Dict[str, str]:
        """
        Get display names for primary account types.
        
        Returns:
            Dict mapping account_type to display name
        """
        return {
            'party': 'Party (Debtor/Creditor)',
            'cash_bank': 'Cash/Bank Account',
            'income': 'Income Account',
            'expense': 'Expense Account',
            'tax_liability': 'Tax Liability (GST)',
            'capital': 'Capital Account',
            'stock': 'Stock Account'
        }
    
    def update_ledger_account(
        self,
        account_id: int,
        company_id: int,
        account_name: str,
        account_type: str,
        group_name: Optional[str] = None,
        opening_balance: float = 0.0,
        opening_balance_type: str = 'Dr',
        account_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update an existing ledger account.
        
        Args:
            account_id: Account ID to update
            company_id: Company ID
            account_name: Account name
            account_type: Account type (party, cash_bank, income, expense, tax_liability, capital, stock)
            group_name: Optional group name for categorization
            opening_balance: Opening balance amount
            opening_balance_type: Balance type ('Dr' or 'Cr')
            account_code: Optional account code
            
        Returns:
            Dict with success status and message or error
        """
        try:
            # Validate account_type
            valid_types = ['party', 'cash_bank', 'income', 'expense', 'tax_liability', 'capital', 'stock']
            if account_type not in valid_types:
                return {
                    'success': False,
                    'error': f'Invalid account_type. Must be one of: {", ".join(valid_types)}'
                }
            
            # Validate opening_balance_type
            if opening_balance_type not in ['Dr', 'Cr']:
                return {
                    'success': False,
                    'error': 'Invalid opening_balance_type. Must be "Dr" or "Cr"'
                }
            
            ph = self.db._get_placeholder()
            
            # Check if account exists and belongs to company
            check_query = f"""
                SELECT id FROM ledger_accounts 
                WHERE id = {ph} AND company_id = {ph}
            """
            existing = self.db.execute_query(check_query, (account_id, company_id))
            
            if not existing:
                return {
                    'success': False,
                    'error': f'Account not found or does not belong to this company'
                }
            
            # Check if new account name conflicts with another account
            name_check_query = f"""
                SELECT id FROM ledger_accounts 
                WHERE company_id = {ph} AND account_name = {ph} AND id != {ph}
            """
            name_conflict = self.db.execute_query(name_check_query, (company_id, account_name, account_id))
            
            if name_conflict:
                return {
                    'success': False,
                    'error': f'Account "{account_name}" already exists for this company'
                }
            
            # Update the ledger account
            update_query = f"""
                UPDATE ledger_accounts 
                SET account_name = {ph}, account_code = {ph}, account_type = {ph},
                    group_name = {ph}, opening_balance = {ph}, opening_balance_type = {ph},
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = {ph} AND company_id = {ph}
            """
            
            self.db.execute_update(update_query, (
                account_name, account_code, account_type,
                group_name, opening_balance, opening_balance_type,
                account_id, company_id
            ))
            
            return {
                'success': True,
                'message': f'Account "{account_name}" updated successfully'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Database error: {str(e)}'
            }
    
    def delete_ledger_account(self, account_id: int, company_id: int) -> Dict[str, Any]:
        """
        Delete a ledger account with safety checks.
        
        Args:
            account_id: Account ID to delete
            company_id: Company ID
            
        Returns:
            Dict with success status and message or error
        """
        try:
            ph = self.db._get_placeholder()
            
            # Check if account exists and belongs to company
            check_query = f"""
                SELECT id, account_name, is_system FROM ledger_accounts 
                WHERE id = {ph} AND company_id = {ph}
            """
            existing = self.db.execute_query(check_query, (account_id, company_id))
            
            if not existing:
                return {
                    'success': False,
                    'error': f'Account not found or does not belong to this company'
                }
            
            account = existing[0]
            account_name = account['account_name']
            
            # Prevent deletion of system accounts
            if account.get('is_system', 0) == 1:
                return {
                    'success': False,
                    'error': f'Cannot delete system account "{account_name}"'
                }
            
            # Check if account has ledger entries (transactions)
            entries_check_query = f"""
                SELECT COUNT(*) as count FROM ledger_entries 
                WHERE account_id = {ph}
            """
            entries_result = self.db.execute_query(entries_check_query, (account_id,))
            entry_count = entries_result[0]['count'] if entries_result else 0
            
            if entry_count > 0:
                return {
                    'success': False,
                    'error': f'Cannot delete account "{account_name}" - it has {entry_count} ledger entries. Delete or modify the transactions first.'
                }
            
            # Delete the account
            delete_query = f"""
                DELETE FROM ledger_accounts 
                WHERE id = {ph} AND company_id = {ph}
            """
            
            self.db.execute_update(delete_query, (account_id, company_id))
            
            return {
                'success': True,
                'message': f'Account "{account_name}" deleted successfully'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Database error: {str(e)}'
            }
