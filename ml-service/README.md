# AgroTech Unified Farmer Service

Advanced FastAPI backend for a multilingual farmer platform.
FastAPI app title **"AgroTech Unified Farmer API"**, version **3.0.0**. Requires **Python ≥ 3.13**.

## Included capabilities

- Crop recommendation (ensemble classification — 7 candidate models, best selected automatically)
- Irrigation scheduler (regression model)
- Disease diagnosis from **typed symptom text** (TF-IDF + logistic regression). It does **not** analyse images; an attached photo is stored against the farmer record but never read by the model.
- Fertilizer advisory model
- Soil analyzer (rule-based, needs no trained model)
- Weather forecast and location search (Open-Meteo integration)
- Government scheme navigator (MyScheme)
- Marketplace prices, equipment rental catalog, investor opportunities — each with a committed offline fallback
- Knowledge search and agricultural news
- Profile, farm, upload and advisory-history endpoints
- Optional JWT write-auth, background retraining, and 11-language output

## Quick start

```bash
cd ml-service
python3 -m venv .venv
source .venv/bin/activate
pip install -e .                          # there is NO requirements.txt in this directory
python scripts/bootstrap_datasets.py      # prepares data/ — succeeds with no network
agrotech-train                            # ~36s; writes artifacts/
python -m uvicorn agrotech_ml.api:app --reload --port 8000
```

Then `curl http://127.0.0.1:8000/health` and browse the interactive docs at `http://127.0.0.1:8000/docs`.

**Entry points.** Both console scripts are installed by `pip install -e .`:

| Command | Equivalent module form | Notes |
|---|---|---|
| `agrotech-train` | `python -m agrotech_ml.services.train` | `python -m agrotech_ml.train` does **not** exist |
| `agrotech-api` | `python -m agrotech_ml.api` | binds `0.0.0.0` on `$PORT`, **default 8080** |

The `uvicorn ... --port 8000` form above is the local-dev convention; it matches the frontend's default `ML_API_URL`. Use `agrotech-api` in containers so Cloud Run's injected `PORT` is honoured.

**The API never trains.** Startup checks `artifacts/` and logs either `Model artifacts ready in <dir>` or an `ERROR` naming exactly which files are missing; the models themselves are then read from disk and memoised on first use. Nothing is ever trained on a request. While artifacts are missing, `GET /health` reports `models_ready: false` and every model-backed route returns `503` carrying the same message, until you run `agrotech-train`.

Training on the committed 2,200-row dataset produced `best_model: "Extra Trees"` at 99.5% accuracy / 99.5% macro-F1, ahead of CatBoost (99.5%) and Random Forest (99.3%). XGBoost is skipped because the labels are crop-name strings. Artifacts written: `crop_model.joblib`, `irrigation_model.joblib`, `fertilizer_model.joblib`, `disease_model.joblib`, `model_metadata.json`, plus the SQLite database `agrotech.db`.

`scripts/bootstrap_datasets.py` accepts `--offline` and `--refresh-remote`. It succeeds with **no network** — `data/Crop_dataset.csv` is the committed canonical copy and the remote mirror is best-effort. It exits non-zero only if no usable dataset exists at all.

## Endpoints

`Auth` marks routes that require `Authorization: Bearer <jwt>` **only when `AGROTECH_REQUIRE_WRITE_AUTH=true`**. With it false (the local-dev default) every route is anonymous and behaviour is unchanged.

### Public (never gated)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | `{status, service, environment, models_ready, write_auth_required}` |
| `GET` | `/languages` | 11 languages: en, hi, bn, te, ta, mr, gu, kn, ml, pa, or |
| `POST` | `/auth/login` | `{username, password}` → bearer token. `401` bad creds, `503` when the JWT secret / admin username are unset |
| `GET` | `/dashboard/summary` | 5 concurrent probes at 2.5s each; degrades to offline data |
| `GET` | `/metadata` | model metadata; `503` when artifacts are absent |
| `GET` | `/weather/forecast` | `?latitude&longitude&language&days(1-10)`; `502` if Open-Meteo is down |
| `GET` | `/locations/search` | `?q` (min 2); `502` on provider failure |
| `GET` | `/search/knowledge` | `?query`(min 2)`&language&limit(1-10)`; `502` on provider failure |
| `GET` | `/news/feed` | `?query&language&limit(1-10)`; may legitimately return `[]` when Google News throttles |
| `GET` | `/market/prices` | `?language&crop&state`. **Always 200** — live data.gov.in feed (300s cache) falling back to a committed CSV |
| `GET` | `/rentals/tools` | `?language&location`. **Always 200 and never empty** — bounded scrape (600s cache) falling back to a committed 10-entry catalogue |
| `GET` | `/investor/opportunities` | `?language` |
| `GET` | `/knowledge/library` | `?language&query`; `502` on provider failure |

