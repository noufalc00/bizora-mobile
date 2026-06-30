"""
Mobile web service layer — reuses desktop dashboard and report logic.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

from config import CURRENCY_SYMBOL, active_company_manager
from db import Database, get_default_database_path
from bizora_core.dashboard_logic import DashboardLogic
from bizora_core.mobile_report_lookups import build_local_report_lookups
from bizora_core.mobile_report_display import build_report_table_payload
from bizora_core.mobile_web_registry import (
    VOUCHER_BOOK_MODES,
    build_navigation_payload,
    get_route_definition,
)
from utils.theme_manager import ThemeManager


VOUCHER_LOGIC_MAP: dict[str, type] = {}


def _load_voucher_logic_map() -> dict[str, type]:
    """Lazy-load voucher book logic classes to avoid circular imports."""
    if VOUCHER_LOGIC_MAP:
        return VOUCHER_LOGIC_MAP

    from bizora_core.purchase_book_logic import PurchaseBookLogic
    from bizora_core.purchase_return_book_logic import PurchaseReturnBookLogic
    from bizora_core.quotation_book_logic import QuotationBookLogic
    from bizora_core.sales_book_logic import SalesBookLogic
    from bizora_core.sales_return_book_logic import SalesReturnBookLogic

    mapping = {
        "sales-book": SalesBookLogic,
        "sales-return-book": SalesReturnBookLogic,
        "purchase-book": PurchaseBookLogic,
        "purchase-return-book": PurchaseReturnBookLogic,
        "quotation-book": QuotationBookLogic,
    }
    VOUCHER_LOGIC_MAP.update(mapping)
    return VOUCHER_LOGIC_MAP


class MobileWebService:
    """Read-only mobile API backed by the same logic layer as the desktop app."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.dashboard_logic = DashboardLogic(self.db)

    def resolve_company_id(self, override_id: Optional[int] = None) -> Optional[int]:
        """Return the mobile session, desktop session, or DB active company."""
        if override_id:
            return int(override_id)
        session_id = active_company_manager.get_active_company_id()
        if session_id:
            return int(session_id)
        try:
            company = self.db.get_active_company()
            if company and company.get("id"):
                return int(company["id"])
        except Exception as exc:
            print(f"[MOBILE] Company resolve failed: {exc}")
        return None

    def get_theme_payload(self, theme_name: Optional[str] = None) -> dict[str, Any]:
        """Return desktop color tokens for light or dark mode."""
        master_db = ThemeManager.resolve_master_db_path()
        resolved = (theme_name or ThemeManager.get_theme_preference(master_db)).strip().lower()
        if resolved not in ThemeManager.VALID_THEMES:
            resolved = ThemeManager.DEFAULT_THEME
        colors = ThemeManager.get_colors(resolved)
        return {
            "theme": resolved,
            "colors": colors,
            "currency_symbol": CURRENCY_SYMBOL,
        }

    def get_dashboard_payload(self, company_id: Optional[int] = None) -> dict[str, Any]:
        """Return the same dashboard metrics/charts/activity as the desktop widget."""
        resolved_id = self.resolve_company_id(company_id)
        if not resolved_id:
            return {
                "success": False,
                "message": "No active company is open.",
                "company_id": None,
                "summary": DashboardLogic._empty_metrics(),
                "sales_chart": [],
                "purchase_chart": [],
                "recent_activity": [],
            }

        summary = self.dashboard_logic.get_summary_metrics(resolved_id)
        sales_chart = self.dashboard_logic.get_monthly_sales_chart_data(resolved_id)
        purchase_chart = self.dashboard_logic.get_monthly_purchase_chart_data(resolved_id)
        recent_rows = self.dashboard_logic.get_recent_activities(resolved_id)
        recent_activity = list(recent_rows or [])

        return {
            "success": True,
            "message": "",
            "company_id": resolved_id,
            "summary": summary,
            "summary_labels": {
                "net_realized_sale": "Net Realized Sale",
                "total_creditors": "Total to Give to Creditors",
                "total_debtors": "Total to Get from Debtors",
                "day_credit_sale": "Day Credit Sale",
            },
            "summary_colors": {
                "net_realized_sale": "button_primary",
                "total_creditors": "button_danger",
                "total_debtors": "button_success",
                "day_credit_sale": "accent",
            },
            "sales_chart": sales_chart,
            "purchase_chart": purchase_chart,
            "recent_activity": recent_activity,
        }

    def get_navigation(self) -> dict[str, Any]:
        """Return Books and Reports navigation tree."""
        return {
            "success": True,
            "sections": build_navigation_payload(),
        }

    def get_report_meta(self, slug: str, company_id: Optional[int] = None) -> dict[str, Any]:
        """Return filter schema and lookup data for one report route."""
        definition = get_route_definition(slug)
        if definition is None:
            return {"success": False, "message": f"Unknown route: {slug}"}

        resolved_id = self.resolve_company_id(company_id)
        lookups: dict[str, Any] = {}
        if resolved_id:
            lookups = build_local_report_lookups(self.db, resolved_id, slug)

        return {
            "success": True,
            "route": definition,
            "lookups": lookups,
            "company_id": resolved_id,
        }

    def run_report(
        self,
        slug: str,
        filters: Optional[dict[str, Any]] = None,
        company_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Execute one mobile report using the desktop logic layer."""
        definition = get_route_definition(slug)
        if definition is None:
            return {"success": False, "message": f"Unknown route: {slug}", "rows": []}

        resolved_id = self.resolve_company_id(company_id)
        if not resolved_id:
            return {
                "success": False,
                "message": "No active company is open.",
                "rows": [],
            }

        handler_name = definition["handler"]
        handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "voucher_book": self._run_voucher_book,
            "day_book": self._run_day_book,
            "cash_book": self._run_cash_book,
            "ledger": self._run_ledger,
            "ledger_statement": self._run_ledger_statement,
            "bill_history": self._run_bill_history,
            "trial_balance": self._run_trial_balance,
            "profit_and_loss": self._run_profit_and_loss,
            "balance_sheet": self._run_balance_sheet,
            "stock_report": self._run_stock_report,
            "gstr1": self._run_gstr1,
            "monthly_analysis": self._run_monthly_analysis,
            "journal_book": self._run_journal_book,
            "pdc_book": self._run_pdc_book,
            "purchase_order_book": self._run_purchase_order_book,
            "sales_profit_book": self._run_sales_profit_book,
            "cash_tender_history": self._run_cash_tender_history,
            "daily_stock_register": self._run_daily_stock_register,
            "price_list": self._run_price_list,
            "gst_sales_report": self._run_gst_sales_report,
            "gst_purchase_report": self._run_gst_purchase_report,
            "daily_collection": self._run_daily_collection,
            "stock_value": self._run_stock_value,
            "best_sellers": self._run_best_sellers,
            "salesman_book": self._run_salesman_book,
        }
        handler = handlers.get(handler_name)
        if handler is None:
            return {
                "success": False,
                "message": f"Handler '{handler_name}' is not implemented yet.",
                "rows": [],
            }
        try:
            result = handler(resolved_id, definition, filters or {})
            if result.get("success"):
                rows = result.get("rows") or []
                from bizora_core.mobile_report_columns import build_slug_table_payload

                table_payload = build_slug_table_payload(
                    slug,
                    rows,
                    handler=handler_name,
                    report_mode=(filters or {}).get("report_mode"),
                    filters=filters or {},
                )
                result.update(table_payload)
            return result
        except Exception as exc:
            print(f"[MOBILE] Report '{slug}' failed: {exc}")
            return {"success": False, "message": str(exc), "rows": []}

    @staticmethod
    def _parse_date(value: Any, fallback: Optional[date] = None) -> str:
        """Normalize incoming date values to ISO strings."""
        if isinstance(value, date):
            return value.isoformat()
        text = str(value or "").strip()
        if text:
            return text[:10]
        return (fallback or date.today()).isoformat()

    @staticmethod
    def _rows_from_logic_result(result: Any) -> dict[str, Any]:
        """Normalize logic-layer dict responses for the mobile table UI."""
        if not isinstance(result, dict):
            return {"success": False, "message": "Invalid report response", "rows": []}
        rows = result.get("data")
        if rows is None:
            rows = result.get("rows", [])
        if isinstance(rows, dict):
            rows = [rows]
        return {
            "success": bool(result.get("success", True)),
            "message": str(result.get("message", "") or ""),
            "rows": rows or [],
            "totals": result.get("totals"),
            "meta": {key: value for key, value in result.items() if key not in {"data", "rows", "success", "message"}},
        }

    def _run_voucher_book(
        self,
        company_id: int,
        definition: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        """Run Sales/Purchase/Return/Quotation book modes."""
        logic_map = _load_voucher_logic_map()
        logic_key = definition.get("logic_key") or definition["slug"]
        logic_cls = logic_map.get(logic_key)
        if logic_cls is None:
            return {"success": False, "message": f"No logic for {logic_key}", "rows": []}

        mode_label = str(filters.get("report_mode") or "Bill Wise")
        method_name = next(
            (mode["method"] for mode in VOUCHER_BOOK_MODES if mode["label"] == mode_label),
            "get_bill_wise",
        )
        logic = logic_cls(self.db)
        method = getattr(logic, method_name, None)
        if method is None:
            return {"success": False, "message": f"Missing method {method_name}", "rows": []}

        from_date = self._parse_date(filters.get("from_date"))
        to_date = self._parse_date(filters.get("to_date"))
        local_filters = {
            key: filters.get(key)
            for key in ("search", "party", "product", "category", "gst")
            if filters.get(key) not in (None, "")
        }
        result = method(company_id, from_date, to_date, local_filters)
        return self._rows_from_logic_result(result)

    def _run_day_book(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.day_book_logic import DayBookLogic
        from bizora_core.mobile_supabase_day_book import DAY_BOOK_SUMMARY_LABELS

        logic = DayBookLogic(self.db)
        from_date = self._parse_date(filters.get("from_date"))
        to_date = self._parse_date(filters.get("to_date"))
        summarize_entries = bool(filters.get("summarize_entries", True))
        summarize_debtors = bool(filters.get("summarize_debtors", False))
        summarize_creditors = bool(filters.get("summarize_creditors", False))
        result = logic.get_day_book_entries(
            company_id,
            from_date,
            to_date,
            summarize_entries=summarize_entries,
            summarize_debtors=summarize_debtors,
            summarize_creditors=summarize_creditors,
        )
        payload = self._rows_from_logic_result(result)
        summary_result = logic.get_day_book_summary(
            company_id,
            from_date,
            to_date,
            summarize_entries=summarize_entries,
            summarize_debtors=summarize_debtors,
            summarize_creditors=summarize_creditors,
        )
        payload["summary"] = summary_result.get("data") or {}
        payload["summary_labels"] = DAY_BOOK_SUMMARY_LABELS
        return payload

    def _run_cash_book(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.cash_book_logic import CashBookLogic

        logic = CashBookLogic(self.db)
        from_dt = date.fromisoformat(self._parse_date(filters.get("from_date")))
        to_dt = date.fromisoformat(self._parse_date(filters.get("to_date")))
        result = logic.get_cash_book(company_id, from_dt, to_dt)
        return self._rows_from_logic_result(result)

    def _run_ledger(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.ledger_logic import LedgerLogic

        logic = LedgerLogic(self.db)
        from_dt = date.fromisoformat(self._parse_date(filters.get("from_date")))
        to_dt = date.fromisoformat(self._parse_date(filters.get("to_date")))
        view = str(filters.get("ledger_view") or "General")
        if view == "Debtors":
            rows = logic.get_debtor_summary(company_id, from_dt, to_dt)
        elif view == "Creditors":
            rows = logic.get_creditor_summary(company_id, from_dt, to_dt)
        elif view == "Cash/Bank":
            rows = logic.get_cash_bank_summary(company_id, from_dt, to_dt)
        else:
            rows = logic.get_general_account_summary(company_id, from_dt, to_dt)

        search = str(filters.get("search") or "").strip().lower()
        if search:
            rows = [
                row for row in rows
                if search in str(row.get("account_name", "")).lower()
            ]
        return {"success": True, "message": "", "rows": rows}

    def _run_ledger_statement(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.ledger_logic import LedgerLogic

        account_id = filters.get("account_id")
        if not account_id:
            return {"success": False, "message": "Account is required.", "rows": []}
        logic = LedgerLogic(self.db)
        from_dt = date.fromisoformat(self._parse_date(filters.get("from_date")))
        to_dt = date.fromisoformat(self._parse_date(filters.get("to_date")))
        result = logic.get_account_ledger(company_id, int(account_id), from_dt, to_dt)
        rows = result.get("entries", []) if isinstance(result, dict) else []
        return {"success": True, "message": "", "rows": rows, "meta": result}

    def _run_bill_history(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.bill_history_logic import BillHistoryLogic

        logic = BillHistoryLogic(self.db)
        result = logic.get_filtered_bills(
            company_id,
            self._parse_date(filters.get("from_date")),
            self._parse_date(filters.get("to_date")),
            search_term=str(filters.get("search") or ""),
            transaction_type=str(filters.get("voucher_type") or "All"),
        )
        return {"success": True, "message": "", "rows": result}

    def _run_trial_balance(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.financial_reporting_engine import FinancialReportingEngine

        engine = FinancialReportingEngine(self.db)
        from_dt = date.fromisoformat(self._parse_date(filters.get("from_date")))
        to_dt = date.fromisoformat(self._parse_date(filters.get("to_date")))
        account_type = str(filters.get("account_type") or "All")
        result = engine.generate_trial_balance(
            company_id,
            from_date=from_dt,
            to_date=to_dt,
            account_type_filter=account_type,
            search_term=str(filters.get("search") or ""),
        )
        rows = result.get("rows", []) if isinstance(result, dict) else []
        return {
            "success": True,
            "message": "",
            "rows": rows,
            "totals": result.get("totals") if isinstance(result, dict) else None,
        }

    def _run_profit_and_loss(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.financial_reporting_engine import FinancialReportingEngine

        engine = FinancialReportingEngine(self.db)
        from_dt = date.fromisoformat(self._parse_date(filters.get("from_date")))
        to_dt = date.fromisoformat(self._parse_date(filters.get("to_date")))
        result = engine.generate_profit_and_loss(company_id, from_dt, to_dt)
        rows: list[dict[str, Any]] = []
        if isinstance(result, dict):
            for side in ("income_rows", "expense_rows"):
                rows.extend(result.get(side, []) or [])
        return {"success": True, "message": "", "rows": rows, "meta": result}

    def _run_balance_sheet(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.financial_reporting_engine import FinancialReportingEngine

        engine = FinancialReportingEngine(self.db)
        as_of = date.fromisoformat(self._parse_date(filters.get("as_of_date")))
        result = engine.generate_balance_sheet(company_id, as_of)
        rows: list[dict[str, Any]] = []
        if isinstance(result, dict):
            for side in ("assets", "liabilities"):
                rows.extend(result.get(side, []) or [])
        return {"success": True, "message": "", "rows": rows, "meta": result}

    def _run_stock_report(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.stock_report_logic import StockReportLogic

        logic = StockReportLogic(self.db)
        result = logic.get_stock_summary(
            company_id,
            {
                "date_from": self._parse_date(filters.get("from_date")),
                "date_to": self._parse_date(filters.get("to_date")),
                "category": filters.get("category"),
                "search_text": filters.get("search"),
            },
            limit=250,
            offset=0,
        )
        return self._rows_from_logic_result(result)

    def _run_gstr1(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.gstr1_logic import GSTR1Logic

        logic = GSTR1Logic(self.db)
        result = logic.generate_gstr1_report(
            company_id,
            self._parse_date(filters.get("from_date")),
            self._parse_date(filters.get("to_date")),
        )
        rows = result.get("data", []) if isinstance(result, dict) else []
        return {"success": bool(result.get("success", True)), "message": result.get("message", ""), "rows": rows}

    def _run_monthly_analysis(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.monthly_analysis_logic import MonthlyAnalysisLogic
        from utils.financial_year import get_working_financial_year_label

        logic = MonthlyAnalysisLogic(self.db)
        fy = str(filters.get("financial_year") or get_working_financial_year_label() or "")
        from_month = str(filters.get("from_month") or "April")
        to_month = str(filters.get("to_month") or "March")
        start_date, end_date = logic.get_financial_year_range(fy, from_month, to_month)
        result = logic.get_monthly_analysis(
            company_id,
            start_date,
            end_date,
            from_month=from_month,
            to_month=to_month,
        )
        return self._rows_from_logic_result(result)

    def _run_journal_book(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.journal_book_logic import JournalBookLogic

        logic = JournalBookLogic(self.db)
        rows = logic.get_journal_book_data(
            company_id,
            self._parse_date(filters.get("from_date")),
            self._parse_date(filters.get("to_date")),
            filters={"narration_search": filters.get("search")},
        )
        return {"success": True, "message": "", "rows": rows}

    def _run_pdc_book(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.pdc_book_logic import PDCBookLogic

        logic = PDCBookLogic(self.db)
        local_filters = {
            key: filters.get(key)
            for key in ("transaction_type", "status", "party")
            if filters.get(key) not in (None, "", "All")
        }
        rows = logic.get_pdc_book_data(
            company_id,
            self._parse_date(filters.get("from_date")),
            self._parse_date(filters.get("to_date")),
            filters=local_filters,
        )
        party = str(filters.get("party") or "").strip().lower()
        if party:
            rows = [row for row in rows if party in str(row).lower()]
        return {"success": True, "message": "", "rows": rows}

    def _run_purchase_order_book(
        self,
        company_id: int,
        _definition: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        """Return purchase order register rows with desktop-style filters."""
        ph = self.db._get_placeholder()
        clauses = [f"company_id = {ph}"]
        params: list[Any] = [company_id]
        from_date = self._parse_date(filters.get("from_date"))
        to_date = self._parse_date(filters.get("to_date"))
        clauses.append(f"DATE(date) >= DATE({ph})")
        params.append(from_date)
        clauses.append(f"DATE(date) <= DATE({ph})")
        params.append(to_date)
        status = str(filters.get("status") or "All")
        if status != "All":
            clauses.append(f"status = {ph}")
            params.append(status)
        search = str(filters.get("search") or "").strip()
        if search:
            clauses.append(f"LOWER(creditor_name) LIKE LOWER({ph})")
            params.append(f"%{search}%")
        query = f"""
            SELECT id, po_number, date, creditor_name, grand_total, status
            FROM purchase_orders
            WHERE {' AND '.join(clauses)}
            ORDER BY date DESC, po_number DESC
            LIMIT 500
        """
        rows = self.db.execute_query(query, tuple(params)) or []
        return {"success": True, "message": "", "rows": rows}

    def _run_sales_profit_book(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.sales_profit_book_logic import SalesProfitBookLogic

        logic = SalesProfitBookLogic(self.db)
        result = logic.get_bill_wise(
            company_id,
            self._parse_date(filters.get("from_date")),
            self._parse_date(filters.get("to_date")),
            filters={"search": filters.get("search")},
        )
        return self._rows_from_logic_result(result)

    def _run_cash_tender_history(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        ph = self.db._get_placeholder()
        query = f"""
            SELECT bill_no, bill_amount, cash_received, balance_returned, payment_mode, created_at
            FROM cash_tender_history
            WHERE company_id = {ph}
              AND DATE(created_at) >= DATE({ph})
              AND DATE(created_at) <= DATE({ph})
            ORDER BY created_at DESC
        """
        params = (
            company_id,
            self._parse_date(filters.get("from_date")),
            self._parse_date(filters.get("to_date")),
        )
        rows = self.db.execute_query(query, params) or []
        return {"success": True, "message": "", "rows": rows}

    def _run_daily_stock_register(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.daily_stock_register_logic import DailyStockRegisterLogic

        logic = DailyStockRegisterLogic(self.db)
        product_name = str(filters.get("product") or "").strip()
        product_id = None
        if product_name:
            ph = self.db._get_placeholder()
            product_rows = self.db.execute_query(
                f"""
                SELECT id
                FROM products
                WHERE company_id = {ph}
                  AND LOWER(name) LIKE LOWER({ph})
                ORDER BY LOWER(name)
                LIMIT 1
                """,
                (company_id, f"%{product_name}%"),
            ) or []
            if product_rows:
                product_id = int(product_rows[0].get("id"))
        movement_type = str(filters.get("voucher_type") or "All")
        voucher_type = None if movement_type == "All" else movement_type
        rows = logic.get_stock_register_data(
            company_id,
            self._parse_date(filters.get("from_date")),
            self._parse_date(filters.get("to_date")),
            product_id=product_id,
            voucher_type=voucher_type,
        )
        return {"success": True, "message": "", "rows": rows}

    def _run_price_list(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        ph = self.db._get_placeholder()
        search = str(filters.get("search") or "").strip()
        clauses = [f"company_id = {ph}"]
        params: list[Any] = [company_id]
        if search:
            clauses.append(f"(LOWER(name) LIKE LOWER({ph}) OR LOWER(COALESCE(barcode, '')) LIKE LOWER({ph}))")
            params.extend([f"%{search}%", f"%{search}%"])
        query = f"""
            SELECT name, barcode, category, unit, sale_price, wholesale_rate, mrp, quantity
            FROM products
            WHERE {' AND '.join(clauses)}
            ORDER BY LOWER(name)
            LIMIT 500
        """
        rows = self.db.execute_query(query, tuple(params)) or []
        return {"success": True, "message": "", "rows": rows}

    def _run_gst_sales_report(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        return self._run_voucher_book(
            company_id,
            {"logic_key": "sales-book", "slug": "gst-sales-report"},
            {**filters, "report_mode": "Tax Summary"},
        )

    def _run_gst_purchase_report(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        return self._run_voucher_book(
            company_id,
            {"logic_key": "purchase-book", "slug": "gst-purchase-report"},
            {**filters, "report_mode": "Tax Summary"},
        )

    def _run_daily_collection(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        ph = self.db._get_placeholder()
        query = f"""
            SELECT invoice_date, invoice_number, party_id, grand_total, amount_received, payment_mode
            FROM sales
            WHERE company_id = {ph}
              AND DATE(invoice_date) >= DATE({ph})
              AND DATE(invoice_date) <= DATE({ph})
              AND COALESCE(amount_received, 0) > 0
            ORDER BY invoice_date DESC, invoice_number DESC
        """
        rows = self.db.execute_query(
            query,
            (
                company_id,
                self._parse_date(filters.get("from_date")),
                self._parse_date(filters.get("to_date")),
            ),
        ) or []
        return {"success": True, "message": "", "rows": rows}

    def _run_stock_value(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.stock_value_logic import StockValueLogic

        logic = StockValueLogic(self.db)
        result = logic.get_stock_valuation(company_id)
        if isinstance(result, dict):
            return self._rows_from_logic_result(result)
        rows = result if isinstance(result, list) else []
        return {"success": True, "message": "", "rows": rows}

    def _run_best_sellers(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        ph = self.db._get_placeholder()
        query = f"""
            SELECT p.name AS product_name,
                   SUM(COALESCE(si.quantity, 0)) AS total_qty,
                   SUM(COALESCE(si.grand_total, 0)) AS total_amount
            FROM sales_items si
            INNER JOIN sales s ON s.id = si.sale_id
            INNER JOIN products p ON p.id = si.product_id
            WHERE s.company_id = {ph}
              AND DATE(s.invoice_date) >= DATE({ph})
              AND DATE(s.invoice_date) <= DATE({ph})
            GROUP BY p.id, p.name
            ORDER BY total_qty DESC
            LIMIT 100
        """
        rows = self.db.execute_query(
            query,
            (
                company_id,
                self._parse_date(filters.get("from_date")),
                self._parse_date(filters.get("to_date")),
            ),
        ) or []
        return {"success": True, "message": "", "rows": rows}

    def _run_salesman_book(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        ph = self.db._get_placeholder()
        query = f"""
            SELECT COALESCE(salesman, 'Unassigned') AS salesman,
                   COUNT(*) AS bill_count,
                   SUM(COALESCE(grand_total, 0)) AS total_sales
            FROM sales
            WHERE company_id = {ph}
              AND DATE(invoice_date) >= DATE({ph})
              AND DATE(invoice_date) <= DATE({ph})
            GROUP BY COALESCE(salesman, 'Unassigned')
            ORDER BY total_sales DESC
        """
        rows = self.db.execute_query(
            query,
            (
                company_id,
                self._parse_date(filters.get("from_date")),
                self._parse_date(filters.get("to_date")),
            ),
        ) or []
        return {"success": True, "message": "", "rows": rows}
