"""Shared party display and lookup helpers."""

from __future__ import annotations

import re
from typing import Any, Dict


def normalise_party_code(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text.upper()[:7]


def party_display_name(party: Dict[str, Any]) -> str:
    name = str(party.get("name") or party.get("party_name") or "").strip()
    code = normalise_party_code(party.get("party_code"))
    return f"{name} ({code})" if name and code else name


def strip_party_display_code(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+\([^()]*\)$", "", text).strip()


def party_matches_text(party: Dict[str, Any], value: Any) -> bool:
    needle = str(value or "").strip().lower()
    if not needle:
        return False
    name = str(party.get("name") or party.get("party_name") or "").strip().lower()
    code = str(party.get("party_code") or "").strip().lower()
    display = party_display_name(party).lower()
    clean_display = strip_party_display_code(value).lower()
    return needle in (name, code, display) or (clean_display and clean_display == name)