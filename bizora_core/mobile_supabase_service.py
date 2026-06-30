"""
Supabase-backed mobile web reads for use when the desktop app is closed.

Uses data previously synced by sync_service.py into Supabase tables.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from bizora_core.mobile_web_registry import build_navigation_payload, get_route_definition
from config import CURRENCY_SYMBOL
from sync_service import get_supabase_client
from utils.color_tokens import build_theme_payload


class MobileSupabaseService:
    """Read-only mobile API backed by Supabase REST instead of local SQLite."""

    def __init__(self) -> None:
        pass

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

    def get_theme_payload(self, theme_name: Optional[str] = None) -> dict[str, Any]:
        """Return desktop color tokens without Qt or local SQLite."""
        return build_theme_payload(theme_name, CURRENCY_SYMBOL)

    def get_navigation(self) -> dict[str, Any]:
        """Return the same Books/Reports navigation tree."""
        return {"success": True, "sections": build_navigation_payload(), "data_source": "supabase"}

    def get_dashboard_payload(self, company_id: Optional[int] = None) -> dict[str, Any]:
        """Build a dashboard snapshot from synced Supabase sales/purchase rows."""
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

        today = date.today().isoformat()
        summary = {
            "net_realized_sale": 0.0,
            "total_creditors": 0.0,
            "total_debtors": 0.0,
            "day_credit_sale": 0.0,
        }
        recent_activity: list[str] = []
        sales_rows: list[dict[str, Any]] = []
        purchases_rows: list[dict[str, Any]] = []

        try:
            sales_rows = (
                self._client()
                .table("sales")
                .select("invoice_number,invoice_date,grand_total,sales_type,payment_mode")
                .eq("company_id", resolved_id)
                .order("invoice_date", desc=True)
                .limit(100)
                .execute()
                .data
                or []
            )
            purchases_rows = (
                self._client()
                .table("purchases")
                .select("purchase_number,purchase_date,grand_total")
                .eq("company_id", resolved_id)
                .order("purchase_date", desc=True)
                .limit(50)
                .execute()
                .data
                or []
            )

            for row in sales_rows:
                amount = float(row.get("grand_total") or 0.0)
                invoice_date = str(row.get("invoice_date") or "")[:10]
                if invoice_date == today:
                    summary["net_realized_sale"] += amount
                    payment_mode = str(row.get("payment_mode") or "").lower()
                    sales_type = str(row.get("sales_type") or "").lower()
                    if "credit" in payment_mode or "credit" in sales_type:
                        summary["day_credit_sale"] += amount

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
                "No sales synced yet. On your PC run: python sync_bulk_to_supabase.py"
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
        return {
            "success": True,
            "route": definition,
            "lookups": {},
            "company_id": self.resolve_company_id(),
            "data_source": "supabase",
        }

    def run_report(self, slug: str, filters: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Run a limited cloud report from synced Supabase tables."""
        definition = get_route_definition(slug)
        if definition is None:
            return {"success": False, "message": f"Unknown route: {slug}", "rows": []}

        company_id = self.resolve_company_id()
        if not company_id:
            return {"success": False, "message": "No company found in Supabase.", "rows": []}

        filters = filters or {}
        from_date = str(filters.get("from_date") or "")[:10]
        to_date = str(filters.get("to_date") or "")[:10]
        table_name = None
        date_col = None
        if slug in {"sales-book", "gst-sales-report", "bill-history"}:
            table_name = "sales"
            date_col = "invoice_date"
        elif slug in {"purchase-book", "gst-purchase-report"}:
            table_name = "purchases"
            date_col = "purchase_date"

        if not table_name:
            return {
                "success": False,
                "message": (
                    "This report is not synced to Supabase yet. "
                    "Open the desktop app to sync more tables, or use local mode."
                ),
                "rows": [],
                "data_source": "supabase",
            }

        try:
            query = (
                self._client()
                .table(table_name)
                .select("*")
                .eq("company_id", company_id)
                .order(date_col, desc=True)
                .limit(300)
            )
            rows = query.execute().data or []
            if from_date:
                rows = [row for row in rows if str(row.get(date_col) or "")[:10] >= from_date]
            if to_date:
                rows = [row for row in rows if str(row.get(date_col) or "")[:10] <= to_date]
            search = str(filters.get("search") or "").strip().lower()
            if search:
                rows = [
                    row for row in rows
                    if search in str(row).lower()
                ]
            return {"success": True, "message": "", "rows": rows, "data_source": "supabase"}
        except Exception as exc:
            return {"success": False, "message": str(exc), "rows": [], "data_source": "supabase"}

    @staticmethod
    def _empty_metrics_fallback() -> dict[str, float]:
        return {
            "net_realized_sale": 0.0,
            "total_creditors": 0.0,
            "total_debtors": 0.0,
            "day_credit_sale": 0.0,
        }
