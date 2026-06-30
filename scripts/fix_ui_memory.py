"""
Repair UiMemoryMixin wiring after a faulty batch patch.

- Removes module-level ``self._init_ui_memory()`` lines.
- Ensures ``UiMemoryMixin`` appears before QWidget/QDialog/QMainWindow bases.
- Inserts ``self._init_ui_memory()`` at the end of each patched class ``__init__``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "ui"

WIDGET_BASES = {"QWidget", "QDialog", "QMainWindow"}


class InitPatcher(ast.NodeTransformer):
    """Append ``self._init_ui_memory()`` to targeted ``__init__`` methods."""

    def __init__(self, class_names: set[str]):
        self.class_names = class_names
        self._current_class: str | None = None
        self.changed = False

    def visit_ClassDef(self, node: ast.ClassDef):  # noqa: N802
        if "UiMemoryMixin" in {base.id for base in node.bases if isinstance(base, ast.Name)}:
            previous = self._current_class
            self._current_class = node.name
            node = self.generic_visit(node)
            self._current_class = previous
            return node
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):  # noqa: N802
        if node.name != "__init__" or self._current_class not in self.class_names:
            return self.generic_visit(node)

        for statement in node.body:
            if (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Call)
                and isinstance(statement.value.func, ast.Attribute)
                and statement.value.func.attr == "_init_ui_memory"
            ):
                return self.generic_visit(node)

        call = ast.Expr(
            value=ast.Call(
                func=ast.Attribute(value=ast.Name(id="self", ctx=ast.Load()), attr="_init_ui_memory", ctx=ast.Load()),
                args=[],
                keywords=[],
            )
        )
        node.body.append(call)
        self.changed = True
        return self.generic_visit(node)


def _reorder_bases(source: str) -> str:
    pattern = re.compile(
        r"^class\s+(\w+)\s*\(([^)]*)\)\s*:",
        re.M,
    )

    def replacer(match: re.Match[str]) -> str:
        class_name = match.group(1)
        bases = [part.strip() for part in match.group(2).split(",") if part.strip()]
        if "UiMemoryMixin" not in bases:
            return match.group(0)

        ordered: list[str] = []
        if "UiMemoryMixin" in bases:
            ordered.append("UiMemoryMixin")
        for base in bases:
            if base == "UiMemoryMixin":
                continue
            ordered.append(base)
        return f"class {class_name}({', '.join(ordered)}):"

    return pattern.sub(replacer, source)


def fix_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    if "UiMemoryMixin" not in original:
        return False

    lines = original.splitlines()
    cleaned_lines = [line for line in lines if line.strip() != "self._init_ui_memory()"]
    source = "\n".join(cleaned_lines)
    if original.endswith("\n"):
        source += "\n"

    source = _reorder_bases(source)

    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        print(f"Syntax error in {path.name}: {error}")
        return False

    class_names = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "UiMemoryMixin" for base in node.bases)
    }
    patcher = InitPatcher(class_names)
    tree = patcher.visit(tree)
    if not patcher.changed and cleaned_lines == lines and source == original:
        return False

    ast.fix_missing_locations(tree)
    new_source = ast.unparse(tree)
    if not new_source.endswith("\n"):
        new_source += "\n"
    path.write_text(new_source, encoding="utf-8")
    return True


def main() -> None:
    fixed: list[str] = []
    for path in sorted(UI_DIR.glob("*.py")):
        if fix_file(path):
            fixed.append(path.name)
    print(f"Fixed {len(fixed)} file(s):")
    for name in fixed:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