### Auth required (mutating and/or farmer PII)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/auth/me` | `{authenticated, subject, role, write_auth_required}` |
| `POST` | `/predict` | `SoilWeatherInput` → ranked recommendations; `503` if artifacts missing |
| `POST` | `/predict/crop` | byte-identical **alias** of `POST /predict` |
| `POST` | `/irrigation/schedule` | `503` if artifacts missing |
| `POST` | `/disease/diagnose` | text symptoms in, diagnosis out; `503` if artifacts missing |
| `POST` | `/fertilizer/recommend` | `503` if artifacts missing |
| `POST` | `/soil/analyze` | rule-based, no model needed |
| `POST` | `/schemes/recommend` | |
| `POST` | `/profiles/user` | `400` on farmer-id conflict |
| `GET` | `/profiles/user/{mobile}` | `{mobile}` also accepts a `farmer_id`; `404` if unknown |
| `GET` | `/profiles/search` | `?q` **min 3 chars**, max 64; `&limit(1-20, default 8)`. `422` outside those bounds. Mobiles match only on exact value or a ≥4-digit prefix |
| `GET` | `/profiles/workspace/{farmer_id}` | `{profile, farms, uploads, advisories}`; `404` if unknown |
| `POST` | `/profiles/farms` | `400` if the farmer profile does not exist |
| `GET` | `/profiles/farms/{mobile}` | `{mobile}` also accepts a `farmer_id` |
| `POST` | `/uploads/assets` | multipart. `415` disallowed content type, `413` over the size cap, `400` unknown farmer, `503` if object storage is unavailable |
| `GET` | `/uploads/assets/{mobile}` | `?module` filter |
| `GET` | `/static/uploads/{stored_name}` | **auth-gated**, served as an inert attachment. `404` for any name this service did not generate. Redirects to a signed URL when GCS is configured |
| `GET` | `/advisories/history/{mobile}` | `?module&limit(1-50, default 20)` |
| `POST` | `/retrain` | **`202`**, non-blocking background job. `409` if one is already queued or running |
| `GET` | `/retrain/status` | `idle \| queued \| running \| succeeded \| failed` plus timings. Training takes 39-52s; the service stays responsive throughout |

**Upload safety.** The stored filename is a fresh UUID plus an extension derived from the *validated* content type — the client filename never reaches the path. Defaults: `image/jpeg, image/png, image/webp, application/pdf`, max 10,485,760 bytes.

## Configuration

Every variable is optional. **With none of them set you get local mode**: SQLite plus local directories, which is what the quick start above uses. `.env` is read from an absolute path (`<ml-service>/.env`), so it works from any working directory.

| Variable | Default | Purpose |
|---|---|---|
| `AGROTECH_ARTIFACTS_DIR` | `<ml-service>/artifacts` | Trained models and the SQLite DB |
| `AGROTECH_UPLOADS_DIR` | `<ml-service>/uploads` | Farmer-submitted files |
| `AGROTECH_DATABASE_URL` | *(unset → SQLite)* | PostgreSQL. Accepts `postgresql://`, `postgres://`, `postgresql+psycopg://` and Cloud SQL unix sockets |
| `AGROTECH_MODELS_GCS_URI` | *(unset)* | `gs://bucket/prefix`; models downloaded into the artifacts dir at startup, skipped if already present |
| `AGROTECH_UPLOADS_GCS_BUCKET` | *(unset)* | Uploads bucket |
| `GOOGLE_CLOUD_PROJECT` | *(unset)* | Passed to the GCS client (no `AGROTECH_` prefix) |
| `PORT` / `AGROTECH_PORT` | `8080` | Port `agrotech-api` binds |
| `AGROTECH_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001` | Comma-separated. An empty value blocks all cross-origin traffic; `*` is honoured but forces `allow_credentials=false` |
| `AGROTECH_REQUIRE_WRITE_AUTH` | `false` | Turns on the JWT gate described above |
| `AGROTECH_JWT_SECRET` | *(unset)* | Required for `/auth/login` |
| `AGROTECH_ADMIN_USERNAME` / `AGROTECH_ADMIN_PASSWORD_HASH` | *(unset)* | Login credentials. Hash format `pbkdf2_sha256$600000$salt$digest` |
| `AGROTECH_ALLOWED_UPLOAD_TYPES` | jpeg, png, webp, pdf | Upload content-type allowlist |
| `AGROTECH_MAX_UPLOAD_SIZE_BYTES` | `10485760` | Upload size cap |
| `AGROTECH_SARVAM_API_KEY` | *(unset)* | Sarvam **translation** API (`mayura:v1`); falls back to a local dictionary |
| `AGROTECH_BRAVE_SEARCH_API_KEY` | *(unset)* | Knowledge search |
| `AGROTECH_MYSCHEME_API_KEY` | *(unset)* | Scheme catalogue |

Generate an admin password hash with:

```bash
python -c "from agrotech_ml.core.auth import hash_password; print(hash_password('your-password'))"
```

