"""
Hydrate synced Supabase rows into a temporary SQLite database and run desktop report logic.
"""

from __future__ import annotations

import os
import tempfile
import time
from contextlib import closing
from threading import Lock
from typing import Any, Callable

# NOTE: `db` is a desktop-only SQLite module. It ships with the PySide6
# installer but is intentionally absent from the mobile web deployment
# image, so importing it at module load time crashes the FastAPI server
# on cold start. The import is deferred until we actually need to build
# the hydration SQLite snapshot, and every call site is guarded so a
# missing module degrades gracefully into a bridge-unavailable response
# instead of tearing down the whole worker.
#
# Same rationale applies to MobileWebService, which transitively imports
# `db` and other desktop modules.
_DesktopDatabase: Any = None
_MobileWebServiceCls: Any = None


def _load_desktop_layer() -> tuple[Any, Any]:
    """Lazy-import the desktop DB + service classes.

    Returns:
        (Database class, MobileWebService class)

    Raises:
        ImportError: caller is responsible for translating this into a
        user-friendly `success=False` payload so callers cannot crash
        the request handler.
    """
    global _DesktopDatabase, _MobileWebServiceCls
    if _DesktopDatabase is not None and _MobileWebServiceCls is not None:
        return _DesktopDatabase, _MobileWebServiceCls

    try:
        from db import Database as _Database
    except ImportError as exc:
        raise ImportError(
            "desktop `db` module unavailable in this environment; "
            "the Supabase bridge cannot hydrate an in-memory SQLite snapshot"
        ) from exc

    try:
        from bizora_core.mobile_web_service import MobileWebService as _MobileWebService
    except ImportError as exc:
        raise ImportError(
            "bizora_core.mobile_web_service unavailable; "
            "desktop report handlers cannot execute"
        ) from exc

    _DesktopDatabase = _Database
    _MobileWebServiceCls = _MobileWebService
    return _DesktopDatabase, _MobileWebServiceCls

# Parent tables first, then child/item tables (matches sync_bulk_to_supabase.py).
HYDRATION_TABLES: tuple[str, ...] = (
    "companies",
    "parties",
    "products",
    "ledger_accounts",
    "sales",
    "sales_items",
    "sales_returns",
    "sales_return_items",
    "purchases",
    "purchase_items",
    "purchase_returns",
    "purchase_return_items",
    "ledger_entries",
    "quotations",
    "quotation_items",
    "purchase_orders",
    "purchase_order_items",
    "pdc_register",
    "stock_movements",
    "journal_vouchers",
    "journal_voucher_lines",
    "cash_tender_history",
)

CHILD_TABLE_PARENT: dict[str, tuple[str, str, str]] = {
    "sales_items": ("sales", "id", "sale_id"),
    "sales_return_items": ("sales_returns", "id", "sales_return_id"),
    "purchase_items": ("purchases", "id", "purchase_id"),
    "purchase_return_items": ("purchase_returns", "id", "purchase_return_id"),
    "quotation_items": ("quotations", "id", "quotation_id"),
    "purchase_order_items": ("purchase_orders", "id", "po_id"),
    "journal_voucher_lines": ("journal_vouchers", "id", "journal_id"),
}

GLOBAL_TABLES = frozenset({"cash_tender_history"})

_CACHE_LOCK = Lock()
# Any = desktop Database class; forward-ref intentionally, see _load_desktop_layer.
_DB_CACHE: dict[int, tuple[float, str, Any]] = {}
_CACHE_TTL_SECONDS = 180
_LAST_BRIDGE_IMPORT_ERROR: str | None = None


def bridge_import_error() -> str | None:
    """Return the last ImportError message when the desktop layer failed to load."""
    return _LAST_BRIDGE_IMPORT_ERROR


def _batch_fetch_child_rows(
    client: Any,
    table_name: str,
    foreign_key: str,
    parent_ids: list[Any],
    *,
    batch_size: int = 80,
) -> list[dict[str, Any]]:
    """Fetch child-table rows for many parent ids via PostgREST."""
    if not parent_ids:
        return []
    rows: list[dict[str, Any]] = []
    for start in range(0, len(parent_ids), batch_size):
        batch = parent_ids[start : start + batch_size]
        try:
            response = (
                client.table(table_name)
                .select("*")
                .in_(foreign_key, batch)
                .limit(10000)
                .execute()
            )
            rows.extend(response.data or [])
        except Exception as exc:
            message = str(exc)
            if "Could not find the table" in message:
                print(f"[MOBILE-BRIDGE] Child table '{table_name}' missing in Supabase.")
                return []
            raise
    return rows


