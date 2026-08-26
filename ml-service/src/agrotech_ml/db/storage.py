from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator, Mapping
from uuid import uuid4

from agrotech_ml.models.schemas import (
    AdvisoryRecord,
    AuditLog,
    DashboardSummary,
    FarmProfile,
    FarmProfileCreate,
    FarmerSearchResult,
    FarmerWorkspace,
    UploadAsset,
    UserProfile,
    UserProfileCreate,
)
from agrotech_ml.core.settings import AppSettings
from agrotech_ml.db.engine import DatabaseConnection
from agrotech_ml.db.engine import connect as _engine_connect

# Rows are mappings on both backends (``sqlite3.Row`` / psycopg ``dict_row``).
Row = Mapping[str, Any]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_farmer_id(farmer_id: str | None) -> str | None:
    if not farmer_id:
        return None
    return farmer_id.strip().upper()


@contextmanager
def connect(settings: AppSettings) -> Iterator[DatabaseConnection]:
    """Open a connection to whichever backend this deployment is configured for.

    SQLite when ``AGROTECH_DATABASE_URL`` is unset, PostgreSQL when it is set.
    """
    with _engine_connect(settings) as connection:
        yield connection


def _ensure_column(connection: DatabaseConnection, table: str, definition: str) -> None:
    connection.dialect.ensure_column(connection, table, definition)


def _count(connection: DatabaseConnection, table: str) -> int:
    """COUNT(*) with a named column, since rows are mappings, not tuples."""
    row = connection.execute(f"SELECT COUNT(*) AS total FROM {table}").fetchone()
    return int(row["total"]) if row is not None else 0


def _generate_farmer_id(connection: DatabaseConnection) -> str:
    for _ in range(20):
        candidate = f"KMA-{uuid4().hex[:8].upper()}"
        exists = connection.execute(
            "SELECT 1 FROM users WHERE farmer_id = ?",
            (candidate,),
        ).fetchone()
        if exists is None:
            return candidate
    raise RuntimeError("Unable to generate a unique farmer ID")


