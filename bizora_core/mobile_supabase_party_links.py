"""
Resolve party -> ledger_account links for Supabase-backed mobile reads.

When `parties.ledger_account_id` is missing in Supabase, we must not collapse
multiple party rows that share a display name onto a single ledger account.
"""

from __future__ import annotations

from typing import Any


def assign_party_ledger_links(
    parties: list[dict[str, Any]],
    ledger_accounts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return party rows with stable, one-to-one ledger_account_id links.

    Matching rules:
        1. Keep an existing `ledger_account_id` when present.
        2. Otherwise match by party name against `account_type='party'` accounts.
        3. Never reuse the same ledger account for two parties (duplicate names).
    """
    accounts_by_name: dict[str, list[int]] = {}
    for account in ledger_accounts:
        if str(account.get("account_type") or "").lower() != "party":
            continue
        name_key = str(account.get("account_name") or "").strip().lower()
        account_id = account.get("id")
        if not name_key or account_id is None:
            continue
        accounts_by_name.setdefault(name_key, []).append(int(account_id))

    for name_key in accounts_by_name:
        accounts_by_name[name_key].sort()

    used_accounts: set[int] = set()
    enriched: list[dict[str, Any]] = []
    for party in sorted(parties, key=lambda row: int(row.get("id") or 0)):
        row = dict(party)
        linked = row.get("ledger_account_id")
        if linked not in (None, "", 0):
            used_accounts.add(int(linked))
            enriched.append(row)
            continue

        party_name = str(row.get("name") or "").strip().lower()
        candidates = [
            account_id
            for account_id in accounts_by_name.get(party_name, [])
            if account_id not in used_accounts
        ]
        if candidates:
            row["ledger_account_id"] = candidates[0]
            used_accounts.add(int(candidates[0]))
        enriched.append(row)
    return enriched


def party_by_ledger_account(
    parties: list[dict[str, Any]],
    ledger_accounts: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    """Map ledger account ids to party rows using explicit or inferred links."""
    linked_parties = assign_party_ledger_links(parties, ledger_accounts)
    mapping: dict[int, dict[str, Any]] = {}
    for party in linked_parties:
        ledger_account_id = party.get("ledger_account_id")
        if ledger_account_id in (None, "", 0):
            continue
        mapping[int(ledger_account_id)] = party
    return mapping
