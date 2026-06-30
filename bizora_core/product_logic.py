"""
Product Logic Module
Handles product business logic and validation.
"""

import random
import time
from typing import Dict, Any, List, Optional
from .barcode_db import (
    DEFAULT_PADDING_TEXT,
    apply_barcode_padding_for_new_code,
    fetch_barcode_preferences,
)
from .stock_logic import StockLogic


class ProductLogic:
    """Business logic for product operations."""

    def __init__(self, db):
        """Initialize product logic with database instance."""
        self.db = db
        self.stock_logic = StockLogic(db)

    def get_products(self, company_id: int) -> Dict[str, Any]:
        """
        Get all products for a company.
        
        Returns:
            Dict with success status, message, and data
        """
        try:
            products = self.db.get_products_by_company(company_id)
            return {
                "success": True,
                "message": "Products retrieved successfully",
                "data": products
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve products: {str(e)}",
                "data": []
            }

    def get_product_by_id(self, company_id: int, product_id: int) -> Dict[str, Any]:
        """
        Get a specific product by ID.

        Returns:
            Dict with success status, message, and data
        """
        try:
            product = self.db.get_product_by_id(company_id, product_id)
            if product:
                return {
                    "success": True,
                    "message": "Product retrieved successfully",
                    "data": product
                }
            else:
                return {
                    "success": False,
                    "message": "Product not found",
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve product: {str(e)}",
                "data": None
            }

    def get_product_by_barcode(self, company_id: int, barcode: str) -> Dict[str, Any]:
        """
        Get a specific product by barcode (exact match).

        Returns:
            Dict with success status, message, and data
        """
        try:
            product = self.db.get_product_by_barcode(company_id, barcode)
            if product:
                return {
                    "success": True,
                    "message": "Product retrieved successfully",
                    "data": product
                }
            else:
                return {
                    "success": False,
                    "message": "Product not found",
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve product: {str(e)}",
                "data": None
            }

    def validate_product_data(self, product_data: Dict[str, Any], 
                            auto_barcode: bool, 
                            current_product_id: Optional[int] = None,
                            company_id: Optional[int] = None,
                            allow_duplicate_name: bool = True) -> Dict[str, Any]:
        """
        Validate product data.
        
        Returns:
            Dict with success status and message
        """
        # Check required fields
        product_name = product_data.get('name', '').strip()
        if not product_name:
            return {
                "success": False,
                "message": "Product/Service Name is required"
            }

        # Block duplicate product names when the page setting disallows them.
        if company_id and not allow_duplicate_name:
            try:
                existing = self.db.get_product_by_exact_name(company_id, product_name)
                existing_id = existing.get('id') if existing else None
                if existing_id and existing_id != current_product_id:
                    return {
                        "success": False,
                        "message": (
                            f"A product named '{product_name}' already exists. "
                            "Enable 'Allow duplicate product' in Product Settings "
                            "to create another with the same name."
                        )
                    }
            except Exception:
                pass

        # Validate barcode if manual entry
        if not auto_barcode:
            barcode = product_data.get('barcode', '').strip()
            if not barcode:
                return {
                    "success": False,
                    "message": "Please enter a barcode or enable Auto Barcode"
                }

            # Check barcode uniqueness if company_id is provided
            if company_id:
                exists = self.db.barcode_exists(company_id, barcode, current_product_id)
                if exists:
                    return {
                        "success": False,
                        "message": f"Barcode '{barcode}' already exists for another product in this company"
                    }

        # Validate numeric fields
        try:
            if product_data.get('purchase_rate'):
                float(product_data['purchase_rate'])
            if product_data.get('sale_price'):
                float(product_data['sale_price'])
            if product_data.get('wholesale_rate'):
                float(product_data['wholesale_rate'])
            if product_data.get('mrp'):
                float(product_data['mrp'])
            if product_data.get('cgst'):
                float(product_data['cgst'])
            if product_data.get('sgst'):
                float(product_data['sgst'])
            if product_data.get('igst'):
                float(product_data['igst'])
            if product_data.get('cess'):
                float(product_data['cess'])
            if product_data.get('reorder_level'):
                float(product_data['reorder_level'])
            if product_data.get('quantity'):
                float(product_data['quantity'])
        except (ValueError, TypeError):
            return {
                "success": False,
                "message": "Please enter valid numeric values for rates, prices, taxes, reorder level, and quantity"
            }

        return {
            "success": True,
            "message": "Product data is valid"
        }

    def normalize_product_data(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize product data (ensure proper types and defaults).
        
        Returns:
            Normalized product data dict
        """
        normalized = product_data.copy()

        # Ensure numeric fields are floats
        numeric_fields = ['purchase_rate', 'sale_price', 'wholesale_rate', 'mrp',
                         'cgst', 'sgst', 'igst', 'cess', 'reorder_level', 'quantity']
        
        for field in numeric_fields:
            value = normalized.get(field)
            if value is None or value == '':
                normalized[field] = 0.0
            else:
                try:
                    normalized[field] = float(value)
                except (ValueError, TypeError):
                    normalized[field] = 0.0

        # Ensure quantity is never negative
        normalized['quantity'] = max(0, normalized.get('quantity', 0.0))

        # Ensure text fields are stripped
        text_fields = ['name', 'barcode', 'hsn', 'color', 'size', 'category', 'description']
        for field in text_fields:
            if field in normalized and normalized[field]:
                normalized[field] = normalized[field].strip()

        return normalized

    def _next_available_barcode(self, company_id: int,
                                exclude_current_id: Optional[int] = None) -> str:
        """Hole-filling next-available barcode finder.

        The continuous sequence is anchored to the highest system auto-generated
        barcode (the baseline seed). Manually keyed jumps are stored with
        auto_barcode = 0 and therefore never lift the seed. Allocation always
        begins one step above the baseline and climbs, skipping every number
        that still lives in the table, so:
          - existing custom numbers and existing items are never duplicated, and
          - deleted gaps below the baseline are permanently left untouched
            (the loop never walks backwards into them).

        Step A: baseline  = MAX(auto-generated barcode)  (or 0 when none exist)
        Step B: candidate = baseline + 1
        Step C/D: while the candidate already exists anywhere, increment again
        Step E: return the first candidate absent from the live table
        """
        baseline = self.db.get_max_auto_barcode(company_id, exclude_current_id) or 0
        # Single live snapshot of every numeric barcode currently in the table
        # (custom + auto + still-existing items). Using a set keeps the skip
        # loop O(1) per probe and protects the Windows UI thread from stutter.
        existing_barcodes = set(self.db.get_existing_barcodes(company_id, exclude_current_id))

        candidate = baseline + 1
        while candidate in existing_barcodes:
            candidate += 1

        return str(candidate)

    def _barcode_padding_setting(self, company_id: int) -> str:
        """Read one company's barcode padding without changing product rows."""
        try:
            prefs = fetch_barcode_preferences(self.db, company_id)
            return prefs.get("barcode_padding") or DEFAULT_PADDING_TEXT
        except Exception:
            return DEFAULT_PADDING_TEXT

    def _format_generated_barcode(self, barcode_value, company_id: int) -> str:
        """Apply barcode padding only to newly generated numeric barcodes."""
        return apply_barcode_padding_for_new_code(
            barcode_value,
            self._barcode_padding_setting(company_id),
        )

    def generate_next_barcode(self, company_id: int, 
                            exclude_current_id: Optional[int] = None) -> str:
        """
        Generate the next unique barcode for a company using the hole-filling
        sequence engine.
        
        Returns:
            Next available barcode as string
        """
        try:
            barcode = self._next_available_barcode(company_id, exclude_current_id)
            return self._format_generated_barcode(barcode, company_id)
        except Exception:
            # Fallback to timestamp-based unique number
            fallback = str(int(time.time() * 1000) % 1000000)
            return self._format_generated_barcode(fallback, company_id)
    
    def generate_sequential_barcode(self, company_id: int) -> str:
        """
        Pre-fill the next sequential barcode (Auto checkbox / fresh form) using
        the same hole-filling engine as save-time allocation.
        
        Returns:
            Next sequential barcode as string
        """
        try:
            barcode = self._next_available_barcode(company_id)
            return self._format_generated_barcode(barcode, company_id)
        except Exception:
            # Fallback to simple sequential number
            return self._format_generated_barcode("1", company_id)

    def save_product(self, company_id: int, product_data: Dict[str, Any],
                    product_id: Optional[int] = None, skip_opening_stock: bool = False) -> Dict[str, Any]:
        """
        Save a product (insert or update).

        Args:
            company_id: Company ID
            product_data: Product data dictionary
            product_id: Product ID (for update)
            skip_opening_stock: If True, skip creating opening stock movement (for products created from Purchase Entry)

        Returns:
            Dict with success status and message
        """
        try:
            # Normalize data
            normalized_data = self.normalize_product_data(product_data)
            opening_qty = float(normalized_data.get('quantity', 0.0))

            if product_id:
                # Update existing product
                self.db.update_product(company_id, product_id, normalized_data)

                # Replace opening stock movement safely (delete old, insert new if > 0)
                # Skip if skip_opening_stock is True (e.g., product being edited from Purchase Entry)
                if not skip_opening_stock:
                    self.db.delete_stock_movements_by_reference('product', product_id)
                    if opening_qty > 0:
                        print(f"INSERTING STOCK MOVEMENT = opening, {opening_qty}, product_creation")
                        self.stock_logic.create_opening_stock_movement(company_id, product_id, opening_qty)
                    # Sync products.quantity cache from movements
                    self.stock_logic.sync_product_quantity_from_movements(company_id, product_id)

                result = self.get_product_by_id(company_id, product_id)
                if result['success']:
                    return {
                        "success": True,
                        "message": "Product updated successfully",
                        "data": result['data']
                    }
                else:
                    return {
                        "success": True,
                        "message": "Product updated successfully",
                        "data": {"id": product_id}
                    }
            else:
                # Insert new product
                product_id = self.db.insert_product(company_id, normalized_data)

                # Create opening stock movement if quantity > 0
                # Skip if skip_opening_stock is True (e.g., product created from Purchase Entry)
                if not skip_opening_stock and opening_qty > 0:
                    print(f"INSERTING STOCK MOVEMENT = opening, {opening_qty}, product_creation")
                    self.stock_logic.create_opening_stock_movement(company_id, product_id, opening_qty)
                    # Sync cache so products.quantity reflects movement balance
                    self.stock_logic.sync_product_quantity_from_movements(company_id, product_id)

                result = self.get_product_by_id(company_id, product_id)
                if result['success']:
                    return {
                        "success": True,
                        "message": "Product saved successfully",
                        "data": result['data']
                    }
                else:
                    return {
                        "success": True,
                        "message": "Product saved successfully",
                        "data": {"id": product_id}
                    }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to save product: {str(e)}"
            }

    def delete_product(self, company_id: int, product_id: int) -> Dict[str, Any]:
        """
        Delete a product.
        
        Returns:
            Dict with success status and message
        """
        try:
            self.db.delete_product(company_id, product_id)
            return {
                "success": True,
                "message": "Product deleted successfully"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to delete product: {str(e)}"
            }

    def filter_products(self, products: List[Dict[str, Any]],
                       search_term: str) -> List[Dict[str, Any]]:
        """
        Filter products based on search term.

        Returns:
            Filtered list of products
        """
        search_term = search_term.strip()

        if not search_term:
            return products

        filtered = []
        for product in products:
            name_match = search_term.lower() in (product.get('name') or "").lower()
            barcode_match = search_term.lower() in (product.get('barcode') or "").lower()

            if name_match or barcode_match:
                filtered.append(product)

        return filtered

    def search_products_limited(self, company_id: int, search_term: str, limit: int = 100) -> Dict[str, Any]:
        """
        Search products by name or barcode with a result limit (DB-backed).

        Safe for very large product catalogs.

        Returns:
            Dict with success status, message, and data
        """
        try:
            products = self.db.search_products_limited(company_id, search_term, limit)
            return {
                "success": True,
                "message": "Products searched successfully",
                "data": products
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to search products: {str(e)}",
                "data": []
            }

    def get_product_count(self, company_id: int) -> Dict[str, Any]:
        """
        Get total product count for a company (lightweight query).

        Returns:
            Dict with success status, message, and count
        """
        try:
            count = self.db.get_product_count(company_id)
            return {
                "success": True,
                "message": "Product count retrieved successfully",
                "data": count
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to get product count: {str(e)}",
                "data": 0
            }

    def get_product_categories(self, company_id: int) -> Dict[str, Any]:
        """
        Get distinct non-empty product categories for a company.

        Returns:
            Dict with success status, message, and category list
        """
        try:
            placeholder = self.db._get_placeholder()
            query = f"""
                SELECT DISTINCT category
                FROM products
                WHERE company_id = {placeholder}
                  AND category IS NOT NULL
                  AND category != ''
                ORDER BY category
            """
            results = self.db.execute_query(query, (company_id,))
            categories = [
                str(row['category']).strip()
                for row in results
                if str(row.get('category') or '').strip()
            ]
            return {
                "success": True,
                "message": "Product categories retrieved successfully",
                "data": categories,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve product categories: {str(e)}",
                "data": [],
            }

    def get_product_by_exact_name(self, company_id: int, name: str) -> Dict[str, Any]:
        """
        Get product by exact name match (DB-backed).

        Safe for very large product catalogs.

        Returns:
            Dict with success status, message, and data
        """
        try:
            product = self.db.get_product_by_exact_name(company_id, name)
            if product:
                return {
                    "success": True,
                    "message": "Product retrieved successfully",
                    "data": product
                }
            else:
                return {
                    "success": False,
                    "message": "Product not found",
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve product: {str(e)}",
                "data": None
            }

    def get_price_list(self, company_id: int) -> Dict[str, Any]:
        """
        Get price list with current stock for all products.

        Returns:
            Dict with success status, message, and data (list of dicts with:
            item_code, item_name, current_stock, purchase_rate, sales_rate,
            wholesale_rate, mrp, gross_margin_percent, markup_percent)
        """
        try:
            ph = self.db._get_placeholder()
            query = f"""
                SELECT
                    p.id,
                    COALESCE(p.barcode, '') AS item_code,
                    COALESCE(p.name, '') AS item_name,
                    COALESCE(sm.current_stock, 0.0) AS current_stock,
                    COALESCE(p.purchase_rate, 0.0) AS purchase_rate,
                    COALESCE(p.sale_price, 0.0) AS sales_rate,
                    COALESCE(p.wholesale_rate, 0.0) AS wholesale_rate,
                    COALESCE(p.mrp, 0.0) AS mrp,
                    CASE
                        WHEN COALESCE(p.sale_price, 0.0) = 0 THEN 0.0
                        ELSE ((COALESCE(p.sale_price, 0.0) - COALESCE(p.purchase_rate, 0.0)) / p.sale_price) * 100
                    END AS gross_margin_percent,
                    CASE
                        WHEN COALESCE(p.purchase_rate, 0.0) = 0 THEN 0.0
                        ELSE ((COALESCE(p.sale_price, 0.0) - COALESCE(p.purchase_rate, 0.0)) / p.purchase_rate) * 100
                    END AS markup_percent
                FROM products p
                LEFT JOIN (
                    SELECT
                        product_id,
                        COALESCE(SUM(quantity), 0.0) AS current_stock
                    FROM stock_movements
                    WHERE company_id = {ph}
                      AND COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')
                    GROUP BY product_id
                ) sm ON sm.product_id = p.id
                WHERE p.company_id = {ph}
                ORDER BY p.name
            """
            rows = self.db.execute_query(query, (company_id, company_id))
            price_list = []

            for product in rows:
                price_list.append({
                    'id': product.get('id'),
                    'item_code': product.get('item_code', ''),
                    'item_name': product.get('item_name', ''),
                    'current_stock': float(product.get('current_stock') or 0.0),
                    'purchase_rate': float(product.get('purchase_rate') or 0.0),
                    'sales_rate': float(product.get('sales_rate') or 0.0),
                    'wholesale_rate': float(product.get('wholesale_rate') or 0.0),
                    'mrp': float(product.get('mrp') or 0.0),
                    'gross_margin_percent': float(product.get('gross_margin_percent') or 0.0),
                    'markup_percent': float(product.get('markup_percent') or 0.0),
                })

            return {
                "success": True,
                "message": "Price list retrieved successfully",
                "data": price_list
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve price list: {str(e)}",
                "data": []
            }