def init_db(settings: AppSettings) -> None:
    with connect(settings) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id {TEXT} PRIMARY KEY,
                farmer_id {TEXT},
                name {TEXT} NOT NULL,
                mobile {TEXT} NOT NULL UNIQUE,
                state {TEXT},
                district {TEXT},
                language {TEXT} NOT NULL,
                created_at {TEXT} NOT NULL,
                updated_at {TEXT} NOT NULL
            );

            CREATE TABLE IF NOT EXISTS farms (
                id {TEXT} PRIMARY KEY,
                farmer_id {TEXT},
                mobile {TEXT} NOT NULL,
                farm_name {TEXT} NOT NULL,
                village {TEXT} NOT NULL,
                district {TEXT},
                state {TEXT} NOT NULL,
                acres {REAL} NOT NULL,
                primary_crop {TEXT} NOT NULL,
                soil_type {TEXT},
                irrigation_source {TEXT},
                latitude {REAL},
                longitude {REAL},
                created_at {TEXT} NOT NULL
            );

            CREATE TABLE IF NOT EXISTS uploads (
                id {TEXT} PRIMARY KEY,
                farmer_id {TEXT},
                mobile {TEXT} NOT NULL,
                module {TEXT} NOT NULL,
                filename {TEXT} NOT NULL,
                stored_name {TEXT} NOT NULL,
                content_type {TEXT} NOT NULL,
                size_bytes {INTEGER} NOT NULL,
                notes {TEXT},
                created_at {TEXT} NOT NULL
            );

            CREATE TABLE IF NOT EXISTS advisories (
                id {TEXT} PRIMARY KEY,
                farmer_id {TEXT},
                mobile {TEXT} NOT NULL,
                module {TEXT} NOT NULL,
                summary {TEXT} NOT NULL,
                language {TEXT} NOT NULL,
                request_payload {TEXT} NOT NULL,
                response_payload {TEXT} NOT NULL,
                created_at {TEXT} NOT NULL
            );

            CREATE TABLE IF NOT EXISTS translation_cache (
                id {SERIAL_PK},
                source_text {TEXT} NOT NULL,
                source_language {TEXT} NOT NULL,
                target_language {TEXT} NOT NULL,
                translated_text {TEXT} NOT NULL,
                provider {TEXT} NOT NULL,
                created_at {TEXT} NOT NULL,
                UNIQUE(source_text, source_language, target_language, provider)
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id {TEXT} PRIMARY KEY,
                request_id {TEXT} NOT NULL,
                actor_type {TEXT} NOT NULL,
                actor_id {TEXT},
                action {TEXT} NOT NULL,
                path {TEXT} NOT NULL,
                method {TEXT} NOT NULL,
                status_code {INTEGER} NOT NULL,
                ip_address {TEXT},
                user_agent {TEXT},
                message {TEXT},
                metadata {TEXT} NOT NULL,
                created_at {TEXT} NOT NULL
            );
            """
        )

        _ensure_column(connection, "users", "farmer_id {TEXT}")
        _ensure_column(connection, "farms", "farmer_id {TEXT}")
        _ensure_column(connection, "uploads", "farmer_id {TEXT}")
        _ensure_column(connection, "advisories", "farmer_id {TEXT}")

        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_farmer_id ON users (farmer_id)"
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_farms_mobile ON farms (mobile)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_farms_farmer_id ON farms (farmer_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_uploads_mobile ON uploads (mobile)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_uploads_farmer_id ON uploads (farmer_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_uploads_module ON uploads (module)")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_advisories_mobile ON advisories (mobile)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_advisories_farmer_id ON advisories (farmer_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_advisories_module ON advisories (module)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs (created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_request_id ON audit_logs (request_id)"
        )

        missing_farmer_ids = connection.execute(
            "SELECT id FROM users WHERE farmer_id IS NULL OR farmer_id = ''"
        ).fetchall()
        for row in missing_farmer_ids:
            connection.execute(
                "UPDATE users SET farmer_id = ? WHERE id = ?",
                (_generate_farmer_id(connection), row["id"]),
            )

        connection.execute(
            """
            UPDATE farms
            SET farmer_id = (
                SELECT farmer_id FROM users WHERE users.mobile = farms.mobile
            )
            WHERE farmer_id IS NULL OR farmer_id = ''
            """
        )
        connection.execute(
            """
            UPDATE uploads
            SET farmer_id = (
                SELECT farmer_id FROM users WHERE users.mobile = uploads.mobile
            )
            WHERE farmer_id IS NULL OR farmer_id = ''
            """
        )
        connection.execute(
            """
            UPDATE advisories
            SET farmer_id = (
                SELECT farmer_id FROM users WHERE users.mobile = advisories.mobile
            )
            WHERE farmer_id IS NULL OR farmer_id = ''
            """
        )
        connection.commit()


def _row_to_user(row: Row) -> UserProfile:
    return UserProfile.model_validate(dict(row))


def _row_to_farm(row: Row) -> FarmProfile:
    return FarmProfile.model_validate(dict(row))


def _row_to_upload(row: Row, settings: AppSettings) -> UploadAsset:
    payload = dict(row)
    payload["url"] = f"{settings.public_base_url}/static/uploads/{payload.pop('stored_name')}"
    return UploadAsset.model_validate(payload)


def _row_to_advisory(row: Row) -> AdvisoryRecord:
    payload = dict(row)
    payload["request_payload"] = json.loads(payload["request_payload"])
    payload["response_payload"] = json.loads(payload["response_payload"])
    return AdvisoryRecord.model_validate(payload)


def _row_to_audit_log(row: Row) -> AuditLog:
    payload = dict(row)
    payload["metadata"] = json.loads(payload["metadata"])
    return AuditLog.model_validate(payload)


def _get_user_row(
    connection: DatabaseConnection,
    *,
    mobile: str | None = None,
    farmer_id: str | None = None,
) -> Row | None:
    if mobile:
        row = connection.execute(
            """
            SELECT id, farmer_id, name, mobile, state, district, language, created_at
            FROM users
            WHERE mobile = ?
            """,
            (mobile,),
        ).fetchone()
        if row is not None:
            return row

    normalized_farmer_id = _normalize_farmer_id(farmer_id)
    if normalized_farmer_id:
        return connection.execute(
            """
            SELECT id, farmer_id, name, mobile, state, district, language, created_at
            FROM users
            WHERE farmer_id = ?
            """,
            (normalized_farmer_id,),
        ).fetchone()

    return None


def resolve_mobile(settings: AppSettings, farmer_id: str) -> str | None:
    with connect(settings) as connection:
        row = _get_user_row(connection, farmer_id=farmer_id)
    if row is None:
        return None
    return str(row["mobile"])


def upsert_user(settings: AppSettings, user: UserProfileCreate) -> UserProfile:
    now = _now_iso()
    requested_farmer_id = _normalize_farmer_id(user.farmer_id)

    with connect(settings) as connection:
        existing_by_mobile = _get_user_row(connection, mobile=user.mobile)
        existing_by_farmer_id = (
            _get_user_row(connection, farmer_id=requested_farmer_id)
            if requested_farmer_id
            else None
        )

        if (
            existing_by_farmer_id is not None
            and existing_by_mobile is not None
            and existing_by_farmer_id["id"] != existing_by_mobile["id"]
        ):
            raise ValueError("Farmer ID already belongs to another profile")

        if existing_by_farmer_id is not None and existing_by_mobile is None:
            raise ValueError("Farmer ID already belongs to another mobile number")

        existing = existing_by_mobile or existing_by_farmer_id
        farmer_id = (
            requested_farmer_id
            or (str(existing["farmer_id"]) if existing is not None else None)
            or _generate_farmer_id(connection)
        )

        if existing:
            connection.execute(
                """
                UPDATE users
                SET farmer_id = ?, name = ?, state = ?, district = ?, language = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    farmer_id,
                    user.name,
                    user.state,
                    user.district,
                    user.language,
                    now,
                    existing["id"],
                ),
            )
        else:
            connection.execute(
                """
                INSERT INTO users (
                    id, farmer_id, name, mobile, state, district, language, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    farmer_id,
                    user.name,
                    user.mobile,
                    user.state,
                    user.district,
                    user.language,
                    now,
                    now,
                ),
            )

        connection.commit()
        row = _get_user_row(connection, mobile=user.mobile)
        assert row is not None
        return _row_to_user(row)


def get_user(settings: AppSettings, identifier: str) -> UserProfile | None:
    with connect(settings) as connection:
        row = _get_user_row(connection, mobile=identifier, farmer_id=identifier)
    if row is None:
        return None
    return _row_to_user(row)


def get_user_by_farmer_id(settings: AppSettings, farmer_id: str) -> UserProfile | None:
    with connect(settings) as connection:
        row = _get_user_row(connection, farmer_id=farmer_id)
    if row is None:
        return None
    return _row_to_user(row)


def add_farm(settings: AppSettings, farm: FarmProfileCreate) -> FarmProfile:
    now = _now_iso()
    with connect(settings) as connection:
        user = _get_user_row(connection, mobile=farm.mobile, farmer_id=farm.farmer_id)
        if user is None:
            raise ValueError("Farmer profile must exist before a farm can be saved")

        farmer_id = str(user["farmer_id"])
        record_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO farms (
                id, farmer_id, mobile, farm_name, village, district, state, acres, primary_crop,
                soil_type, irrigation_source, latitude, longitude, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                farmer_id,
                farm.mobile,
                farm.farm_name,
                farm.village,
                farm.district,
                farm.state,
                farm.acres,
                farm.primary_crop,
                farm.soil_type,
                farm.irrigation_source,
                farm.latitude,
                farm.longitude,
                now,
            ),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT id, farmer_id, mobile, farm_name, village, district, state, acres, primary_crop,
                   soil_type, irrigation_source, latitude, longitude, created_at
            FROM farms
            WHERE id = ?
            """,
            (record_id,),
        ).fetchone()
        assert row is not None
        return _row_to_farm(row)


