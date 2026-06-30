"""
Purchase Return Logic Module
Handles purchase return business logic and validation.
"""

from typing import Dict, Any, List, Optional
from .stock_logic import StockLogic
from bizora_core.common_finance import to_decimal, money_round, is_balanced, safe_add, safe_subtract


class PurchaseReturnLogic:
    """Business logic for purchase return operations."""

    def __init__(self, db):
        """Initialize purchase return logic with database instance."""
        self.db = db
        self.stock_logic = StockLogic(db)
        self.ledger_logic = None

    def _get_ledger_logic(self):
        """Lazy load ledger_logic."""
        if self.ledger_logic is None:
            from .ledger_logic import LedgerLogic
            self.ledger_logic = LedgerLogic(self.db)
        return self.ledger_logic

    def _is_cash_return_type(self, return_type: Any) -> bool:
        """Return True when the purchase return is a cash transaction."""
        return "cash" in str(return_type or "").strip().casefold()

    def _normalise_party_id(self, party_id: Any) -> Optional[int]:
        """Convert a selected party/account id to an integer, or None if blank."""
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

    def _normalise_positive_int(self, value: Any) -> Optional[int]:
        """Return a positive integer value, or None when the input is blank."""
        return self._normalise_party_id(value)

    def _get_party_by_id(self, company_id: int, party_id: int) -> Optional[Dict[str, Any]]:
        """Return a party row only when the party belongs to the company."""
        try:
            return self.db.get_party_by_id(company_id, party_id)
        except Exception as exc:
            print(f"Error checking purchase return party: {exc}")
            return None

    def _get_product_by_id(self, company_id: int, product_id: int) -> Optional[Dict[str, Any]]:
        """Return a product row only when the product belongs to the company."""
        try:
            return self.db.get_product_by_id(company_id, product_id)
        except Exception as exc:
            print(f"Error checking purchase return product: {exc}")
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
        """Ensure the fallback party has a linked ledger account for posting."""
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
        """Return a valid parties.id for cash purchase returns without a supplier."""
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
            "notes": "System fallback for cash purchase returns without a supplier.",
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

    def resolve_purchase_return_party_id(self, purchase_return_data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure purchase return payload has a parties.id-safe party_id before saving."""
        company_id = purchase_return_data.get("company_id")
        if not company_id:
            return {"success": False, "message": "Missing required field: company_id"}

        return_type = purchase_return_data.get("return_type", "Cash")
        party_id = self._normalise_party_id(purchase_return_data.get("party_id"))
        if party_id:
            party = self._get_party_by_id(company_id, party_id)
            if party:
                purchase_return_data["party_id"] = party_id
                return {"success": True, "party_id": party_id, "message": "Party resolved."}
            if not self._is_cash_return_type(return_type):
                return {
                    "success": False,
                    "message": "Selected supplier was not found. Please select the supplier again.",
                }

        if self._is_cash_return_type(return_type):
            cash_party_id = self._get_or_create_cash_supplier_party_id(company_id)
            if cash_party_id:
                purchase_return_data["party_id"] = cash_party_id
                return {
                    "success": True,
                    "party_id": cash_party_id,
                    "message": "Cash Supplier resolved for cash purchase return.",
                }
            return {
                "success": False,
                "message": "Cash return requires a valid Cash Supplier party. Please create one and try again.",
            }

        return {
            "success": False,
            "message": "Credit return requires a supplier. Please select a supplier first.",
        }

    def get_purchase_returns(self, company_id: int) -> Dict[str, Any]:
        """
        Get all purchase returns for a company.

        Returns:
            Dict with success status, message, and data
        """
        try:
            purchase_returns = self.db.get_purchase_returns_by_company(company_id)
            return {
                "success": True,
                "message": "Purchase returns retrieved successfully",
                "data": purchase_returns
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve purchase returns: {str(e)}",
                "data": []
            }

    def get_purchase_return_by_id(self, company_id: int, purchase_return_id: int) -> Dict[str, Any]:
        """
        Get a specific purchase return by ID.

        Returns:
            Dict with success status, message, and data
        """
        try:
            purchase_return = self.db.get_purchase_return_by_id(company_id, purchase_return_id)
            if purchase_return:
                return {
                    "success": True,
                    "message": "Purchase return retrieved successfully",
                    "data": purchase_return
                }
            else:
                return {
                    "success": False,
                    "message": "Purchase return not found",
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve purchase return: {str(e)}",
                "data": None
            }

    def get_purchase_return_items(self, purchase_return_id: int) -> Dict[str, Any]:
        """
        Get all items for a specific purchase return.

        Returns:
            Dict with success status, message, and data
        """
        try:
            items = self.db.get_purchase_return_items(purchase_return_id)
            return {
                "success": True,
                "message": "Purchase return items retrieved successfully",
                "data": items
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve purchase return items: {str(e)}",
                "data": []
            }

    def validate_purchase_return_data(self, purchase_return_data: Dict[str, Any],
                                      current_purchase_return_id: Optional[int] = None) -> Dict[str, Any]:
        """Validate purchase return data and foreign-key-sensitive payload values."""
        company_id = purchase_return_data.get('company_id')
        if not company_id:
            return {"success": False, "message": "Missing required field: company_id"}

        return_no = purchase_return_data.get('return_no', '').strip()
        if not return_no:
            return {"success": False, "message": "Missing required field: return_no"}

        if not purchase_return_data.get('return_date'):
            return {"success": False, "message": "Missing required field: return_date"}

        return_type = str(purchase_return_data.get('return_type', 'Cash')).strip()
        party_id = self._normalise_party_id(purchase_return_data.get('party_id'))
        if return_type == 'Credit' and not party_id:
            return {"success": False, "message": "Credit return requires a party (creditor)."}
        if not party_id:
            return {"success": False, "message": "Purchase return requires a valid supplier party."}
        if not self._get_party_by_id(company_id, party_id):
            return {
                "success": False,
                "message": "Selected supplier was not found. Please select the supplier again.",
            }
        purchase_return_data['party_id'] = party_id

        items = purchase_return_data.get('items', [])
        if not items:
            return {"success": False, "message": "Purchase return must have at least one item."}

        for idx, item in enumerate(items):
            product_id = self._normalise_positive_int(item.get('product_id'))
            if not product_id:
                return {"success": False, "message": f"Item {idx + 1}: Missing product."}
            if not self._get_product_by_id(company_id, product_id):
                return {
                    "success": False,
                    "message": f"Item {idx + 1}: Selected product was not found. Please add the product again.",
                }
            item['product_id'] = product_id
            try:
                quantity = float(money_round(to_decimal(item.get('quantity', 0))))
            except (TypeError, ValueError):
                quantity = 0.0
            if quantity <= 0:
                return {"success": False, "message": f"Item {idx + 1}: Quantity must be > 0."}

        # Uniqueness check only on new save
        if current_purchase_return_id is None:
            existing = self.db.get_purchase_return_by_return_no(company_id, return_no)
            if existing:
                return {"success": False, "message": f"Return No '{return_no}' already exists."}

        return {"success": True, "message": "Valid"}

    def save_purchase_return(self, purchase_return_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a new purchase return with items and stock movements."""
        try:
            party_resolution = self.resolve_purchase_return_party_id(purchase_return_data)
            if not party_resolution['success']:
                return party_resolution

            validation = self.validate_purchase_return_data(purchase_return_data)
            if not validation['success']:
                return validation

            company_id = purchase_return_data['company_id']

            # Save header
            items = purchase_return_data.get('items', [])

            # Commercial calculation/posting validation BEFORE any DB mutation.
            try:
                from .voucher_posting_engine import VoucherPostingEngine
                preview_engine = VoucherPostingEngine(self.db)
                preview = preview_engine.repost_voucher(
                    company_id=company_id,
                    voucher_type="purchase_return",
                    voucher_id=0,
                    header=purchase_return_data,
                    items=items,
                    apply_stock=False,
                    dry_run=True,
                ).to_dict()
                if not preview.get('success'):
                    return {'success': False, 'message': f"Commercial validation failed: {preview.get('message')}"}
            except Exception as e:
                return {'success': False, 'message': f'Commercial validation error: {str(e)}'}

            # Save header
            purchase_return_id = self.db.insert_purchase_return(company_id, purchase_return_data)
            if not purchase_return_id:
                return {"success": False, "message": "Failed to insert purchase return header."}

            # Save items
            items = purchase_return_data.get('items', [])
            for item in items:
                self.db.insert_purchase_return_item(purchase_return_id, item)

            # Use VoucherPostingEngine to post ledger and stock entries
            try:
                from .voucher_posting_engine import VoucherPostingEngine
                engine = VoucherPostingEngine(self.db)
                post_result = engine.repost_voucher_from_db(
                    company_id, "purchase_return", purchase_return_id,
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
                "message": "Purchase return saved successfully",
                "purchase_return_id": purchase_return_id
            }

        except Exception as e:
            return {"success": False, "message": f"Failed to save purchase return: {str(e)}"}

    def update_purchase_return(self, purchase_return_id: int, purchase_return_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing purchase return - replace items and stock movements."""
        try:
            company_id = purchase_return_data['company_id']

            party_resolution = self.resolve_purchase_return_party_id(purchase_return_data)
            if not party_resolution['success']:
                return party_resolution

            validation = self.validate_purchase_return_data(
                purchase_return_data, current_purchase_return_id=purchase_return_id
            )
            if not validation['success']:
                return validation

            # Update header

            new_items = purchase_return_data.get('items', [])
            # Commercial calculation/posting validation BEFORE any DB mutation.
            try:
                from .voucher_posting_engine import VoucherPostingEngine
                preview_engine = VoucherPostingEngine(self.db)
                preview = preview_engine.repost_voucher(
                    company_id=company_id,
                    voucher_type="purchase_return",
                    voucher_id=purchase_return_id,
                    header=purchase_return_data,
                    items=new_items,
                    apply_stock=False,
                    dry_run=True,
                ).to_dict()
                if not preview.get('success'):
                    return {'success': False, 'message': f"Commercial validation failed: {preview.get('message')}"}
            except Exception as e:
                return {'success': False, 'message': f'Commercial validation error: {str(e)}'}

            # Update header
            self.db.update_purchase_return(purchase_return_id, purchase_return_data)

            # Replace items
            new_items = purchase_return_data.get('items', [])
            self.db.delete_purchase_return_items(purchase_return_id)
            for item in new_items:
                self.db.insert_purchase_return_item(purchase_return_id, item)

            # Use VoucherPostingEngine to repost ledger and stock entries
            try:
                from .voucher_posting_engine import VoucherPostingEngine
                engine = VoucherPostingEngine(self.db)
                post_result = engine.repost_voucher_from_db(
                    company_id, "purchase_return", purchase_return_id,
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

            return {"success": True, "message": "Purchase return updated successfully"}

        except Exception as e:
            return {"success": False, "message": f"Failed to update purchase return: {str(e)}"}

    def delete_purchase_return(self, company_id: int, purchase_return_id: int) -> Dict[str, Any]:
        """Delete a purchase return and reverse its stock movements."""
        conn = self.db.connect()
        try:
            conn.execute("BEGIN")
            cursor = conn.cursor()

            existing = self.get_purchase_return_by_id(company_id, purchase_return_id)
            if not existing['success']:
                return existing

            # Use VoucherPostingEngine to clean up ledger and stock entries
            try:
                from .voucher_posting_engine import VoucherPostingEngine
                engine = VoucherPostingEngine(self.db)
                delete_result = engine.delete_voucher_postings(company_id, "purchase_return", purchase_return_id)
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

            # Delete items then header (cascade handles items but explicit is safer)
            self.db.delete_purchase_return_items(purchase_return_id)
            self.db.delete_purchase_return(purchase_return_id)

            conn.commit()
            return {"success": True, "message": "Purchase return deleted successfully"}

        except Exception:
            conn.rollback()
            raise
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

            return get_next_voucher_number(self.db, company_id, "purchase_return")
        except Exception:
            return "001"
