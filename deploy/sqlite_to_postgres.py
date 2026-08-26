#!/usr/bin/env python3
"""Copy KrishiMitra's local SQLite data into Cloud SQL for PostgreSQL.

This moves DATA only. The PostgreSQL schema must already exist — create it by
running the migration job (``deploy/30-deploy.sh`` does this automatically, or
``gcloud run jobs execute krishimitra-migrate``) before running this script.
Deliberately so: keeping one authority for the schema means this tool cannot
drift away from what the application expects.

Typical use, from a workstation, through the Cloud SQL Auth Proxy::

    # 1. terminal A — open a local tunnel to Cloud SQL
    cloud-sql-proxy PROJECT:asia-south1:krishimitra-pg --port 5433

    # 2. terminal B — copy the data
    export PGPASSWORD="$(gcloud secrets versions access latest \\
        --secret=krishimitra-db-password --project=PROJECT)"
    python deploy/sqlite_to_postgres.py \\
        --sqlite /tmp/agrotech_artifacts/agrotech.db \\
        --database-url "postgresql://agrotech:$PGPASSWORD@127.0.0.1:5433/agrotech" \\
        --dry-run          # inspect the plan first
    python deploy/sqlite_to_postgres.py \\
        --sqlite /tmp/agrotech_artifacts/agrotech.db \\
        --database-url "postgresql://agrotech:$PGPASSWORD@127.0.0.1:5433/agrotech"

Safety properties:

* **Dry run by habit.** ``--dry-run`` reports exactly what would be inserted and
  touches nothing.
* **Never destructive.** Existing PostgreSQL rows are never updated or deleted.
  Conflicting primary keys are skipped (``ON CONFLICT DO NOTHING``) unless you
  pass ``--truncate``, which asks for confirmation first.
* **Column intersection.** Only columns present in BOTH databases are copied, so
  a schema that has moved on in PostgreSQL does not abort the migration.
* **One transaction per table.** A failure rolls that table back rather than
  leaving a half-loaded table behind.

Requires ``psycopg`` (v3) or ``psycopg2``; the ml-service ``cloud`` extra
provides one of them.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from typing import Any, Iterable

# Parent-before-child, so foreign keys resolve without disabling triggers
# (Cloud SQL does not hand out real superuser, so `SET session_replication_role`
# is not available to the application user).
PREFERRED_ORDER = [
    "users",
    "farms",
    "uploads",
    "advisories",
    "translation_cache",
    "audit_logs",
]

BATCH_SIZE = 500


def connect_postgres(database_url: str):
    """Return (connection, paramstyle_placeholder) for psycopg 3 or psycopg2."""
    try:
        import psycopg  # type: ignore

        return psycopg.connect(database_url), "%s"
    except ImportError:
        pass
    try:
        import psycopg2  # type: ignore

        return psycopg2.connect(database_url), "%s"
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise SystemExit(
            "neither psycopg (v3) nor psycopg2 is installed.\n"
            "  pip install 'psycopg[binary]'\n"
            "or run this inside the API image, which ships the cloud extra."
        ) from exc


def sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    names = [r[0] for r in rows]
    # Known tables first, in dependency order; anything new goes on the end.
    ordered = [t for t in PREFERRED_ORDER if t in names]
    ordered += [t for t in names if t not in ordered]
    return ordered


def sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def postgres_columns(pg_conn, table: str) -> list[str]:
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s "
            "ORDER BY ordinal_position",
            (table,),
        )
        return [r[0] for r in cur.fetchall()]


def chunked(rows: Iterable[Any], size: int) -> Iterable[list[Any]]:
    batch: list[Any] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--sqlite",
        default="/tmp/agrotech_artifacts/agrotech.db",
        help="path to the SQLite database (default: %(default)s)",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("AGROTECH_DATABASE_URL", ""),
        help="PostgreSQL URL (default: $AGROTECH_DATABASE_URL)",
    )
    parser.add_argument(
        "--tables",
        default="",
        help="comma-separated subset of tables to copy (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be copied and exit without writing",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="DELETE existing rows in each target table first (asks first)",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        parser.error("--database-url is required (or set AGROTECH_DATABASE_URL)")
    if not os.path.isfile(args.sqlite):
        parser.error(f"no SQLite database at {args.sqlite}")

    sq = sqlite3.connect(f"file:{args.sqlite}?mode=ro", uri=True)
    sq.row_factory = sqlite3.Row

    tables = sqlite_tables(sq)
    if args.tables:
        wanted = {t.strip() for t in args.tables.split(",") if t.strip()}
        missing = wanted - set(tables)
        if missing:
            parser.error(f"not present in the SQLite database: {', '.join(sorted(missing))}")
        tables = [t for t in tables if t in wanted]

    pg_conn, ph = connect_postgres(args.database_url)

    # Redact the password before echoing the target back to the operator.
    safe_url = args.database_url
    if "@" in safe_url and "://" in safe_url:
        scheme, _, rest = safe_url.partition("://")
        creds, _, host = rest.rpartition("@")
        user = creds.split(":", 1)[0] if creds else ""
        safe_url = f"{scheme}://{user}:***@{host}" if creds else safe_url

    print(f"source : {args.sqlite}")
    print(f"target : {safe_url}")
    print(f"mode   : {'DRY RUN' if args.dry_run else 'WRITE'}")
    print()

    if args.truncate and not args.dry_run:
        print("--truncate will DELETE every existing row in these tables:")
        for table in tables:
            print(f"    {table}")
        reply = input("Type 'DELETE' to confirm: ")
        if reply != "DELETE":
            print("aborted", file=sys.stderr)
            return 1

    total_copied = 0
    total_skipped = 0

    for table in tables:
        src_cols = sqlite_columns(sq, table)
        dst_cols = postgres_columns(pg_conn, table)

        if not dst_cols:
            print(f"  {table:<20} SKIPPED — no such table in PostgreSQL "
                  f"(run the migration job first)")
            continue

        shared = [c for c in src_cols if c in dst_cols]
        dropped = [c for c in src_cols if c not in dst_cols]
        added = [c for c in dst_cols if c not in src_cols]
        if not shared:
            print(f"  {table:<20} SKIPPED — no columns in common")
            continue

        rows = sq.execute(
            "SELECT {} FROM \"{}\"".format(
                ", ".join(f'"{c}"' for c in shared), table
            )
        ).fetchall()

        note = ""
        if dropped:
            note += f"  [not in target: {', '.join(dropped)}]"
        if added:
            note += f"  [target-only, left at default: {', '.join(added)}]"

        if args.dry_run:
            print(f"  {table:<20} would copy {len(rows):>6} row(s){note}")
            total_copied += len(rows)
            continue

        column_sql = ", ".join(f'"{c}"' for c in shared)
        placeholders = ", ".join([ph] * len(shared))
        # ON CONFLICT DO NOTHING makes re-runs safe: rows already migrated are
        # left exactly as they are, so this script can be run repeatedly during
        # a staged cutover.
        insert_sql = (
            f'INSERT INTO "{table}" ({column_sql}) VALUES ({placeholders}) '
            f"ON CONFLICT DO NOTHING"
        )

        inserted = 0
        try:
            with pg_conn.cursor() as cur:
                if args.truncate:
                    cur.execute(f'DELETE FROM "{table}"')
                for batch in chunked(rows, BATCH_SIZE):
                    cur.executemany(insert_sql, [tuple(r) for r in batch])
                    inserted += len(batch)
            pg_conn.commit()
        except Exception as exc:  # noqa: BLE001 - report and continue per table
            pg_conn.rollback()
            print(f"  {table:<20} FAILED — {exc}")
            total_skipped += len(rows)
            continue

        print(f"  {table:<20} copied {inserted:>6} row(s){note}")
        total_copied += inserted

    sq.close()
    pg_conn.close()

    print()
    if args.dry_run:
        print(f"dry run complete: {total_copied} row(s) would be copied")
        print("re-run without --dry-run to apply")
    else:
        print(f"done: {total_copied} row(s) copied, {total_skipped} skipped")
        print()
        print("Verify with:")
        print('  psql "$AGROTECH_DATABASE_URL" -c "SELECT count(*) FROM users;"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