def list_farms(settings: AppSettings, identifier: str) -> list[FarmProfile]:
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT id, farmer_id, mobile, farm_name, village, district, state, acres, primary_crop,
                   soil_type, irrigation_source, latitude, longitude, created_at
            FROM farms
            WHERE mobile = ? OR farmer_id = ?
            ORDER BY created_at DESC
            """,
            (identifier, _normalize_farmer_id(identifier)),
        ).fetchall()
    return [_row_to_farm(row) for row in rows]


def save_upload(
    settings: AppSettings,
    *,
    mobile: str | None,
    module: str,
    filename: str,
    stored_name: str,
    content_type: str,
    size_bytes: int,
    notes: str | None = None,
    farmer_id: str | None = None,
) -> UploadAsset:
    now = _now_iso()
    with connect(settings) as connection:
        user = _get_user_row(connection, mobile=mobile, farmer_id=farmer_id)
        if user is None:
            raise ValueError("Farmer profile must exist before upload")

        resolved_farmer_id = str(user["farmer_id"])
        resolved_mobile = str(user["mobile"])
        record_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO uploads (
                id, farmer_id, mobile, module, filename, stored_name, content_type, size_bytes, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                resolved_farmer_id,
                resolved_mobile,
                module,
                filename,
                stored_name,
                content_type,
                size_bytes,
                notes,
                now,
            ),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT id, farmer_id, mobile, module, filename, stored_name, content_type, size_bytes, notes, created_at
            FROM uploads
            WHERE id = ?
            """,
            (record_id,),
        ).fetchone()
        assert row is not None
        return _row_to_upload(row, settings)


