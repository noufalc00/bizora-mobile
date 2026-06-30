# Validation Report

Package: Sales / Purchase Books modules

## Compile

All generated Python files compiled successfully.

## Placeholder scan

Generated module files contain zero hardcoded SQL question mark placeholders.

## Runtime query checks against uploaded accounting.db copy

Active company in uploaded DB:
- Varnam Clothing Centre Vdl
- company_id 24

Observed data from logic layer:
- Sales Book bill wise rows: 4
- Sales Book item wise rows: 5
- Sales Book tax summary rows: 1
- Sales Book party wise rows: 2
- Purchase Book bill wise rows: 3
- Purchase Book item wise rows: 6
- Purchase Book tax summary rows: 1
- Purchase Book party wise rows: 1
- Sales Return Book rows: 0 in sample DB range
- Purchase Return Book rows: 0 in sample DB range

## Notes

Return books are implemented. They will show rows when sales return or purchase return vouchers exist in the database.
