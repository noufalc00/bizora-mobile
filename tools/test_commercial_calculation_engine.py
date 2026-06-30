#!/usr/bin/env python3
"""Commercial calculation / posting engine audit and dry-run tests."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import Database
from bizora_core.commercial_voucher_validator import CommercialVoucherValidator
from bizora_core.voucher_posting_engine import VoucherPostingEngine


def active_company_id(db):
    rows = db.execute_query("SELECT id, business_name FROM companies WHERE is_active = 1 LIMIT 1")
    if rows:
        return int(rows[0]["id"]), rows[0]["business_name"]
    rows = db.execute_query("SELECT id, business_name FROM companies ORDER BY id LIMIT 1")
    if rows:
        return int(rows[0]["id"]), rows[0]["business_name"]
    return None, ""


def run():
    db = Database()
    init_result = db.initialize_database()
    company_id, company_name = active_company_id(db)
    lines = []
    lines.append("# Commercial Calculation Engine Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"DB initialize result: {init_result}")
    lines.append(f"Active company: {company_name} ({company_id})")
    lines.append("")

    validator = CommercialVoucherValidator()
    validator_tests = [
        ("cash_sale_overpayment_block", "sales", "Sales", 5000, 10000, False),
        ("credit_sale_overpayment_allow", "sales", "Credit Sales", 5000, 10000, True),
        ("cash_purchase_overpayment_block", "purchase", "Cash", 5000, 10000, False),
        ("credit_purchase_overpayment_allow", "purchase", "Credit", 5000, 10000, True),
        ("cash_return_overpayment_block", "sales_return", "Cash", 5000, 10000, False),
        ("credit_return_overpayment_allow", "sales_return", "Credit", 5000, 10000, True),
    ]
    all_ok = True
    lines.append("## Validator rules")
    for name, vt, ptype, grand, paid, expected in validator_tests:
        res = validator.validate_payment_amount(vt, ptype, grand, paid, "Amount")
        ok = bool(res["success"]) == expected
        all_ok = all_ok and ok
        lines.append(f"- {name}: {'PASS' if ok else 'FAIL'} result={res}")
    lines.append("")

    engine = VoucherPostingEngine(db)
    lines.append("## Existing voucher dry-run")
    if not company_id:
        lines.append("No company found; voucher dry-run skipped.")
        all_ok = False
    else:
        result = engine.repost_all_company(company_id, dry_run=True)
        all_ok = all_ok and bool(result.get("success"))
        lines.append(f"success: {result.get('success')}")
        lines.append(f"posted: {result.get('posted')}")
        lines.append(f"failed_count: {len(result.get('failed', []))}")
        for failed in result.get("failed", [])[:20]:
            lines.append(f"- FAILED {failed.get('voucher_type')} {failed.get('voucher_id')}: {failed.get('message')}")
    lines.append("")

    lines.append("## Required engine method audit")
    methods = [
        "repost_voucher_from_db",
        "delete_voucher_postings",
        "post_cash_receipt",
        "post_cash_payment",
        "post_bank_receipt",
        "post_bank_payment",
        "post_journal_entry",
        "update_voucher_ledger_entries",
        "delete_voucher_ledger_entries",
        "repost_all_company",
    ]
    for method in methods:
        exists = hasattr(engine, method)
        all_ok = all_ok and exists
        lines.append(f"- {method}: {'YES' if exists else 'NO'}")
    lines.append("")

    lines.append("## Final")
    lines.append(f"success: {all_ok}")
    if all_ok:
        lines.append("failed_count: 0")
    else:
        lines.append("failed_count: 1")

    report_path = ROOT / "reports" / "commercial_calculation_engine_report.md"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(run())
