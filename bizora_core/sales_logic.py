"""
Sales Logic Module
Handles sales business logic and validation.
"""

import sqlite3
from contextlib import closing, contextmanager
from typing import Optional, List, Dict, Any
from decimal import Decimal
from db import DB_PATH
from .audit_logic import log_action
from .stock_logic import StockLogic


def _attempt_supabase_sale_sync(
    company_id: int,
    sale_data: Dict[str, Any],
    sale_id: Optional[int],
) -> None:
    """Push a saved sale to Supabase without affecting the local transaction."""
    try:
        from sync_service import sync_sale_after_save

        sync_sale_after_save(company_id, sale_data, sale_id)
    except Exception as sync_error:
        print(f"Supabase sync error (local save retained): {sync_error}")


class SalesLogic:
    """Business logic for sales operations."""

    def __init__(self, db):
        """Initialize sales logic with database instance."""
        self.db = db
        self.stock_logic = StockLogic(db)
        self.ledger_logic = None  # Lazy load ledger_logic when needed

    def _get_ledger_logic(self):
        """Lazy load ledger_logic."""
        if self.ledger_logic is None:
            from .ledger_logic import LedgerLogic
            self.ledger_logic = LedgerLogic(self.db)
        return self.ledger_logic

    def get_sales(self, company_id: int) -> Dict[str, Any]:
        """
        Get all sales for a company.

        Returns:
            Dict with success status, message, and data
        """
        try:
            sales = self.db.get_sales_by_company(company_id)
            return {
                "success": True,
                "message": "Sales retrieved successfully",
                "data": sales
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve sales: {str(e)}",
                "data": []
            }

    def get_sale_by_id(self, company_id: int, sale_id: int) -> Dict[str, Any]:
        """
        Get a specific sale by ID.

        Returns:
            Dict with success status, message, and data
        """
        try:
            sale = self.db.get_sale_by_id(company_id, sale_id)
            if sale:
                return {
                    "success": True,
                    "message": "Sale retrieved successfully",
                    "data": sale
                }
            else:
                return {
                    "success": False,
                    "message": "Sale not found",
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve sale: {str(e)}",
                "data": None
            }

    def get_sale_items(self, sale_id: int) -> Dict[str, Any]:
        """
        Get all items for a specific sale.

        Returns:
            Dict with success status, message, and data
        """
        try:
            items = self.db.get_sale_items(sale_id)
            return {
                "success": True,
                "message": "Sale items retrieved successfully",
                "data": items
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve sale items: {str(e)}",
                "data": []
            }

    def validate_sale_data(self, sale_data: Dict[str, Any], 
                          current_sale_id: Optional[int] = None,
                          company_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Validate sale data.

        Returns:
            Dict with success status and message
        """
        # Check required fields
        if not sale_data.get('invoice_number', '').strip():
            return {
                "success": False,
                "message": "Invoice Number is required"
            }

        if not sale_data.get('invoice_date', '').strip():
            return {
                "success": False,
                "message": "Invoice Date is required"
            }

        if not sale_data.get('party_id'):
            return {
                "success": False,
                "message": "Customer/Party is required"
            }

        # Check for duplicate invoice number if company_id is provided
        if company_id:
            exists = self.db.invoice_number_exists(company_id, sale_data['invoice_number'].strip(), current_sale_id)
            if exists:
                return {
                    "success": False,
                    "message": "Invoice Number already exists"
                }

        return {
            "success": True,
            "message": "Sale data is valid"
        }

    def normalize_sale_data(self, sale_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize sale data by trimming and converting types.

        Returns:
            Normalized sale data
        """
        return {
            'invoice_number': str(sale_data.get('invoice_number', '')).strip(),
            'invoice_date': str(sale_data.get('invoice_date', '')).strip(),
            'party_id': int(sale_data.get('party_id', 0)),
            'sales_type': str(sale_data.get('sales_type', 'Sales')).strip(),
            'bill_series': str(sale_data.get('bill_series', '')).strip(),
            'nature': str(sale_data.get('nature', '')).strip(),
            'due_date': str(sale_data.get('due_date', '')).strip() if sale_data.get('due_date') else None,
            'address': str(sale_data.get('address', '')).strip(),
            'gstin': str(sale_data.get('gstin', '')).strip().upper(),
            'state': str(sale_data.get('state', '')).strip(),
            'sales_rate': str(sale_data.get('sales_rate', 'Exclusive')).strip(),
            'narration': str(sale_data.get('narration', '')).strip(),
            'salesman': str(sale_data.get('salesman', '')).strip() or None,
            'sub_total': float(sale_data.get('sub_total', 0.0)),
            'discount_total': float(sale_data.get('discount_total', 0.0)),
            'tax_total': float(sale_data.get('tax_total', 0.0)),
            'round_off': float(sale_data.get('round_off', 0.0)),
            'grand_total': float(sale_data.get('grand_total', 0.0)),
            'freight': float(sale_data.get('freight', 0.0)),  # CRITICAL FIX: Include freight in normalized data
            'amount_received': float(sale_data.get('amount_received', 0.0)),
            'payment_mode': str(sale_data.get('payment_mode', 'Cash')).strip() or 'Cash',
        }

    @contextmanager
    def _open_sale_write_connection(self):
        """Yield a fresh SQLite connection for the Sales Entry write transaction."""
        db_path = getattr(self.db, 'db_path', None) or DB_PATH
        with closing(sqlite3.connect(db_path, timeout=30.0)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA journal_mode = DELETE")
            conn.execute("PRAGMA synchronous = NORMAL")
            try:
                yield conn
            except sqlite3.Error:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
                raise
            except Exception:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
                raise

    def save_sale(self, company_id: int, sale_data: Dict[str, Any],
                   sale_items: List[Dict[str, Any]],
                   current_sale_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Save a sale (create or update).

        Args:
            company_id: Company ID
            sale_data: Dictionary containing sale header information
            sale_items: List of dictionaries containing sale item information
            current_sale_id: Sale ID (None for create, ID for update)

        Returns:
            Dictionary with operation result
        """
        # Validate sale data
        validation = self.validate_sale_data(sale_data, current_sale_id, company_id)
        if not validation['success']:
            return {
                'success': False,
                'message': validation['message'],
                'errors': None,
                'data': None
            }

        # Normalize sale data
        normalized_data = self.normalize_sale_data(sale_data)

        # Commercial calculation/posting validation BEFORE any DB mutation.
        try:
            from .voucher_posting_engine import VoucherPostingEngine
            preview_engine = VoucherPostingEngine(self.db)
            preview = preview_engine.repost_voucher(
                company_id=company_id,
                voucher_type="sales",
                voucher_id=current_sale_id or 0,
                header=normalized_data,
                items=sale_items,
                apply_stock=False,
                dry_run=True,
            ).to_dict()
            if not preview.get('success'):
                preview_message = str(preview.get('message'))
                if "System Error: Ledger math is unbalanced. Save aborted to protect Trial Balance." in preview_message:
                    preview_message = "System Error: Ledger math is unbalanced. Save aborted to protect Trial Balance."
                else:
                    preview_message = f"Commercial validation failed: {preview.get('message')}"
                return {
                    'success': False,
                    'message': preview_message,
                    'errors': preview,
                    'data': None
                }
        except Exception as e:
            return {
                'success': False,
                'message': f'Commercial validation error: {str(e)}',
                'errors': None,
                'data': None
            }

        conn = None
        try:
            with self._open_sale_write_connection() as conn:
                with closing(conn.cursor()) as cursor:
                    conn.execute("BEGIN")
                    saved_sale_id = current_sale_id
                    success_message = 'Sale updated successfully'

                    if current_sale_id:
                        # ---------- UPDATE EXISTING SALE ----------
                        # Remove old sales_items
                        self.db.delete_sale_items_by_sale(current_sale_id, conn=conn, cursor=cursor)

                        # Update the sale header
                        self.db.update_sale(company_id, current_sale_id, normalized_data, conn=conn, cursor=cursor)

                        # Insert new items with historical cost snapshot
                        for item_data in sale_items:
                            # Snapshot historical cost at time of sale using product's purchase_rate
                            product_id = item_data.get('product_id')
                            quantity = float(item_data.get('quantity', 0))
                            cost_price = 0.0
                            if product_id:
                                cursor.execute(
                                    f"""
                                    SELECT purchase_rate
                                    FROM products
                                    WHERE company_id = {self.db._get_placeholder()} AND id = {self.db._get_placeholder()}
                                    """,
                                    (company_id, product_id),
                                )
                                product = cursor.fetchone()
                                if product:
                                    cost_price = float(product['purchase_rate'] or 0.0)
                            cost_value = cost_price * quantity
                            item_data['cost_price'] = cost_price
                            item_data['cost_value'] = cost_value
                            self.db.insert_sale_item(current_sale_id, item_data, conn=conn, cursor=cursor)

                        # Use VoucherPostingEngine to repost ledger and stock entries
                        try:
                            from .voucher_posting_engine import VoucherPostingEngine
                            engine = VoucherPostingEngine(self.db)
                            post_result = engine.repost_voucher(
                                company_id=company_id,
                                voucher_type="sales",
                                voucher_id=current_sale_id,
                                header=normalized_data,
                                items=sale_items,
                                apply_stock=True,
                                dry_run=False,
                                conn=conn,
                                cursor=cursor,
                                commit=False,
                            )
                            if not post_result.success:
                                raise Exception(f'Voucher posting failed: {post_result.message}')
                        except Exception as e:
                            raise Exception(f'Voucher posting error: {str(e)}')

                        if not log_action(
                            company_id,
                            None,
                            'Sales',
                            'UPDATE',
                            normalized_data['invoice_number'],
                            f"Updated Sales Invoice for {normalized_data['grand_total']}",
                            conn=conn,
                            cursor=cursor,
                        ):
                            raise Exception('Audit logging failed')

                    # ---------- CREATE NEW SALE ----------
                    else:
                        sale_id = self.db.insert_sale(company_id, normalized_data, conn=conn, cursor=cursor)
                        if sale_id:
                            saved_sale_id = sale_id
                            success_message = 'Sale saved successfully'
                            # Insert new items with historical cost snapshot
                            for item_data in sale_items:
                                # Snapshot historical cost at time of sale using product's purchase_rate
                                product_id = item_data.get('product_id')
                                quantity = float(item_data.get('quantity', 0))
                                cost_price = 0.0
                                if product_id:
                                    cursor.execute(
                                        f"""
                                        SELECT purchase_rate
                                        FROM products
                                        WHERE company_id = {self.db._get_placeholder()} AND id = {self.db._get_placeholder()}
                                        """,
                                        (company_id, product_id),
                                    )
                                    product = cursor.fetchone()
                                    if product:
                                        cost_price = float(product['purchase_rate'] or 0.0)
                                cost_value = cost_price * quantity
                                item_data['cost_price'] = cost_price
                                item_data['cost_value'] = cost_value
                                self.db.insert_sale_item(sale_id, item_data, conn=conn, cursor=cursor)

                            # Use VoucherPostingEngine to post ledger and stock entries
                            try:
                                from .voucher_posting_engine import VoucherPostingEngine
                                engine = VoucherPostingEngine(self.db)
                                post_result = engine.repost_voucher(
                                    company_id=company_id,
                                    voucher_type="sales",
                                    voucher_id=sale_id,
                                    header=normalized_data,
                                    items=sale_items,
                                    apply_stock=True,
                                    dry_run=False,
                                    conn=conn,
                                    cursor=cursor,
                                    commit=False,
                                )
                                if not post_result.success:
                                    raise Exception(f'Voucher posting failed: {post_result.message}')
                            except Exception as e:
                                raise Exception(f'Voucher posting error: {str(e)}')

                            if not log_action(
                                company_id,
                                None,
                                'Sales',
                                'CREATE',
                                normalized_data['invoice_number'],
                                f"Created Sales Invoice for {normalized_data['grand_total']}",
                                conn=conn,
                                cursor=cursor,
                            ):
                                raise Exception('Audit logging failed')

                        else:
                            if conn is not None:
                                conn.rollback()
                            return {
                                'success': False,
                                'message': 'Transaction failed: Failed to save sale',
                                'errors': None,
                                'data': None
                            }

                    conn.commit()
                    from ui.dashboard_refresh import request_dashboard_refresh
                    request_dashboard_refresh()
                    _attempt_supabase_sale_sync(company_id, normalized_data, saved_sale_id)
                    return {
                        'success': True,
                        'message': success_message,
                        'errors': None,
                        'data': {'sale_id': saved_sale_id}
                    }

        except sqlite3.Error:
            if conn is not None:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
            raise
        except Exception as e:
            if conn is not None:
                try:
                    conn.rollback()
                except sqlite3.Error:
                    pass
            error_message = str(e)
            if "System Error: Ledger math is unbalanced. Save aborted to protect Trial Balance." in error_message:
                error_message = "System Error: Ledger math is unbalanced. Save aborted to protect Trial Balance."
            else:
                error_message = f'Transaction failed: {error_message}'
            return {
                'success': False,
                'message': error_message,
                'errors': None,
                'data': None
            }

    def delete_sale(self, company_id: int, sale_id: int) -> Dict[str, Any]:
        """
        Delete a sale.

        Args:
            company_id: Company ID
            sale_id: Sale ID

        Returns:
            Dictionary with operation result
        """
        conn = self.db.connect()
        try:
            conn.execute("BEGIN")
            cursor = conn.cursor()
            ph = self.db._get_placeholder()
            cursor.execute(
                f"""
                SELECT invoice_number, grand_total
                FROM sales
                WHERE id = {ph} AND company_id = {ph}
                """,
                (sale_id, company_id),
            )
            sale_row = cursor.fetchone()
            old_voucher_no = str(sale_id)
            old_grand_total = 0.0
            if sale_row:
                if hasattr(sale_row, "keys"):
                    old_voucher_no = sale_row["invoice_number"]
                    old_grand_total = sale_row["grand_total"] or 0.0
                else:
                    old_voucher_no = sale_row[0]
                    old_grand_total = sale_row[1] or 0.0

            # Use VoucherPostingEngine to clean up ledger and stock entries
            try:
                from .voucher_posting_engine import VoucherPostingEngine
                engine = VoucherPostingEngine(self.db)
                delete_result = engine.delete_voucher_postings(
                    company_id, "sales", sale_id, conn=conn, commit=False
                )
                if not delete_result['success']:
                    raise Exception(f'Voucher deletion failed: {delete_result["message"]}')
            except Exception as e:
                raise Exception(f'Voucher deletion error: {str(e)}')

            # Delete sale header (cascade will delete sale_items)
            query = f"DELETE FROM sales WHERE id = {ph} AND company_id = {ph}"
            cursor.execute(query, (sale_id, company_id))
            success = cursor.rowcount != 0

            if success:
                if not log_action(
                    company_id,
                    None,
                    'Sales',
                    'DELETE',
                    old_voucher_no,
                    f"Deleted Sales Invoice for {old_grand_total}",
                    conn=conn,
                ):
                    raise Exception('Audit logging failed')
                conn.commit()
                return {
                    'success': True,
                    'message': 'Sale deleted successfully'
                }
            else:
                raise Exception('Failed to delete sale')

        except Exception as e:
            conn.rollback()
            return {
                'success': False,
                'message': f'Transaction failed: {str(e)}'
            }
        finally:
            self.db.disconnect()
