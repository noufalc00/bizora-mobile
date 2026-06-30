#!/usr/bin/env python3
"""
Start the BIZORA mobile web server.

Usage:
    python start_mobile_web.py

Phone access (same Wi-Fi):
    Use a LAN URL printed below, e.g. http://192.168.1.10:8080
    Do not use 127.0.0.1 on a phone.

Cloud access when desktop app is closed:
    1. Sync data from desktop (sales/purchases/companies via sync_service)
    2. Set MOBILE_DATA_SOURCE=supabase in .env
    3. Run this server on an always-on PC, VM, or cloud host with the same .env

Requires:
    pip install fastapi uvicorn supabase python-dotenv
"""

from __future__ import annotations

import os

try:
    import uvicorn
except ImportError as exc:
    raise SystemExit("uvicorn is not installed. Run: pip install fastapi uvicorn") from exc

from utils.network_urls import build_mobile_access_urls


def print_startup_banner(port: int) -> None:
    """Print laptop and phone URLs plus firewall guidance."""
    urls = build_mobile_access_urls(port)
    data_source = (os.getenv("MOBILE_DATA_SOURCE") or "local").strip().lower()
    public_url = (os.getenv("MOBILE_PUBLIC_URL") or "").strip()

    print("")
    print("=" * 60)
    print("BIZORA Mobile Web Server")
    print("=" * 60)
    print(f"Data source: {data_source}")
    print("")
    print("Laptop browser:")
    for url in urls["localhost"]:
        print(f"  {url}")
    print("")
    print("Phone browser (same Wi-Fi):")
    if urls["lan"]:
        for url in urls["lan"]:
            print(f"  {url}")
    else:
        print("  LAN IP not detected. Run: ipconfig")
        print(f"  Then open: http://<your-pc-ip>:{port}")
    print("")
    print("If phone cannot connect:")
    print("  1. PC and phone must be on the same Wi-Fi")
    print("  2. Do not use 127.0.0.1 on the phone")
    print(
        f"  3. Allow Windows Firewall inbound TCP port {port} "
        "(run PowerShell as Administrator):"
    )
    print(
        f'     netsh advfirewall firewall add rule name="BIZORA Mobile Web" '
        f'dir=in action=allow protocol=TCP localport={port}'
    )
    print("")
    print("Supabase cloud mode (desktop app closed):")
    print("  MOBILE_DATA_SOURCE=supabase")
    print("  SUPABASE_URL=https://xxxx.supabase.co")
    print("  SERVICE_KEY=<service-role-key>")
    print("  MOBILE_COMPANY_ID=<optional company id>")
    if public_url:
        print(f"  Public URL: {public_url}")
    print("=" * 60)
    print("")


if __name__ == "__main__":
    port = int(os.getenv("MOBILE_WEB_PORT", "8080"))
    print_startup_banner(port)
    uvicorn.run("mobile_api:app", host="0.0.0.0", port=port, reload=False)
