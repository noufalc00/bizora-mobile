"""
DB Schema + Index MySQL Compatibility Scanner

This scanner inspects db.py for schema and index compatibility issues
that may affect MySQL migration.
"""

import re
from pathlib import Path
from datetime import datetime


class DBSchemaMySQLCompatibilityScanner:
    """Scanner for db.py schema/index MySQL compatibility issues."""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.db_py_path = self.project_root / "db.py"
        self.issues = []
        
        # Fields that should be VARCHAR-safe (indexed, unique, or search-heavy)
        self.varchar_safe_fields = [
            'business_name', 'phone_number', 'gstin', 'email', 'state', 'pincode',
            'name', 'account_name', 'party_name', 'product_name', 'barcode', 'hsn',
            'voucher_no', 'voucher_type', 'invoice_number', 'purchase_number',
            'return_number', 'bill_no', 'bill_series', 'account_number', 'ifsc_code',
            'bank_name', 'branch_name', 'type', 'category', 'party_type', 'account_type',
        ]
        
        # Fields that can remain TEXT (long text fields)
        self.text_safe_fields = [
            'address', 'narration', 'notes', 'description', 'message',
        ]
    
    def scan(self):
        """Scan db.py for schema/index compatibility issues."""
        if not self.db_py_path.exists():
            print(f"ERROR: db.py not found at {self.db_py_path}")
            return
        
        print(f"Scanning db.py at: {self.db_py_path}")
        print("=" * 80)
        
        with open(self.db_py_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            self._check_line(line_num, line, lines)
        
        self._generate_report()
    
    def _check_line(self, line_num: int, line: str, all_lines: list):
        """Check a single line for compatibility issues."""
        # Skip comments
        if line.strip().startswith('#'):
            return
        
        # Check for TEXT fields in UNIQUE constraints or indexed columns
        for field in self.varchar_safe_fields:
            # Check: field TEXT UNIQUE or field TEXT NOT NULL UNIQUE
            if re.search(rf'{field}\s+TEXT\s+(?:NOT\s+NULL\s+)?UNIQUE', line, re.IGNORECASE):
                context = self._get_context(line_num, all_lines)
                self.issues.append({
                    'line': line_num,
                    'severity': 'WARNING',
                    'description': f'TEXT field "{field}" in UNIQUE constraint (should be VARCHAR for MySQL)',
                    'code': line.strip(),
                    'context': context,
                    'suggested_fix': f'Use {self._get_varchar_suggestion(field)} instead of TEXT'
                })
            
            # Check: field TEXT NOT NULL (for indexed/search-heavy fields)
            if re.search(rf'{field}\s+TEXT\s+NOT\s+NULL', line, re.IGNORECASE):
                context = self._get_context(line_num, all_lines)
                self.issues.append({
                    'line': line_num,
                    'severity': 'WARNING',
                    'description': f'TEXT field "{field}" (should be VARCHAR for MySQL index compatibility)',
                    'code': line.strip(),
                    'context': context,
                    'suggested_fix': f'Use {self._get_varchar_suggestion(field)} instead of TEXT'
                })
        
        # Check for raw CREATE INDEX IF NOT EXISTS
        if re.search(r'CREATE\s+(UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS', line, re.IGNORECASE):
            context = self._get_context(line_num, all_lines)
            self.issues.append({
                'line': line_num,
                'severity': 'CRITICAL',
                'description': 'Raw CREATE INDEX IF NOT EXISTS (MySQL does not support IF NOT EXISTS)',
                'code': line.strip(),
                'context': context,
                'suggested_fix': 'Use self.create_index_if_missing() helper method'
            })
        
        # Check for PRAGMA usage without clear SQLite guard
        if 'PRAGMA' in line.upper():
            # Check if it's inside a SQLite guard
            context_start = max(0, line_num - 10)
            context = '\n'.join(all_lines[context_start:line_num])
            if 'if self._is_sqlite():' not in context and 'if self.db_type == "sqlite":' not in context:
                self.issues.append({
                    'line': line_num,
                    'severity': 'CRITICAL',
                    'description': 'PRAGMA statement without clear SQLite-only guard',
                    'code': line.strip(),
                    'context': self._get_context(line_num, all_lines),
                    'suggested_fix': 'Wrap PRAGMA in "if self._is_sqlite():" block'
                })
        
        # Check for sqlite_master usage without clear SQLite guard
        if 'sqlite_master' in line.lower():
            context_start = max(0, line_num - 10)
            context = '\n'.join(all_lines[context_start:line_num])
            if 'if self._is_sqlite():' not in context and 'if self.db_type == "sqlite":' not in context:
                self.issues.append({
                    'line': line_num,
                    'severity': 'CRITICAL',
                    'description': 'sqlite_master usage without clear SQLite-only guard',
                    'code': line.strip(),
                    'context': self._get_context(line_num, all_lines),
                    'suggested_fix': 'Wrap sqlite_master usage in "if self._is_sqlite():" block or use information_schema for MySQL'
                })
        
        # Check for INSERT OR REPLACE
        if re.search(r'INSERT\s+OR\s+REPLACE', line, re.IGNORECASE):
            context_start = max(0, line_num - 5)
            context = '\n'.join(all_lines[context_start:line_num])
            if 'if self._is_sqlite():' not in context:
                self.issues.append({
                    'line': line_num,
                    'severity': 'CRITICAL',
                    'description': 'INSERT OR REPLACE (SQLite-only) without backend guard',
                    'code': line.strip(),
                    'context': self._get_context(line_num, all_lines),
                    'suggested_fix': 'Use backend-safe: if self._is_sqlite(): INSERT OR REPLACE ... else: INSERT ... ON DUPLICATE KEY UPDATE ...'
                })
        
        # Check for AUTOINCREMENT usage
        if 'AUTOINCREMENT' in line.upper():
            context = self._get_context(line_num, all_lines)
            self.issues.append({
                'line': line_num,
                'severity': 'WARNING',
                'description': 'AUTOINCREMENT usage (SQLite-specific)',
                'code': line.strip(),
                'context': context,
                'suggested_fix': 'Use self._get_primary_key_autoincrement() helper'
            })
    
    def _get_context(self, line_num: int, all_lines: list) -> str:
        """Get context around a line."""
        context_start = max(0, line_num - 2)
        context_end = min(len(all_lines), line_num + 2)
        return '\n'.join(all_lines[context_start:context_end])
    
    def _get_varchar_suggestion(self, field: str) -> str:
        """Get VARCHAR suggestion for a field."""
        # Suggest appropriate length based on field
        if field in ['business_name', 'name', 'account_name', 'party_name', 'product_name', 'bank_name', 'branch_name']:
            return 'self._get_varchar_type(255)'
        elif field in ['barcode', 'hsn']:
            return 'self._get_varchar_type(100)'
        elif field in ['phone_number', 'account_number', 'ifsc_code']:
            return 'self._get_varchar_type(50)'
        elif field in ['gstin', 'email']:
            return 'self._get_varchar_type(255)'
        elif field in ['invoice_number', 'purchase_number', 'return_number', 'bill_no']:
            return 'self._get_varchar_type(50)'
        elif field in ['state']:
            return 'self._get_varchar_type(100)'
        elif field in ['pincode']:
            return 'self._get_varchar_type(20)'
        elif field in ['voucher_no', 'voucher_type', 'bill_series']:
            return 'self._get_varchar_type(50)'
        elif field in ['type', 'category', 'party_type', 'account_type']:
            return 'self._get_varchar_type(50)'
        else:
            return 'self._get_varchar_type(255)'
    
    def _generate_report(self):
        """Generate the markdown report."""
        report_dir = self.project_root / "reports"
        report_dir.mkdir(exist_ok=True)
        
        report_path = report_dir / "db_schema_mysql_compatibility_report.md"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("# DB Schema + Index MySQL Compatibility Scanner Report\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**File Scanned:** {self.db_py_path}\n")
            f.write(f"**Total Issues Found:** {len(self.issues)}\n\n")
            
            # Count by severity
            critical_issues = [i for i in self.issues if i['severity'] == 'CRITICAL']
            warning_issues = [i for i in self.issues if i['severity'] == 'WARNING']
            
            f.write(f"**Critical Issues:** {len(critical_issues)}\n")
            f.write(f"**Warning Issues:** {len(warning_issues)}\n\n")
            
            if not self.issues:
                f.write("## ✅ NO ISSUES FOUND\n\n")
                f.write("db.py has no schema/index compatibility issues for MySQL migration.\n")
            else:
                f.write("## ISSUES FOUND\n\n")
                
                # Group by severity
                for severity in ['CRITICAL', 'WARNING']:
                    severity_issues = [i for i in self.issues if i['severity'] == severity]
                    if severity_issues:
                        f.write(f"### {severity} Issues ({len(severity_issues)})\n\n")
                        
                        for i, issue in enumerate(severity_issues, 1):
                            f.write(f"#### {severity} Issue {i}\n\n")
                            f.write(f"**Line:** {issue['line']}\n")
                            f.write(f"**Description:** {issue['description']}\n")
                            f.write(f"**Code:**\n```\n{issue['code']}\n```\n")
                            f.write(f"**Context:**\n```\n{issue['context']}\n```\n")
                            if 'suggested_fix' in issue:
                                f.write(f"**Suggested Fix:** {issue['suggested_fix']}\n")
                            f.write("\n")
        
        print(f"\nReport written to: {report_path}")
        print(f"Total issues: {len(self.issues)} (Critical: {len(critical_issues)}, Warnings: {len(warning_issues)})")


def main():
    """Main entry point."""
    import sys
    
    # Get project root from script location
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    
    scanner = DBSchemaMySQLCompatibilityScanner(str(project_root))
    scanner.scan()


if __name__ == "__main__":
    main()
