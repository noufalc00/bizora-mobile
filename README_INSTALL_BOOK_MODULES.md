# Sales / Purchase Books Module Package

This package contains four new Books modules for the accounting app:

- Sales Book
- Sales Return Book
- Purchase Book
- Purchase Return Book

## Files included

Copy these files into the matching project folders:

### Logic
- logic/book_report_common.py
- logic/sales_book_logic.py
- logic/sales_return_book_logic.py
- logic/purchase_book_logic.py
- logic/purchase_return_book_logic.py

### UI
- ui/book_report_common.py
- ui/sales_book_page.py
- ui/sales_return_book_page.py
- ui/purchase_book_page.py
- ui/purchase_return_book_page.py
- ui/main_window.py

### Project note
- ACTIVE_RUNTIME_FILES.md

## Very important

Do not replace:
- accounting.db
- db.py
- config.py
- main.py

The included ui/main_window.py is patched from the uploaded active file to add the four Books opening methods and menu routing.

## Manual test after copying

Run:

python -m py_compile logic/book_report_common.py logic/sales_book_logic.py logic/sales_return_book_logic.py logic/purchase_book_logic.py logic/purchase_return_book_logic.py
python -m py_compile ui/book_report_common.py ui/sales_book_page.py ui/sales_return_book_page.py ui/purchase_book_page.py ui/purchase_return_book_page.py ui/main_window.py
python main.py

Then test:

Books -> Sales Book
Books -> Sales Return Book
Books -> Purchase Book
Books -> Purchase Return Book

Each page supports:
- Bill wise
- Item wise
- Tax wise
- Tax summary
- Party wise
- Credit or pending where applicable
- Date range
- Party search completer
- Product search completer
- General search
- Excel export
- PDF export if reportlab is installed
- Double click row details

## Validation performed here

Using the uploaded accounting.db copy:

- Sales Book bill wise returned rows
- Sales Book item wise returned rows
- Purchase Book bill wise returned rows
- Purchase Book item wise returned rows
- Sales Return and Purchase Return returned empty because the sample DB has no return vouchers in the tested date range
- All included Python files passed py_compile
- New files contain no hardcoded SQL question mark placeholders
