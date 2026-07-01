"""
Mobile web service layer — reuses desktop dashboard and report logic.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

from config import CURRENCY_SYMBOL, active_company_manager
from db import Database, get_default_database_path
from bizora_core.mobile_report_lookups import build_local_report_lookups
from bizora_core.mobile_report_display import build_report_table_payload
from bizora_core.mobile_web_registry import (
    VOUCHER_BOOK_MODES,
    build_navigation_payload,
    get_route_definition,
)


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
        from bizora_core.dashboard_logic import DashboardLogic

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
        from utils.theme_manager import ThemeManager

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

                table_slug = str(result.get("render_slug") or slug)
                table_payload = build_slug_table_payload(
                    table_slug,
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
        """Bridge handler for Cash Book.

        `CashBookLogic.get_cash_book` returns its rows under `entries` (not
        `data`/`rows`), so the generic `_rows_from_logic_result` helper
        silently drops them into `meta`. That was the reason the web
        Cash Book table was empty before this fix. We extract `entries`
        explicitly and expose the desktop summary keys (opening balance,
        totals, closing balance) so the fast-path RPC and the bridge can
        be compared 1:1 by the QA harness.
        """
        from bizora_core.cash_book_logic import CashBookLogic

        logic = CashBookLogic(self.db)
        from_dt = date.fromisoformat(self._parse_date(filters.get("from_date")))
        to_dt = date.fromisoformat(self._parse_date(filters.get("to_date")))
        result = logic.get_cash_book(company_id, from_dt, to_dt)
        if not isinstance(result, dict):
            return {"success": False, "message": "Invalid Cash Book response", "rows": []}

        # `Decimal` values from cash_book_logic serialize badly through JSON.
        # Coerce to float here so the mobile UI (and the QA harness) sees
        # comparable numeric types on both sides.
        def _f(value: Any) -> float:
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                return 0.0

        rows = []
        for entry in result.get("entries") or []:
            row = dict(entry)
            row["debit"] = _f(row.get("debit"))
            row["credit"] = _f(row.get("credit"))
            row["running_balance"] = _f(row.get("running_balance"))
            rows.append(row)

        summary = {
            "opening_balance": _f(result.get("opening_balance")),
            "total_receipts": _f(result.get("total_receipts")),
            "total_payments": _f(result.get("total_payments")),
            "closing_balance": _f(result.get("closing_balance")),
        }

        return {
            "success": bool(result.get("success", True)),
            "message": str(result.get("message") or ""),
            "rows": rows,
            "summary": summary,
            "summary_labels": {
                "opening_balance": "Opening Balance",
                "total_receipts": "Total Receipts",
                "total_payments": "Total Payments",
                "closing_balance": "Closing Balance",
            },
        }

    def _run_ledger(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.ledger_logic import LedgerLogic
        from bizora_core.mobile_ledger_statement_rows import (
            DESKTOP_LEDGER_SUMMARY_LABELS,
            ledger_summary_totals,
            resolve_ledger_account_id,
        )

        account_id = resolve_ledger_account_id(filters)
        if account_id is not None:
            account_name = str(filters.get("account_name") or "").strip()
            if not account_name:
                account = LedgerLogic(self.db).get_account(company_id, account_id) or {}
                account_name = str(account.get("account_name") or "")
            detail = self._run_ledger_statement(
                company_id,
                _definition,
                {
                    **(filters or {}),
                    "account_id": account_id,
                    "account_name": account_name,
                },
            )
            detail["render_slug"] = "ledger-statement"
            return detail

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

        from bizora_core.mobile_supabase_ledger import filter_ledger_summary_rows

        rows = filter_ledger_summary_rows(rows, filters.get("search"))
        totals = ledger_summary_totals(rows)
        return {
            "success": True,
            "message": "",
            "rows": rows,
            "summary": totals,
            "summary_labels": {
                "opening_balance": "Opening",
                "period_debit": "Debit",
                "period_credit": "Credit",
            },
            "render_slug": "ledger",
        }

    def _run_ledger_statement(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        """Bridge handler for Ledger Statement (desktop detail grid parity)."""
        from bizora_core.ledger_logic import LedgerLogic
        from bizora_core.mobile_ledger_statement_rows import (
            DESKTOP_LEDGER_SUMMARY_LABELS,
            build_desktop_ledger_statement_payload,
        )

        account_id = filters.get("account_id")
        if not account_id:
            return {
                "success": False,
                "message": "Account is required.",
                "rows": [],
                "summary": {
                    "opening_balance": 0.0,
                    "period_debit": 0.0,
                    "period_credit": 0.0,
                    "closing_balance": 0.0,
                },
                "summary_labels": dict(DESKTOP_LEDGER_SUMMARY_LABELS),
            }
        try:
            account_id_int = int(account_id)
        except (TypeError, ValueError):
            return {
                "success": False,
                "message": f"Invalid account_id: {account_id!r}",
                "rows": [],
            }

        logic = LedgerLogic(self.db)
        from_dt = date.fromisoformat(self._parse_date(filters.get("from_date")))
        to_dt = date.fromisoformat(self._parse_date(filters.get("to_date")))
        result = logic.get_account_ledger(company_id, account_id_int, from_dt, to_dt)
        if not isinstance(result, dict):
            return {"success": False, "message": "Invalid Ledger response", "rows": []}

        account_name = str(filters.get("account_name") or "")
        payload = build_desktop_ledger_statement_payload(
            result,
            account_id=account_id_int,
            account_name=account_name,
        )
        return {
            "success": True,
            "message": "",
            "rows": payload["rows"],
            "summary": payload["summary"],
            "summary_labels": payload["summary_labels"],
            "ledger_statement_format": payload.get("ledger_statement_format"),
        }

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
        result = engine.generate_profit_and_loss(company_id, from_dt, to_dt) or {}
        rows: list[dict[str, Any]] = []

        def append_row(left_label: str, left_amount: float, right_label: str, right_amount: float, row_type: str = "") -> None:
            rows.append(
                {
                    "left_particulars": left_label,
                    "left_amount": left_amount or "",
                    "right_particulars": right_label,
                    "right_amount": right_amount or "",
                    "row_type": row_type,
                }
            )

        rows.append({"left_particulars": "TRADING ACCOUNT", "left_amount": "", "right_particulars": "", "right_amount": "", "row_type": "section"})
        left_rows = [(f"To {acc['account_name']}", acc['balance']) for acc in result.get("direct_expenses", [])]
        left_total = float(result.get("total_direct_expenses", 0) or 0)
        right_rows = [(f"By {acc['account_name']}", acc['balance']) for acc in result.get("direct_incomes", [])]
        right_total = float(result.get("total_direct_incomes", 0) or 0)
        gross_profit = float(result.get("gross_profit", 0) or 0)
        if gross_profit >= 0:
            left_rows.append(("To Gross Profit c/d", gross_profit))
            left_total += gross_profit
        else:
            right_rows.append(("By Gross Loss c/d", abs(gross_profit)))
            right_total += abs(gross_profit)
        final_total = max(left_total, right_total)
        for i in range(max(len(left_rows), len(right_rows))):
            ll, la = left_rows[i] if i < len(left_rows) else ("", 0)
            rl, ra = right_rows[i] if i < len(right_rows) else ("", 0)
            append_row(ll, la, rl, ra)
        append_row("Total", final_total, "Total", final_total, "total")

        rows.append({"left_particulars": "PROFIT & LOSS ACCOUNT", "left_amount": "", "right_particulars": "", "right_amount": "", "row_type": "section"})
        left_rows = [(f"To {acc['account_name']}", acc['balance']) for acc in result.get("indirect_expenses", [])]
        left_total = float(result.get("total_indirect_expenses", 0) or 0)
        if gross_profit >= 0:
            right_rows = [("By Gross Profit b/d", gross_profit)]
            right_total = gross_profit
        else:
            left_rows.append(("To Gross Loss b/d", abs(gross_profit)))
            left_total += abs(gross_profit)
            right_rows = []
            right_total = 0.0
        for acc in result.get("indirect_incomes", []):
            right_rows.append((f"By {acc['account_name']}", acc['balance']))
        right_total += float(result.get("total_indirect_incomes", 0) or 0)
        net_profit = float(result.get("net_profit", 0) or 0)
        if net_profit >= 0:
            left_rows.append(("To Net Profit", net_profit))
            left_total += net_profit
        else:
            right_rows.append(("By Net Loss", abs(net_profit)))
            right_total += abs(net_profit)
        final_total = max(left_total, right_total)
        for i in range(max(len(left_rows), len(right_rows))):
            ll, la = left_rows[i] if i < len(left_rows) else ("", 0)
            rl, ra = right_rows[i] if i < len(right_rows) else ("", 0)
            append_row(ll, la, rl, ra)
        append_row("Total", final_total, "Total", final_total, "total")

        summary = {
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "total_direct_incomes": result.get("total_direct_incomes", 0),
            "total_direct_expenses": result.get("total_direct_expenses", 0),
            "total_indirect_incomes": result.get("total_indirect_incomes", 0),
            "total_indirect_expenses": result.get("total_indirect_expenses", 0),
        }
        return {
            "success": True,
            "message": "",
            "rows": rows,
            "meta": result,
            "summary": summary,
            "summary_labels": {
                "gross_profit": "Gross Profit",
                "net_profit": "Net Profit",
                "total_direct_incomes": "Direct Incomes",
                "total_direct_expenses": "Direct Expenses",
                "total_indirect_incomes": "Indirect Incomes",
                "total_indirect_expenses": "Indirect Expenses",
            },
        }

    def _run_balance_sheet(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.financial_reporting_engine import FinancialReportingEngine

        engine = FinancialReportingEngine(self.db)
        as_of = date.fromisoformat(self._parse_date(filters.get("as_of_date") or filters.get("to_date")))
        result = engine.generate_balance_sheet(company_id, as_of) or {}

        left_rows: list[tuple[str, float]] = []
        for acc in result.get("capital_accounts", []) or []:
            left_rows.append((acc.get("account_name", ""), float(acc.get("balance") or 0)))
        net_profit = float(result.get("net_profit", 0) or 0)
        if net_profit >= 0:
            left_rows.append(("Add: Net Profit", net_profit))
        else:
            left_rows.append(("Less: Net Loss", abs(net_profit)))
        for acc in result.get("current_liabilities", []) or []:
            left_rows.append((acc.get("account_name", ""), float(acc.get("balance") or 0)))

        right_rows: list[tuple[str, float]] = []
        for acc in result.get("fixed_assets", []) or []:
            right_rows.append((acc.get("account_name", ""), float(acc.get("balance") or 0)))
        for acc in result.get("current_assets", []) or []:
            right_rows.append((acc.get("account_name", ""), float(acc.get("balance") or 0)))

        left_total = abs(float(result.get("adjusted_capital", 0) or 0) + float(result.get("total_liabilities", 0) or 0))
        right_total = abs(float(result.get("total_assets", 0) or 0))
        left_rows.append(("Total", left_total))
        right_rows.append(("Total", right_total))

        rows: list[dict[str, Any]] = []
        for i in range(max(len(left_rows), len(right_rows))):
            ll, la = left_rows[i] if i < len(left_rows) else ("", 0)
            rl, ra = right_rows[i] if i < len(right_rows) else ("", 0)
            row_type = "total" if (ll == "Total" or rl == "Total") else ""
            rows.append(
                {
                    "left_particulars": ll,
                    "left_amount": la or "",
                    "right_particulars": rl,
                    "right_amount": ra or "",
                    "row_type": row_type,
                }
            )

        return {
            "success": True,
            "message": "",
            "rows": rows,
            "meta": result,
            "summary": {
                "net_profit": net_profit,
                "total_assets": result.get("total_assets", 0),
                "total_liabilities": result.get("total_liabilities", 0),
                "adjusted_capital": result.get("adjusted_capital", 0),
            },
            "summary_labels": {
                "net_profit": "Net Profit",
                "total_assets": "Total Assets",
                "total_liabilities": "Total Liabilities",
                "adjusted_capital": "Adjusted Capital",
            },
        }

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
        report = logic.generate_gstr1_report(
            company_id,
            self._parse_date(filters.get("from_date")),
            self._parse_date(filters.get("to_date")),
        )
        rows = []
        for item in report.get("hsn", []) if isinstance(report, dict) else []:
            rows.append(
                {
                    "hsn": item.get("hsn", ""),
                    "description": item.get("desc", ""),
                    "uqc": item.get("uqc", ""),
                    "quantity": item.get("qty", 0),
                    "taxable_amount": item.get("val", 0),
                    "igst_amount": item.get("iamt", 0),
                    "cgst_amount": item.get("camt", 0),
                    "sgst_amount": item.get("samt", 0),
                    "cess_amount": item.get("csamt", 0),
                    "tax_percent": item.get("rt", 0),
                }
            )
        return {
            "success": True,
            "message": "",
            "rows": rows,
            "meta": report if isinstance(report, dict) else {},
        }

    def _run_monthly_analysis(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        from bizora_core.monthly_analysis_logic import MonthlyAnalysisLogic
        from utils.financial_year import get_working_financial_year_label

        logic = MonthlyAnalysisLogic(self.db)
        fy = str(filters.get("financial_year") or "").strip()
        if not fy:
            fy = get_working_financial_year_label() or ""
        if not fy:
            today = date.today()
            start_year = today.year if today.month >= 4 else today.year - 1
            fy = f"{start_year}-{str(start_year + 1)[-2:]}"
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
        payload = self._rows_from_logic_result(result)
        rows = payload.get("rows") or []
        for row in rows:
            if row.get("month_name") and not row.get("month_label"):
                row["month_label"] = f"{row.get('month_name')} {row.get('year', '')}".strip()
        payload["rows"] = rows
        return payload

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
        mode_label = str(filters.get("report_mode") or "Bill Wise Profit")
        method_map = {
            "Bill Wise Profit": "get_bill_wise",
            "Party Wise Profit": "get_party_wise",
            "Item Wise Profit": "get_item_wise",
        }
        method_name = method_map.get(mode_label, "get_bill_wise")
        method = getattr(logic, method_name, None)
        if method is None:
            return {"success": False, "message": f"Missing method {method_name}", "rows": []}
        result = method(
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
            WHERE DATE(created_at) >= DATE({ph})
              AND DATE(created_at) <= DATE({ph})
            ORDER BY created_at DESC
        """
        params = (
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
        shaped = []
        for row in rows:
            shaped.append(
                {
                    "item_code": row.get("barcode", ""),
                    "product_name": row.get("name", ""),
                    "current_stock": row.get("quantity", 0),
                    "purchase_rate": row.get("purchase_rate", 0),
                    "sales_rate": row.get("sale_price", 0),
                    "wholesale_rate": row.get("wholesale_rate", 0),
                    "mrp": row.get("mrp", 0),
                }
            )
        return {"success": True, "message": "", "rows": shaped}

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
            SELECT s.invoice_date AS collection_date,
                   COALESCE(p.name, 'Cash Customer') AS party_name,
                   s.amount_received AS amount,
                   s.payment_mode
            FROM sales s
            LEFT JOIN parties p ON p.id = s.party_id
            WHERE s.company_id = {ph}
              AND DATE(s.invoice_date) >= DATE({ph})
              AND DATE(s.invoice_date) <= DATE({ph})
              AND COALESCE(s.amount_received, 0) > 0
            ORDER BY s.invoice_date DESC, s.invoice_number DESC
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
                   SUM(COALESCE(si.quantity, 0)) AS quantity_sold,
                   SUM(COALESCE(si.grand_total, 0)) AS revenue
            FROM sales_items si
            INNER JOIN sales s ON s.id = si.sale_id
            INNER JOIN products p ON p.id = si.product_id
            WHERE s.company_id = {ph}
              AND DATE(s.invoice_date) >= DATE({ph})
              AND DATE(s.invoice_date) <= DATE({ph})
            GROUP BY p.id, p.name
            ORDER BY quantity_sold DESC
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
        for index, row in enumerate(rows, start=1):
            row["rank"] = index
        return {"success": True, "message": "", "rows": rows}

    def _run_salesman_book(self, company_id: int, _definition: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        ph = self.db._get_placeholder()
        query = f"""
            SELECT COALESCE(salesman, 'Unassigned') AS salesman_name,
                   COUNT(*) AS bill_count,
                   SUM(COALESCE(grand_total, 0)) AS net_sales
            FROM sales
            WHERE company_id = {ph}
              AND DATE(invoice_date) >= DATE({ph})
              AND DATE(invoice_date) <= DATE({ph})
            GROUP BY COALESCE(salesman, 'Unassigned')
            ORDER BY net_sales DESC
        """
        rows = self.db.execute_query(
            query,
            (
                company_id,
                self._parse_date(filters.get("from_date")),
                self._parse_date(filters.get("to_date")),
            ),
        ) or []
        for row in rows:
            bill_count = float(row.get("bill_count") or 0)
            net_sales = float(row.get("net_sales") or 0)
            row["avg_bill_value"] = round(net_sales / bill_count, 2) if bill_count else 0.0
        return {"success": True, "message": "", "rows": rows}
