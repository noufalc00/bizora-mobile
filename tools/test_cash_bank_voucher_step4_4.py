"""Safe diagnostic test for Cash/Bank voucher Step 4.4 repair.
Runs on a temporary copy of accounting.db and does not alter live data.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMP_DB = ROOT / "cash_bank_step4_4_test_temp.db"
LIVE_DB = ROOT / "accounting.db"
REPORT = ROOT / "reports" / "cash_bank_voucher_step4_4_test_report.md"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    if TEMP_DB.exists():
        TEMP_DB.unlink()
    shutil.copy2(LIVE_DB, TEMP_DB)

    from db import Database
    from bizora_core.cash_bank_voucher_logic import CashBankVoucherLogic
    from bizora_core.day_book_logic import DayBookLogic

    db = Database(db_path=str(TEMP_DB))
    logic = CashBankVoucherLogic(db)
    logic.ensure_schema()
    company = db.get_active_company()
    company_id = int(company["id"])
    logic.ensure_system_accounts(company_id)

    lines = ["# Cash/Bank Voucher Step 4.4 Test", "", f"Company: {company.get('business_name')} ({company_id})", ""]
    results = []

    def first_option(kind):
        opts = logic.get_account_options(company_id, kind)
        if not opts:
            opts = logic.get_account_options(company_id, "general")
        return opts[0]

    test_cases = [
        ("cash_receipt", "debtor", 100.0, 10.0),
        ("cash_payment", "creditor", 120.0, 0.0),
        ("bank_receipt", "debtor", 130.0, 15.0),
        ("bank_payment", "creditor", 140.0, 0.0),
    ]

    for voucher_type, account_kind, amount, discount in test_cases:
        money = logic.get_money_accounts(company_id, voucher_type)[0]
        opt = first_option(account_kind)
        voucher_no = "TEST-" + logic.VOUCHERS[voucher_type]["prefix"] + "-444"
        header = {
            "voucher_no": voucher_no,
            "voucher_date": "2026-05-04",
            "money_account_id": int(money["id"]),
            "remark": f"step4.4 {voucher_type}",
        }
        item = {
            "account_id": int(opt["id"]),
            "party_id": opt.get("party_id"),
            "account_kind": opt.get("kind") or account_kind,
            "towards_voucher_no": "test",
            "amount": amount,
            "discount": discount,
        }
        res = logic.save_or_update_voucher(company_id, voucher_type, header, [item])
        vid = res.get("data", {}).get("id")
        entries = []
        if vid:
            con = sqlite3.connect(TEMP_DB)
            con.row_factory = sqlite3.Row
            entries = [dict(r) for r in con.execute(
                "select debit, credit from ledger_entries where company_id=? and voucher_type=? and voucher_id=?",
                (company_id, voucher_type, vid),
            ).fetchall()]
            con.close()
        total_debit = round(sum(e["debit"] for e in entries), 2)
        total_credit = round(sum(e["credit"] for e in entries), 2)
        balanced = abs(total_debit - total_credit) <= 0.01 and total_debit > 0
        results.append((voucher_type, res.get("success"), balanced, total_debit, total_credit, vid))
        lines.append(f"- {voucher_type}: success={res.get('success')} balanced={balanced} debit={total_debit:.2f} credit={total_credit:.2f}")
        if vid:
            logic.delete_voucher(company_id, voucher_type, int(vid))

    day = DayBookLogic(db).get_day_book_entries(company_id, "2026-05-04", "2026-05-04")
    lines.append("")
    lines.append(f"Day Book callable: {day.get('success')} rows={len(day.get('data', []))}")
    success = all(r[1] and r[2] for r in results) and bool(day.get("success"))
    lines.append("")
    lines.append(f"FINAL_SUCCESS: {success}")
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    try:
        TEMP_DB.unlink()
    except Exception:
        pass
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
