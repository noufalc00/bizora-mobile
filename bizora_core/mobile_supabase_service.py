"""
Supabase-backed mobile web reads for use when the desktop app is closed.

Uses data previously synced by sync_service.py into Supabase tables.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from bizora_core.mobile_report_lookups import build_supabase_report_lookups
from bizora_core.mobile_supabase_charts import build_monthly_chart_series
from bizora_core.mobile_supabase_ledger import (
    build_account_summary,
    filter_accounts_for_view,
)
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
from utils.date_display import format_display_date


class MobileSupabaseService:
    """Read-only mobile API backed by Supabase REST instead of local SQLite."""

    def _client(self):
        client = get_supabase_client()
        if client is None:
            raise RuntimeError(
                "Supabase is not configured. Set SUPABASE_URL and SERVICE_KEY in .env"
            )
        return client

    def resolve_company_id(self, override_id: Optional[int] = None) -> Optional[int]:
        """Resolve the company used for cloud mobile views."""
        if override_id:
            return int(override_id)
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

    _COMPANY_BASE_COLUMNS = (
        "id,business_name,gstin,phone_number,email,state,is_active"
    )

    def _fetch_company_rows(
        self,
        *,
        company_id: Optional[int] = None,
        active_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch company rows from Supabase, with visibility when the column exists."""
        try:
            query = (
                self._client()
                .table("companies")
                .select(f"{self._COMPANY_BASE_COLUMNS},visibility")
                .limit(limit)
            )
        except Exception as exc:
            print(f"[MOBILE-SUPABASE] Company query init failed: {exc}")
            return []

        if company_id is not None:
            query = query.eq("id", company_id)
        if active_only:
            query = query.eq("is_active", True)
        if company_id is None:
            query = query.order("id")

        try:
            rows = query.execute().data or []
        except Exception as exc:
            message = str(exc)
            if "visibility" not in message:
                print(f"[MOBILE-SUPABASE] Company query failed: {exc}")
                return []
            fallback = (
                self._client()
                .table("companies")
                .select(self._COMPANY_BASE_COLUMNS)
                .limit(limit)
            )
            if company_id is not None:
                fallback = fallback.eq("id", company_id)
            if active_only:
                fallback = fallback.eq("is_active", True)
            if company_id is None:
                fallback = fallback.order("id")
            rows = fallback.execute().data or []
            for row in rows:
                row["visibility"] = "normal"

        return rows

    @staticmethod
    def _public_company_row(row: dict[str, Any]) -> dict[str, Any]:
        """Return a safe company payload for the mobile login UI."""
        return {
            "id": row.get("id"),
            "business_name": row.get("business_name") or "",
            "gstin": row.get("gstin") or "",
            "phone_number": row.get("phone_number") or "",
            "email": row.get("email") or "",
            "state": row.get("state") or "",
            "is_active": bool(row.get("is_active")),
            "visibility": str(row.get("visibility") or "normal").strip().lower(),
        }

    def list_companies(self, visibility: Optional[str] = None) -> dict[str, Any]:
        """List synced companies available for cloud mobile login."""
        try:
            rows = self._fetch_company_rows()
            if visibility:
                pool = visibility.strip().lower()
                rows = [
                    row for row in rows
                    if str(row.get("visibility") or "normal").strip().lower() == pool
                ]
            companies = [self._public_company_row(row) for row in rows]
            return {"success": True, "companies": companies}
        except Exception as exc:
            return {"success": False, "message": str(exc), "companies": []}

    def get_bootstrap(self, last_company_id: Optional[int] = None) -> dict[str, Any]:
        """Return the active normal company for the cloud login screen."""
        try:
            import os

            rows = self._fetch_company_rows(limit=50)
            normal_rows = [
                row for row in rows
                if str(row.get("visibility") or "normal").strip().lower() == "normal"
            ]
            chosen = None
            if last_company_id is not None:
                chosen = next(
                    (row for row in normal_rows if int(row.get("id") or 0) == int(last_company_id)),
                    None,
                )
            if chosen is None:
                forced = (os.getenv("MOBILE_COMPANY_ID") or "").strip()
                if forced.isdigit():
                    chosen = next(
                        (row for row in normal_rows if int(row.get("id") or 0) == int(forced)),
                        None,
                    )
            if chosen is None:
                active_rows = [row for row in normal_rows if row.get("is_active")]
                chosen = active_rows[0] if active_rows else (normal_rows[0] if normal_rows else None)
            company = self._public_company_row(chosen) if chosen else None
            return {
                "success": True,
                "company": company,
                "usernames": ["admin"],
            }
        except Exception as exc:
            return {"success": False, "message": str(exc), "company": None, "usernames": []}

    def cloud_login(self, company_id: int, username: str, *, is_secret: bool = False) -> dict[str, Any]:
        """Open a synced company for read-only cloud mobile access."""
        try:
            rows = self._fetch_company_rows(company_id=company_id, limit=1)
            if not rows:
                return {"success": False, "message": "Company not found in Supabase."}
            company = rows[0]
            public_company = self._public_company_row(company)
            return {
                "success": True,
                "message": "",
                "session": {
                    "company_id": int(company.get("id") or company_id),
                    "company_name": company.get("business_name") or "",
                    "username": str(username or "admin").strip() or "admin",
                    "role": "Admin",
                    "is_secret": bool(is_secret),
                },
                "company": public_company,
            }
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def _fetch_table(
        self,
        table_name: str,
        company_id: int,
        *,
        select: str = "*",
        limit: int = 1000,
        order_col: Optional[str] = None,
        company_scoped: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch one company-scoped table from Supabase."""
        query = self._client().table(table_name).select(select).limit(limit)
        if company_scoped:
            query = query.eq("company_id", company_id)
        if order_col:
            query = query.order(order_col, desc=True)
        try:
            return query.execute().data or []
        except Exception as exc:
            message = str(exc)
            if company_scoped and "company_id does not exist" in message:
                fallback = (
                    self._client()
                    .table(table_name)
                    .select(select)
                    .limit(limit)
                )
                if order_col:
                    fallback = fallback.order(order_col, desc=True)
                return fallback.execute().data or []
            if "Could not find the table" in message:
                print(
                    f"[MOBILE-SUPABASE] Table '{table_name}' missing. "
                    "Run: python setup_supabase.py && python sync_bulk_to_supabase.py"
                )
                return []
            raise

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
        resolved_id = self.resolve_company_id(company_id)
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
                limit=2000,
                order_col="invoice_date",
            )
            purchases_rows = self._fetch_table(
                "purchases",
                resolved_id,
                select="company_id,purchase_number,purchase_date,grand_total,status",
                limit=2000,
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
                invoice_date = format_display_date(row.get("invoice_date", ""))
                recent_activity.append(
                    f"Sale {row.get('invoice_number', '')} — ₹{float(row.get('grand_total') or 0):,.2f} ({invoice_date})"
                )
            for row in purchases_rows[:3]:
                purchase_date = format_display_date(row.get("purchase_date", ""))
                recent_activity.append(
                    f"Purchase {row.get('purchase_number', '')} — ₹{float(row.get('grand_total') or 0):,.2f} ({purchase_date})"
                )

            sales_chart = build_monthly_chart_series(
                sales_rows,
                date_column="invoice_date",
                amount_column="grand_total",
            )
            purchase_chart = build_monthly_chart_series(
                purchases_rows,
                date_column="purchase_date",
                amount_column="grand_total",
            )
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

    def get_report_meta(self, slug: str, company_id: Optional[int] = None) -> dict[str, Any]:
        """Return report filter metadata."""
        definition = get_route_definition(slug)
        if definition is None:
            return {"success": False, "message": f"Unknown route: {slug}"}

        resolved_id = self.resolve_company_id(company_id)
        lookups: dict[str, Any] = {}
        if resolved_id:
            try:
                lookups = build_supabase_report_lookups(self._fetch_table, resolved_id, slug)
            except Exception as exc:
                print(f"[MOBILE-SUPABASE] Lookup build failed: {exc}")

        return {
            "success": True,
            "route": definition,
            "lookups": lookups,
            "company_id": resolved_id,
            "data_source": "supabase",
        }

    @staticmethod
    def _movement_row_date(row: dict[str, Any]) -> str:
        """Return ISO date for a stock movement row."""
        return str(row.get("movement_date") or row.get("created_at") or "")[:10]

    def _run_cloud_ledger(self, company_id: int, filters: dict[str, Any]) -> dict[str, Any]:
        """Run ledger summary views from synced accounts and entries."""
        from_date = date.fromisoformat(str(filters.get("from_date") or date.today())[:10])
        to_date = date.fromisoformat(str(filters.get("to_date") or date.today())[:10])
        view = str(filters.get("ledger_view") or "General")

        ledger_accounts = self._fetch_table(
            "ledger_accounts",
            company_id,
            select="id,company_id,account_name,account_type,group_name,opening_balance,opening_balance_type,is_active",
            limit=1000,
        )
        parties = self._fetch_table(
            "parties",
            company_id,
            select="id,party_type,name",
            limit=1000,
        )
        entries = self._fetch_table(
            "ledger_entries",
            company_id,
            select="company_id,account_id,voucher_type,voucher_date,debit,credit",
            limit=10000,
            order_col="voucher_date",
        )
        accounts = filter_accounts_for_view(ledger_accounts, parties, view)
        rows = build_account_summary(accounts, entries, company_id, from_date, to_date)

        search = str(filters.get("search") or "").strip().lower()
        if search:
            rows = [
                row for row in rows
                if search in str(row.get("account_name", "")).lower()
            ]
        return {"success": True, "message": "", "rows": rows, "data_source": "supabase"}

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

        if filter_mode == "pdc":
            transaction_type = str(filters.get("transaction_type") or "All")
            if transaction_type != "All":
                rows = [
                    row for row in rows
                    if str(row.get("transaction_type") or "") == transaction_type
                ]
            status = str(filters.get("status") or "All")
            if status != "All":
                rows = [
                    row for row in rows
                    if str(row.get("status") or "") == status
                ]
            party = str(filters.get("party") or "").strip().lower()
            if party:
                rows = [row for row in rows if party in str(row).lower()]

        if filter_mode == "purchase_order":
            status = str(filters.get("status") or "All")
            if status != "All":
                rows = [
                    row for row in rows
                    if str(row.get("status") or "") == status
                ]
            if search:
                rows = [
                    row for row in rows
                    if search in str(row.get("creditor_name") or "").lower()
                ]

        if filter_mode == "daily_stock":
            excluded_types = {"quotation", "estimate", "draft"}
            rows = [
                row for row in rows
                if str(row.get("voucher_type") or "").lower() not in excluded_types
            ]
            product_name = str(filters.get("product") or "").strip().lower()
            if product_name:
                products = self._fetch_table(
                    "products",
                    company_id,
                    select="id,name",
                    limit=2000,
                )
                product_ids = {
                    str(product.get("id"))
                    for product in products
                    if product_name in str(product.get("name") or "").lower()
                }
                rows = [
                    row for row in rows
                    if str(row.get("product_id")) in product_ids
                ]
            movement_type = str(filters.get("voucher_type") or "All")
            if movement_type != "All":
                rows = [
                    row for row in rows
                    if str(row.get("movement_type") or "") == movement_type
                ]
            if from_date:
                rows = [
                    row for row in rows
                    if self._movement_row_date(row) >= from_date
                ]
            if to_date:
                rows = [
                    row for row in rows
                    if self._movement_row_date(row) <= to_date
                ]
            return rows

        if date_col:
            if from_date:
                if date_col in {"movement_date", "created_at"} and filter_mode == "daily_stock":
                    rows = [
                        row for row in rows
                        if self._movement_row_date(row) >= from_date
                    ]
                elif date_col == "movement_date":
                    rows = [
                        row for row in rows
                        if self._movement_row_date(row) >= from_date
                    ]
                else:
                    rows = [
                        row for row in rows
                        if str(row.get(date_col) or "")[:10] >= from_date
                    ]
            if to_date:
                if date_col in {"movement_date", "created_at"} and filter_mode == "daily_stock":
                    rows = [
                        row for row in rows
                        if self._movement_row_date(row) <= to_date
                    ]
                elif date_col == "movement_date":
                    rows = [
                        row for row in rows
                        if self._movement_row_date(row) <= to_date
                    ]
                else:
                    rows = [
                        row for row in rows
                        if str(row.get(date_col) or "")[:10] <= to_date
                    ]

        if search and filter_mode not in {"purchase_order"}:
            rows = [row for row in rows if search in str(row).lower()]

        party = str(filters.get("party") or "").strip().lower()
        if party and party not in {"all parties", "all"}:
            rows = [row for row in rows if party in str(row).lower()]

        product = str(filters.get("product") or "").strip().lower()
        if product:
            rows = [row for row in rows if product in str(row).lower()]

        category = str(filters.get("category") or "").strip().lower()
        if category and category not in {"all categories", "all"}:
            rows = [row for row in rows if category in str(row).lower()]

        gst_value = str(filters.get("gst") or "").strip()
        if gst_value:
            rows = [
                row for row in rows
                if gst_value in str(row.get("gst_percent", row.get("tax_percent", "")))
            ]

        return rows

    def _run_cloud_table_report(
        self,
        slug: str,
        company_id: int,
        filters: dict[str, Any],
        definition: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Fetch and filter one simple Supabase table for a cloud report slug."""
        source = get_report_source(slug)
        if source is None:
            return None

        from bizora_core.mobile_report_columns import build_slug_table_payload

        table_name, date_col, filter_mode = source
        order_col = date_col if date_col not in {None, "created_at"} else "created_at"
        try:
            rows = self._fetch_table(
                table_name,
                company_id,
                select="*",
                limit=5000,
                order_col=order_col,
            )
        except Exception as exc:
            print(f"[MOBILE-SUPABASE] Table report '{slug}' failed: {exc}")
            return {
                "success": False,
                "message": f"Cloud report read failed: {exc}",
                "rows": [],
                "data_source": "supabase",
            }

        rows = self._apply_report_filters(
            slug,
            rows,
            filters,
            date_col,
            filter_mode,
            company_id,
        )
        table_payload = build_slug_table_payload(
            slug,
            rows,
            handler=str(definition.get("handler") or slug),
            report_mode=filters.get("report_mode"),
            filters=filters,
        )
        return {
            "success": True,
            "message": "" if rows else "No records found for the selected filters.",
            "data_source": "supabase",
            **table_payload,
        }

    def _debug_dispatch_state(self, slug: str, resolved_id: Optional[int]) -> None:
        """Emit a one-line snapshot of the fast-path decision inputs.

        Prints the environment flags Render / uvicorn / gunicorn need to
        see before the fast-path check runs, so we can tell from the log
        alone whether the process actually has SUPABASE_URL, whether the
        Supabase client could be constructed (SERVICE_ACTIVE), which
        MOBILE_DATA_SOURCE is selected, and whether the slug is mapped
        to a fast-path RPC at all.

        Note on `SERVICE_ACTIVE`:
            `get_supabase_client()` caches the client at module scope so
            an env var that got unset AFTER the first call still shows
            the client as available. We compute SERVICE_ACTIVE from a
            fresh env read here so the log reflects the CURRENT env
            variables on the worker, not the ones present at boot.
        """
        import os

        from bizora_core.mobile_supabase_fast_reports import FAST_PATH_HANDLERS

        supabase_url_set = bool((os.environ.get("SUPABASE_URL") or "").strip())
        service_key_set = bool(
            (os.environ.get("SERVICE_KEY") or "").strip()
            or (os.environ.get("SUPABASE_SERVICE_KEY") or "").strip()
            or (os.environ.get("SUPABASE_KEY") or "").strip()
        )
        data_source_env = (os.environ.get("MOBILE_DATA_SOURCE") or "").lower() or "(unset)"
        is_service_active = supabase_url_set and service_key_set

        # Separate probe: is the cached / lazily-constructed client
        # currently usable? A False here with SERVICE_ACTIVE=True means
        # env is present but the client itself failed (e.g. URL malformed,
        # supabase package missing, network refused at construction).
        try:
            client_ok = self._client() is not None
            client_error = ""
        except Exception as exc:
            client_ok = False
            client_error = f" client_error={type(exc).__name__}: {exc}"

        slug_on_fast_path = slug in FAST_PATH_HANDLERS

        print(
            f"DEBUG: Fast-Path Check -> "
            f"SUPABASE_URL_SET: {supabase_url_set}, "
            f"SERVICE_ACTIVE: {is_service_active}"
            f" | slug='{slug}' company_id={resolved_id} "
            f"MOBILE_DATA_SOURCE={data_source_env} "
            f"SERVICE_KEY_SET={service_key_set} "
            f"CLIENT_OK={client_ok} "
            f"slug_on_fast_path={slug_on_fast_path}{client_error}"
        )

    def run_report(
        self,
        slug: str,
        filters: Optional[dict[str, Any]] = None,
        company_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Run a cloud report using desktop logic on synced Supabase data.

        Report dispatch order:
            1. Fast-path RPC (Supabase views + `f_*` functions).
            2. Desktop SQLite hydration bridge (same handlers as desktop app).
            3. Cloud Python handlers (`mobile_supabase_report_handlers`).
            4. Simple table fetch + filter for mapped Supabase tables.
            5. Friendly unsupported message on cloud-only deployments.
        """
        definition = get_route_definition(slug)
        if definition is None:
            return {"success": False, "message": f"Unknown route: {slug}", "rows": []}

        resolved_id = self.resolve_company_id(company_id)
        report_filters = filters or {}

        # Diagnostic snapshot for Render / uvicorn logs. Cheap - one line.
        self._debug_dispatch_state(slug, resolved_id)

        if resolved_id is None:
            return {"success": False, "message": "No company found in Supabase.", "rows": []}

        from bizora_core.mobile_supabase_fast_reports import (
            FAST_PATH_HANDLERS,
            try_run_fast_report,
        )
        from bizora_core.mobile_supabase_desktop_bridge import (
            desktop_bridge_available,
            run_report_via_desktop_bridge,
        )

        fast_result = try_run_fast_report(
            self._client,
            slug,
            resolved_id,
            report_filters,
        )
        if fast_result is not None:
            return fast_result

        if desktop_bridge_available():
            bridge_result = run_report_via_desktop_bridge(
                self,
                slug,
                report_filters,
                company_id,
            )
            if bridge_result.get("success"):
                return bridge_result
            print(
                f"DEBUG: Desktop bridge did not serve slug='{slug}' "
                f"company_id={resolved_id}: {bridge_result.get('message', '')}"
            )

        from bizora_core.mobile_supabase_report_handlers import run_cloud_handler_report

        cloud_result = run_cloud_handler_report(
            str(definition.get("handler") or ""),
            slug,
            self._fetch_table,
            resolved_id,
            report_filters,
        )
        if cloud_result is not None:
            return cloud_result

        if slug not in FAST_PATH_HANDLERS:
            table_result = self._run_cloud_table_report(
                slug,
                resolved_id,
                report_filters,
                definition,
            )
            if table_result is not None:
                return table_result

        if slug in FAST_PATH_HANDLERS:
            bridge_reason = "RPC_FAILED_OR_MISSING"
        else:
            bridge_reason = "SLUG_NOT_MAPPED"

        if desktop_bridge_available():
            print(
                f"DEBUG: Cloud handlers did not serve slug='{slug}' "
                f"company_id={resolved_id}; bridge already attempted."
            )
        else:
            print(
                f"DEBUG: Cloud report unavailable without bridge. "
                f"bridge_reason={bridge_reason} slug='{slug}' company_id={resolved_id}"
            )
        return {
            "success": False,
            "message": UNSUPPORTED_CLOUD_MESSAGE,
            "rows": [],
            "data_source": "supabase",
            "bridge_available": desktop_bridge_available(),
        }

    @staticmethod
    def _empty_metrics_fallback() -> dict[str, float]:
        return {
            "net_realized_sale": 0.0,
            "total_creditors": 0.0,
            "total_debtors": 0.0,
            "day_credit_sale": 0.0,
        }
