#!/usr/bin/env python3
"""Apply the hosted schema and optional Supabase public-read policy."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_ROOT = ROOT / "db"
URL_ENV = "ATLAS_DATABASE_URL"


def parse_args() -> argparse.Namespace:
    """Parse migration scope without placing credentials on argv."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema-only", action="store_true")
    return parser.parse_args()


def read_sql(schema_only: bool) -> list[str]:
    """Load ordered, reviewed SQL migration units."""
    names = ["schema.sql"] if schema_only else ["schema.sql", "policy.sql"]
    return [(DB_ROOT / name).read_text(encoding="utf-8") for name in names]


def main() -> None:
    """Apply migrations transactionally through a server-only connection."""
    args = parse_args()
    database_url = os.environ.get(URL_ENV, "")
    if not database_url:
        raise SystemExit(f"{URL_ENV} is required")
    import psycopg

    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            for statement in read_sql(args.schema_only):
                cursor.execute(statement)
    print("Hosted database migration applied")


if __name__ == "__main__":
    main()