def list_uploads(
    settings: AppSettings,
    identifier: str,
    *,
    module: str | None = None,
) -> list[UploadAsset]:
    query = """
        SELECT id, farmer_id, mobile, module, filename, stored_name, content_type, size_bytes, notes, created_at
        FROM uploads
        WHERE (mobile = ? OR farmer_id = ?)
    """
    params: list[Any] = [identifier, _normalize_farmer_id(identifier)]
    if module:
        query += " AND module = ?"
        params.append(module)
    query += " ORDER BY created_at DESC"

    with connect(settings) as connection:
        rows = connection.execute(query, params).fetchall()
    return [_row_to_upload(row, settings) for row in rows]


def save_advisory(
    settings: AppSettings,
    *,
    mobile: str | None,
    module: str,
    summary: str,
    language: str,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    farmer_id: str | None = None,
) -> AdvisoryRecord:
    now = _now_iso()
    with connect(settings) as connection:
        user = _get_user_row(connection, mobile=mobile, farmer_id=farmer_id)
        if user is None:
            raise ValueError("Farmer profile must exist before saving an advisory")

        resolved_farmer_id = str(user["farmer_id"])
        resolved_mobile = str(user["mobile"])
        record_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO advisories (
                id, farmer_id, mobile, module, summary, language, request_payload, response_payload, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                resolved_farmer_id,
                resolved_mobile,
                module,
                summary,
                language,
                json.dumps(request_payload, ensure_ascii=False),
                json.dumps(response_payload, ensure_ascii=False),
                now,
            ),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT id, farmer_id, mobile, module, summary, language, request_payload, response_payload, created_at
            FROM advisories
            WHERE id = ?
            """,
            (record_id,),
        ).fetchone()
        assert row is not None
        return _row_to_advisory(row)


def list_advisories(
    settings: AppSettings,
    identifier: str,
    *,
    module: str | None = None,
    limit: int = 20,
) -> list[AdvisoryRecord]:
    query = """
        SELECT id, farmer_id, mobile, module, summary, language, request_payload, response_payload, created_at
        FROM advisories
        WHERE (mobile = ? OR farmer_id = ?)
    """
    params: list[Any] = [identifier, _normalize_farmer_id(identifier)]
    if module:
        query += " AND module = ?"
        params.append(module)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with connect(settings) as connection:
        rows = connection.execute(query, params).fetchall()
    return [_row_to_advisory(row) for row in rows]


def search_users(settings: AppSettings, query: str, limit: int = 8) -> list[FarmerSearchResult]:
    pattern = f"%{query.strip()}%"
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT farmer_id, name, mobile, state, district
            FROM users
            -- LOWER(...) on both sides keeps the match case-insensitive on
            -- PostgreSQL too (its LIKE is case-sensitive; SQLite LIKE is not).
            WHERE LOWER(farmer_id) LIKE LOWER(?) OR LOWER(name) LIKE LOWER(?)
               OR mobile LIKE ? OR LOWER(district) LIKE LOWER(?) OR LOWER(state) LIKE LOWER(?)
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (pattern, pattern, pattern, pattern, pattern, limit),
        ).fetchall()

        results: list[FarmerSearchResult] = []
        for row in rows:
            latest_farm = connection.execute(
                """
                SELECT village, primary_crop, acres
                FROM farms
                WHERE farmer_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (row["farmer_id"],),
            ).fetchone()
            results.append(
                FarmerSearchResult(
                    farmer_id=str(row["farmer_id"]),
                    name=str(row["name"]),
                    mobile=str(row["mobile"]),
                    state=row["state"],
                    district=row["district"],
                    village=latest_farm["village"] if latest_farm else None,
                    primary_crop=latest_farm["primary_crop"] if latest_farm else None,
                    acres=float(latest_farm["acres"]) if latest_farm and latest_farm["acres"] is not None else None,
                )
            )
    return results