Verify the resolved configuration at any time:

```bash
python -c "from agrotech_ml.core.settings import get_settings; s=get_settings(); print(s.artifacts_dir, s.database_path, s.use_postgres, s.port)"
```

## Local vs. cloud

The same code runs both ways; only the environment differs.

| Concern | Local (no env vars) | Google Cloud |
|---|---|---|
| Database | SQLite + WAL at `artifacts/agrotech.db` | Cloud SQL for PostgreSQL via `AGROTECH_DATABASE_URL` |
| Models | `artifacts/` on disk | GCS, synced at startup via `AGROTECH_MODELS_GCS_URI` |
| Uploads | `uploads/` on disk | GCS via `AGROTECH_UPLOADS_GCS_BUCKET` |
| Secrets | `.env` / shell environment | Secret Manager |
| Install | `pip install -e .` | `pip install -e '.[cloud]'` |

The cloud dependencies (`psycopg[binary]`, `google-cloud-storage`) live in an **optional extra** so a local install stays light:

```bash
pip install -e '.[cloud]'
```

If `AGROTECH_DATABASE_URL` is set but the driver is missing, startup fails with an actionable message telling you to install that extra. If a GCS variable is set but `google-cloud-storage` is missing, the service still boots and the affected routes return `503` rather than `500`.

A Cloud SQL connection string uses a Unix socket and has an **empty host before the slash**:

```text
postgresql://USER:PASS@/DBNAME?host=/cloudsql/PROJECT:REGION:INSTANCE
```

Full deployment instructions are in **[`../docs/DEPLOY_GCP.md`](../docs/DEPLOY_GCP.md)**. Migrating an existing SQLite database to Cloud SQL is covered there, using `deploy/sqlite_to_postgres.py`.

## Notes for downstream consumers

- `storage.connect(settings)` yields an `agrotech_ml.db.engine.DatabaseConnection`, **not** a `sqlite3.Connection`. Write `?` placeholders (the engine rewrites them to `%s` for PostgreSQL) and read columns **by name** — positional `row[0]` does not work on PostgreSQL dict rows, so use `SELECT COUNT(*) AS total`.
- New schema DDL uses `{TEXT}` / `{INTEGER}` / `{REAL}` / `{SERIAL_PK}` tokens rendered per dialect. Any SQL added to `db/storage.py` should use the same tokens.
- `get_settings()` runs, in order: ensure artifacts dir → ensure uploads dir → sync models from GCS → `init_db()`.
- For GCS uploads use `agrotech_ml.cloud.storage_gcs.upload_bytes()` / `public_url()` / `signed_url()`.

## Known limitations

- **The PostgreSQL path has never run against a real PostgreSQL server.** It was verified through the dialect layer's generated SQL and a fake `psycopg` driver that records every emitted statement (30/30 checks pass); the SQLite→Postgres migrator was separately tested against a real PostgreSQL 18 instance (17/17). What remains untested is live DDL acceptance and real psycopg type round-tripping. Do one dry run against a real instance before the first production cutover.
- **`Dockerfile.api` has never been built successfully** (no container-registry access in the development sandbox). Its structure and build context were validated offline, but Python dependency resolution inside the image is unproven.
- **The MyScheme API key is compromised.** It is committed in git history (`b119cb8`) and is still hardcoded in `src/agrotech_ml/services/data_service.py` inside `_official_browser_headers()`, which is the copy actually sent over the wire. Rotate it at the provider. The code fix is to read `settings.myscheme_api_key` and omit the `x-api-key` header entirely when it is `None`.
- **A farmer-submitted upload is still tracked in git**: `uploads/759ccdb7-c7da-4dd2-a03f-368d447c63ea.jpg`. Adding `uploads/*` to `.gitignore` does not untrack an already-committed file; that needs `git rm --cached`.
- **Audit logging is advertised but never written.** `save_audit_log()` / `list_audit_logs()` exist, the `audit_logs` table is created, and `/dashboard/summary` reports `audit_logging_enabled: true`, but no code path inserts a row.
- **`db/storage.py::search_users` still runs an unanchored `LIKE '%q%'` against `mobile` at the SQL layer.** The PII hardening lives in `services/data_service.py::search_farmers`, which is the only caller reachable over HTTP, so the API is safe. Any *future* caller importing `search_users` directly would bypass it.
- **No PostgreSQL connection pooling.** Every call opens its own connection, exactly as the SQLite code did — correct, but chatty against Cloud SQL. `psycopg_pool` can be dropped into `db/engine.py` behind the same `connect()` contextmanager without touching `storage.py`.
- **`GET /news/feed` intermittently returns `[]`.** Upstream throttling by Google News, reproducible with a bare `curl`. The route is timeout-bounded and never 500s; there is deliberately no stale-news fallback.
- **`agrotech/` is a broken venv stub** containing only `lib/`. Nothing references it and it should be deleted.
