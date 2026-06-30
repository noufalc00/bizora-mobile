"""
Stock Value Logic Module.

Provides inventory valuation based on selected rate basis.
Uses existing stock movement system and stock balance logic.
"""

from typing import Dict, List, Any, Optional


class StockValueLogic:
    """Logic for stock value inventory valuation."""

    def __init__(self, db=None):
        """
        Initialize stock value logic.

        Args:
            db: Database instance (optional, will create default if not provided)
        """
        if db is None:
            from db import Database
            self.db = Database()
        else:
            self.db = db

        self._stock_logic = None

    def _get_stock_logic(self):
        """Lazy load stock logic."""
        if self._stock_logic is None:
            from bizora_core.stock_logic import StockLogic
            self._stock_logic = StockLogic(self.db)
        return self._stock_logic

    def get_stock_valuation(self, company_id: int, 
                           rate_basis: str = "purchase_rate",
                           product_id: Optional[int] = None,
                           product_name: Optional[str] = None,
                           barcode: Optional[str] = None,
                           category: Optional[str] = None,
                           location: Optional[str] = None,
                           hide_zero_stock: bool = False) -> List[Dict[str, Any]]:
        """
        Get stock valuation for products.

        Args:
            company_id: Company ID
            rate_basis: Rate basis to use (purchase_rate, sale_price, wholesale_rate, mrp)
            product_id: Optional product filter
            product_name: Optional partial product name filter
            barcode: Optional barcode filter
            category: Optional category filter
            location: Optional location filter
            hide_zero_stock: If True, exclude products with zero stock

        Returns:
            List of product valuation records
        """
        try:
            ph = self.db._get_placeholder()

            # Build WHERE clause for filters
            where_conditions = [f"p.company_id = {ph}"]
            params = [company_id]

            if product_id:
                where_conditions.append(f"p.id = {ph}")
                params.append(product_id)

            if product_name and not product_id:
                where_conditions.append(f"LOWER(p.name) LIKE LOWER({ph})")
                params.append(f"%{product_name.strip()}%")

            if barcode:
                where_conditions.append(f"p.barcode = {ph}")
                params.append(barcode)

            if category:
                where_conditions.append(f"p.category = {ph}")
                params.append(category)

            # Location filter - disabled for now as location column may not exist
            # if location:
            #     # Location filter - filter by products in this location
            #     # This would require a location-based stock query
            #     # For now, we'll skip location filtering until location architecture is clear
            #     pass

            where_clause = " AND ".join(where_conditions)

            # Rate basis field mapping
            rate_field_map = {
                "purchase_rate": "p.purchase_rate",
                "sale_price": "p.sale_price",
                "wholesale_rate": "p.wholesale_rate",
                "mrp": "p.mrp"
            }
            rate_field = rate_field_map.get(rate_basis, "p.purchase_rate")

            # Query products with stock balance
            query = f"""
                SELECT 
                    p.id,
                    p.barcode,
                    p.name,
                    p.category,
                    p.unit,
                    {rate_field} as rate,
                    COALESCE(sm.balance, 0.0) as current_qty
                FROM products p
                LEFT JOIN (
                    SELECT 
                        product_id,
                        COALESCE(SUM(quantity), 0) as balance
                    FROM stock_movements
                    WHERE company_id = {ph}
                      AND COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')
                    GROUP BY product_id
                ) sm ON p.id = sm.product_id
                WHERE {where_clause}
                ORDER BY p.name
            """
            params.insert(0, company_id)  # Add company_id for subquery

            results = self.db.execute_query(query, tuple(params))

            if not results:
                return []

            # Calculate stock value and apply zero-stock filter
            valuation_records = []
            for row in results:
                current_qty = row.get('current_qty', 0.0)
                rate = row.get('rate', 0.0)
                stock_value = current_qty * rate

                # Apply zero-stock filter
                if hide_zero_stock and current_qty == 0.0:
                    continue

                valuation_records.append({
                    'product_id': row.get('id'),
                    'barcode': row.get('barcode', ''),
                    'name': row.get('name', ''),
                    'category': row.get('category', ''),
                    'unit': row.get('unit', 'pcs'),
                    'current_qty': current_qty,
                    'rate': rate,
                    'stock_value': stock_value
                })

            print("STOCK VALUE PRODUCT COUNT =", len(valuation_records))
            print("RATE BASIS =", rate_basis)

            return valuation_records

        except Exception as e:
            print(f"Error getting stock valuation: {e}")
            return []

    def get_stock_valuation_totals(self, valuation_records: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Calculate totals from valuation records.

        Args:
            valuation_records: List of valuation records

        Returns:
            Dict with total_qty and total_value
        """
        total_qty = 0.0
        total_value = 0.0

        for record in valuation_records:
            total_qty += record.get('current_qty', 0.0)
            total_value += record.get('stock_value', 0.0)

        print("TOTAL STOCK VALUE =", total_value)

        return {
            'total_qty': total_qty,
            'total_value': total_value
        }

    def resolve_product(
        self,
        company_id: int,
        search_text: str,
        *,
        barcode: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Resolve a single product from typed name or barcode for filters."""
        barcode_text = str(barcode or "").strip()
        if barcode_text:
            product = self.get_product_by_barcode(company_id, barcode_text)
            if product:
                return product

        text = str(search_text or "").strip()
        if not text:
            return None

        try:
            ph = self.db._get_placeholder()
            columns = (
                "id, name, barcode, hsn, unit, quantity, sale_price, mrp, purchase_rate"
            )
            exact_query = f"""
                SELECT {columns}
                FROM products
                WHERE company_id = {ph}
                  AND LOWER(name) = LOWER({ph})
                LIMIT 1
            """
            exact_rows = self.db.execute_query(exact_query, (company_id, text))
            if exact_rows:
                return dict(exact_rows[0])

            barcode_query = f"""
                SELECT {columns}
                FROM products
                WHERE company_id = {ph}
                  AND barcode = {ph}
                LIMIT 1
            """
            barcode_rows = self.db.execute_query(barcode_query, (company_id, text))
            if barcode_rows:
                return dict(barcode_rows[0])

            partial_query = f"""
                SELECT {columns}
                FROM products
                WHERE company_id = {ph}
                  AND name LIKE {ph}
                ORDER BY name
                LIMIT 2
            """
            partial_rows = self.db.execute_query(partial_query, (company_id, f"%{text}%"))
            if len(partial_rows) == 1:
                return dict(partial_rows[0])
            return None
        except Exception as exc:
            print(f"Error resolving product filter: {exc}")
            return None

    def get_product_by_barcode(
        self,
        company_id: int,
        barcode: str,
    ) -> Optional[Dict[str, Any]]:
        """Return one product row matched by barcode."""
        barcode_text = str(barcode or "").strip()
        if not barcode_text:
            return None
        try:
            ph = self.db._get_placeholder()
            query = f"""
                SELECT id, name, barcode, hsn, unit, quantity, sale_price, mrp, purchase_rate
                FROM products
                WHERE company_id = {ph}
                  AND barcode = {ph}
                LIMIT 1
            """
            rows = self.db.execute_query(query, (company_id, barcode_text))
            return dict(rows[0]) if rows else None
        except Exception as exc:
            print(f"Error loading product by barcode: {exc}")
            return None

    def get_categories(self, company_id: int) -> List[str]:
        """
        Get unique product categories.

        Args:
            company_id: Company ID

        Returns:
            List of category names
        """
        try:
            ph = self.db._get_placeholder()
            query = f"""
                SELECT DISTINCT category
                FROM products
                WHERE company_id = {ph}
                  AND category IS NOT NULL
                  AND category != ''
                ORDER BY category
            """
            results = self.db.execute_query(query, (company_id,))
            return [row['category'] for row in results] if results else []
        except Exception as e:
            print(f"Error getting categories: {e}")
            return []

    def get_locations(self, company_id: int) -> List[str]:
        """
        Get unique stock locations.

        Args:
            company_id: Company ID

        Returns:
            List of location names
        """
        # Disabled - location column may not exist in stock_movements table
        return []