def get_farmer_workspace(settings: AppSettings, farmer_id: str) -> FarmerWorkspace | None:
    profile = get_user_by_farmer_id(settings, farmer_id)
    if profile is None:
        return None
    return FarmerWorkspace(
        profile=profile,
        farms=list_farms(settings, farmer_id),
        uploads=list_uploads(settings, farmer_id),
        advisories=list_advisories(settings, farmer_id, limit=30),
    )


def get_cached_translation(
    settings: AppSettings,
    *,
    source_text: str,
    source_language: str,
    target_language: str,
    provider: str,
) -> str | None:
    with connect(settings) as connection:
        row = connection.execute(
            """
            SELECT translated_text
            FROM translation_cache
            WHERE source_text = ? AND source_language = ? AND target_language = ? AND provider = ?
            """,
            (source_text, source_language, target_language, provider),
        ).fetchone()
    if row is None:
        return None
    return str(row["translated_text"])


def cache_translation(
    settings: AppSettings,
    *,
    source_text: str,
    source_language: str,
    target_language: str,
    translated_text: str,
    provider: str,
) -> None:
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO translation_cache (
                source_text, source_language, target_language, translated_text, provider, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_text, source_language, target_language, provider)
            DO UPDATE SET translated_text = excluded.translated_text, created_at = excluded.created_at
            """,
            (
                source_text,
                source_language,
                target_language,
                translated_text,
                provider,
                _now_iso(),
            ),
        )
        connection.commit()


def save_audit_log(
    settings: AppSettings,
    *,
    request_id: str,
    actor_type: str,
    actor_id: str | None,
    action: str,
    path: str,
    method: str,
    status_code: int,
    ip_address: str | None,
    user_agent: str | None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    now = _now_iso()
    record_id = str(uuid4())
    with connect(settings) as connection:
        connection.execute(
            """
            INSERT INTO audit_logs (
                id, request_id, actor_type, actor_id, action, path, method, status_code,
                ip_address, user_agent, message, metadata, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                request_id,
                actor_type,
                actor_id,
                action,
                path,
                method,
                status_code,
                ip_address,
                user_agent,
                message,
                json.dumps(metadata or {}, ensure_ascii=False),
                now,
            ),
        )
        connection.commit()
        row = connection.execute(
            """
            SELECT id, request_id, actor_type, actor_id, action, path, method, status_code,
                   ip_address, user_agent, message, metadata, created_at
            FROM audit_logs
            WHERE id = ?
            """,
            (record_id,),
        ).fetchone()
        assert row is not None
        return _row_to_audit_log(row)


def list_audit_logs(settings: AppSettings, limit: int = 100) -> list[AuditLog]:
    with connect(settings) as connection:
        rows = connection.execute(
            """
            SELECT id, request_id, actor_type, actor_id, action, path, method, status_code,
                   ip_address, user_agent, message, metadata, created_at
            FROM audit_logs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_audit_log(row) for row in rows]


def dashboard_summary(
    settings: AppSettings,
    *,
    listed_tools: int,
    investor_deals: int,
    available_languages: int,
    translation_enabled: bool,
    live_search_enabled: bool,
    live_market_enabled: bool = False,
    live_scheme_enabled: bool = False,
    write_auth_enabled: bool = False,
    audit_logging_enabled: bool = False,
) -> DashboardSummary:
    with connect(settings) as connection:
        active_users = _count(connection, "users")
        total_farms = _count(connection, "farms")
        saved_assets = _count(connection, "uploads")
        advisory_runs = _count(connection, "advisories")

    return DashboardSummary(
        active_users=active_users,
        total_farms=total_farms,
        listed_tools=listed_tools,
        investor_deals=investor_deals,
        available_languages=available_languages,
        saved_assets=saved_assets,
        advisory_runs=advisory_runs,
        translation_enabled=translation_enabled,
        live_search_enabled=live_search_enabled,
        live_market_enabled=live_market_enabled,
        live_scheme_enabled=live_scheme_enabled,
        write_auth_enabled=write_auth_enabled,
        audit_logging_enabled=audit_logging_enabled,
    )
