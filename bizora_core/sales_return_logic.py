"""
Sales Return Logic Module
Handles sales return business logic and validation.
"""

from typing import Dict, Any, List, Optional
from .stock_logic import StockLogic


class SalesReturnLogic:
    """Business logic for sales return operations."""

    def __init__(self, db):
        """Initialize sales return logic with database instance."""
        self.db = db
        self.stock_logic = StockLogic(db)
        self.ledger_logic = None  # Lazy load ledger_logic when needed

    def _get_ledger_logic(self):
        """Lazy load ledger_logic."""
        if self.ledger_logic is None:
            from .ledger_logic import LedgerLogic
            self.ledger_logic = LedgerLogic(self.db)
        return self.ledger_logic

    def get_sales_returns(self, company_id: int) -> Dict[str, Any]:
        """
        Get all sales returns for a company.

        Returns:
            Dict with success status, message, and data
        """
        try:
            sales_returns = self.db.get_sales_returns_by_company(company_id)
            return {
                "success": True,
                "message": "Sales returns retrieved successfully",
                "data": sales_returns
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve sales returns: {str(e)}",
                "data": []
            }

    def get_sales_return_by_id(self, company_id: int, sales_return_id: int) -> Dict[str, Any]:
        """
        Get a specific sales return by ID.

        Returns:
            Dict with success status, message, and data
        """
        try:
            sales_return = self.db.get_sales_return_by_id(company_id, sales_return_id)
            if sales_return:
                return {
                    "success": True,
                    "message": "Sales return retrieved successfully",
                    "data": sales_return
                }
            else:
                return {
                    "success": False,
                    "message": "Sales return not found",
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve sales return: {str(e)}",
                "data": None
            }

    def get_sales_return_items(self, sales_return_id: int) -> Dict[str, Any]:
        """
        Get all items for a specific sales return.

        Returns:
            Dict with success status, message, and data
        """
        try:
            items = self.db.get_sales_return_items(sales_return_id)
            return {
                "success": True,
                "message": "Sales return items retrieved successfully",
                "data": items
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve sales return items: {str(e)}",
                "data": []
            }

    def validate_sales_return_data(self, sales_return_data: Dict[str, Any],
                                   current_sales_return_id: Optional[int] = None,
                                   company_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Validate sales return data.

        Returns:
            Dict with success status and message
        """
        # Check required fields (party_id is optional for Cash returns)
        required_fields = ['company_id', 'return_no', 'return_date']
        for field in required_fields:
            if field not in sales_return_data or not sales_return_data[field]:
                return {
                    "success": False,
                    "message": f"Missing required field: {field}"
                }
        # Credit return must have a party
        if sales_return_data.get('return_type') == 'Credit' and not sales_return_data.get('party_id'):
            return {
                "success": False,
                "message": "Credit return requires a customer (party_id)"
            }

        # Check if items exist
        if 'items' not in sales_return_data or not sales_return_data['items']:
            return {
                "success": False,
                "message": "Sales return must have at least one item"
            }

        # Validate items
        for idx, item in enumerate(sales_return_data['items']):
            if 'product_id' not in item or not item['product_id']:
                return {
                    "success": False,
                    "message": f"Item {idx + 1}: Missing product_id"
                }
            if 'quantity' not in item or item['quantity'] <= 0:
                return {
                    "success": False,
                    "message": f"Item {idx + 1}: Quantity must be greater than 0"
                }

        # Check return_no uniqueness if new
        if current_sales_return_id is None:
            existing = self.db.get_sales_return_by_return_no(
                sales_return_data['company_id'],
                sales_return_data['return_no']
            )
            if existing:
                return {
                    "success": False,
                    "message": f"Return number {sales_return_data['return_no']} already exists"
                }

        return {
            "success": True,
            "message": "Sales return data is valid"
        }

    def save_sales_return(self, sales_return_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save a new sales return with items.

        Returns:
            Dict with success status, message, and sales_return_id
        """
        try:
            # Validate data
            validation = self.validate_sales_return_data(sales_return_data)
            if not validation['success']:
                return validation

            company_id = sales_return_data['company_id']

            # Save sales return header
            items = sales_return_data.get('items', [])

            # Commercial calculation/posting validation BEFORE any DB mutation.
            try:
                from .voucher_posting_engine import VoucherPostingEngine
                preview_engine = VoucherPostingEngine(self.db)
                preview = preview_engine.repost_voucher(
                    company_id=company_id,
                    voucher_type="sales_return",
                    voucher_id=0,
                    header=sales_return_data,
                    items=items,
                    apply_stock=False,
                    dry_run=True,
                ).to_dict()
                if not preview.get('success'):
                    return {'success': False, 'message': f"Commercial validation failed: {preview.get('message')}"}
            except Exception as e:
                return {'success': False, 'message': f'Commercial validation error: {str(e)}'}

            # Save sales return header
            sales_return_id = self.db.insert_sales_return(company_id, sales_return_data)

            # Save items
            items = sales_return_data.get('items', [])
            for item in items:
                self.db.insert_sales_return_item(sales_return_id, item)

            # Use VoucherPostingEngine to post ledger and stock entries
            try:
                from .voucher_posting_engine import VoucherPostingEngine
                engine = VoucherPostingEngine(self.db)
                post_result = engine.repost_voucher_from_db(
                    company_id, "sales_return", sales_return_id,
                    apply_stock=True, dry_run=False
                )
                if not post_result['success']:
                    return {
                        'success': False,
                        'message': f'Voucher posting failed: {post_result["message"]}'
                    }
            except Exception as e:
                return {
                    'success': False,
                    'message': f'Voucher posting error: {str(e)}'
                }

            return {
                "success": True,
                "message": "Sales return saved successfully",
                "sales_return_id": sales_return_id
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to save sales return: {str(e)}"
            }

    def update_sales_return(self, sales_return_id: int, sales_return_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing sales return.

        Returns:
            Dict with success status and message
        """
        try:
            company_id = sales_return_data['company_id']

            # Get existing sales return
            existing = self.get_sales_return_by_id(company_id, sales_return_id)

            items = sales_return_data.get('items', [])
            # Commercial calculation/posting validation BEFORE any DB mutation.
            try:
                from .voucher_posting_engine import VoucherPostingEngine
                preview_engine = VoucherPostingEngine(self.db)
                preview = preview_engine.repost_voucher(
                    company_id=company_id,
                    voucher_type="sales_return",
                    voucher_id=sales_return_id,
                    header=sales_return_data,
                    items=items,
                    apply_stock=False,
                    dry_run=True,
                ).to_dict()
                if not preview.get('success'):
                    return {'success': False, 'message': f"Commercial validation failed: {preview.get('message')}"}
            except Exception as e:
                return {'success': False, 'message': f'Commercial validation error: {str(e)}'}

            # Get existing sales return
            existing = self.get_sales_return_by_id(company_id, sales_return_id)
            if not existing['success']:
                return existing

            # Delete old items
            self.db.delete_sales_return_items(sales_return_id)

            # Update header
            self.db.update_sales_return(sales_return_id, sales_return_data)

            # Save new items
            items = sales_return_data.get('items', [])
            for item in items:
                self.db.insert_sales_return_item(sales_return_id, item)

            # Use VoucherPostingEngine to repost ledger and stock entries
            try:
                from .voucher_posting_engine import VoucherPostingEngine
                engine = VoucherPostingEngine(self.db)
                post_result = engine.repost_voucher_from_db(
                    company_id, "sales_return", sales_return_id,
                    apply_stock=True, dry_run=False
                )
                if not post_result['success']:
                    return {
                        'success': False,
                        'message': f'Voucher posting failed: {post_result["message"]}'
                    }
            except Exception as e:
                return {
                    'success': False,
                    'message': f'Voucher posting error: {str(e)}'
                }

            return {
                "success": True,
                "message": "Sales return updated successfully"
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to update sales return: {str(e)}"
            }

    def delete_sales_return(self, company_id: int, sales_return_id: int) -> Dict[str, Any]:
        """
        Delete a sales return.

        Returns:
            Dict with success status and message
        """
        conn = self.db.connect()
        try:
            conn.execute("BEGIN")
            cursor = conn.cursor()

            # Use VoucherPostingEngine to clean up ledger and stock entries
            try:
                from .voucher_posting_engine import VoucherPostingEngine
                engine = VoucherPostingEngine(self.db)
                delete_result = engine.delete_voucher_postings(company_id, "sales_return", sales_return_id)
                if not delete_result['success']:
                    return {
                        'success': False,
                        'message': f'Voucher deletion failed: {delete_result["message"]}'
                    }
            except Exception as e:
                return {
                    'success': False,
                    'message': f'Voucher deletion error: {str(e)}'
                }

            # Delete items (cascade handles, but explicit for safety)
            self.db.delete_sales_return_items(sales_return_id)

            # Delete header
            self.db.delete_sales_return(sales_return_id)

            conn.commit()
            return {
                "success": True,
                "message": "Sales return deleted successfully"
            }

        except Exception as e:
            conn.rollback()
            return {
                "success": False,
                "message": f"Failed to delete sales return: {str(e)}"
            }
        finally:
            self.db.disconnect()

    def get_next_return_no(self, company_id: int) -> str:
        """
        Get next return number for a company.

        Returns:
            Next return number as string
        """
        try:
            from bizora_core.invoice_numbering import get_next_voucher_number

            return get_next_voucher_number(self.db, company_id, "sales_return")
        except Exception:
            return "001"
