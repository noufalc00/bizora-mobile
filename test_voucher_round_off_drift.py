import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bizora_core.voucher_posting_engine import VoucherPostingEngine


class DummyVoucherPostingEngine(VoucherPostingEngine):
    """Test double that supplies a stable Round Off account without a database."""

    def __init__(self):
        super().__init__(db=None)

    def _round_off_account(self, company_id):
        """Return a fixed Round Off account for helper-level assertions."""
        return {"id": 99, "account_name": self.ROUND_OFF_ACCOUNT_NAME}


class TestVoucherRoundOffDrift(unittest.TestCase):
    """Verify voucher drift is absorbed before mathematical firewall posting."""

    def setUp(self):
        """Create a helper-only posting engine for each assertion."""
        self.engine = DummyVoucherPostingEngine()

    def _assert_balanced(self, entries):
        """Assert entry totals are equal after commercial rounding."""
        total_debit = self.engine._entry_side_total(entries, "debit")
        total_credit = self.engine._entry_side_total(entries, "credit")
        self.assertEqual(total_debit, total_credit)

    def test_credit_drift_adds_round_off_debit(self):
        """Credit-heavy drift is balanced with a Round Off debit."""
        entries = [
            {"account_id": 1, "debit": 600.00, "credit": 0.0},
            {"account_id": 2, "debit": 0.0, "credit": 600.01},
        ]

        result = self.engine._balance_entries_with_round_off(1, entries, [])

        round_off = result[-1]
        self.assertEqual(round_off["account_id"], 99)
        self.assertEqual(round_off["debit"], 0.01)
        self.assertEqual(round_off["credit"], 0.0)
        self._assert_balanced(result)

    def test_debit_drift_adds_round_off_credit(self):
        """Debit-heavy drift is balanced with a Round Off credit."""
        entries = [
            {"account_id": 1, "debit": 600.01, "credit": 0.0},
            {"account_id": 2, "debit": 0.0, "credit": 600.00},
        ]

        result = self.engine._balance_entries_with_round_off(1, entries, [])

        round_off = result[-1]
        self.assertEqual(round_off["account_id"], 99)
        self.assertEqual(round_off["debit"], 0.0)
        self.assertEqual(round_off["credit"], 0.01)
        self._assert_balanced(result)

    def test_balanced_entries_are_not_adjusted(self):
        """Already balanced entries remain unchanged."""
        entries = [
            {"account_id": 1, "debit": 600.00, "credit": 0.0},
            {"account_id": 2, "debit": 0.0, "credit": 600.00},
        ]

        result = self.engine._balance_entries_with_round_off(1, entries, [])

        self.assertEqual(len(result), 2)
        self._assert_balanced(result)

    def test_existing_round_off_entry_is_adjusted(self):
        """Existing Round Off rows are adjusted rather than duplicated."""
        entries = [
            {"account_id": 1, "debit": 600.00, "credit": 0.0},
            {"account_id": 2, "debit": 0.0, "credit": 600.01},
            {"account_id": 99, "debit": 0.0, "credit": 0.02},
        ]

        result = self.engine._balance_entries_with_round_off(1, entries, [])
        round_off_entries = [entry for entry in result if entry["account_id"] == 99]

        self.assertEqual(len(round_off_entries), 1)
        self.assertEqual(round_off_entries[0]["debit"], 0.01)
        self.assertEqual(round_off_entries[0]["credit"], 0.0)
        self._assert_balanced(result)


if __name__ == "__main__":
    unittest.main()
