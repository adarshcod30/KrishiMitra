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
agrotech-train                            # ~35s; writes artifacts/ (~174 MB)
python -m uvicorn agrotech_ml.api:app --reload --port 8000
```

Then `curl http://127.0.0.1:8000/health` and browse the interactive docs at `http://127.0.0.1:8000/docs`.

That is the entire local setup: **no environment variables, no containers, no accounts.** The service falls back to SQLite under the artifacts directory and to local upload directories on its own. For the full stack with a real Postgres, or for the free hosted deployment, see [Local vs. deployed](#local-vs-deployed).

**Entry points.** Both console scripts are installed by `pip install -e .`:

| Command | Equivalent module form | Notes |
|---|---|---|
| `agrotech-train` | `python -m agrotech_ml.services.train` | `python -m agrotech_ml.train` does **not** exist |
| `agrotech-api` | `python -m agrotech_ml.api` | binds `0.0.0.0` on `$PORT`, **default 8080** |

The `uvicorn ... --port 8000` form above is the local-dev convention; it matches the frontend's default `ML_API_URL`. Use `agrotech-api` in containers so the host's injected `PORT` is honoured — a Hugging Face Space sets `PORT=7860`, and the default when nothing sets it is `8080`. It always binds `0.0.0.0`; a container-internal `127.0.0.1` listener would be unreachable.

> If `agrotech-train` fails with `ModuleNotFoundError: No module named 'agrotech_ml.train'`, the virtualenv predates the entry-point rename and still holds the old console-script shim. Re-run `pip install -e .`; a fresh editable install maps the script to `agrotech_ml.services.train:main`. `python -m agrotech_ml.services.train` works either way.

**The API never trains, and never downloads.** Startup checks the artifacts directory and reads the models from disk, memoising them on first use; nothing is trained on a request and nothing is fetched over the network at boot. When the files are missing, startup prints the exact list and `GET /health` reports `models_ready: false` while every model-backed route returns `503` carrying the same message — verified against an empty artifacts directory:

```text
Model artifacts are missing from /tmp/empty: crop_model.joblib, model_metadata.json,
disease_model.joblib, fertilizer_model.joblib, irrigation_model.joblib. Run `agrotech-train`
(or `python -m agrotech_ml.services.train`) to build them, or point AGROTECH_ARTIFACTS_DIR at a
directory that already holds them. Training is never performed on the request path.
```

The happy path is quiet: the matching `Model artifacts ready in <dir>` line is logged at `INFO`, which uvicorn's default configuration does not surface.

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
| `GET` | `/static/uploads/{stored_name}` | **auth-gated**, served as an inert attachment (`nosniff`, `attachment`, `default-src 'none'; sandbox`, `no-store`). `404` for any name this service did not generate. `307` to a short-lived presigned URL when the S3 backend is configured |
| `GET` | `/advisories/history/{mobile}` | `?module&limit(1-50, default 20)` |
| `POST` | `/retrain` | **`202`**, non-blocking background job. `409` if one is already queued or running |
| `GET` | `/retrain/status` | `idle \| queued \| running \| succeeded \| failed` plus timings. Training takes roughly 35-50s; the service stays responsive throughout |

**Upload safety.** The stored filename is a fresh UUID plus an extension derived from the *validated* content type — the client filename never reaches the path. Defaults: `image/jpeg, image/png, image/webp, application/pdf`, max 10,485,760 bytes.

## Configuration

Every variable is optional. **With none of them set you get local mode**: SQLite plus local directories, which is what the quick start above uses. `.env` is read from an absolute path (`<ml-service>/.env`), so it works from any working directory.

| Variable | Default | Purpose |
|---|---|---|
| `AGROTECH_ARTIFACTS_DIR` | `<ml-service>/artifacts` | Trained models and the SQLite DB |
| `AGROTECH_UPLOADS_DIR` | `<ml-service>/uploads` | Farmer-submitted files |
| `AGROTECH_DATABASE_URL` | *(unset → SQLite)* | Any PostgreSQL URL — Neon, Supabase, a compose container. Accepts `postgresql://`, `postgres://` and `postgresql+psycopg://`; only the scheme is rewritten, so query parameters such as `?sslmode=require&channel_binding=require` reach libpq untouched. Needs the `postgres` extra |
| `AGROTECH_S3_ENDPOINT_URL` | *(unset)* | S3-compatible endpoint (Cloudflare R2, Supabase Storage, Backblaze B2, MinIO, AWS S3). Needs the `s3` extra |
| `AGROTECH_S3_BUCKET` | *(unset)* | Uploads bucket |
| `AGROTECH_S3_ACCESS_KEY_ID` / `AGROTECH_S3_SECRET_ACCESS_KEY` | *(unset)* | Credentials. **All four of endpoint/bucket/key/secret must be set** or uploads stay on local disk |
| `AGROTECH_S3_PUBLIC_BASE_URL` | *(unset)* | CDN/public hostname in front of the bucket. When empty, downloads are handed out as 1-hour presigned URLs instead |
| `AGROTECH_S3_REGION` | `auto` | SigV4 needs a region. `auto` is correct for R2/B2/MinIO; set the real region only for AWS S3 itself |
| `PORT` / `AGROTECH_PORT` | `8080` | Port `agrotech-api` binds on `0.0.0.0`. Injected by the host — Hugging Face Spaces sets `7860` |
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
python -c "from agrotech_ml.core.settings import get_settings; s=get_settings(); print(s.artifacts_dir, s.database_path, s.use_postgres, s.uploads_to_s3, s.port)"
# fresh clone, no env vars:
# /…/ml-service/artifacts /…/ml-service/artifacts/agrotech.db False False 8080
```

## Local vs. deployed

The same code runs both ways; only the environment differs. **With no variables set at
all you get the local mode** — SQLite, local directories, nothing to install beyond
`pip install -e .`.

| Concern | Local (no env vars) | Deployed (the free stack) |
|---|---|---|
| Database | SQLite + WAL at `artifacts/agrotech.db` | Neon — or any Postgres — via `AGROTECH_DATABASE_URL` |
| Models | `artifacts/` on disk | the same files **baked into the container image**; never downloaded at boot |
| Uploads | `uploads/` on disk | the host's disk (ephemeral on a Space), or an S3-compatible bucket via `AGROTECH_S3_*` |
| Secrets | `.env` / shell environment | the host's secret store (Hugging Face Space secrets) |
| Port | `8000` by local convention | `$PORT` injected by the host (`7860` on a Space) |
| Install | `pip install -e .` | `pip install -e '.[postgres]'`, plus `'.[s3]'` if you use S3 |

The managed-service drivers live in **optional extras**, so a local install stays light:

```bash
pip install -e .              # SQLite + local directories
pip install -e '.[postgres]'  # + psycopg[binary]
pip install -e '.[s3]'        # + boto3
pip install -e '.[cloud]'     # both, as one name
```

`spaces/api/Dockerfile` installs `postgres` + `s3` by default (`ARG PIP_EXTRAS="postgres"`,
`ARG WITH_S3=1`) and verifies both imports in the build, so the deployed image can talk to
Postgres and S3 whether or not those variables are set at runtime. Build with
`--build-arg WITH_S3=0` for a local-disk-only image.

If `AGROTECH_DATABASE_URL` is set but `psycopg` is missing, startup fails with an
actionable message naming the extra. If the `AGROTECH_S3_*` variables are set but
`boto3` is missing, the service still boots and the upload routes return `503` rather
than `500`.

**S3 is all-or-nothing.** Uploads move off local disk only when
`AGROTECH_S3_ENDPOINT_URL`, `AGROTECH_S3_BUCKET`, `AGROTECH_S3_ACCESS_KEY_ID` **and**
`AGROTECH_S3_SECRET_ACCESS_KEY` are all present; any partial configuration silently
keeps writing locally. The client uses path-style addressing, which MinIO and Supabase
require.

A Neon connection string is just a Postgres URL, and its TLS parameters matter:

```text
postgresql://USER:PASS@ep-xxxx-pooler.ap-south-1.aws.neon.tech/neondb?sslmode=require
```

Prefer the **pooled** host (it contains `-pooler`) — this service opens a connection per
call and does not pool.

Full deployment instructions — Neon, the Hugging Face Space, Vercel, and every free-tier
limit — are in **[`../docs/DEPLOY_FREE.md`](../docs/DEPLOY_FREE.md)**. Migrating an
existing SQLite database is covered there too, using `scripts/sqlite_to_postgres.py`
from the repository root. For the local full stack with a real Postgres, run
`docker compose up --build` from the repository root; it builds this service from
`spaces/api/Dockerfile`.

## Notes for downstream consumers

- `storage.connect(settings)` yields an `agrotech_ml.db.engine.DatabaseConnection`, **not** a `sqlite3.Connection`. Write `?` placeholders (the engine rewrites them to `%s` for PostgreSQL) and read columns **by name** — positional `row[0]` does not work on PostgreSQL dict rows, so use `SELECT COUNT(*) AS total`.
- New schema DDL uses `{TEXT}` / `{INTEGER}` / `{REAL}` / `{SERIAL_PK}` tokens rendered per dialect. Any SQL added to `db/storage.py` should use the same tokens.
- `get_settings()` runs, in order: ensure artifacts dir → ensure uploads dir → `init_db()`. There is no model-download step; artifacts are read straight from `AGROTECH_ARTIFACTS_DIR`.
- For S3 uploads use `agrotech_ml.cloud.storage_s3.upload_bytes()` / `public_url()` / `presigned_url()` / `download_url()`. Nothing in `agrotech_ml.cloud` imports `boto3` at module scope, so the package imports cleanly with the `s3` extra uninstalled; calling into it without a complete configuration raises `S3NotConfigured`.

## Known limitations

- **The PostgreSQL path has never run against a real PostgreSQL server.** It was
  verified through the dialect layer's generated SQL and a fake `psycopg` driver that
  records every emitted statement (30/30 checks pass); the SQLite→Postgres migrator was
  separately tested against a real PostgreSQL 18 instance (17/17). DSN normalisation was
  re-verified for `postgres://`, `postgresql://` and `postgresql+psycopg://` with
  `?sslmode=require` / `channel_binding=require` preserved verbatim, which is what Neon
  needs. What remains untested is live DDL acceptance and real psycopg type
  round-tripping. Do one dry run against a real instance before the first production
  cutover.
- **The optional S3 upload backend has never talked to a real R2 / Supabase / B2 /
  MinIO endpoint.** It was tested against a local fake S3 endpoint that captured the
  exact request the client emits — path-style URL, SigV4 `Authorization` header,
  `ContentType`, `ContentDisposition`, body bytes — plus offline presigned-URL
  generation, the `415` allowlist still applying in S3 mode, and a `503` (not a `500`)
  when the endpoint disappears mid-request. Each provider's own response handling is the
  untested part.
- **Uploads are lost on any host with an ephemeral filesystem unless S3 is
  configured.** A Hugging Face Space wipes its container disk on every restart and
  rebuild, so with `AGROTECH_S3_*` unset, farmer-submitted images are effectively
  disposable. Database rows are unaffected — they live in Postgres. Configure all four
  S3 variables to keep uploads; a partial configuration silently stays on local disk.
- **`spaces/api/Dockerfile` has never been built.** The Docker daemon is not running in
  this development environment (`docker info` fails to connect to the socket), so
  `docker compose config` — a client-side operation — passes while no image has actually
  been produced. Structure, build context and every `COPY` source were checked
  statically; Python dependency resolution inside the image is unproven. The image must
  `COPY ml-service/artifacts/` (~174 MB of `.joblib` files) or the API boots with
  `models_ready: false`.
- **A virtualenv created before the entry-point rename carries a stale `agrotech-train`
  shim** that fails with `ModuleNotFoundError: No module named 'agrotech_ml.train'`. The
  packaging is correct — a fresh `pip install -e .` generates
  `from agrotech_ml.services.train import main` — so re-running the editable install
  fixes it.
- **The MyScheme API key must still be rotated.** The code fix has landed:
  `services/data_service.py` reads `settings.myscheme_api_key` and omits the `x-api-key`
  header entirely when it is `None`. But the old key is in git history (`b119cb8`), so it
  is compromised regardless. Rotate it at the provider; decide separately whether to
  scrub the history.
- **A farmer-submitted upload is still reachable in git history.**
  `uploads/759ccdb7-c7da-4dd2-a03f-368d447c63ea.jpg` was untracked in `f31e572` and is
  no longer in `HEAD`, but the blob remains in earlier commits.
- **Audit logging is advertised but never written.** `save_audit_log()` /
  `list_audit_logs()` exist in `db/storage.py`, the `audit_logs` table is created, and
  `/dashboard/summary` reports `audit_logging_enabled: true`, but no code path inserts a
  row — grepping the API and services layers returns zero call sites.
- **`db/storage.py::search_users` still runs an unanchored `LIKE '%q%'` against
  `mobile` at the SQL layer.** The PII hardening lives in
  `services/data_service.py::search_farmers`, which is the only caller reachable over
  HTTP, so the API is safe. Any *future* caller importing `search_users` directly would
  bypass it.
- **No PostgreSQL connection pooling.** Every call opens its own connection, exactly as
  the SQLite code did — correct, but chatty against a remote database. On Neon, use the
  pooled connection string (its host contains `-pooler`). `psycopg_pool` can be dropped
  into `db/engine.py` behind the same `connect()` contextmanager without touching
  `storage.py`.
- **`GET /news/feed` intermittently returns `[]`.** Upstream throttling by Google News,
  reproducible with a bare `curl`. The route is timeout-bounded and never 500s; there is
  deliberately no stale-news fallback.
