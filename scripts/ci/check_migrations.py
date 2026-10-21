#!/usr/bin/env python3
"""Fail a new Alembic upgrade that is not expand-only.

Downgrade functions may drop objects. An upgrade may do the same only when
the file contains the comment `# contract-step: approved`.
"""

from __future__ import annotations

import ast
import re
import sys
import tempfile
from pathlib import Path

MARKER = re.compile(r"^\s*#.*\bcontract-step:\s*approved\b", re.MULTILINE)
DROP_TABLE = re.compile(r"\bdrop\s+table\b", re.IGNORECASE)
DROP_COLUMN = re.compile(r"\bdrop\s+column\b", re.IGNORECASE)
RENAME_COLUMN = re.compile(r"\brename\s+column\b", re.IGNORECASE)
ALTER_TYPE = re.compile(
    r"\balter\s+column\b[^;]*\b(?:type|set\s+data\s+type)\b",
    re.IGNORECASE,
)
SET_NOT_NULL = re.compile(r"\bset\s+not\s+null\b", re.IGNORECASE)
HAS_DEFAULT = re.compile(r"\bdefault\b", re.IGNORECASE)
EXECUTE_NAMES = {"execute", "exec_driver_sql"}


def problems(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if MARKER.search(text):
        return []
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [f"syntax error: {exc.msg}"]
    upgrade = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "upgrade"
        ),
        None,
    )
    if upgrade is None:
        return ["missing upgrade()"]
    found: list[str] = []
    for node in ast.walk(upgrade):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in {"drop_table", "drop_column"}:
            found.append(name)
        elif name == "alter_column":
            found.extend(_alter_column_problems(node))
        elif name in EXECUTE_NAMES:
            found.extend(_sql_problems(node))
    return found


def check_files(paths: list[str]) -> int:
    failed = 0
    for raw in paths:
        path = Path(raw)
        found = problems(path)
        if not found:
            continue
        failed = 1
        for item in found:
            print(f"destructive migration: {path}: {item}", file=sys.stderr)
    return failed


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _keyword(node: ast.Call, name: str) -> ast.expr | None:
    for item in node.keywords:
        if item.arg == name:
            return item.value
    return None


def _is_none(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _is_false(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _alter_column_problems(node: ast.Call) -> list[str]:
    found: list[str] = []
    renamed = _keyword(node, "new_column_name")
    if renamed is not None and not _is_none(renamed):
        found.append("column rename")
    new_type = _keyword(node, "type_")
    if new_type is not None and not _is_none(new_type):
        found.append("type change")
    nullable = _keyword(node, "nullable")
    if isinstance(nullable, ast.Constant) and nullable.value is False:
        default = _keyword(node, "server_default")
        if default is None or _is_none(default) or _is_false(default):
            found.append("NOT NULL without server_default")
    return found


def _sql_problems(node: ast.Call) -> list[str]:
    found: list[str] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Constant) or not isinstance(child.value, str):
            continue
        sql = child.value
        if DROP_TABLE.search(sql):
            found.append("SQL drop table")
        if DROP_COLUMN.search(sql):
            found.append("SQL drop column")
        if RENAME_COLUMN.search(sql):
            found.append("SQL column rename")
        if ALTER_TYPE.search(sql):
            found.append("SQL type change")
        if SET_NOT_NULL.search(sql) and not HAS_DEFAULT.search(sql):
            found.append("SQL NOT NULL without default")
    return found


def _self_test() -> int:
    cases = [
        (
            True,
            "create table and downgrade drop",
            "def upgrade():\n"
            "    op.create_table('t', sa.Column('id', sa.Integer(), nullable=False))\n"
            "def downgrade():\n"
            "    op.drop_table('t')\n",
        ),
        (
            False,
            "drop column in upgrade",
            "def upgrade():\n    op.drop_column('t', 'c')\n",
        ),
        (
            False,
            "drop table in upgrade",
            "def upgrade():\n    op.drop_table('t')\n",
        ),
        (
            True,
            "approved contract step",
            "# contract-step: approved\n"
            "def upgrade():\n    op.drop_table('t')\n",
        ),
        (
            False,
            "rename",
            "def upgrade():\n"
            "    op.alter_column('t', 'c', new_column_name='d')\n",
        ),
        (
            False,
            "type change",
            "def upgrade():\n"
            "    op.alter_column('t', 'c', type_=sa.String(10))\n",
        ),
        (
            False,
            "not null without default",
            "def upgrade():\n    op.alter_column('t', 'c', nullable=False)\n",
        ),
        (
            True,
            "not null with server default",
            "def upgrade():\n"
            "    op.alter_column('t', 'c', nullable=False, server_default=sa.text('0'))\n",
        ),
        (
            False,
            "sql drop column",
            "def upgrade():\n    op.execute('ALTER TABLE t DROP COLUMN c')\n",
        ),
        (
            True,
            "sql drop only in downgrade",
            "def upgrade():\n    op.execute('SELECT 1')\n"
            "def downgrade():\n    op.execute('DROP TABLE t')\n",
        ),
        (
            False,
            "batch drop column",
            "def upgrade():\n"
            "    with op.batch_alter_table('t') as batch:\n"
            "        batch.drop_column('c')\n",
        ),
        (False, "syntax error", "def upgrade(\n"),
        (False, "missing upgrade", "def downgrade():\n    pass\n"),
    ]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for ok, label, body in cases:
            path = root / f"{label.replace(' ', '_')}.py"
            path.write_text(body, encoding="utf-8")
            found = problems(path)
            if ok and found:
                print(f"self-test expected pass: {label}: {found}", file=sys.stderr)
                return 1
            if not ok and not found:
                print(f"self-test expected failure: {label}", file=sys.stderr)
                return 1
    print("migration contract self-test: ok")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv[1:]:
        return _self_test()
    paths = [item for item in argv[1:] if not item.startswith("-")]
    return check_files(paths)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