def _fetch_table_rows(
    service: Any,
    table_name: str,
    company_id: int,
    *,
    hydrated: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Fetch one table for hydration, including child tables scoped by parent ids."""
    if table_name in hydrated:
        return hydrated[table_name]

    client = service._client()
    fetch_table = service._fetch_table

    if table_name in GLOBAL_TABLES:
        try:
            response = client.table(table_name).select("*").limit(10000).execute()
            rows = response.data or []
        except Exception as exc:
            if "Could not find the table" in str(exc):
                rows = []
            else:
                raise
        hydrated[table_name] = rows
        return rows

    if table_name == "companies":
        rows = service._fetch_company_rows(company_id=company_id, limit=1)
        hydrated[table_name] = rows
        return rows

    child_meta = CHILD_TABLE_PARENT.get(table_name)
    if child_meta is not None:
        parent_table, parent_pk, foreign_key = child_meta
        parent_rows = _fetch_table_rows(service, parent_table, company_id, hydrated=hydrated)
        parent_ids = [row.get(parent_pk) for row in parent_rows if row.get(parent_pk) is not None]
        rows = _batch_fetch_child_rows(client, table_name, foreign_key, parent_ids)
        hydrated[table_name] = rows
        return rows

    limit = 50000 if table_name == "ledger_entries" else 15000
    rows = fetch_table(table_name, company_id, select="*", limit=limit, company_scoped=True)
    hydrated[table_name] = rows
    return rows


def _sqlite_columns(connection, table_name: str) -> set[str]:
    """Return column names present in the hydrated SQLite table."""
    with closing(connection.cursor()) as cursor:
        cursor.execute(f"PRAGMA table_info({table_name})")
        return {str(row[1]) for row in cursor.fetchall()}


def _insert_rows(connection, table_name: str, rows: list[dict[str, Any]]) -> None:
    """Insert Supabase rows into the matching SQLite table."""
    if not rows:
        return
    columns = _sqlite_columns(connection, table_name)
    if not columns:
        return
    with closing(connection.cursor()) as cursor:
        for row in rows:
            if not isinstance(row, dict):
                continue
            usable = [key for key in row.keys() if key in columns]
            if not usable:
                continue
            placeholders = ",".join(["?"] * len(usable))
            sql = (
                f"INSERT OR REPLACE INTO {table_name} "
                f"({','.join(usable)}) VALUES ({placeholders})"
            )
            values = [row[key] for key in usable]
            try:
                cursor.execute(sql, values)
            except Exception as exc:
                print(f"[MOBILE-BRIDGE] Skip row in {table_name}: {exc}")
        connection.commit()


def _apply_desktop_party_links(hydrated: dict[str, list[dict[str, Any]]]) -> None:
    """Backfill party -> ledger links before desktop logic runs on hydrated SQLite."""
    parties = hydrated.get("parties") or []
    ledger_accounts = hydrated.get("ledger_accounts") or []
    if not parties or not ledger_accounts:
        return
    try:
        from bizora_core.mobile_supabase_party_links import assign_party_ledger_links

        hydrated["parties"] = assign_party_ledger_links(parties, ledger_accounts)
    except Exception as exc:
        print(f"[MOBILE-BRIDGE] Party link assignment failed: {exc}")


def build_desktop_database(service: Any, company_id: int) -> tuple[Any, str]:
    """Create a temporary SQLite file populated with one company's synced data.

    Raises ImportError when the desktop `db` module isn't packaged with
    this deployment (e.g. cloud FastAPI worker). Callers must translate
    that into a graceful `success=False` payload rather than propagating.
    """
    database_cls, _mobile_web_service_cls = _load_desktop_layer()

    temp_file = tempfile.NamedTemporaryFile(prefix=f"mobile_co_{company_id}_", suffix=".db", delete=False)
    temp_path = temp_file.name
    temp_file.close()

    db = database_cls(db_path=temp_path)
    connection = db.connect()
    hydrated: dict[str, list[dict[str, Any]]] = {}

    for table_name in HYDRATION_TABLES:
        rows = _fetch_table_rows(service, table_name, company_id, hydrated=hydrated)
        hydrated[table_name] = rows

    _apply_desktop_party_links(hydrated)

    for table_name in HYDRATION_TABLES:
        _insert_rows(connection, table_name, hydrated.get(table_name) or [])

    return db, temp_path


def _get_cached_database(service: Any, company_id: int) -> tuple[Any, str]:
    """Reuse a recently built SQLite snapshot for the same company."""
    now = time.time()
    with _CACHE_LOCK:
        cached = _DB_CACHE.get(company_id)
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[2], cached[1]

    db, path = build_desktop_database(service, company_id)

    with _CACHE_LOCK:
        previous = _DB_CACHE.pop(company_id, None)
        if previous:
            try:
                previous[2].force_disconnect()
                os.unlink(previous[1])
            except OSError:
                pass
        _DB_CACHE[company_id] = (now, path, db)
    return db, path


def desktop_bridge_available() -> bool:
    """Return True when the desktop SQLite hydration layer can be imported."""
    global _LAST_BRIDGE_IMPORT_ERROR
    try:
        _load_desktop_layer()
        _LAST_BRIDGE_IMPORT_ERROR = None
        return True
    except ImportError as exc:
        _LAST_BRIDGE_IMPORT_ERROR = str(exc)
        print(f"[MOBILE-BRIDGE] Desktop layer unavailable: {exc}")
        return False


def run_report_via_desktop_bridge(
    supabase_service: Any,
    slug: str,
    filters: dict[str, Any],
    company_id: int | None,
) -> dict[str, Any]:
    """Run any Books/Reports route through the same logic layer as the desktop app.

    Falls back to a `success=False` payload (never raises) so a missing
    desktop `db` module in the cloud deployment cannot crash the request
    handler. Callers should surface `message` to the user and pursue the
    fast-path RPCs (see `mobile_supabase_fast_reports`) as the primary
    reporting route in cloud environments.
    """
    resolved_id = supabase_service.resolve_company_id(company_id)
    if not resolved_id:
        return {"success": False, "message": "No company found in Supabase.", "rows": []}

    try:
        database_cls, mobile_web_service_cls = _load_desktop_layer()
    except ImportError as exc:
        # Cloud deployment without the desktop `db` module. Log once and
        # return a graceful payload so the server stays up.
        print(f"[MOBILE-BRIDGE] Desktop layer unavailable ({exc}); "
              f"report '{slug}' cannot use SQLite hydration bridge.")
        return {
            "success": False,
            "message": (
                "The SQLite hydration bridge is disabled on this deployment. "
                "Enable the desktop 'db' module or use the fast-path RPCs."
            ),
            "rows": [],
            "data_source": "supabase",
            "bridge_available": False,
        }

    try:
        db, _path = _get_cached_database(supabase_service, resolved_id)
    except ImportError as exc:
        # Belt-and-braces: a later ImportError in _load_desktop_layer.
        print(f"[MOBILE-BRIDGE] Cache build failed for company {resolved_id}: {exc}")
        return {
            "success": False,
            "message": str(exc),
            "rows": [],
            "data_source": "supabase",
            "bridge_available": False,
        }
    except Exception as exc:
        # Non-import failures (network, permission, disk) still need to
        # be caught so we don't crash the worker.
        print(f"[MOBILE-BRIDGE] Cache build failed for company {resolved_id}: {exc}")
        return {"success": False, "message": str(exc), "rows": [], "data_source": "supabase"}

    try:
        _ = database_cls  # silence unused-linter; class captured above so we validate the import
        result = mobile_web_service_cls(db=db).run_report(slug, filters, company_id=resolved_id)
        result["data_source"] = "desktop_mirror"
        result["mirror_mode"] = True
        return result
    except Exception as exc:
        print(f"[MOBILE-BRIDGE] Report '{slug}' failed: {exc}")
        return {"success": False, "message": str(exc), "rows": [], "data_source": "supabase"}
