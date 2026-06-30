"""
Purchase Logic Module
Handles purchase business logic and validation.
"""

import sqlite3
from contextlib import closing, contextmanager
from typing import Dict, Any, List, Optional
from db import DB_PATH
from .audit_logic import log_action
from .stock_logic import StockLogic
from bizora_core.common_finance import to_decimal, money_round, is_balanced, safe_add, safe_subtract


def _attempt_supabase_purchase_sync(
    company_id: int,
    purchase_data: Dict[str, Any],
    purchase_id: Optional[int],
) -> None:
    """Push a saved purchase to Supabase without affecting the local transaction."""
    try:
        from sync_service import sync_purchase_after_save

        sync_purchase_after_save(company_id, purchase_data, purchase_id)
    except Exception as sync_error:
        print(f"Supabase sync error (local save retained): {sync_error}")


class PurchaseLogic:
    """Business logic for purchase operations."""

    def __init__(self, db):
        """Initialize purchase logic with database instance."""
        self.db = db
        self.stock_logic = StockLogic(db)
        self.ledger_logic = None  # Lazy load ledger_logic when needed

    def _get_ledger_logic(self):
        """Lazy load ledger_logic."""
        if self.ledger_logic is None:
            from .ledger_logic import LedgerLogic
            self.ledger_logic = LedgerLogic(self.db)
        return self.ledger_logic

    def _is_cash_purchase_type(self, purchase_type: Any) -> bool:
        """Return True when the purchase is a cash transaction."""
        return "cash" in str(purchase_type or "").strip().casefold()

    def _normalise_party_id(self, party_id: Any) -> Optional[int]:
        """Convert a selected party id to a positive integer, or None if blank."""
        try:
            if party_id is None:
                return None
            party_id_text = str(party_id).strip()
            if not party_id_text:
                return None
            normalised_id = int(party_id_text)
            return normalised_id if normalised_id > 0 else None
        except (TypeError, ValueError):
            return None

    def _get_party_by_id(self, company_id: int, party_id: int) -> Optional[Dict[str, Any]]:
        """Return a party row only when the party belongs to the company."""
        try:
            return self.db.get_party_by_id(company_id, party_id)
        except Exception as exc:
            print(f"Error checking purchase party: {exc}")
            return None

    def _find_party_by_name(self, company_id: int, party_name: str) -> Optional[Dict[str, Any]]:
        """Find a party by exact name using portable SQL functions."""
        try:
            ph = self.db._get_placeholder()
            query = f"""
                SELECT id, name, party_type
                FROM parties
                WHERE company_id = {ph}
                  AND LOWER(TRIM(name)) = LOWER(TRIM({ph}))
                ORDER BY id
            """
            rows = self.db.execute_query(query, (company_id, party_name)) or []
            return rows[0] if rows else None
        except Exception as exc:
            print(f"Error finding cash supplier party: {exc}")
            return None

    def _ensure_party_ledger_account(self, company_id: int, party_id: int,
                                     party_name: str, party_type: str) -> None:
        """Ensure the fallback party has a linked creditor ledger account."""
        try:
            ledger_logic = self._get_ledger_logic()
            if hasattr(ledger_logic, "ensure_system_accounts"):
                ledger_logic.ensure_system_accounts(company_id)
            if hasattr(ledger_logic, "get_or_create_party_account"):
                ledger_logic.get_or_create_party_account(
                    company_id,
                    party_id,
                    party_name,
                    party_type,
                    0.0,
                    "Cr",
                )
        except Exception as exc:
            print(f"Warning: Cash supplier ledger creation failed: {exc}")

    def _get_or_create_cash_supplier_party_id(self, company_id: int) -> Optional[int]:
        """Return a valid parties.id for cash purchases without a supplier."""
        candidate_names = ("Cash Supplier", "Cash Purchase Return Supplier")
        first_missing_name = None
        for party_name in candidate_names:
            party = self._find_party_by_name(company_id, party_name)
            if not party:
                if first_missing_name is None:
                    first_missing_name = party_name
                continue
            party_type = str(party.get("party_type") or "").strip()
            if party_type in ("Creditor", "Both"):
                party_id = self._normalise_party_id(party.get("id"))
                if party_id:
                    self._ensure_party_ledger_account(
                        company_id, party_id, party.get("name") or party_name, party_type
                    )
                    return party_id

        create_name = first_missing_name or candidate_names[-1]
        party_data = {
            "name": create_name,
            "party_type": "Creditor",
            "opening_balance": 0.0,
            "notes": "System fallback for cash purchases without a supplier.",
        }
        try:
            party_id = self.db.insert_party(company_id, party_data)
            if not party_id:
                party = self._find_party_by_name(company_id, create_name)
                party_id = self._normalise_party_id(party.get("id")) if party else None
            if party_id:
                self._ensure_party_ledger_account(
                    company_id, party_id, create_name, "Creditor"
                )
                return party_id
        except Exception as exc:
            print(f"Error creating cash supplier party: {exc}")
            return None
        return None

    def resolve_purchase_party_id(self, company_id: int,
                                  purchase_data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure purchase payload has a parties.id-safe party_id before saving."""
        if not company_id:
            return {"success": False, "message": "Missing required field: company_id"}

        purchase_type = purchase_data.get("purchase_type", "Cash")
        party_id = self._normalise_party_id(purchase_data.get("party_id"))
        if party_id:
            party = self._get_party_by_id(company_id, party_id)
            if party:
                purchase_data["party_id"] = party_id
                return {"success": True, "party_id": party_id, "message": "Party resolved."}
            if not self._is_cash_purchase_type(purchase_type):
                return {
                    "success": False,
                    "message": "Selected supplier was not found. Please select the supplier again.",
                }

        if self._is_cash_purchase_type(purchase_type):
            cash_party_id = self._get_or_create_cash_supplier_party_id(company_id)
            if cash_party_id:
                purchase_data["party_id"] = cash_party_id
                return {
                    "success": True,
                    "party_id": cash_party_id,
                    "message": "Cash Supplier resolved for cash purchase.",
                }
            return {
                "success": False,
                "message": "Cash purchase requires a valid Cash Supplier party. Please create one and try again.",
            }

        return {
            "success": False,
            "message": "Credit purchase requires a supplier. Please select a supplier first.",
        }

    def get_purchases(self, company_id: int) -> Dict[str, Any]:
        """
        Get all purchases for a company.

        Returns:
            Dict with success status, message, and data
        """
        try:
            purchases = self.db.get_purchases_by_company(company_id)
            return {
                "success": True,
                "message": "Purchases retrieved successfully",
                "data": purchases
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve purchases: {str(e)}",
                "data": []
            }

    def get_purchase_by_id(self, company_id: int, purchase_id: int) -> Dict[str, Any]:
        """
        Get a specific purchase by ID.

        Returns:
            Dict with success status, message, and data
        """
        try:
            purchase = self.db.get_purchase_by_id(company_id, purchase_id)
            if purchase:
                return {
                    "success": True,
                    "message": "Purchase retrieved successfully",
                    "data": purchase
                }
            else:
                return {
                    "success": False,
                    "message": "Purchase not found",
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve purchase: {str(e)}",
                "data": None
            }

    def get_purchase_items(self, purchase_id: int) -> Dict[str, Any]:
        """
        Get all items for a specific purchase.

        Returns:
            Dict with success status, message, and data
        """
        try:
            items = self.db.get_purchase_items(purchase_id)
            return {
                "success": True,
                "message": "Purchase items retrieved successfully",
                "data": items
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve purchase items: {str(e)}",
                "data": []
            }

    def validate_purchase_data(self, purchase_data: Dict[str, Any],
                               current_purchase_id: Optional[int] = None,
                               company_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Validate purchase data.

        Returns:
            Dict with success status and message
        """
        # Check required fields
        if not purchase_data.get('purchase_number', '').strip():
            return {
                "success": False,
                "message": "Purchase Number is required"
            }

        if not purchase_data.get('purchase_date', '').strip():
            return {
                "success": False,
                "message": "Purchase Date is required"
            }

        purchase_type = str(purchase_data.get('purchase_type', 'Cash')).strip()
        party_id = self._normalise_party_id(purchase_data.get('party_id'))
        if purchase_type == 'Credit' and not party_id:
            return {
                "success": False,
                "message": "Credit purchase requires a supplier/creditor"
            }
        if not party_id:
            return {
                "success": False,
                "message": "Purchase requires a valid supplier party"
            }
        if company_id and not self._get_party_by_id(company_id, party_id):
            return {
                "success": False,
                "message": "Selected supplier was not found. Please select the supplier again."
            }
        purchase_data['party_id'] = party_id

        # Check for duplicate purchase number if company_id is provided
        if company_id:
            exists = self.db.purchase_number_exists(company_id, purchase_data['purchase_number'].strip(), current_purchase_id)
            if exists:
                return {
                    "success": False,
                    "message": "Purchase Number already exists"
                }

        return {
            "success": True,
            "message": "Purchase data is valid"
        }

    def normalize_purchase_data(self, purchase_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize purchase data by trimming and converting types.

        Returns:
            Normalized purchase data
        """
        return {
            'purchase_number': str(purchase_data.get('purchase_number', '')).strip(),
            'purchase_date': str(purchase_data.get('purchase_date', '')).strip(),
            'party_id': int(purchase_data.get('party_id', 0)),
            'purchase_type': str(purchase_data.get('purchase_type', 'Cash')).strip(),
            'bill_series': str(purchase_data.get('bill_series', '')).strip(),
            'nature': str(purchase_data.get('nature', '')).strip(),
            'due_date': str(purchase_data.get('due_date', '')).strip() if purchase_data.get('due_date') else None,
            'address': str(purchase_data.get('address', '')).strip(),
            'gstin': str(purchase_data.get('gstin', '')).strip().upper(),
            'state': str(purchase_data.get('state', '')).strip(),
            'supplier_invoice_no': str(purchase_data.get('supplier_invoice_no', '')).strip(),
            'narration': str(purchase_data.get('narration', '')).strip(),
            'sub_total': float(money_round(to_decimal(purchase_data.get('sub_total', 0.0)))),
            'discount_total': float(money_round(to_decimal(purchase_data.get('discount_total', 0.0)))),
            'tax_total': float(money_round(to_decimal(purchase_data.get('tax_total', 0.0)))),
            'freight': float(money_round(to_decimal(purchase_data.get('freight', 0.0)))),
            'round_off': float(money_round(to_decimal(purchase_data.get('round_off', 0.0)))),
            'purchase_expense': float(money_round(to_decimal(purchase_data.get('purchase_expense', 0.0)))),
            'grand_total': float(money_round(to_decimal(purchase_data.get('grand_total', 0.0)))),
            'amount_paid': float(money_round(to_decimal(purchase_data.get('amount_paid', 0.0))))
        }

    @contextmanager
    def _open_purchase_write_connection(self):
        """Yield a fresh SQLite connection for the Purchase Entry write transaction."""
        db_path = getattr(self.db, 'db_path', None) or DB_PATH
        with closing(sqlite3.connect(db_path, timeout=30.0)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("PRAGMA journal_mode = WAL")
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

    def save_purchase(self, company_id: int, purchase_data: Dict[str, Any],
                     purchase_items: List[Dict[str, Any]],
                     current_purchase_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Save a purchase (create or update).

        Args:
            company_id: Company ID
            purchase_data: Dictionary containing purchase header information
            purchase_items: List of dictionaries containing purchase item information
            current_purchase_id: Purchase ID (None for create, ID for update)

        Returns:
            Dictionary with operation result
        """
        # Resolve cash purchases without a selected supplier to a real parties.id
        # because purchases.party_id is a NOT NULL foreign key to parties.id.
        party_resolution = self.resolve_purchase_party_id(company_id, purchase_data)
        if not party_resolution['success']:
            return {
                'success': False,
                'message': party_resolution['message'],
                'errors': None,
                'data': None
            }

        # Validate purchase data
        validation = self.validate_purchase_data(purchase_data, current_purchase_id, company_id)
        if not validation['success']:
            return {
                'success': False,
                'message': validation['message'],
                'errors': None,
                'data': None
            }

        # Normalize purchase data
        normalized_data = self.normalize_purchase_data(purchase_data)

        # Commercial calculation/posting validation BEFORE any DB mutation.
        try:
            from .voucher_posting_engine import VoucherPostingEngine
            preview_engine = VoucherPostingEngine(self.db)
            preview = preview_engine.repost_voucher(
                company_id=company_id,
                voucher_type="purchase",
                voucher_id=current_purchase_id or 0,
                header=normalized_data,
                items=purchase_items,
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
            with self._open_purchase_write_connection() as conn:
                with closing(conn.cursor()) as cursor:
                    conn.execute("BEGIN")

                    if current_purchase_id:
                        # ---------- UPDATE EXISTING PURCHASE ----------
                        self.db.update_purchase(
                            company_id, current_purchase_id, normalized_data, conn=conn, cursor=cursor
                        )

                        # Replace items before reposting stock and ledger entries.
                        self.db.delete_purchase_items_by_purchase(current_purchase_id, conn=conn, cursor=cursor)
                        for item_data in purchase_items:
                            self.db.insert_purchase_item(current_purchase_id, item_data, conn=conn, cursor=cursor)

                        from .voucher_posting_engine import VoucherPostingEngine
                        engine = VoucherPostingEngine(self.db)
                        post_result = engine.repost_voucher(
                            company_id=company_id,
                            voucher_type="purchase",
                            voucher_id=current_purchase_id,
                            header=normalized_data,
                            items=purchase_items,
                            apply_stock=True,
                            dry_run=False,
                            conn=conn,
                            cursor=cursor,
                            commit=False,
                        )
                        if not post_result.success:
                            raise Exception(f'Voucher posting failed: {post_result.message}')
                        if not log_action(
                            company_id,
                            None,
                            'Purchase',
                            'UPDATE',
                            normalized_data['purchase_number'],
                            f"Updated Purchase Voucher for {normalized_data['grand_total']}",
                            conn=conn,
                        ):
                            raise Exception('Audit logging failed')

                        conn.commit()
                        from ui.dashboard_refresh import request_dashboard_refresh
                        request_dashboard_refresh()
                        _attempt_supabase_purchase_sync(
                            company_id,
                            normalized_data,
                            current_purchase_id,
                        )
                        return {
                            'success': True,
                            'message': 'Purchase updated successfully',
                            'errors': None,
                            'data': {'purchase_id': current_purchase_id}
                        }

                    # ---------- CREATE NEW PURCHASE ----------
                    purchase_id = self.db.save_purchase(
                        company_id, normalized_data, purchase_items, conn=conn, cursor=cursor
                    )
                    if not purchase_id:
                        raise Exception("Failed to save purchase header/items")

                    from .voucher_posting_engine import VoucherPostingEngine
                    engine = VoucherPostingEngine(self.db)
                    post_result = engine.repost_voucher(
                        company_id=company_id,
                        voucher_type="purchase",
                        voucher_id=purchase_id,
                        header=normalized_data,
                        items=purchase_items,
                        apply_stock=True,
                        dry_run=False,
                        conn=conn,
                        cursor=cursor,
                        commit=False,
                    )
                    if not post_result.success:
                        raise Exception(f'Voucher posting failed: {post_result.message}')

                    if not log_action(
                        company_id,
                        None,
                        'Purchase',
                        'CREATE',
                        normalized_data['purchase_number'],
                        f"Created Purchase Voucher for {normalized_data['grand_total']}",
                        conn=conn,
                    ):
                        raise Exception('Audit logging failed')

                    conn.commit()
                    from ui.dashboard_refresh import request_dashboard_refresh
                    request_dashboard_refresh()
                    _attempt_supabase_purchase_sync(
                        company_id,
                        normalized_data,
                        purchase_id,
                    )
                    return {
                        'success': True,
                        'message': 'Purchase saved successfully',
                        'errors': None,
                        'data': {'purchase_id': purchase_id}
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

    def delete_purchase(self, company_id: int, purchase_id: int) -> Dict[str, Any]:
        """
        Delete a purchase.

        Args:
            company_id: Company ID
            purchase_id: Purchase ID

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
                SELECT purchase_number, grand_total
                FROM purchases
                WHERE id = {ph} AND company_id = {ph}
                """,
                (purchase_id, company_id),
            )
            purchase_row = cursor.fetchone()
            old_voucher_no = str(purchase_id)
            old_grand_total = 0.0
            if purchase_row:
                if hasattr(purchase_row, "keys"):
                    old_voucher_no = purchase_row["purchase_number"]
                    old_grand_total = purchase_row["grand_total"] or 0.0
                else:
                    old_voucher_no = purchase_row[0]
                    old_grand_total = purchase_row[1] or 0.0

            # Use VoucherPostingEngine to clean up ledger and stock entries
            try:
                from .voucher_posting_engine import VoucherPostingEngine
                engine = VoucherPostingEngine(self.db)
                delete_result = engine.delete_voucher_postings(
                    company_id, "purchase", purchase_id, conn=conn, commit=False
                )
                if not delete_result['success']:
                    raise Exception(f'Voucher deletion failed: {delete_result["message"]}')
            except Exception as e:
                raise Exception(f'Voucher deletion error: {str(e)}')

            # Delete purchase header (cascade deletes purchase_items)
            success = self.db.delete_purchase(company_id, purchase_id, conn=conn, cursor=cursor)

            if success:
                if not log_action(
                    company_id,
                    None,
                    'Purchase',
                    'DELETE',
                    old_voucher_no,
                    f"Deleted Purchase Voucher for {old_grand_total}",
                    conn=conn,
                ):
                    raise Exception('Audit logging failed')
                conn.commit()
                return {
                    'success': True,
                    'message': 'Purchase deleted successfully'
                }
            else:
                raise Exception('Failed to delete purchase')

        except Exception as e:
            conn.rollback()
            return {
                'success': False,
                'message': f'Transaction failed: {str(e)}'
            }
        finally:
            self.db.disconnect()
