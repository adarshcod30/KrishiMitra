# Deploying KrishiMitra to Google Cloud

A complete runbook: what gets created, how to create it, how to migrate the
existing SQLite data, how to roll back, what it costs, and what to check before
letting real farmers use it.

Everything here is designed so that **the same code still runs locally with zero
GCP configuration**. Unset `AGROTECH_DATABASE_URL` and the API falls back to
SQLite; unset `AGROTECH_MODELS_GCS_URI` and it reads models from disk. That dual
mode is a hard requirement, not a nicety — it is what keeps development possible
without a cloud account.

---

## Contents

1. [Architecture](#1-architecture)
2. [Prerequisites](#2-prerequisites)
3. [Configuration contract](#3-configuration-contract)
4. [Deploy, step by step](#4-deploy-step-by-step)
5. [Uploading trained models](#5-uploading-trained-models)
6. [Migrating SQLite to Cloud SQL](#6-migrating-sqlite-to-cloud-sql)
7. [Earth Engine on GCP](#7-earth-engine-on-gcp)
8. [Continuous deployment](#8-continuous-deployment)
9. [Rollback](#9-rollback)
10. [Monitoring and logging](#10-monitoring-and-logging)
11. [Cost estimate](#11-cost-estimate)
12. [Security checklist](#12-security-checklist)
13. [Troubleshooting](#13-troubleshooting)
14. [Teardown](#14-teardown)

---

## 1. Architecture

```mermaid
flowchart TB
    subgraph Internet
        Farmer["Farmer / browser"]
    end

    subgraph GCP["Google Cloud project"]
        subgraph Serving["Cloud Run (asia-south1)"]
            WEB["krishimitra-web<br/>Next.js standalone<br/>:$PORT 3000<br/>SA: krishimitra-web<br/><b>public</b>"]
            API["krishimitra-api<br/>FastAPI + uvicorn<br/>:$PORT 8080<br/>SA: krishimitra-api<br/><b>private</b>"]
            MIG["krishimitra-migrate<br/>one-shot Job"]
            SAT["krishimitra-satellite<br/>batch Job"]
        end

        subgraph Data["Managed data"]
            SQL[("Cloud SQL<br/>PostgreSQL 17<br/>private, SSL only")]
            MODELS[("GCS: -models<br/>versioned")]
            UPLOADS[("GCS: -uploads<br/>PAP enforced")]
            SATOUT[("GCS: -satellite<br/>versioned")]
        end

        subgraph Platform["Platform services"]
            SM["Secret Manager"]
            AR["Artifact Registry"]
            CB["Cloud Build"]
            SCHED["Cloud Scheduler<br/>weekly cron"]
            LOG["Cloud Logging<br/>Monitoring / Trace"]
        end

        EE["Earth Engine API<br/>Sentinel-1/2, ERA5-Land"]
    end

    Farmer -->|HTTPS| WEB
    WEB -->|"/api/ml proxy<br/>+ Google ID token"| API

    API -->|Unix socket<br/>/cloudsql/...| SQL
    API -->|models at startup| MODELS
    API -->|farmer uploads| UPLOADS
    API -->|env from| SM

    MIG -->|schema| SQL
    SCHED -->|jobs.run| SAT
    SAT -->|imagery| EE
    SAT -->|"gcsfuse volume<br/>mounted at /app/outputs"| SATOUT
    API -->|read maps| SATOUT

    CB -->|images| AR
    AR -.->|pull| Serving
    Serving --> LOG

    classDef public fill:#1b5e20,stroke:#a5d6a7,color:#fff
    classDef private fill:#0d47a1,stroke:#90caf9,color:#fff
    classDef store fill:#4a148c,stroke:#ce93d8,color:#fff
    class WEB public
    class API,MIG,SAT private
    class SQL,MODELS,UPLOADS,SATOUT store
```

### The two things worth understanding

**The browser never talks to the API directly.** `NEXT_PUBLIC_ML_API_URL` is
baked into the client bundle as `/api/ml`, a same-origin path. The Next.js
server-side route handler at that path forwards to `ML_API_URL` (the API's real
Cloud Run URL, a *runtime* env var). Consequences:

- No CORS preflight, ever.
- The API hostname never appears in shipped JavaScript.
- The API can be `--no-allow-unauthenticated`: only `krishimitra-web`'s service
  account holds `roles/run.invoker` on it.
- Changing which API the frontend targets is a redeploy, not a rebuild.

**Cloud Run reaches Cloud SQL over a Unix socket, not the network.**
`--add-cloudsql-instances` injects a socket at
`/cloudsql/PROJECT:REGION:INSTANCE`. The connection string is therefore
`postgresql://user:pass@/dbname?host=/cloudsql/PROJECT:REGION:INSTANCE` — note
the empty host before the `/`. No VPC connector, no NAT gateway, no authorized
networks, no per-hour networking charge.

### Repository layout

| Path | Purpose |
|---|---|
| `Dockerfile.api` | FastAPI ml-service → Cloud Run service |
| `Dockerfile.web` | Next.js frontend → Cloud Run service |
| `satellite-ml/Dockerfile` | satellite-ml → Cloud Run **job** (owned by that module) |
| `cloudbuild.yaml` | CI: build, push, migrate, deploy |
| `docker-compose.yml` | The same topology, locally |
| `deploy/00-enable-apis.sh` | Enable the required Google APIs |
| `deploy/10-provision.sh` | Registry, buckets, Cloud SQL, service accounts, IAM |
| `deploy/20-secrets.sh` | Secret Manager entries and access grants |
| `deploy/30-deploy.sh` | Build + deploy both services, wire URLs |
| `deploy/40-satellite-job.sh` | Satellite job + Cloud Scheduler trigger |
| `deploy/sqlite_to_postgres.py` | One-time data migration |
| `deploy/models/` | Optional offline model bake for the API image |
| `deploy/terraform/` | Optional IaC alternative to `10-provision.sh` |

---

## 2. Prerequisites

### Local tools

| Tool | Version | Needed for |
|---|---|---|
| `gcloud` | ≥ 480 | everything |
| `bash` | ≥ 4 | the deploy scripts (macOS ships 3.2 — `brew install bash`) |
| `openssl` | any | generating the JWT secret and DB password |
| `python3` | ≥ 3.10 | password hashing, SQLite migration |
| `git` | any | image tags derive from the commit SHA |
| `docker` | optional | only for `docker-compose.yml`; Cloud Build does the real builds |
| `terraform` | ≥ 1.5, optional | only if you use `deploy/terraform/` |

```bash
gcloud auth login
gcloud auth application-default login    # for terraform / local ADC
gcloud components update
```

### GCP prerequisites

- A project (`gcloud projects create`, or an existing one).
- **Billing enabled.** Cloud Run, Cloud SQL and Artifact Registry all require it.
- Your account needs, at minimum: `roles/owner`, or the combination
  `roles/serviceusage.serviceUsageAdmin`, `roles/iam.serviceAccountAdmin`,
  `roles/resourcemanager.projectIamAdmin`, `roles/artifactregistry.admin`,
  `roles/cloudsql.admin`, `roles/storage.admin`, `roles/secretmanager.admin`,
  `roles/run.admin`, `roles/cloudscheduler.admin`.
- For the satellite job only: the project registered for Earth Engine
  (see [§7](#7-earth-engine-on-gcp)).

### Quotas worth checking before you start

`gcloud compute project-info describe --project PROJECT` and the Cloud SQL quota
page. On a brand-new project the defaults are ample for a pilot; the one that
bites is Cloud Build concurrent builds (10) if you trigger many pushes at once.

---

## 3. Configuration contract

Every environment variable the platform reads. **These names are exact.**
Inventing an alias breaks the contract between the app, the containers and the
deploy scripts.

### API (`ml-service`)

| Variable | Source | Unset means |
|---|---|---|
| `PORT` | injected by Cloud Run | 8080; the app **must** bind `0.0.0.0:$PORT` |
| `AGROTECH_ENVIRONMENT` | env var | `development` |
| `AGROTECH_DATABASE_URL` | **Secret Manager** | fall back to local SQLite |
| `AGROTECH_ARTIFACTS_DIR` | env var | `/app/artifacts` (a real directory) |
| `AGROTECH_MODELS_GCS_URI` | env var | no download; read models from disk |
| `AGROTECH_UPLOADS_GCS_BUCKET` | env var | uploads go to local disk |
| `AGROTECH_PUBLIC_BASE_URL` | env var, set post-deploy | `http://127.0.0.1:8000` |
| `AGROTECH_CORS_ORIGINS` | env var, set post-deploy | localhost defaults |
| `AGROTECH_JWT_SECRET` | **Secret Manager** | startup fails in production |
| `AGROTECH_ADMIN_USERNAME` | env var | no admin |
| `AGROTECH_ADMIN_PASSWORD_HASH` | **Secret Manager** | no admin |
| `AGROTECH_REQUIRE_WRITE_AUTH` | env var | `false` |
| `AGROTECH_SARVAM_API_KEY` | **Secret Manager**, optional | translation degrades |
| `AGROTECH_BRAVE_SEARCH_API_KEY` | **Secret Manager**, optional | search degrades |
| `AGROTECH_MYSCHEME_API_KEY` | **Secret Manager**, optional | scheme lookup degrades |
| `GOOGLE_CLOUD_PROJECT` | env var | ADC-dependent features degrade |

### Frontend (`Next.js`)

| Variable | When | Notes |
|---|---|---|
| `NEXT_PUBLIC_ML_API_URL` | **build time only** | inlined into the client bundle; default `/api/ml` |
| `ML_API_URL` | runtime, server-side | the API's Cloud Run URL; never reaches the browser |
| `PORT` | injected by Cloud Run | 3000 |
| `HOSTNAME` | set in the image | must be `0.0.0.0`, or Cloud Run's probe sees a dead container |

> The single most common Next-on-Cloud-Run failure is forgetting `HOSTNAME`.
> `.next/standalone/server.js` binds `process.env.HOSTNAME` and defaults to
> `localhost`, so the container listens on a loopback the sandbox cannot reach
> and the deploy times out with "container failed to start and listen on port".
> `Dockerfile.web` sets it; do not remove it.

### Satellite job (`satellite-ml`)

| Variable | Notes |
|---|---|
| `EE_PROJECT` | Cloud project registered for Earth Engine; falls back to `GOOGLE_CLOUD_PROJECT` |
| `EE_SERVICE_ACCOUNT_JSON` | optional; a key file path *or* raw JSON. Prefer omitting it — see [§7](#7-earth-engine-on-gcp) |
| `GOOGLE_CLOUD_PROJECT` | for ADC |
| `MPLBACKEND` | `Agg` — set in the image; there is no display in a batch container |

The job has no output env var. `deploy/40-satellite-job.sh` mounts
`gs://<project>-krishimitra-satellite` at `/app/outputs` through a Cloud Run
Cloud Storage volume, so the pipeline's ordinary file writes land in GCS with no
upload step and no extra dependency.

### Operator configuration

`deploy/env` (copied from `deploy/env.example`) drives the scripts. It contains
**no secret values** — only names, sizes and switches.

---

## 4. Deploy, step by step

```bash
git clone <repo> && cd KrishiMitra
cp deploy/env.example deploy/env
$EDITOR deploy/env          # set PROJECT_ID; everything else has a sane default
```

Each script prints exactly what it will create and waits for confirmation.
Nothing is destructive; nothing has a destructive default.

### 4.1 Enable APIs (~2 minutes)

```bash
./deploy/00-enable-apis.sh
```

Required: `run`, `sqladmin`, `secretmanager`, `artifactregistry`, `cloudbuild`,
`storage`, `iam`, `iamcredentials`, `cloudresourcemanager`, `serviceusage`,
`logging`, `monitoring`.
Optional: `cloudscheduler`, `earthengine`, `compute`, `cloudtrace`,
`containerscanning`.

`earthengine.googleapis.com` fails to enable on an unregistered project. The
script says so and continues — everything except the satellite job works
without it.

### 4.2 Provision (~12 minutes, mostly Cloud SQL)

```bash
./deploy/10-provision.sh
```

Creates the registry, both buckets, the Cloud SQL instance, five service
accounts, all IAM, and the two database secrets. It generates the database
password itself and puts it straight into Secret Manager.

The Cloud SQL instance is created with **deletion protection on**, encrypted
connections only, daily backups, and 7-day point-in-time recovery.

*(Terraform alternative: `deploy/terraform/` — see its README.)*

### 4.3 Secrets (~2 minutes)

```bash
./deploy/20-secrets.sh
```

- `agrotech-jwt-secret` is generated locally with `openssl rand -hex 32`. No
  human ever sees it.
- `agrotech-admin-password-hash` prompts for a password (hidden, confirmed,
  12-character minimum) and stores only a PBKDF2-SHA256 hash — 600,000
  iterations, per OWASP guidance. The plaintext never leaves the process.
- Third-party keys are optional. Skip them and those features degrade rather
  than breaking the service.

Re-running never overwrites an existing value. To rotate:

```bash
./deploy/20-secrets.sh --rotate agrotech-jwt-secret
gcloud run services update krishimitra-api --region asia-south1 \
  --update-secrets AGROTECH_JWT_SECRET=agrotech-jwt-secret:latest
```

> Rotating the JWT secret invalidates every issued token. Do it during a quiet
> window.

### 4.4 Build and deploy (~10 minutes first time)

```bash
./deploy/30-deploy.sh
```

1. Cloud Build builds `Dockerfile.api` and `Dockerfile.web` (linux/amd64, so
   this works from an Apple Silicon Mac) and pushes to Artifact Registry.
2. A one-shot Cloud Run Job applies the database schema.
3. The API deploys with the Cloud SQL connector, secrets and probes.
4. The frontend deploys pointed at the API's real URL.
5. `AGROTECH_CORS_ORIGINS` and `AGROTECH_PUBLIC_BASE_URL` are set to the real
   URLs, which only exist after step 3 and 4.
6. `krishimitra-web`'s service account is granted `roles/run.invoker` on the
   API service — scoped to that one service, not the project.

Images are tagged with the short commit SHA, plus `-dirty-<timestamp>` when the
working tree has uncommitted changes. A revision can always be traced to a
commit.

```bash
./deploy/30-deploy.sh --skip-build          # redeploy current images
./deploy/30-deploy.sh --skip-migrate        # deploy without touching the DB
./deploy/30-deploy.sh --tag v1.4.0          # explicit tag
```

### 4.5 Satellite job (optional)

```bash
./deploy/40-satellite-job.sh               # build, deploy, schedule weekly
./deploy/40-satellite-job.sh --run-now     # ...and run once immediately
./deploy/40-satellite-job.sh --no-schedule # deploy without the cron
```

The image is built from `satellite-ml/Dockerfile`, with `satellite-ml/` as the
build context — that Dockerfile belongs to the satellite module, and this script
deliberately does not define a competing one.

Defaults to `--source simulate`, which runs fully offline. Switch to Earth
Engine by setting `SATELLITE_ARGS=--source,gee` in `deploy/env` after completing
[§7](#7-earth-engine-on-gcp).

**Where the outputs go.** The job mounts `gs://<project>-krishimitra-satellite`
at `/app/outputs` using a Cloud Run Cloud Storage volume, so `crop_map.png`,
the moisture-stress figures and the FAO-56 advisory tables are written straight
into the bucket. No upload step, no `google-cloud-storage` dependency, nothing
to go wrong after a successful run. Two consequences worth knowing:

- Each run **overwrites** the previous run's object names. The bucket is
  versioned, so last week's products are still there as noncurrent generations
  (`gcloud storage ls -a gs://...`), and the lifecycle rule only deletes
  superseded versions after 90 days.
- gcsfuse does not support **random writes**. That is fine for the default
  PNG + `.npy` outputs, which are written sequentially, but GeoTIFF writers seek
  within a file. Keep `SATELLITE_EXTRAS=gee` (no `geo`), or turn off
  `output.save_geotiff` in the pilot config. `40-satellite-job.sh` warns and
  asks for confirmation if you set `geo`.

---

## 5. Uploading trained models

The API downloads model artifacts from `AGROTECH_MODELS_GCS_URI` at startup.
They total ~170 MB, which is why they are not in the image.

```bash
# Train locally (or on any machine with the dataset)
cd ml-service && python -m agrotech_ml.train

# Upload. On a dev checkout the artifacts live in ml-service/artifacts/
# (override with AGROTECH_ARTIFACTS_DIR).
export PROJECT_ID=your-project
gcloud storage cp ml-service/artifacts/crop_model.joblib \
                  ml-service/artifacts/disease_model.joblib \
                  ml-service/artifacts/fertilizer_model.joblib \
                  ml-service/artifacts/irrigation_model.joblib \
                  ml-service/artifacts/model_metadata.json \
                  gs://${PROJECT_ID}-krishimitra-models/artifacts/

# Restart the API so it picks them up
gcloud run services update krishimitra-api --region asia-south1 \
  --update-env-vars MODELS_REFRESHED_AT=$(date -u +%Y%m%dT%H%M%SZ)
```

That last command is a deliberate no-op env change: Cloud Run only creates a new
revision when the configuration changes, and a new revision is what re-runs the
startup download.

Verify:

```bash
curl -s https://<api-url>/metadata | python3 -m json.tool
```

**Rolling back a bad model.** The models bucket has object versioning on:

```bash
gcloud storage ls -a gs://${PROJECT_ID}-krishimitra-models/artifacts/crop_model.joblib
gcloud storage cp gs://.../crop_model.joblib#1719000000000000 \
                  gs://.../crop_model.joblib
```

Superseded versions are deleted 90 days after being superseded
(`MODELS_NONCURRENT_RETENTION_DAYS`). Live objects are never touched by that
rule.

**Alternative: bake models into the image.** For air-gapped deployments, put the
artifacts in `deploy/models/` and rebuild — see `deploy/models/README.md`. Do
not commit them to git.

---

## 6. Migrating SQLite to Cloud SQL

The development database is `agrotech.db` inside `AGROTECH_ARTIFACTS_DIR`, with
tables `users`, `farms`, `uploads`, `advisories`, `translation_cache`,
`audit_logs`.

### 6.1 Create the schema first

The schema comes from the application, not from the migration tool — one
authority, no drift.

```bash
gcloud run jobs execute krishimitra-migrate --region asia-south1 --wait
```

### 6.2 Open a tunnel

```bash
# Install once: https://cloud.google.com/sql/docs/postgres/sql-proxy
cloud-sql-proxy ${PROJECT_ID}:asia-south1:krishimitra-pg --port 5433
```

Your account needs `roles/cloudsql.client`.

### 6.3 Copy the data

```bash
export PGPASSWORD="$(gcloud secrets versions access latest \
    --secret=krishimitra-db-password --project=${PROJECT_ID})"

# Always dry-run first.
python3 deploy/sqlite_to_postgres.py \
  --sqlite ml-service/artifacts/agrotech.db \
  --database-url "postgresql://agrotech:${PGPASSWORD}@127.0.0.1:5433/agrotech" \
  --dry-run

# Then for real.
python3 deploy/sqlite_to_postgres.py \
  --sqlite ml-service/artifacts/agrotech.db \
  --database-url "postgresql://agrotech:${PGPASSWORD}@127.0.0.1:5433/agrotech"

unset PGPASSWORD
```

Properties that matter:

- **Never destructive.** Conflicting primary keys are skipped
  (`ON CONFLICT DO NOTHING`); nothing is updated or deleted. `--truncate` exists
  but demands you type `DELETE` to confirm.
- **Re-runnable.** Run it repeatedly during a staged cutover; already-migrated
  rows are left alone.
- **Schema-tolerant.** Only columns present in both databases are copied, and
  the report names what was dropped or defaulted.
- **Ordered.** Parents (`users`) before children (`farms`, `uploads`,
  `advisories`), so foreign keys resolve without superuser tricks Cloud SQL does
  not grant.

### 6.4 Migrate the uploaded files too

Database rows reference files. Move them as well:

```bash
gcloud storage cp -r ml-service/uploads/* gs://${PROJECT_ID}-krishimitra-uploads/
```

### 6.5 Verify

```bash
psql "postgresql://agrotech:${PGPASSWORD}@127.0.0.1:5433/agrotech" -c "
  SELECT 'users' t, count(*) FROM users
  UNION ALL SELECT 'farms', count(*) FROM farms
  UNION ALL SELECT 'advisories', count(*) FROM advisories
  UNION ALL SELECT 'uploads', count(*) FROM uploads;"
```

Compare against the same query on SQLite. Then keep the SQLite file for at least
one release cycle before deleting it.

---

## 7. Earth Engine on GCP

This is the part most guides get wrong, because Google changed it: **individual
service accounts can no longer be registered with Earth Engine. The Cloud
*project* is registered, and every service account in it inherits access.**

### 7.1 Register the project

1. Go to <https://console.cloud.google.com/earth-engine> with your project
   selected (equivalently, <https://code.earthengine.google.com/register>).
2. Choose a use case. Non-commercial/research use is free; commercial use needs
   a paid Earth Engine plan.
3. Complete registration and wait for it to show as registered — this can take
   minutes to a day for a new organisation.

### 7.2 Enable the API

```bash
gcloud services enable earthengine.googleapis.com --project ${PROJECT_ID}
```

This **fails** on an unregistered project. If it does, step 7.1 has not
completed.

### 7.3 Grant the roles

`deploy/10-provision.sh` does this automatically once the API is enabled:

| Role | Why |
|---|---|
| `roles/earthengine.writer` | create computations and assets. `roles/earthengine.viewer` is enough for read-only analysis; the pipeline exports, so it needs writer. |
| `roles/serviceusage.serviceUsageConsumer` | grants `serviceusage.services.use`. **The one everybody forgets.** Without it `ee.Initialize(project=...)` returns a 403 that never mentions Service Usage. |

Manually:

```bash
SAT_SA="krishimitra-satellite@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SAT_SA}" --role="roles/earthengine.writer"
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SAT_SA}" --role="roles/serviceusage.serviceUsageConsumer"
```

### 7.4 Authentication: prefer no key at all

**Recommended — Workload Identity / ADC.** On Cloud Run, the runtime service
account is already available through Application Default Credentials. No key
file exists, so no key can leak, be committed, or need rotating. Application
code:

```python
import ee, os
# No credentials argument: ADC resolves the Cloud Run runtime service account.
ee.Initialize(project=os.environ["EE_PROJECT"])
```

This is the default. `EE_USE_KEY=false` in `deploy/env`, and
`EE_SERVICE_ACCOUNT_JSON` stays unset.

**Fallback — a JSON key from Secret Manager.** Only when you must authenticate
as a service account in a project you do not control, or from outside GCP.

```bash
# 1. Create a key (this is the moment key material comes into existence)
gcloud iam service-accounts keys create /tmp/ee-key.json \
  --iam-account="krishimitra-satellite@${PROJECT_ID}.iam.gserviceaccount.com"

# 2. Store it and destroy the local copy
echo "EE_USE_KEY=true" >> deploy/env
./deploy/20-secrets.sh          # prompts for the path to /tmp/ee-key.json
shred -u /tmp/ee-key.json       # macOS: rm -P /tmp/ee-key.json

# 3. Deploy — the job maps it as an env var
./deploy/40-satellite-job.sh
```

`--set-secrets EE_SERVICE_ACCOUNT_JSON=ee-service-account-json:latest` puts the
JSON into an env var. `satellite-ml`'s own ingestion module handles it: it
accepts either **raw JSON** or a **path** to a mounted key file (so a Secret
Manager *volume* mount at, say, `/var/secrets/ee/key.json` works equally well),
builds `ee.ServiceAccountCredentials` from it, and falls back to ADC when the
variable is unset. Nothing in `deploy/` needs to unpack the credential.

Because the key only ever exists as an environment variable inside the running
task, it is never written to durable storage.

If you use keys, rotate them:

```bash
gcloud iam service-accounts keys list --iam-account="${SAT_SA}"
gcloud iam service-accounts keys delete KEY_ID --iam-account="${SAT_SA}"
```

Better: set an org policy `constraints/iam.disableServiceAccountKeyCreation` and
never take this branch.

### 7.5 Verify

```bash
gcloud run jobs execute krishimitra-satellite --region asia-south1 --wait
gcloud logging read \
  'resource.type=cloud_run_job AND resource.labels.job_name=krishimitra-satellite' \
  --limit=50 --project ${PROJECT_ID}
gcloud storage ls -r gs://${PROJECT_ID}-krishimitra-satellite/
```

| Symptom | Cause |
|---|---|
| `Not signed up for Earth Engine` | project not registered (§7.1) |
| `Caller does not have permission ... serviceusage.services.use` | missing `serviceUsageConsumer` (§7.3) |
| `Earth Engine client library not initialized` | `EE_PROJECT` unset |
| `Permission denied on resource project` | `EE_PROJECT` points at an unregistered project |

---

## 8. Continuous deployment

`cloudbuild.yaml` performs the same sequence as `deploy/30-deploy.sh`, without
prompts.

```bash
gcloud builds triggers create github \
  --name=krishimitra-main \
  --repo-owner=YOUR_ORG --repo-name=KrishiMitra \
  --branch-pattern='^main$' \
  --build-config=cloudbuild.yaml \
  --region=asia-south1 \
  --service-account=projects/${PROJECT_ID}/serviceAccounts/krishimitra-build@${PROJECT_ID}.iam.gserviceaccount.com \
  --substitutions=_IMAGE_TAG='$SHORT_SHA' \
  --project=${PROJECT_ID}
```

Manual run:

```bash
gcloud builds submit --config cloudbuild.yaml --region=asia-south1 \
  --substitutions=_IMAGE_TAG=$(git rev-parse --short=12 HEAD)
```

Notes:

- `serviceAccount:` is set, which is why `options.logging: CLOUD_LOGGING_ONLY`
  is mandatory — a build with a user-specified service account has no default
  logs bucket and is rejected without an explicit logging choice.
- `_RUN_MIGRATIONS=false` skips the migration step for a code-only deploy.
- The `deploy-api` step maps optional secrets **only when they have a version**.
  Mapping a versionless secret makes the revision fail to start with a Secret
  Manager 404 — taking down a service that would otherwise have degraded
  gracefully.

If you change env wiring in `cloudbuild.yaml`, change it in
`deploy/30-deploy.sh` too. They are intentionally identical.

---

## 9. Rollback

### Application: shift traffic to the previous revision

Cloud Run keeps every revision. Rollback is a traffic change, not a redeploy,
and takes seconds.

```bash
gcloud run revisions list --service krishimitra-api --region asia-south1

gcloud run services update-traffic krishimitra-api --region asia-south1 \
  --to-revisions krishimitra-api-00007-abc=100
```

Return to the newest:

```bash
gcloud run services update-traffic krishimitra-api --region asia-south1 --to-latest
```

Roll back the frontend the same way. **Roll back the API first** — the frontend
tolerates an older API more readily than the reverse.

### Canary instead of a big-bang deploy

```bash
gcloud run deploy krishimitra-api --image ...:NEW --region asia-south1 --no-traffic
gcloud run services update-traffic krishimitra-api --region asia-south1 \
  --to-revisions LATEST=10        # 10% to the new revision
# watch the error rate, then LATEST=100 or drop back to 0
```

### Database

Schema migrations are **not** reverted by a traffic rollback. Design them
additively (add nullable columns, never rename or drop in the same release as
the code change) so revision N-1 keeps working against schema N.

Point-in-time recovery is on with 7 days of transaction logs. PITR restores into
a **new instance**; it never overwrites the live one:

```bash
gcloud sql instances clone krishimitra-pg krishimitra-pg-restored \
  --point-in-time '2026-08-25T14:30:00.000Z' --project ${PROJECT_ID}
```

Inspect the clone, copy out what you need, then delete it. Restoring in place is
a decision, not a command you run while panicking.

### Models

See [§5](#5-uploading-trained-models) — restore a previous object generation.

---

## 10. Monitoring and logging

### Logs

```bash
gcloud run services logs read krishimitra-api --region asia-south1 --limit 100
gcloud run services logs tail krishimitra-api --region asia-south1

# Errors only, last hour
gcloud logging read '
  resource.type=cloud_run_revision AND
  resource.labels.service_name=krishimitra-api AND
  severity>=ERROR' --freshness=1h --limit=50 --project ${PROJECT_ID}

# Slow requests
gcloud logging read '
  resource.type=cloud_run_revision AND
  resource.labels.service_name=krishimitra-api AND
  httpRequest.latency>="3s"' --freshness=24h --limit=20 --project ${PROJECT_ID}

# Satellite job
gcloud logging read '
  resource.type=cloud_run_job AND
  resource.labels.job_name=krishimitra-satellite' --limit=100 --project ${PROJECT_ID}
```

### Metrics worth watching

| Metric | Why | Alert at |
|---|---|---|
| `run.googleapis.com/request_count` (5xx) | user-visible failure | > 1% over 5 min |
| `run.googleapis.com/request_latencies` p95 | model inference degradation | > 5 s |
| `run.googleapis.com/container/memory/utilizations` | joblib unpickling OOM | > 85% |
| `run.googleapis.com/container/instance_count` | runaway scale / cost | at `max-instances` |
| `cloudsql.googleapis.com/database/postgresql/num_backends` | connection exhaustion | > 80 of 100 |
| `cloudsql.googleapis.com/database/disk/utilization` | autoresize churn | > 80% |

### Alerting: a starting policy

```bash
gcloud alpha monitoring policies create --project ${PROJECT_ID} --policy-from-file=- <<'EOF'
displayName: "KrishiMitra API 5xx rate"
combiner: OR
conditions:
  - displayName: "5xx > 1% over 5 minutes"
    conditionThreshold:
      filter: >
        resource.type="cloud_run_revision"
        AND resource.labels.service_name="krishimitra-api"
        AND metric.type="run.googleapis.com/request_count"
        AND metric.labels.response_code_class="5xx"
      comparison: COMPARISON_GT
      thresholdValue: 5
      duration: 300s
      aggregations:
        - alignmentPeriod: 60s
          perSeriesAligner: ALIGN_RATE
EOF
```

Add a notification channel (`gcloud alpha monitoring channels create`) or the
alert fires into the void.

### Uptime check

```bash
gcloud monitoring uptime create krishimitra-web-health \
  --resource-type=uptime-url \
  --resource-labels=host=<web-host>,project_id=${PROJECT_ID} \
  --path=/api/health --period=5 --project ${PROJECT_ID}
```

Point it at the **frontend**, which is public. The API is private, so an uptime
check against it will report 403 forever.

### Cost monitoring

```bash
gcloud billing budgets create \
  --billing-account=${BILLING_ACCOUNT} \
  --display-name="KrishiMitra pilot" \
  --budget-amount=100USD \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0
```

Set this on day one. The failure mode is not a slow drift — it is one runaway
retry loop against a paid API over a weekend.

---

## 11. Cost estimate

**Small pilot**: ~500 farmers, ~50,000 API requests/month, one weekly satellite
run, `min-instances=0`. Region `asia-south1` (Mumbai, a Tier-1 Cloud Run
region). USD, list price, no committed-use discount.

Cloud Run Tier-1 rates used below: **$0.000024 per vCPU-second**, **$0.0000025
per GiB-second**, **$0.40 per million requests**, with a monthly free tier of
180,000 vCPU-s / 360,000 GiB-s / 2M requests.

| Component | Sizing | Monthly usage | Cost |
|---|---|---|---|
| Cloud Run — API | 2 vCPU, 2 GiB, min 0 | 50k req × 0.4 s × 2 vCPU = 40k vCPU-s; 40k GiB-s | **$0** (inside free tier) |
| Cloud Run — web | 1 vCPU, 512 MiB, min 0 | 50k req × 0.15 s = 7.5k vCPU-s | **$0** (inside free tier) |
| Cloud Run — satellite job | 2 vCPU, 4 GiB, 4 runs × ~20 min | 9.6k vCPU-s, 19.2k GiB-s | **~$0.28** |
| Cloud SQL — PostgreSQL | `db-g1-small`, 10 GB HDD, zonal | always on | **~$32** |
| Cloud SQL — backups | 7 daily + 7-day PITR logs, ~15 GB | | **~$1.30** |
| Cloud Storage — models | ~1 GB with versions, Standard | | **~$0.03** |
| Cloud Storage — uploads | ~5 GB growing | | **~$0.13** |
| Cloud Storage — satellite | ~2 GB of maps/tables with versions | | **~$0.05** |
| Cloud Storage — gcsfuse ops | ~50k Class A/B ops per run | | **~$0.02** |
| Artifact Registry | ~4 GB of images | | **~$0.40** |
| Cloud Build | ~40 builds × 8 min on E2_HIGHCPU_8 | 320 build-min | **~$1.60** (120 free min/day) |
| Secret Manager | 8 secrets, ~50k accesses | | **~$0.35** |
| Cloud Scheduler | 1 job | | **$0** (3 free) |
| Cloud Logging | ~5 GB ingested | | **$0** (50 GB free) |
| Egress | ~10 GB to the internet | | **~$1.20** |
| **Total** | | | **~$37/month** |

**Cloud SQL is 85% of the bill.** Everything else rounds to noise at pilot scale.

### Levers

| Change | Delta |
|---|---|
| `SQL_TIER=db-f1-micro` | −$20/mo; no SLA, dev only |
| `SQL_AVAILABILITY=REGIONAL` | +$32/mo; automatic failover |
| `SQL_STORAGE_TYPE=PD_SSD` | +$1/mo at 10 GB; worth it if queries get analytical |
| `API_MIN_INSTANCES=1` | **+$50–60/mo** (2 vCPU × 2.6M s × $0.000018 idle rate + memory). Removes the ~25 s cold start caused by downloading and unpickling 170 MB of models. The honest trade: pay it, or accept that the first farmer of the morning waits. |
| Cloud SQL 1-year CUD | −25% on the instance |

### Scaling to ~10,000 farmers

~1M requests/month: Cloud Run leaves the free tier (~$25–35/mo for both
services), Cloud SQL wants `db-custom-2-7680` (~$110/mo), egress rises. Budget
**~$180–220/month**.

> Prices change and vary by region. Verify against
> <https://cloud.google.com/products/calculator> before quoting these to anyone
> who signs cheques.

---

## 12. Security checklist

Work through this before real farmer data touches the system.

### Identity and access

- [ ] Each service runs as its **own** service account. No Compute Engine
      default SA anywhere (`gcloud run services describe <svc>
      --format='value(spec.template.spec.serviceAccountName)'`).
- [ ] The API is `--no-allow-unauthenticated`; only `krishimitra-web`'s SA holds
      `roles/run.invoker` on it, scoped to that service.
- [ ] No `roles/editor` or `roles/owner` on any service account.
      `gcloud projects get-iam-policy ${PROJECT_ID} --flatten='bindings[].members' \
       --filter='bindings.role:roles/owner OR bindings.role:roles/editor'`
- [ ] Storage grants are **bucket-scoped**: `objectViewer` on models,
      `objectAdmin` on uploads. Never project-wide `storage.admin`.
- [ ] Secret access is granted **per secret**, not with a project-level
      `secretmanager.secretAccessor`.
- [ ] `krishimitra-db-password` is readable by operators only — no runtime
      identity can read it. The API consumes the assembled URL instead.
- [ ] No service-account JSON keys exist:
      `gcloud iam service-accounts keys list --iam-account=<sa> --managed-by=user`
      returns nothing. Consider the org policy
      `constraints/iam.disableServiceAccountKeyCreation`.

### Secrets

- [ ] No secret is in an env var in `cloudbuild.yaml`, `deploy/env`, a
      Dockerfile, or git. All arrive via `--set-secrets`.
- [ ] `AGROTECH_JWT_SECRET` is ≥ 256 bits and machine-generated.
- [ ] `AGROTECH_ADMIN_PASSWORD_HASH` is a hash. The plaintext exists nowhere.
- [ ] `git log -p --all -- '*.env' '*key*.json'` finds nothing. If it does, the
      secret is compromised: rotate it, do not just delete the file.
- [ ] A rotation schedule exists for third-party API keys.

### Data

- [ ] Cloud SQL: `--ssl-mode=ENCRYPTED_ONLY`, **empty** authorized-networks list,
      deletion protection on.
      `gcloud sql instances describe krishimitra-pg \
       --format='value(settings.ipConfiguration.authorizedNetworks)'` → empty.
- [ ] Automated backups on, PITR on, restore actually tested (a backup you have
      never restored is a hypothesis).
- [ ] All three data buckets (models, uploads, satellite): uniform bucket-level
      access **and** public access prevention enforced.
      `gcloud storage buckets describe gs://<bucket> \
       --format='value(iamConfiguration.publicAccessPrevention)'` → `enforced`.
- [ ] No bucket has an `allUsers`/`allAuthenticatedUsers` binding — check the
      uploads bucket especially, it holds farmer photographs.
- [ ] The satellite job's identity can write ONLY the satellite bucket, and the
      API's identity can only read it. Neither has access to the other's data.
- [ ] Uploads are validated server-side for content type and size
      (`AGROTECH_MAX_UPLOAD_SIZE_BYTES`, `AGROTECH_ALLOWED_UPLOAD_TYPES`).
      Farmer photographs are personal data.

### Application

- [ ] `AGROTECH_ENVIRONMENT=production` and `AGROTECH_REQUIRE_WRITE_AUTH=true`.
- [ ] `AGROTECH_CORS_ORIGINS` lists exact origins. Never `*`. It is honoured —
      confirm with a cross-origin `OPTIONS` from an unlisted origin.
- [ ] Containers run as non-root (all three Dockerfiles do; verify with
      `docker run --rm <image> id`).
- [ ] No `latest` tag in a deployed revision — every revision pins a digest or a
      commit SHA.
- [ ] Artifact Registry vulnerability scanning is on, and someone reads the
      results.

### Operations

- [ ] A billing budget with alerts exists.
- [ ] `max-instances` is set on both services — the guard against a retry storm
      becoming a five-figure bill.
- [ ] Alerts route to a human, not an unread inbox.
- [ ] Audit logging is on for Secret Manager and Cloud SQL admin activity.
- [ ] Terraform state (if used) is in a private, versioned GCS bucket — it holds
      the database password in plaintext.

---

## 13. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Container failed to start and listen on PORT` (web) | `HOSTNAME` not `0.0.0.0` | it is set in `Dockerfile.web`; check it was not overridden by a deploy flag |
| `.next/standalone` missing at build | `output: "standalone"` absent from `next.config.ts` | add it; `Dockerfile.web` fails with this exact message on purpose |
| API revision fails, logs show `Set AGROTECH_JWT_SECRET` | production mode without the secret | `./deploy/20-secrets.sh`, then redeploy |
| `Revision ... Secret Manager 404` | a mapped secret has no version | `gcloud secrets versions list <name>`; unmap it or add a version |
| `libgomp.so.1: cannot open shared object file` | `libgomp1` missing from a slim runtime | it is installed in `Dockerfile.api`; do not remove it |
| `could not connect to server: No such file or directory` | `--add-cloudsql-instances` missing, or a TCP URL used on Cloud Run | use the `?host=/cloudsql/...` form |
| Startup probe timeout on the API | model download + unpickle exceeds the budget | raise `failureThreshold`, or set `API_MIN_INSTANCES=1` |
| CORS error in the browser | the frontend is calling the API cross-origin | set `NEXT_PUBLIC_ML_API_URL=/api/ml` and rebuild — this is a **build-time** value |
| `PERMISSION_DENIED: iam.serviceAccounts.actAs` | build SA lacks `roles/iam.serviceAccountUser` | re-run `./deploy/10-provision.sh` |
| Cloud Build: "must specify logs_bucket or logging option" | `serviceAccount:` set without `options.logging` | already set to `CLOUD_LOGGING_ONLY`; do not remove it |
| Satellite job 403 on `serviceusage.services.use` | missing `serviceUsageConsumer` | [§7.3](#73-grant-the-roles) |

Useful one-liners:

```bash
# What is actually deployed, config and all
gcloud run services describe krishimitra-api --region asia-south1 --format=yaml

# Env vars on the live revision
gcloud run services describe krishimitra-api --region asia-south1 \
  --format='value(spec.template.spec.containers[0].env)'

# Why did the last revision fail?
gcloud run revisions describe <revision> --region asia-south1 \
  --format='value(status.conditions)'

# Reproduce the container locally, exactly
docker run --rm -p 8080:8080 -e PORT=8080 \
  asia-south1-docker.pkg.dev/${PROJECT_ID}/krishimitra/krishimitra-api:<tag>
```

---

## 14. Teardown

Deliberately not a script. Delete in this order; each command is destructive.

```bash
# 1. Stop scheduled work
gcloud scheduler jobs delete krishimitra-satellite-weekly --location asia-south1

# 2. Cloud Run
gcloud run services delete krishimitra-web       --region asia-south1
gcloud run services delete krishimitra-api       --region asia-south1
gcloud run jobs delete     krishimitra-migrate   --region asia-south1
gcloud run jobs delete     krishimitra-satellite --region asia-south1

# 3. Back up the database BEFORE deleting it
gcloud sql export sql krishimitra-pg \
  gs://${PROJECT_ID}-krishimitra-models/final-backup.sql.gz --database=agrotech

# 4. Cloud SQL — deletion protection must be removed first, on purpose
gcloud sql instances patch krishimitra-pg --no-deletion-protection
gcloud sql instances delete krishimitra-pg

# 5. Buckets — copy anything you want to keep first. This is irreversible.
gcloud storage rm -r gs://${PROJECT_ID}-krishimitra-uploads
gcloud storage rm -r gs://${PROJECT_ID}-krishimitra-satellite
gcloud storage rm -r gs://${PROJECT_ID}-krishimitra-models

# 6. Registry, secrets, service accounts
gcloud artifacts repositories delete krishimitra --location asia-south1
for s in agrotech-database-url agrotech-jwt-secret agrotech-admin-password-hash \
         agrotech-sarvam-api-key agrotech-brave-search-api-key \
         agrotech-myscheme-api-key krishimitra-db-password ee-service-account-json; do
  gcloud secrets delete "$s" --quiet
done
for sa in api web satellite scheduler build; do
  gcloud iam service-accounts delete "krishimitra-${sa}@${PROJECT_ID}.iam.gserviceaccount.com" --quiet
done
```

Simplest and safest of all, if the project holds nothing else:

```bash
gcloud projects delete ${PROJECT_ID}      # 30-day recovery window
```
