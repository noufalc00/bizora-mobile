# Cash/Bank Voucher Step 4.7 Navigation Button Fix

Fixed the voucher Previous/Next up/down symbols not being visible.

Cause: the normal QPushButton style had padding that clipped the ▲ / ▼ symbols inside the very small fixed buttons.

Fix:
- Added a dedicated no-padding compact nav button style.
- Kept the Sales/Purchase-style voucher number field with a vertical ▲ / ▼ button stack beside it.
- Added tooltips.
- Disabled focus on nav buttons so keyboard entry flow is not disturbed.

Files changed:
- ui/voucher_grid_common.py

py_compile: success.
