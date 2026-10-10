"""فحص صحة قاعدة البيانات — للقراءة فقط.

كل جلسة في هذا المشروع احتاجت نفس الأسئلة: هل الختم عند أحدث مراجعة؟ هل بقيت
جداول ``_alembic_tmp_`` من هجرة انصفت في منتصفها؟ هل هناك صفوف يتيمة؟ هذا
مصمَّم ليعمل على أي ملف قاعدة بيانات دون أن يكتب فيه شيئًا، ويعطي رمز خروج غير
صفري عند وجود مشكلة — فيصلح كخطوة قبل النشر أو كخطوة في CI.

الاستعمال::

    python scripts/check_db_health.py                     # القاعدة الافتراضية
    python scripts/check_db_health.py some_copy.db         # نسخة
    python scripts/check_db_health.py --at-head-only       # تحذير بدل الفشل

لا يتصل بأي شيء: يفتح الملف بوضع القراءة ``mode=ro``، فيفشل بدل أن يعدّل لو
انحرف المسار أو أُعطي ملفًا غير موجود.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_DB = ROOT / "fleet_assets.db"
TEMP_TABLE_PREFIX = "_alembic_tmp_"


def _connect_ro(path: Path) -> sqlite3.Connection:
    """يفتح الملف للقراءة فقط. لا يوجد مسار يكتب هنا."""
    resolved = path.resolve()
    if not resolved.is_file():
        raise SystemExit(f"no such database: {resolved}")
    return sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True)


def alembic_head() -> str | None:
    """أحدث مراجعة في migrations/versions، أو None إن تعذّرت القراءة."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config(str(ROOT / "alembic.ini"))
        return ScriptDirectory.from_config(config).get_current_head()
    except Exception:
        return None


def check(path: Path) -> tuple[list[str], list[str]]:
    """يعيد (مشكلات، تحذيرات). كل الاستعلامات قراءة فقط."""
    problems: list[str] = []
    warnings: list[str] = []

    con = _connect_ro(path)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            problems.append(f"integrity_check: {integrity}")

        tables = [
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'")
        ]

        for row in con.execute("SELECT name FROM sqlite_master WHERE name LIKE ?",
                               (f"{TEMP_TABLE_PREFIX}%",)):
            warnings.append(
                f"stray table {row[0]!r} left by a half-applied batch_alter_table; "
                "it makes the next migration fail with 'table already exists'"
            )

        if "alembic_version" in tables:
            stamps = sorted(
                v[0] for v in con.execute("SELECT version_num FROM alembic_version")
            )
            head = alembic_head()
            if head and stamps != [head]:
                problems.append(
                    f"alembic_version is {stamps} but head is {head!r}; "
                    "run: python -m alembic upgrade head"
                )
            elif not head:
                warnings.append("could not read the migration head to compare against")
        else:
            warnings.append("no alembic_version table -- never migrated")

        grouped: dict[str, list] = {}
        for table, rowid, parent, _fkid in con.execute("PRAGMA foreign_key_check"):
            grouped.setdefault(f"{table} -> {parent}", []).append(rowid)
        for target, rows in sorted(grouped.items()):
            problems.append(
                f"{len(rows)} orphaned row(s) in {target}, e.g. rowid {rows[0]}"
            )
    finally:
        con.close()

    return problems, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="read-only SQLite health check")
    parser.add_argument("database", nargs="?", type=Path, default=DEFAULT_DB,
                        help=f"path to the SQLite file (default: {DEFAULT_DB.name})")
    parser.add_argument("--at-head-only", action="store_true",
                        help="report problems without failing the exit code")
    args = parser.parse_args(argv)

    problems, warnings = check(args.database)

    print(f"database: {args.database.resolve()}")
    if warnings:
        print(f"\n{len(warnings)} warning(s)")
        for item in warnings:
            print(f"  ! {item}")
    if problems:
        print(f"\n{len(problems)} problem(s)")
        for item in problems:
            print(f"  x {item}")
    else:
        print("\nno problems found")

    return 1 if (problems and not args.at_head_only) else 0


if __name__ == "__main__":
    raise SystemExit(main())