import sys
sys.path.insert(0, r'h:\Shared drives\My Drive\App making\apps with windsurf\accounting_app')
from tools.audit_active_logic_mysql_placeholders import ActiveLogicPlaceholderScanner, Path

scanner = ActiveLogicPlaceholderScanner(r'h:\Shared drives\My Drive\App making\apps with windsurf\accounting_app')
scanner.scan()
