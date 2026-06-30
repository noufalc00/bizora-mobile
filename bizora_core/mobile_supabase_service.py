"""
Supabase-backed mobile web reads for use when the desktop app is closed.

Uses data previously synced by sync_service.py into Supabase tables.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from bizora_core.mobile_supabase_metrics import (
    calculate_day_credit_sales,
    calculate_net_realized_sale,
    calculate_sundry_group_balance_total,
)
from bizora_core.mobile_supabase_reports import (
    UNSUPPORTED_CLOUD_MESSAGE,
    get_report_source,
)
from bizora_core.mobile_web_registry import build_navigation_payload, get_route_definition
from config import CURRENCY_SYMBOL
from sync_service import get_supabase_client
from utils.color_tokens import build_theme_payload


class MobileSupabaseService:
    """Read-only mobile API backed by Supabase REST instead of local SQLite."""

    def _client(self):
        client = get_supabase_client()
        if client is None:
            raise RuntimeError(
                "Supabase is not configured. Set SUPABASE_URL and SERVICE_KEY in .env"
            )
        return client

    def resolve_company_id(self) -> Optional[int]:
        """Resolve the company used for cloud mobile views."""
        import os

        forced = (os.getenv("MOBILE_COMPANY_ID") or "").strip()
        if forced.isdigit():
            return int(forced)

        try:
            response = (
                self._client()
                .table("companies")
                .select("id,business_name,is_active")
                .order("id")
                .limit(20)
                .execute()
            )
            rows = response.data or []
            active_rows = [row for row in rows if row.get("is_active")]
            chosen = active_rows[0] if active_rows else (rows[0] if rows else None)
            if chosen and chosen.get("id"):
                return int(chosen["id"])
        except Exception as exc:
            print(f"[MOBILE-SUPABASE] Company resolve failed: {exc}")
        return None

    def _fetch_table(
        self,
        table_name: str,
        company_id: int,
        *,
        select: str = "*",
        limit: int = 1000,
        order_col: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Fetch one company-scoped table from Supabase."""
        query = (
            self._client()
            .table(table_name)
            .select(select)
            .eq("company_id", company_id)
            .limit(limit)
        )
        if order_col:
            query = query.order(order_col, desc=True)
        return query.execute().data or []

    @staticmethod
    def _financial_year_range(today: date) -> tuple[date, date]:
        """Return a simple Indian financial year range Apr 1 to Mar 31."""
        if today.month >= 4:
            start = date(today.year, 4, 1)
            end = date(today.year + 1, 3, 31)
        else:
            start = date(today.year - 1, 4, 1)
            end = date(today.year, 3, 31)
        return start, min(today, end)

    def get_theme_payload(self, theme_name: Optional[str] = None) -> dict[str, Any]:
        """Return desktop color tokens without Qt or local SQLite."""
        return build_theme_payload(theme_name, CURRENCY_SYMBOL)

    def get_navigation(self) -> dict[str, Any]:
        """Return the same Books/Reports navigation tree."""
        return {"success": True, "sections": build_navigation_payload(), "data_source": "supabase"}

    def get_dashboard_payload(self, company_id: Optional[int] = None) -> dict[str, Any]:
        """Build a dashboard snapshot from synced Supabase business tables."""
        resolved_id = company_id or self.resolve_company_id()
        if not resolved_id:
            return {
                "success": False,
                "message": "No company found in Supabase. Sync data from the desktop app first.",
                "company_id": None,
                "summary": MobileSupabaseService._empty_metrics_fallback(),
                "sales_chart": [],
                "purchase_chart": [],
                "recent_activity": [],
                "data_source": "supabase",
            }

        today = date.today()
        today_text = today.isoformat()
        fy_start, fy_end = self._financial_year_range(today)
        summary = MobileSupabaseService._empty_metrics_fallback()
        recent_activity: list[str] = []
        sales_rows: list[dict[str, Any]] = []
        purchases_rows: list[dict[str, Any]] = []

        try:
            sales_rows = self._fetch_table(
                "sales",
                resolved_id,
                select="company_id,invoice_number,invoice_date,grand_total,sales_type,payment_mode,status",
                limit=500,
                order_col="invoice_date",
            )
            purchases_rows = self._fetch_table(
                "purchases",
                resolved_id,
                select="company_id,purchase_number,purchase_date,grand_total,status",
                limit=300,
                order_col="purchase_date",
            )
            sales_return_rows = self._fetch_table(
                "sales_returns",
                resolved_id,
                select="company_id,return_date,grand_total,status",
                limit=300,
                order_col="return_date",
            )
            ledger_accounts = self._fetch_table(
                "ledger_accounts",
                resolved_id,
                select="id,company_id,account_name,group_name,opening_balance,opening_balance_type,is_active",
                limit=500,
            )
            ledger_entries = self._fetch_table(
                "ledger_entries",
                resolved_id,
                select="company_id,account_id,voucher_type,voucher_date,debit,credit",
                limit=5000,
                order_col="voucher_date",
            )

            summary = {
                "net_realized_sale": calculate_net_realized_sale(
                    sales_rows,
                    sales_return_rows,
                    resolved_id,
                    today_text,
                    today_text,
                ),
                "total_creditors": calculate_sundry_group_balance_total(
                    ledger_accounts,
                    ledger_entries,
                    resolved_id,
                    fy_start,
                    fy_end,
                    "Sundry Creditors",
                    "Cr",
                ),
                "total_debtors": calculate_sundry_group_balance_total(
                    ledger_accounts,
                    ledger_entries,
                    resolved_id,
                    fy_start,
                    fy_end,
                    "Sundry Debtors",
                    "Dr",
                ),
                "day_credit_sale": calculate_day_credit_sales(sales_rows, today_text),
            }

            for row in sales_rows[:5]:
                recent_activity.append(
                    f"Sale {row.get('invoice_number', '')} — ₹{float(row.get('grand_total') or 0):,.2f} ({row.get('invoice_date', '')})"
                )
            for row in purchases_rows[:3]:
                recent_activity.append(
                    f"Purchase {row.get('purchase_number', '')} — ₹{float(row.get('grand_total') or 0):,.2f} ({row.get('purchase_date', '')})"
                )

            sales_chart = self._monthly_totals(sales_rows, "invoice_date", "grand_total")
            purchase_chart = self._monthly_totals(purchases_rows, "purchase_date", "grand_total")
        except Exception as exc:
            return {
                "success": False,
                "message": f"Supabase dashboard read failed: {exc}",
                "company_id": resolved_id,
                "summary": summary,
                "sales_chart": [],
                "purchase_chart": [],
                "recent_activity": [],
                "data_source": "supabase",
            }

        return {
            "success": True,
            "message": "",
            "company_id": resolved_id,
            "sync_hint": (
                "No sales synced yet. On your PC run: python setup_supabase.py "
                "and python sync_bulk_to_supabase.py"
                if not sales_rows and not purchases_rows
                else ""
            ),
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
            "data_source": "supabase",
        }

    @staticmethod
    def _monthly_totals(rows: list[dict[str, Any]], date_key: str, amount_key: str) -> list[dict[str, Any]]:
        """Aggregate rows into the last six month buckets for mobile charts."""
        buckets: dict[str, float] = {}
        for row in rows:
            month = str(row.get(date_key) or "")[:7]
            if not month:
                continue
            buckets[month] = buckets.get(month, 0.0) + float(row.get(amount_key) or 0.0)
        labels = sorted(buckets.keys())[-6:]
        return [{"label": label, "total": round(buckets[label], 2)} for label in labels]

    def get_report_meta(self, slug: str) -> dict[str, Any]:
        """Return report filter metadata."""
        definition = get_route_definition(slug)
        if definition is None:
            return {"success": False, "message": f"Unknown route: {slug}"}

        lookups: dict[str, Any] = {}
        company_id = self.resolve_company_id()
        if company_id and slug == "ledger-statement":
            try:
                accounts = self._fetch_table(
                    "ledger_accounts",
                    company_id,
                    select="id,account_name,account_type,group_name",
                    limit=300,
                )
                lookups["accounts"] = [
                    {
                        "id": row.get("id"),
                        "account_name": row.get("account_name"),
                    }
                    for row in accounts
                    if row.get("id") is not None
                ]
            except Exception as exc:
                print(f"[MOBILE-SUPABASE] Account lookup failed: {exc}")

        return {
            "success": True,
            "route": definition,
            "lookups": lookups,
            "company_id": company_id,
            "data_source": "supabase",
        }

    def _apply_report_filters(
        self,
        slug: str,
        rows: list[dict[str, Any]],
        filters: dict[str, Any],
        date_col: Optional[str],
        filter_mode: Optional[str],
        company_id: int,
    ) -> list[dict[str, Any]]:
        """Apply date/search/account filters to cloud report rows."""
        from_date = str(filters.get("from_date") or "")[:10]
        to_date = str(filters.get("to_date") or "")[:10]
        search = str(filters.get("search") or "").strip().lower()

        if filter_mode == "account_id":
            account_id = str(filters.get("account_id") or "").strip()
            if account_id:
                rows = [row for row in rows if str(row.get("account_id")) == account_id]

        if filter_mode == "cash_bank":
            accounts = self._fetch_table(
                "ledger_accounts",
                company_id,
                select="id,account_type",
                limit=300,
            )
            cash_ids = {
                str(row.get("id"))
                for row in accounts
                if str(row.get("account_type") or "").lower() == "cash_bank"
            }
            rows = [row for row in rows if str(row.get("account_id")) in cash_ids]

        if filter_mode == "journal":
            rows = [
                row
                for row in rows
                if "journal" in str(row.get("voucher_type") or "").lower()
            ]

        if date_col:
            if from_date:
                rows = [row for row in rows if str(row.get(date_col) or "")[:10] >= from_date]
            if to_date:
                rows = [row for row in rows if str(row.get(date_col) or "")[:10] <= to_date]

        if search:
            rows = [row for row in rows if search in str(row).lower()]

        if slug in {"sales-book", "gst-sales-report", "bill-history"}:
            party = str(filters.get("party") or "").strip().lower()
            if party:
                rows = [row for row in rows if party in str(row).lower()]

        return rows

    def run_report(self, slug: str, filters: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Run a cloud report from synced Supabase tables."""
        definition = get_route_definition(slug)
        if definition is None:
            return {"success": False, "message": f"Unknown route: {slug}", "rows": []}

        company_id = self.resolve_company_id()
        if not company_id:
            return {"success": False, "message": "No company found in Supabase.", "rows": []}

        source = get_report_source(slug)
        if source is None:
            return {
                "success": False,
                "message": UNSUPPORTED_CLOUD_MESSAGE,
                "rows": [],
                "data_source": "supabase",
            }

        table_name, date_col, filter_mode = source
        filters = filters or {}

        try:
            rows = self._fetch_table(
                table_name,
                company_id,
                limit=1000,
                order_col=date_col,
            )
            rows = self._apply_report_filters(
                slug,
                rows,
                filters,
                date_col,
                filter_mode,
                company_id,
            )
            if not rows:
                return {
                    "success": True,
                    "message": "No records found for the selected filters.",
                    "rows": [],
                    "data_source": "supabase",
                }
            return {"success": True, "message": "", "rows": rows, "data_source": "supabase"}
        except Exception as exc:
            message = str(exc)
            if "Could not find the table" in message:
                message = (
                    f"Table '{table_name}' is missing in Supabase. "
                    "Run: python setup_supabase.py && python sync_bulk_to_supabase.py"
                )
            return {"success": False, "message": message, "rows": [], "data_source": "supabase"}

    @staticmethod
    def _empty_metrics_fallback() -> dict[str, float]:
        return {
            "net_realized_sale": 0.0,
            "total_creditors": 0.0,
            "total_debtors": 0.0,
            "day_credit_sale": 0.0,
        }
