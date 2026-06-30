"""
DB.PY MySQL Placeholder Scanner

This scanner inspects db.py only for hardcoded SQLite `?` placeholders
that need to be replaced with backend-agnostic placeholder usage.
"""

import re
from pathlib import Path
from datetime import datetime


class DBPyPlaceholderScanner:
    """Scanner for db.py MySQL placeholder issues."""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.db_py_path = self.project_root / "db.py"
        self.issues = []
        self.allowed_patterns = [
            r'#.*\?',  # Comments
            r'""".*?\?.*?"""',  # Docstrings/comments
            r"'''.*?\?.*?'''",  # Docstrings/comments
        ]
    
    def scan(self):
        """Scan db.py for hardcoded SQLite placeholders."""
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
        """Check a single line for placeholder issues."""
        # Skip comments
        if line.strip().startswith('#'):
            return
        
        # Skip _get_placeholder() implementation
        if 'def _get_placeholder' in line:
            return
        if 'return "?" if' in line:
            return
        
        # Skip lines inside _get_placeholder method
        context_start = max(0, line_num - 10)
        context = '\n'.join(all_lines[context_start:line_num])
        if 'def _get_placeholder' in context and 'def ' not in context.split('def _get_placeholder')[0].split('\n')[-5:]:
            return
        
        # Check for SQL with hardcoded ?
        patterns = [
            (r'cursor\.execute\([^)]*\?', "cursor.execute with hardcoded ?"),
            (r'self\.execute_query\([^)]*\?', "self.execute_query with hardcoded ?"),
            (r'self\.execute_update\([^)]*\?', "self.execute_update with hardcoded ?"),
            (r'query\s*=\s*["\'][^"\']*\?', "query variable assignment with hardcoded ?"),
            (r'sql\s*=\s*["\'][^"\']*\?', "sql variable assignment with hardcoded ?"),
            (r'INSERT INTO.*VALUES.*\?', "INSERT with hardcoded ?"),
            (r'SELECT.*WHERE.*\?', "SELECT WHERE with hardcoded ?"),
            (r'UPDATE.*SET.*WHERE.*\?', "UPDATE with hardcoded ?"),
            (r'DELETE.*WHERE.*\?', "DELETE with hardcoded ?"),
            (r'PRAGMA.*\?', "PRAGMA with ? placeholder (unsafe for table names)"),
        ]
        
        for pattern, description in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                # Get context
                context_start = max(0, line_num - 2)
                context_end = min(len(all_lines), line_num + 2)
                context = '\n'.join(all_lines[context_start:context_end])
                
                self.issues.append({
                    'line': line_num,
                    'description': description,
                    'code': line.strip(),
                    'context': context
                })
                break  # Only report first match per line
    
    def _generate_report(self):
        """Generate the markdown report."""
        report_path = self.project_root / "reports" / "db_py_mysql_placeholder_report.md"
        report_path.parent.mkdir(exist_ok=True)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("# DB.PY MySQL Placeholder Scanner Report\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**File Scanned:** {self.db_py_path}\n")
            f.write(f"**Total Issues Found:** {len(self.issues)}\n\n")
            
            if not self.issues:
                f.write("## ✅ NO ISSUES FOUND\n\n")
                f.write("db.py has no hardcoded SQLite `?` placeholders that need fixing.\n")
            else:
                f.write("## ISSUES FOUND\n\n")
                f.write(f"The following {len(self.issues)} lines contain hardcoded SQLite `?` placeholders:\n\n")
                
                for i, issue in enumerate(self.issues, 1):
                    f.write(f"### Issue {i}\n\n")
                    f.write(f"**Line:** {issue['line']}\n")
                    f.write(f"**Description:** {issue['description']}\n")
                    f.write(f"**Code:**\n```\n{issue['code']}\n```\n")
                    f.write(f"**Context:**\n```\n{issue['context']}\n```\n\n")
        
        print(f"\nReport written to: {report_path}")
        print(f"Total issues: {len(self.issues)}")


def main():
    """Main entry point."""
    import sys
    
    # Get project root from script location
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    
    scanner = DBPyPlaceholderScanner(str(project_root))
    scanner.scan()


if __name__ == "__main__":
    main()
