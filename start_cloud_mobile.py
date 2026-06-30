#!/usr/bin/env python3
"""
Start the cloud mobile web API (Option A: Supabase-backed, public access).

Usage:
    python start_cloud_mobile.py

Required .env variables:
    SUPABASE_URL=https://xxxx.supabase.co
    SERVICE_KEY=<supabase-service-role-key>
    MOBILE_COMPANY_ID=1

Deploy:
    Render: connect this repo and use render.yaml
    Docker: docker build -f Dockerfile.cloud -t bizora-mobile . && docker run -p 8080:8080 --env-file .env bizora-mobile
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("MOBILE_DATA_SOURCE", "supabase")

render_url = (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
# Keep API calls relative on Render (same host). Absolute URLs can fail on some mobile browsers.
if render_url and not (os.getenv("MOBILE_PUBLIC_URL") or "").strip():
    if (os.getenv("MOBILE_FORCE_RELATIVE_API") or "true").strip().lower() not in {"1", "true", "yes"}:
        os.environ["MOBILE_PUBLIC_URL"] = render_url.rstrip("/")

try:
    import uvicorn
except ImportError as exc:
    raise SystemExit(
        "Cloud dependencies missing. Run: pip install -r requirements-cloud.txt"
    ) from exc


def validate_cloud_credentials() -> None:
    """Warn early when Supabase credentials are missing."""
    from sync_service import get_supabase_client

    if get_supabase_client() is None:
        print("WARNING: Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY.")


def print_cloud_banner(port: int) -> None:
    """Print cloud startup instructions."""
    public_url = (
        (os.getenv("MOBILE_PUBLIC_URL") or "").strip()
        or (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
    )
    company_id = (os.getenv("MOBILE_COMPANY_ID") or "").strip() or "(auto)"

    print("")
    print("=" * 60)
    print("BIZORA Cloud Mobile Web")
    print("=" * 60)
    print("Data source: supabase")
    print(f"Company id: {company_id}")
    print("")
    if public_url:
        print("Open on phone (any network):")
        print(f"  {public_url}")
    else:
        print(f"Local test URL: http://127.0.0.1:{port}")
        print("After cloud deploy, Render gives a public https URL.")
    print("")
    print("Desktop sync checklist:")
    print("  1. python setup_supabase.py")
    print("  2. Save sales/purchases in desktop app")
    print("  3. Data appears in Supabase tables")
    print("=" * 60)
    print("")


if __name__ == "__main__":
    port = int(os.getenv("PORT", os.getenv("MOBILE_WEB_PORT", "8080")))
    validate_cloud_credentials()
    print_cloud_banner(port)
    uvicorn.run("mobile_api:app", host="0.0.0.0", port=port, reload=False)
