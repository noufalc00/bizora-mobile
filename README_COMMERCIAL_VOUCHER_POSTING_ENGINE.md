# Commercial Voucher Posting Engine Package

Copy these files into the same paths in your running project:

- `logic/voucher_posting_engine.py`
- `tools/test_voucher_posting_engine.py`
- `tools/rebuild_voucher_postings_with_engine.py`
- `WINDSURF_INTEGRATE_VOUCHER_POSTING_ENGINE.txt`

Do not copy or replace `accounting.db`, `db.py`, `config.py`, or `main.py` from any package.

## First command after copying

```bash
python tools/test_voucher_posting_engine.py
```

This is a dry-run. It should not change your data.

## Optional rebuild command after dry-run is clean

```bash
python tools/rebuild_voucher_postings_with_engine.py --apply
```

Only run `--apply` after checking the dry-run report.

## Purpose

The engine gives one commercial posting route:

Voucher save/update -> saved header/items -> delete old ledger entries -> delete old stock movements -> repost ledger -> repost stock -> sync quantity cache.

It is designed to fix hidden issues such as duplicate ledger rows, amount-received changes not reflecting in ledger, and stock movement duplication after update.
