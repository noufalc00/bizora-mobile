"""
Bank Account Logic Module
Handles bank account business logic and validation.
"""

from typing import Dict, Any, List, Optional
from config import active_company_manager
from bizora_core.ledger_logic import LedgerLogic


class BankAccountLogic:
    """Business logic for bank accounts."""
    
    def __init__(self, db):
        """Initialize bank account logic with database instance."""
        self.db = db
        self.ledger_logic = LedgerLogic(db)
    
    def validate_bank_account_data(self, bank_account_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate bank account data before creation or update.
        
        Args:
            bank_account_data: Dictionary containing bank account information
            
        Returns:
            Dictionary with validation result and normalized data
        """
        errors = []
        
        # Validate required fields
        if 'account_name' not in bank_account_data or not bank_account_data['account_name']:
            errors.append("Account Name is required")
        else:
            account_name = str(bank_account_data['account_name']).strip()
            if not account_name:
                errors.append("Account Name cannot be empty")
        
        if 'bank_name' not in bank_account_data or not bank_account_data['bank_name']:
            errors.append("Bank Name is required")
        else:
            bank_name = str(bank_account_data['bank_name']).strip()
            if not bank_name:
                errors.append("Bank Name cannot be empty")
        
        if 'account_number' not in bank_account_data or not bank_account_data['account_number']:
            errors.append("Account Number is required")
        else:
            account_number = str(bank_account_data['account_number']).strip()
            if not account_number:
                errors.append("Account Number cannot be empty")
        
        # Validate opening balance
        if 'opening_balance' in bank_account_data:
            try:
                opening_balance = float(bank_account_data['opening_balance'])
                if opening_balance < 0:
                    errors.append("Opening Balance cannot be negative")
            except (ValueError, TypeError):
                errors.append("Opening Balance must be a valid number")
        
        if errors:
            return {
                'success': False,
                'errors': errors,
                'data': None
            }
        
        # Normalize data
        normalized_data = {
            'account_name': str(bank_account_data['account_name']).strip(),
            'bank_name': str(bank_account_data['bank_name']).strip(),
            'account_number': str(bank_account_data['account_number']).strip(),
            'ifsc_code': str(bank_account_data.get('ifsc_code', '')).strip().upper(),
            'branch_name': str(bank_account_data.get('branch_name', '')).strip(),
            'opening_balance': float(bank_account_data.get('opening_balance', 0.0)),
            'notes': str(bank_account_data.get('notes', '')).strip()
        }
        
        return {
            'success': True,
            'errors': None,
            'data': normalized_data
        }
    
    def save_bank_account(self, company_id: int, bank_account_data: Dict[str, Any], 
                         bank_account_id: Optional[int] = None) -> Dict[str, Any]:
        """Save a bank account (create or update).
        
        Args:
            company_id: Company ID
            bank_account_data: Dictionary containing bank account information
            bank_account_id: Bank account ID (None for create, ID for update)
            
        Returns:
            Dictionary with operation result
        """
        # Check if company exists
        active_company = active_company_manager.get_active_company()
        if not active_company or active_company['id'] != company_id:
            return {
                'success': False,
                'message': 'Invalid or inactive company'
            }
        
        # Validate bank account data
        validation = self.validate_bank_account_data(bank_account_data)
        
        if not validation['success']:
            return {
                'success': False,
                'message': 'Validation failed',
                'errors': validation['errors']
            }
        
        data = validation['data']
        
        # Check for duplicate account name
        if bank_account_id:
            if self.db.bank_account_name_exists(company_id, data['account_name'], bank_account_id):
                return {
                    'success': False,
                    'message': 'Bank account with this name already exists'
                }
        else:
            if self.db.bank_account_name_exists(company_id, data['account_name']):
                return {
                    'success': False,
                    'message': 'Bank account with this name already exists'
                }
        
        try:
            if bank_account_id:
                # Update existing bank account
                success = self.db.update_bank_account(company_id, bank_account_id, data)
                if success:
                    self._sync_bank_ledger(company_id, bank_account_id, data)
                    return {
                        'success': True,
                        'message': 'Bank account updated successfully',
                        'data': data,
                        'bank_account_id': bank_account_id
                    }
                else:
                    return {
                        'success': False,
                        'message': 'Failed to update bank account'
                    }
            else:
                # Create new bank account
                new_bank_account_id = self.db.insert_bank_account(company_id, data)
                if new_bank_account_id:
                    self._sync_bank_ledger(company_id, new_bank_account_id, data)
                    return {
                        'success': True,
                        'message': 'Bank account created successfully',
                        'data': data,
                        'bank_account_id': new_bank_account_id,
                    }
                else:
                    return {
                        'success': False,
                        'message': 'Failed to create bank account'
                    }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Error saving bank account: {str(e)}'
            }

    def _sync_bank_ledger(self, company_id: int, bank_account_id: int, data: Dict[str, Any]) -> None:
        """Create or update the ledger account linked to a bank master row."""
        try:
            self.ledger_logic.get_or_create_bank_master_ledger(company_id, int(bank_account_id))
        except Exception as exc:
            print(f"Warning: could not sync bank master ledger for id={bank_account_id}: {exc}")
    
    def get_bank_accounts(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all bank accounts for a specific company.
        
        Args:
            company_id: Company ID
            
        Returns:
            List of bank account records
        """
        try:
            accounts = self.db.get_bank_accounts_by_company(company_id)
            try:
                self.ledger_logic.ensure_bank_master_ledgers(company_id)
            except Exception:
                pass
            return accounts
        except Exception as e:
            print(f"Error getting bank accounts: {e}")
            return []
    
    def get_bank_account(self, company_id: int, bank_account_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific bank account by ID for a company.
        
        Args:
            company_id: Company ID
            bank_account_id: Bank account ID
            
        Returns:
            Bank account record or None
        """
        try:
            return self.db.get_bank_account_by_id(company_id, bank_account_id)
        except Exception as e:
            print(f"Error getting bank account: {e}")
            return None
    
    def delete_bank_account(self, company_id: int, bank_account_id: int) -> Dict[str, Any]:
        """Delete a bank account for a company.
        
        Args:
            company_id: Company ID
            bank_account_id: Bank account ID
            
        Returns:
            Dictionary with operation result
        """
        try:
            # Check if bank account exists
            bank_account = self.db.get_bank_account_by_id(company_id, bank_account_id)
            if not bank_account:
                return {
                    'success': False,
                    'message': 'Bank account not found'
                }
            
            success = self.db.delete_bank_account(company_id, bank_account_id)
            
            if success:
                return {
                    'success': True,
                    'message': 'Bank account deleted successfully'
                }
            else:
                return {
                    'success': False,
                    'message': 'Failed to delete bank account'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Error deleting bank account: {str(e)}'
            }
    
    def filter_bank_accounts(self, accounts: List[Dict[str, Any]], search_term: str) -> List[Dict[str, Any]]:
        """Filter bank accounts by search term.
        
        Args:
            accounts: List of bank account records
            search_term: Search term to filter by
            
        Returns:
            Filtered list of bank account records
        """
        if not search_term:
            return accounts
        
        search_term = str(search_term).strip().lower()
        if not search_term:
            return accounts
        
        filtered = []
        for account in accounts:
            # Search in Account Name, Bank Name, Account Number, IFSC Code
            if (search_term in account.get('account_name', '').lower() or
                search_term in account.get('bank_name', '').lower() or
                search_term in account.get('account_number', '').lower() or
                search_term in account.get('ifsc_code', '').lower()):
                filtered.append(account)
        
        return filtered
