"""
Helpers for printing LAN URLs used by the mobile web server.
"""

from __future__ import annotations

import socket


def get_lan_ip_addresses() -> list[str]:
    """Return likely IPv4 LAN addresses for this Windows machine."""
    addresses: list[str] = []

    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        primary = probe.getsockname()[0]
        probe.close()
        if primary and not primary.startswith("127."):
            addresses.append(primary)
    except OSError:
        pass

    try:
        host_name = socket.gethostname()
        for info in socket.getaddrinfo(host_name, None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127.") or ip in addresses:
                continue
            addresses.append(ip)
    except OSError:
        pass

    return addresses


def build_mobile_access_urls(port: int) -> dict[str, list[str]]:
    """Build localhost and LAN URLs for the mobile web app."""
    localhost = [f"http://127.0.0.1:{port}", f"http://localhost:{port}"]
    lan = [f"http://{ip}:{port}" for ip in get_lan_ip_addresses()]
    return {"localhost": localhost, "lan": lan}
