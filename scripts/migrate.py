#!/usr/bin/env python3
"""Apply AquaGold SQL migrations once, in lexical order, under an advisory lock."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "neon" / "migrations"
DATABASE_URL_KEYS = ("AQUAGOLD_DATABASE_URL", "DATABASE_URL", "POSTGRES_URL", "NEON_DATABASE_URL")


def database_url() -> str:
    for key in DATABASE_URL_KEYS:
        if os.getenv(key):
            return os.environ[key]
    raise SystemExit("No AquaGold database URL is configured")


def main() -> None:
    files = sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"))
    if not files:
        raise SystemExit("No migrations found")

    with psycopg.connect(database_url(), autocommit=False) as db:
        with db.cursor() as cur:
            cur.execute("select pg_advisory_lock(hashtext('aquagold-schema-migrations'))")
            cur.execute(
                """create table if not exists public.schema_migrations(
                       version text primary key,
                       checksum text not null,
                       applied_at timestamptz not null default now()
                   )"""
            )
            db.commit()
            try:
                for path in files:
                    sql = path.read_text(encoding="utf-8")
                    checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
                    cur.execute("select checksum from public.schema_migrations where version=%s", (path.name,))
                    row = cur.fetchone()
                    if row:
                        if row[0] != checksum:
                            raise RuntimeError(f"Applied migration was modified: {path.name}")
                        print(f"skip  {path.name}")
                        continue
                    print(f"apply {path.name}")
                    cur.execute(sql)
                    cur.execute(
                        "insert into public.schema_migrations(version,checksum) values(%s,%s)",
                        (path.name, checksum),
                    )
                    db.commit()
            finally:
                cur.execute("select pg_advisory_unlock(hashtext('aquagold-schema-migrations'))")
                db.commit()


if __name__ == "__main__":
    main()
