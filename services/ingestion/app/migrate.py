"""Plain-SQL migration runner.

Convention (per CLAUDE.md / Sprint 1 spec): numbered plain SQL files in
services/ingestion/migrations/, no migration framework (no Alembic/sqitch/
dbmate). Each file is expected to be internally idempotent
(`CREATE ... IF NOT EXISTS` etc.), and this runner additionally tracks which
filenames have already been applied in a `_migrations_applied` bookkeeping
table so that re-running the whole set is a safe no-op even for files that
aren't purely declarative.

Usage:
    python -m app.migrate            # apply all pending migrations
    python -m app.migrate --dry-run  # list what would be applied, no changes
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import asyncpg

from eparking_common.config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

_BOOKKEEPING_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS public._migrations_applied (
    filename    TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def discover_migrations() -> list[Path]:
    """Return .sql files in migrations/, sorted by numeric filename prefix."""
    if not MIGRATIONS_DIR.exists():
        return []
    files = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)
    return files


async def apply_migrations(*, dry_run: bool = False) -> list[str]:
    """Apply pending migrations in order. Returns filenames actually applied."""
    settings = get_settings()
    files = discover_migrations()
    if not files:
        print(f"No migration files found in {MIGRATIONS_DIR}")
        return []

    conn = await asyncpg.connect(dsn=settings.asyncpg_dsn)
    applied: list[str] = []
    try:
        await conn.execute(_BOOKKEEPING_TABLE_SQL)

        already_applied = {
            row["filename"]
            for row in await conn.fetch("SELECT filename FROM public._migrations_applied")
        }

        for path in files:
            if path.name in already_applied:
                print(f"[skip]  {path.name} (already applied)")
                continue

            if dry_run:
                print(f"[would apply] {path.name}")
                continue

            sql = path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO public._migrations_applied (filename) VALUES ($1)",
                    path.name,
                )
            print(f"[apply] {path.name}")
            applied.append(path.name)
    finally:
        await conn.close()

    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply pending SQL migrations.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List pending migrations without applying them.",
    )
    args = parser.parse_args()

    try:
        applied = asyncio.run(apply_migrations(dry_run=args.dry_run))
    except Exception as exc:  # noqa: BLE001 - top-level CLI error reporting
        print(f"Migration run failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if not args.dry_run:
        print(f"Done. {len(applied)} migration(s) applied this run.")


if __name__ == "__main__":
    main()
