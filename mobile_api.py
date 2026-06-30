"""
Faizan Pro / BIZORA mobile web API.

Serves the mobile dashboard, Books/Reports navigation, and report queries
using local SQLite or Supabase depending on MOBILE_DATA_SOURCE.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    import uvicorn
except ImportError:  # pragma: no cover
    uvicorn = None  # type: ignore[assignment]

from config import BRAND_NAME
from utils.network_urls import build_mobile_access_urls

ROOT_DIR = Path(__file__).resolve().parent
MOBILE_WEB_DIR = ROOT_DIR / "mobile_web"
MOBILE_STATIC_DIR = MOBILE_WEB_DIR / "static"
MOBILE_INDEX = MOBILE_WEB_DIR / "index.html"

app = FastAPI(
    title=f"{BRAND_NAME} Mobile Web",
    description="Mobile dashboard and reports for Faizan Pro Accounting.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MobileServiceProtocol(Protocol):
    """Shared mobile service surface for local and Supabase backends."""

    def get_theme_payload(self, theme_name: Optional[str] = None) -> dict[str, Any]: ...

    def get_navigation(self) -> dict[str, Any]: ...

    def get_dashboard_payload(self, company_id: Optional[int] = None) -> dict[str, Any]: ...

    def get_report_meta(self, slug: str, company_id: Optional[int] = None) -> dict[str, Any]: ...

    def run_report(
        self,
        slug: str,
        filters: Optional[dict[str, Any]] = None,
        company_id: Optional[int] = None,
    ) -> dict[str, Any]: ...


def resolve_server_port() -> int:
    """Resolve HTTP port for local runs and cloud hosts (Render sets PORT)."""
    return int(os.getenv("PORT", os.getenv("MOBILE_WEB_PORT", "8080")))


def resolve_mobile_service() -> tuple[MobileServiceProtocol, str]:
    """
    Choose the mobile data backend.

    MOBILE_DATA_SOURCE:
        local    - read local SQLite (desktop app database)
        supabase - read synced Supabase tables (works without desktop DB)
        auto     - try local first, then Supabase
    """
    from bizora_core.mobile_supabase_service import MobileSupabaseService

    mode = (os.getenv("MOBILE_DATA_SOURCE") or "local").strip().lower()
    supabase_service = MobileSupabaseService()

    if mode == "supabase":
        return supabase_service, "supabase"

    from bizora_core.mobile_web_service import MobileWebService

    local_service = MobileWebService()

    if mode == "auto":
        try:
            payload = local_service.get_dashboard_payload()
            if payload.get("success"):
                return local_service, "local"
        except Exception:
            pass
        return supabase_service, "supabase"

    return local_service, "local"


_service, _data_source = resolve_mobile_service()


class ReportRequest(BaseModel):
    """Filter payload for mobile report execution."""

    filters: dict[str, Any] = Field(default_factory=dict)


class LoginRequest(BaseModel):
    """Mobile login payload matching the desktop company gateway."""

    company_id: int
    username: str
    password: str = ""
    is_secret: bool = False


def _resolve_company_id_param(
    company_id: Optional[int] = Query(default=None),
    x_bizora_company_id: Optional[str] = Header(default=None),
) -> Optional[int]:
    """Resolve company scope from query string or mobile session header."""
    if company_id is not None:
        try:
            return int(company_id)
        except (TypeError, ValueError):
            return None
    header_value = (x_bizora_company_id or "").strip()
    if header_value.isdigit():
        return int(header_value)
    return None


def _auth_backend():
    """Return auth helpers for the active mobile data backend."""
    if _data_source == "supabase":
        return _service, "supabase"
    from bizora_core.mobile_auth_service import MobileAuthService

    return MobileAuthService(), "local"


def _inject_mobile_html(content: str) -> str:
    """Inject or update optional remote API base for split static/API hosting."""
    import re

    split_host = (os.getenv("MOBILE_SPLIT_HOST") or "").strip().lower() in {"1", "true", "yes"}
    force_relative = (os.getenv("MOBILE_FORCE_RELATIVE_API") or "true").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    public_url = ""
    if split_host and not force_relative:
        public_url = (os.getenv("MOBILE_PUBLIC_URL") or "").strip().rstrip("/")
    meta_tag = f'<meta name="mobile-api-base" content="{public_url}">'
    if 'name="mobile-api-base"' in content:
        return re.sub(
            r'<meta\s+name="mobile-api-base"\s+content="[^"]*"\s*/?>',
            meta_tag,
            content,
            count=1,
        )
    return content.replace(
        '<meta name="theme-color"',
        f'{meta_tag}\n  <meta name="theme-color"',
    )


@app.get("/api/health")
def api_health() -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": f"{BRAND_NAME} mobile API is running"}


@app.get("/api/status")
def api_status() -> dict[str, Any]:
    """Return active backend and connection hints for mobile clients."""
    port = resolve_server_port()
    urls = build_mobile_access_urls(port)
    public_url = (
        (os.getenv("MOBILE_PUBLIC_URL") or "").strip()
        or (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
    )
    return {
        "data_source": _data_source,
        "deployment": "cloud" if _data_source == "supabase" else "local",
        "public_url": public_url,
        "localhost_urls": urls["localhost"],
        "lan_urls": urls["lan"],
        "mobile_hint": (
            "Cloud mode: open your public URL from any network. "
            "Local mode: use a LAN URL on the same Wi-Fi."
        ),
        "supabase_mode_hint": (
            "Desktop app syncs sales/purchases to Supabase. "
            "Cloud API reads that data when MOBILE_DATA_SOURCE=supabase."
        ),
    }


@app.get("/api/network-info")
def api_network_info() -> dict[str, Any]:
    """Return LAN URLs for opening the app from a phone on the same Wi-Fi."""
    port = resolve_server_port()
    urls = build_mobile_access_urls(port)
    return {
        "port": port,
        "localhost_urls": urls["localhost"],
        "lan_urls": urls["lan"],
        "phone_instructions": (
            "Connect phone and PC to the same Wi-Fi, then open a LAN URL. "
            "Allow port through Windows Firewall if the page does not load."
        ),
    }


@app.get("/api/theme")
def api_theme(theme: Optional[str] = Query(default=None)) -> dict[str, Any]:
    """Return desktop-matched color tokens for light or dark mode."""
    return _service.get_theme_payload(theme)


@app.get("/api/navigation")
def api_navigation() -> dict[str, Any]:
    """Return Books and Reports sidebar navigation."""
    payload = _service.get_navigation()
    payload["data_source"] = _data_source
    return payload


@app.get("/api/auth/bootstrap")
def api_auth_bootstrap(
    last_company_id: Optional[int] = Query(default=None),
) -> dict[str, Any]:
    """Return last active company and usernames for the mobile login screen."""
    auth_service, source = _auth_backend()
    payload = auth_service.get_bootstrap(last_company_id=last_company_id)
    payload["data_source"] = _data_source
    return payload


@app.get("/api/companies")
def api_companies(
    visibility: Optional[str] = Query(default="normal"),
) -> dict[str, Any]:
    """List companies available for mobile login."""
    auth_service, source = _auth_backend()
    if source == "supabase":
        payload = auth_service.list_companies(visibility=visibility)
    else:
        payload = auth_service.list_companies(visibility=visibility)
    payload["data_source"] = _data_source
    return payload


@app.get("/api/companies/{company_id}/users")
def api_company_users(company_id: int) -> dict[str, Any]:
    """Return usernames for one company on the login screen."""
    if _data_source == "supabase":
        return {
            "success": True,
            "usernames": ["admin"],
            "data_source": _data_source,
        }
    from bizora_core.mobile_auth_service import MobileAuthService

    auth_service = MobileAuthService()
    return {
        "success": True,
        "usernames": auth_service.list_usernames(company_id),
        "data_source": _data_source,
    }


@app.post("/api/auth/login")
def api_auth_login(body: LoginRequest) -> dict[str, Any]:
    """Authenticate and open a company for mobile dashboard access."""
    auth_service, source = _auth_backend()
    if source == "supabase":
        payload = auth_service.cloud_login(
            body.company_id,
            body.username,
            is_secret=body.is_secret,
        )
    else:
        payload = auth_service.login(
            body.company_id,
            body.username,
            body.password,
            is_secret=body.is_secret,
        )
    payload["data_source"] = _data_source
    return payload


@app.get("/api/dashboard")
def api_dashboard(
    company_id: Optional[int] = Depends(_resolve_company_id_param),
) -> dict[str, Any]:
    """Return the dashboard payload from the active backend."""
    payload = _service.get_dashboard_payload(company_id=company_id)
    payload["data_source"] = _data_source
    return payload


@app.get("/api/reports/{slug}/meta")
def api_report_meta(
    slug: str,
    company_id: Optional[int] = Depends(_resolve_company_id_param),
) -> dict[str, Any]:
    """Return filter schema and lookup values for one report route."""
    payload = _service.get_report_meta(slug, company_id=company_id)
    if not payload.get("success"):
        raise HTTPException(status_code=404, detail=payload.get("message", "Not found"))
    payload["data_source"] = _data_source
    return payload


@app.post("/api/reports/{slug}/run")
def api_report_run(
    slug: str,
    body: ReportRequest,
    company_id: Optional[int] = Depends(_resolve_company_id_param),
) -> dict[str, Any]:
    """Execute one Books/Reports query with the supplied filters."""
    payload = _service.run_report(slug, body.filters, company_id=company_id)
    payload["data_source"] = _data_source
    return payload


@app.get("/", response_class=HTMLResponse)
def mobile_home() -> HTMLResponse:
    """Serve the mobile web shell."""
    if not MOBILE_INDEX.is_file():
        raise HTTPException(status_code=404, detail="mobile_web/index.html not found")
    content = _inject_mobile_html(MOBILE_INDEX.read_text(encoding="utf-8"))
    return HTMLResponse(content=content, headers={"Cache-Control": "no-store"})


@app.get("/static/mobile.js")
def mobile_js_asset() -> FileResponse:
    """Serve mobile JS with no-cache so phones always get the latest build."""
    asset = MOBILE_STATIC_DIR / "mobile.js"
    if not asset.is_file():
        raise HTTPException(status_code=404, detail="mobile.js not found")
    return FileResponse(
        asset,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/static/mobile.css")
def mobile_css_asset() -> FileResponse:
    """Serve mobile CSS with no-cache so phones always get the latest build."""
    asset = MOBILE_STATIC_DIR / "mobile.css"
    if not asset.is_file():
        raise HTTPException(status_code=404, detail="mobile.css not found")
    return FileResponse(
        asset,
        media_type="text/css",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/static/app_logo.png")
@app.get("/static/app_logo_mobile.png")
def mobile_logo_asset() -> FileResponse:
    """Serve the optimized BIZORA brand logo for mobile screens."""
    candidates = (
        MOBILE_STATIC_DIR / "app_logo_mobile.png",
        MOBILE_STATIC_DIR / "app_logo.png",
        ROOT_DIR / "assets" / "icons" / "app_logo.png",
    )
    asset = next((path for path in candidates if path.is_file()), None)
    if asset is None:
        raise HTTPException(status_code=404, detail="app_logo.png not found")
    return FileResponse(
        asset,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/static/file.svg")
def mobile_file_icon_asset() -> FileResponse:
    """Serve the secret file icon used on the mobile login screen."""
    asset = MOBILE_STATIC_DIR / "file.svg"
    if not asset.is_file():
        fallback = ROOT_DIR / "assets" / "icons" / "file.svg"
        if fallback.is_file():
            asset = fallback
        else:
            raise HTTPException(status_code=404, detail="file.svg not found")
    return FileResponse(
        asset,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


if MOBILE_STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(MOBILE_STATIC_DIR)), name="static")


if __name__ == "__main__":
    if uvicorn is None:
        raise SystemExit("uvicorn is not installed. Run: pip install fastapi uvicorn")
    port = resolve_server_port()
    uvicorn.run(app, host="0.0.0.0", port=port)
