"""Dual-mode database engine: local SQLite file, or managed PostgreSQL.

The rest of the codebase talks to a single small surface (:func:`connect`
returning a :class:`DatabaseConnection`) so the SQL differences between the two
backends live in exactly one place:

* parameter style (``?`` vs ``%s``)
* column types (``REAL`` vs ``DOUBLE PRECISION``)
* autoincrement primary keys (``INTEGER ... AUTOINCREMENT`` vs ``BIGSERIAL``)
* schema introspection (``PRAGMA table_info`` vs ``information_schema``)
* running a multi-statement schema script

Selection is driven purely by ``AGROTECH_DATABASE_URL``: when it is unset the
behaviour is byte-for-byte the previous SQLite behaviour. Any Postgres URL works
(Neon, Supabase, a local container); TLS parameters such as ``?sslmode=require``
are preserved verbatim and handled by libpq.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence

from agrotech_ml.core.settings import AppSettings

SQLITE = "sqlite"
POSTGRES = "postgresql"

Params = Sequence[Any] | Mapping[str, Any]

_TYPE_TOKEN_RE = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")


def normalize_dsn(database_url: str) -> str:
    """Accept the common URL spellings and hand libpq something it understands.

    Only the scheme is rewritten, so query parameters survive untouched. That
    matters for Neon, whose connection strings carry ``?sslmode=require`` (and
    often ``&channel_binding=require``) which libpq must still see.
    """
    dsn = database_url.strip()
    scheme, separator, rest = dsn.partition("://")
    if not separator:
        return dsn
    base = scheme.split("+", 1)[0].lower()
    if base in {"postgres", "postgresql"}:
        return f"postgresql://{rest}"
    return dsn


class Dialect:
    """SQL rendering rules for one backend."""

    name = SQLITE
    placeholder = "?"
    types: dict[str, str] = {
        "TEXT": "TEXT",
        "INTEGER": "INTEGER",
        "REAL": "REAL",
        "SERIAL_PK": "INTEGER PRIMARY KEY AUTOINCREMENT",
    }

    @property
    def is_postgres(self) -> bool:
        return self.name == POSTGRES

    def render(self, sql: str) -> str:
        """Substitute ``{TEXT}``-style type tokens for this backend.

        Unknown ``{...}`` sequences are left untouched, so this is safe to run
        over every statement rather than only over schema DDL.
        """
        if "{" not in sql:
            return sql
        return _TYPE_TOKEN_RE.sub(
            lambda match: self.types.get(match.group(1), match.group(0)), sql
        )

    def prepare(self, sql: str, params: Params | None) -> str:
        """Convert a ``?``-style statement into this backend's parameter style."""
        return sql

    # -- schema introspection -------------------------------------------------

    def existing_columns(self, connection: "DatabaseConnection", table: str) -> set[str]:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row["name"]) for row in rows}

    def ensure_column(
        self, connection: "DatabaseConnection", table: str, definition: str
    ) -> None:
        rendered = self.render(definition)
        column_name = rendered.split()[0]
        if column_name in self.existing_columns(connection, table):
            return
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {rendered}")


class SqliteDialect(Dialect):
    name = SQLITE


class PostgresDialect(Dialect):
    name = POSTGRES
    placeholder = "%s"
    types = {
        "TEXT": "TEXT",
        "INTEGER": "INTEGER",
        "REAL": "DOUBLE PRECISION",
        "SERIAL_PK": "BIGSERIAL PRIMARY KEY",
    }

    def prepare(self, sql: str, params: Params | None) -> str:
        if not params:
            # psycopg only interpolates when parameters are supplied, so a
            # parameterless statement must be left exactly as written.
            return sql
        return _to_pyformat(sql)

    def existing_columns(self, connection: "DatabaseConnection", table: str) -> set[str]:
        rows = connection.execute(
            """
            SELECT column_name AS name
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = ?
            """,
            (table,),
        ).fetchall()
        return {str(row["name"]) for row in rows}


def _to_pyformat(sql: str) -> str:
    """Rewrite ``?`` placeholders to ``%s``, leaving quoted literals alone.

    Literal percent signs are doubled first because psycopg treats ``%`` as the
    start of a placeholder whenever parameters are bound.
    """
    out: list[str] = []
    in_string = False
    for char in sql:
        if char == "'":
            in_string = not in_string
            out.append(char)
        elif char == "%":
            out.append("%%")
        elif char == "?" and not in_string:
            out.append("%s")
        else:
            out.append(char)
    return "".join(out)


def _split_statements(script: str) -> list[str]:
    """Split a schema script on top-level semicolons (no literals contain one)."""
    return [statement.strip() for statement in script.split(";") if statement.strip()]


class DatabaseConnection:
    """Thin, backend-agnostic wrapper around a DB-API connection."""

    def __init__(self, raw: Any, dialect: Dialect) -> None:
        self._raw = raw
        self.dialect = dialect

    @property
    def raw(self) -> Any:
        return self._raw

    def execute(self, sql: str, params: Params | None = None) -> Any:
        statement = self.dialect.prepare(self.dialect.render(sql), params)
        if params is None:
            return self._raw.execute(statement)
        if isinstance(params, Mapping):
            return self._raw.execute(statement, params)
        return self._raw.execute(statement, tuple(params))

    def executescript(self, script: str) -> None:
        rendered = self.dialect.render(script)
        if self.dialect.is_postgres:
            for statement in _split_statements(rendered):
                self._raw.execute(statement)
            return
        self._raw.executescript(rendered)

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()


def _connect_sqlite(settings: AppSettings) -> DatabaseConnection:
    connection = sqlite3.connect(settings.database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return DatabaseConnection(connection, SqliteDialect())


def _connect_postgres(settings: AppSettings) -> DatabaseConnection:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on install extras
        raise RuntimeError(
            "AGROTECH_DATABASE_URL is set but psycopg is not installed. "
            "Install the postgres extra: pip install 'agrotech-ml[postgres]'"
        ) from exc

    assert settings.database_url is not None
    connection = psycopg.connect(normalize_dsn(settings.database_url), row_factory=dict_row)
    return DatabaseConnection(connection, PostgresDialect())


def get_dialect(settings: AppSettings) -> Dialect:
    return PostgresDialect() if settings.use_postgres else SqliteDialect()


@contextmanager
def connect(settings: AppSettings) -> Iterator[DatabaseConnection]:
    connection = (
        _connect_postgres(settings) if settings.use_postgres else _connect_sqlite(settings)
    )
    try:
        yield connection
    finally:
        connection.close()
