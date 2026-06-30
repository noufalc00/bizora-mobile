"""Tests for Purchase Entry cash supplier fallback validation."""

from bizora_core.purchase_logic import PurchaseLogic


class DummyPurchaseDb:
    """Minimal database double for purchase party resolution tests."""

    def __init__(self):
        """Seed one real creditor and track fallback party creation."""
        self.parties = {
            7: {
                "id": 7,
                "name": "Existing Supplier",
                "party_type": "Creditor",
            }
        }
        self.inserted_parties = []

    def _get_placeholder(self):
        """Return the SQLite placeholder used by query builders."""
        return "?"

    def execute_query(self, query, params=()):
        """Support exact-name lookup used by the fallback resolver."""
        if "FROM parties" not in query:
            return []

        company_id, party_name = params
        del company_id
        wanted_name = str(party_name or "").strip().casefold()
        return [
            party
            for party in self.parties.values()
            if str(party.get("name") or "").strip().casefold() == wanted_name
        ]

    def get_party_by_id(self, company_id, party_id):
        """Return a party by id for the active company."""
        del company_id
        return self.parties.get(party_id)

    def insert_party(self, company_id, party_data):
        """Create a party row and return its parties.id."""
        del company_id
        party_id = max(self.parties) + 1
        party = {
            "id": party_id,
            "name": party_data.get("name"),
            "party_type": party_data.get("party_type"),
        }
        self.parties[party_id] = party
        self.inserted_parties.append(party)
        return party_id


def make_logic():
    """Create PurchaseLogic with ledger creation disabled for focused tests."""
    logic = PurchaseLogic(DummyPurchaseDb())
    logic._ensure_party_ledger_account = lambda *args, **kwargs: None
    return logic


def test_credit_purchase_without_supplier_is_blocked():
    """Credit purchases must still require a supplier/creditor party."""
    logic = make_logic()
    payload = {"purchase_type": "Credit", "party_id": None}

    result = logic.resolve_purchase_party_id(1, payload)

    assert result["success"] is False
    assert "Credit purchase requires a supplier" in result["message"]
    assert payload["party_id"] is None


def test_cash_purchase_without_supplier_gets_cash_supplier_party():
    """Cash purchases without a supplier get a valid fallback parties.id."""
    logic = make_logic()
    payload = {"purchase_type": "Cash", "party_id": None}

    result = logic.resolve_purchase_party_id(1, payload)

    assert result["success"] is True
    assert payload["party_id"] == result["party_id"]
    assert logic.db.get_party_by_id(1, payload["party_id"]) is not None
    assert logic.db.inserted_parties[0]["name"] == "Cash Supplier"


def test_cash_purchase_with_supplier_keeps_selected_party():
    """Cash purchases with a selected supplier keep that supplier party id."""
    logic = make_logic()
    payload = {"purchase_type": "Cash", "party_id": 7}

    result = logic.resolve_purchase_party_id(1, payload)

    assert result["success"] is True
    assert payload["party_id"] == 7
    assert logic.db.inserted_parties == []
