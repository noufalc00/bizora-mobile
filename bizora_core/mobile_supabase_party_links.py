"""
Resolve party -> ledger_account links for Supabase-backed mobile reads.

When `parties.ledger_account_id` is missing in Supabase, we must not collapse
multiple party rows that share a display name onto a single ledger account.
"""

from __future__ import annotations

from typing import Any


def _party_opening_balance(party: dict[str, Any]) -> float:
    """Return the party master opening balance as a float."""
    try:
        return round(float(party.get("opening_balance") or 0.0), 2)
    except (TypeError, ValueError):
        return 0.0


def _account_opening_balance(account: dict[str, Any]) -> float:
    """Return the ledger account opening balance as a float."""
    try:
        return round(float(account.get("opening_balance") or 0.0), 2)
    except (TypeError, ValueError):
        return 0.0


def _expected_opening_type(party_type: str) -> str:
    """Map party type to the desktop opening balance side."""
    if str(party_type or "").strip() == "Creditor":
        return "Cr"
    return "Dr"


def _match_score(
    party: dict[str, Any],
    account_id: int,
    accounts_by_id: dict[int, dict[str, Any]],
) -> tuple[int, int, int, float, int]:
    """Score one party/account pair; lower tuples are better matches."""
    account = accounts_by_id.get(account_id) or {}
    party_name = str(party.get("name") or "").strip()
    account_name = str(account.get("account_name") or "").strip()
    exact_name = 0 if party_name == account_name else 1
    case_insensitive = (
        0
        if party_name.lower() == account_name.lower()
        else 1
    )
    opening_delta = abs(
        _party_opening_balance(party) - _account_opening_balance(account)
    )
    party_type = str(party.get("party_type") or "")
    account_ob_type = str(account.get("opening_balance_type") or "Dr").strip()
    type_penalty = 0 if account_ob_type == _expected_opening_type(party_type) else 1
    return (exact_name, case_insensitive, type_penalty, opening_delta, account_id)


def _pick_ledger_account(
    party: dict[str, Any],
    candidate_ids: list[int],
    accounts_by_id: dict[int, dict[str, Any]],
    used_accounts: set[int],
) -> int | None:
    """Choose the best unused ledger account for one party row."""
    available = [account_id for account_id in candidate_ids if account_id not in used_accounts]
    if not available:
        return None
    ranked = sorted(
        available,
        key=lambda account_id: _match_score(party, account_id, accounts_by_id),
    )
    return ranked[0]


def assign_party_ledger_links(
    parties: list[dict[str, Any]],
    ledger_accounts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return party rows with stable, one-to-one ledger_account_id links.

    Matching rules:
        1. Keep an existing `ledger_account_id` when present.
        2. Otherwise match by party name against `account_type='party'` accounts.
        3. Prefer exact account-name matches, then opening balance + Dr/Cr side.
        4. Never reuse the same ledger account for two parties.
    """
    accounts_by_id: dict[int, dict[str, Any]] = {}
    accounts_by_name: dict[str, list[int]] = {}
    for account in ledger_accounts:
        account_id = account.get("id")
        if account_id is None:
            continue
        account_id_int = int(account_id)
        accounts_by_id[account_id_int] = account
        if str(account.get("account_type") or "").lower() != "party":
            continue
        name_key = str(account.get("account_name") or "").strip().lower()
        if not name_key:
            continue
        accounts_by_name.setdefault(name_key, []).append(account_id_int)

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
        candidates = accounts_by_name.get(party_name, [])
        picked = _pick_ledger_account(row, candidates, accounts_by_id, used_accounts)
        if picked is not None:
            row["ledger_account_id"] = picked
            used_accounts.add(int(picked))
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
