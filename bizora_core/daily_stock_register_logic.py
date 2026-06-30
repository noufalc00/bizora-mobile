"""
Daily Stock Register Logic module for the Accounting Desktop Application.
Handles read-only stock movement reporting with running balance calculation.
"""

from typing import Optional, List, Dict, Any
from datetime import date


class DailyStockRegisterLogic:
    """Business logic for Daily Stock Register - read-only inventory reporting."""

    STOCK_EXCLUSION_SQL = "COALESCE(voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')"
    
    def __init__(self, db):
        """Initialize stock register logic with database instance."""
        self.db = db
    
    def get_stock_register_data(
        self,
        company_id: int,
        from_date: str,
        to_date: str,
        product_id: Optional[int] = None,
        voucher_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get stock register data with running balance calculation.
        
        This is a READ-ONLY reporting method. It does not modify any stock data.
        
        Args:
            company_id: Company ID
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            product_id: Optional product filter
            voucher_type: Optional voucher / movement type filter
            
        Returns:
            List of stock movement records with running balance
        """
        try:
            ph = self.db._get_placeholder()
            
            # Build WHERE clause with filters. Quotations/estimates/drafts are
            # intentionally invisible to the physical inventory engine.
            where_conditions = [
                f"sm.company_id = {ph}",
                "COALESCE(sm.voucher_type, '') NOT IN ('quotation', 'estimate', 'draft')",
            ]
            params = [company_id]
            
            # Date range filter on ISO date prefix (movement_date or created_at fallback).
            movement_date_expr = "SUBSTR(COALESCE(sm.movement_date, sm.created_at), 1, 10)"
            where_conditions.append(f"{movement_date_expr} >= {ph}")
            params.append(from_date)
            where_conditions.append(f"{movement_date_expr} <= {ph}")
            params.append(to_date)

            # Product filter
            if product_id:
                where_conditions.append(f"sm.product_id = {ph}")
                params.append(product_id)

            # Voucher / movement filter: match either stored movement_type or voucher label.
            if voucher_type:
                where_conditions.append(
                    f"(LOWER(COALESCE(sm.movement_type, '')) = LOWER({ph}) "
                    f"OR LOWER(COALESCE(sm.voucher_type, sm.reference_type, '')) = LOWER({ph}))"
                )
                params.append(voucher_type)
            
            where_clause = " AND ".join(where_conditions)
            
            # Query stock movements with product info
            # Use indexed columns for performance
            # Use COALESCE to handle NULL migrated columns
            # Include product rate for fallback calculation
            query = f"""
                SELECT
                    sm.id,
                    sm.company_id,
                    sm.product_id,
                    sm.movement_type,
                    sm.quantity,
                    COALESCE(sm.movement_date, sm.created_at) as movement_date,
                    COALESCE(sm.voucher_type, sm.reference_type) as voucher_type,
                    COALESCE(sm.voucher_no, CAST(sm.reference_id AS TEXT)) as voucher_no,
                    sm.narration,
                    sm.qty_in,
                    sm.qty_out,
                    sm.rate,
                    sm.value_in,
                    sm.value_out,
                    sm.balance_qty,
                    sm.balance_value,
                    sm.reference_type,
                    sm.reference_id,
                    p.name as product_name,
                    p.barcode as product_barcode,
                    p.hsn,
                    p.unit,
                    p.sale_price,
                    p.purchase_rate,
                    p.mrp,
                    sm.created_at
                FROM stock_movements sm
                LEFT JOIN products p ON p.id = sm.product_id
                WHERE {where_clause}
                ORDER BY sm.product_id ASC, COALESCE(sm.movement_date, sm.created_at) ASC, sm.id ASC
            """
            
            print(f"DATE RANGE: {from_date} to {to_date}")
            print(f"FILTER PRODUCT = {product_id}")
            print(f"FILTER MOVEMENT TYPE = {voucher_type}")
            
            movements = self.db.execute_query(query, tuple(params))
            
            print(f"RAW QUERY RESULT COUNT = {len(movements) if movements else 0}")
            
            if not movements:
                print("STOCK MOVEMENT COUNT = 0")
                return []
            
            print(f"STOCK MOVEMENT COUNT = {len(movements)}")
            
            # Opening balance before from_date. In all-product mode this returns
            # product-wise balances so each product has its own running timeline.
            opening_balance = self._get_opening_balance_before_date(
                company_id, from_date, product_id
            )
            running_balances = (
                {product_id: float(opening_balance or 0.0)}
                if product_id else dict(opening_balance or {})
            )
            print(f"RUNNING BALANCE (opening) = {running_balances}")
            
            # Process movements and calculate running balance
            result = []
            for movement in movements:
                movement_type = movement.get('movement_type', '').lower()
                voucher_type = movement.get('voucher_type', '').lower()
                movement_product_id = movement.get('product_id')
                quantity = float(movement.get('quantity') or 0.0)

                # Signed quantity is the single source of truth:
                # positive = inward, negative = outward.
                qty_in = quantity if quantity > 0 else 0.0
                qty_out = abs(quantity) if quantity < 0 else 0.0
                running_balance = running_balances.get(movement_product_id, 0.0) + quantity
                running_balances[movement_product_id] = running_balance
                
                # Calculate rate and value
                # Use stock_movement rate if available, otherwise fallback to product rate
                rate = movement.get('rate', 0.0) or 0.0
                if rate == 0.0:
                    # Fallback to product rate based on movement type
                    if (
                        voucher_type == 'sales_return'
                        or movement_type in ('sale', 'sales_return')
                    ):
                        rate = movement.get('sale_price', 0.0) or movement.get('mrp', 0.0) or 0.0
                    elif (
                        voucher_type == 'purchase_return'
                        or movement_type in ('purchase', 'purchase_return')
                    ):
                        rate = movement.get('purchase_rate', 0.0) or 0.0
                    else:
                        rate = movement.get('purchase_rate', 0.0) or movement.get('sale_price', 0.0) or movement.get('mrp', 0.0) or 0.0

                value = qty_in * rate if qty_in > 0 else qty_out * rate
                
                # Build result row
                row = {
                    'id': movement.get('id'),
                    'date': movement.get('movement_date') or movement.get('created_at', ''),
                    'voucher_type': movement.get('voucher_type', ''),
                    'voucher_no': movement.get('voucher_no', ''),
                    'product_name': movement.get('product_name', ''),
                    'product_barcode': movement.get('product_barcode', ''),
                    'location': '',  # Will be populated when location support is added
                    'qty_in': qty_in,
                    'qty_out': qty_out,
                    'balance_qty': running_balance,
                    'rate': rate,
                    'value': value,
                    'narration': movement.get('narration', ''),
                    'movement_type': movement_type,
                    'reference_type': movement.get('reference_type', ''),
                    'reference_id': movement.get('reference_id'),
                }
                
                result.append(row)
                print(f"RUNNING BALANCE after row = {running_balance}")
            
            return result
            
        except Exception as e:
            print(f"Error getting stock register data: {e}")
            return []
    
    def _get_opening_balance_before_date(
        self,
        company_id: int,
        before_date: str,
        product_id: Optional[int] = None,
        location_id: Optional[int] = None
    ) -> Any:
        """
        Calculate opening balance before a specific date.
        
        Args:
            company_id: Company ID
            before_date: Date to calculate opening balance before (YYYY-MM-DD)
            product_id: Optional product filter
            location_id: Optional location filter
            
        Returns:
            Opening balance as float for selected product, otherwise dict keyed by product_id.
        """
        try:
            ph = self.db._get_placeholder()
            
            movement_date_expr = "SUBSTR(COALESCE(movement_date, created_at), 1, 10)"
            where_conditions = [
                f"company_id = {ph}",
                f"{movement_date_expr} < {ph}",
                self.STOCK_EXCLUSION_SQL,
            ]
            params = [company_id, before_date]

            if product_id:
                where_conditions.append(f"product_id = {ph}")
                params.append(product_id)
            
            where_clause = " AND ".join(where_conditions)
            
            select_columns = "COALESCE(SUM(quantity), 0) as balance"
            group_clause = ""
            if not product_id:
                select_columns = "product_id, COALESCE(SUM(quantity), 0) as balance"
                group_clause = " GROUP BY product_id"

            query = f"""
                SELECT {select_columns}
                FROM stock_movements
                WHERE {where_clause}
                {group_clause}
            """
            
            result = self.db.execute_query(query, tuple(params))
            if product_id:
                return float(result[0]['balance']) if result and result[0]['balance'] else 0.0
            return {
                row['product_id']: float(row['balance'] or 0.0)
                for row in (result or [])
                if row.get('product_id') is not None
            }
            
        except Exception as e:
            print(f"Error calculating opening balance: {e}")
            return 0.0
    
    def resolve_product(
        self,
        company_id: int,
        search_text: str,
        *,
        barcode: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve a product from typed name or barcode for register filters.

        Returns a single unambiguous match only; returns None when not found
        or when multiple products share the same partial name.
        """
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

    def get_product_by_barcode(self, company_id: int, barcode: str) -> Optional[Dict[str, Any]]:
        """
        Get product by barcode for auto-selection.
        
        Args:
            company_id: Company ID
            barcode: Product barcode
            
        Returns:
            Product dictionary or None
        """
        try:
            ph = self.db._get_placeholder()
            query = f"""
                SELECT id, name, barcode, hsn, unit, quantity, sale_price, mrp, purchase_rate
                FROM products
                WHERE company_id = {ph} AND barcode = {ph}
                LIMIT 1
            """
            result = self.db.execute_query(query, (company_id, barcode))
            return dict(result[0]) if result else None
        except Exception as e:
            print(f"Error getting product by barcode: {e}")
            return None
    
    def get_all_products(self, company_id: int) -> List[Dict[str, Any]]:
        """
        Get all products for product filter dropdown.

        Args:
            company_id: Company ID

        Returns:
            List of product dictionaries
        """
        try:
            ph = self.db._get_placeholder()
            query = f"""
                SELECT id, name, barcode, hsn, unit, quantity, sale_price, mrp, purchase_rate
                FROM products
                WHERE company_id = {ph}
                ORDER BY name
            """
            return self.db.execute_query(query, (company_id,))
        except Exception as e:
            print(f"Error getting products: {e}")
            return []
    
    def get_voucher_types(self, company_id: int) -> List[str]:
        """
        Get distinct movement types from stock movements for filter dropdown.
        Uses movement_type column (NOT NULL) instead of voucher_type (may be NULL).
        
        Args:
            company_id: Company ID
            
        Returns:
            List of movement type strings
        """
        try:
            ph = self.db._get_placeholder()
            query = f"""
                SELECT DISTINCT movement_type
                FROM stock_movements
                WHERE company_id = {ph}
                  AND movement_type IS NOT NULL
                  AND {self.STOCK_EXCLUSION_SQL}
                ORDER BY movement_type
            """
            result = self.db.execute_query(query, (company_id,))
            movement_types = [row['movement_type'] for row in result] if result else []
            print(f"[DAILY STOCK REGISTER] MOVEMENT TYPES FROM DB = {movement_types}")
            return movement_types
        except Exception as e:
            print(f"Error getting movement types: {e}")
            return []
