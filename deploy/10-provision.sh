#!/usr/bin/env bash
# =============================================================================
# 10 — Provision the durable infrastructure.
#
#   ./deploy/10-provision.sh
#
# Creates (all idempotent — re-running converges, never duplicates):
#   * Artifact Registry Docker repository
#   * GCS buckets: models (versioned) + uploads
#   * Cloud SQL for PostgreSQL instance, database and application user
#   * Five service accounts with least-privilege IAM
#   * Secret Manager entries derived from the generated DB password
#
# Deletes NOTHING. There is no --destroy flag on purpose: tearing this down is a
# deliberate, manual act (the teardown commands are listed in
# docs/DEPLOY_GCP.md so they cannot be run by accident from here).
#
# COST WARNING: the Cloud SQL instance is the only always-on resource and is
# billed by the hour whether or not anything talks to it. See the cost table in
# docs/DEPLOY_GCP.md.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

load_env
require_cmd gcloud openssl
require_project
require_billing

# URL scheme for AGROTECH_DATABASE_URL. Plain `postgresql://` suits psycopg and
# SQLAlchemy's default (psycopg2) driver. Set SQL_URL_SCHEME=postgresql+psycopg
# if ml-service moves to SQLAlchemy with psycopg 3.
: "${SQL_URL_SCHEME:=postgresql}"

# Secret names. 20-secrets.sh manages the operator-supplied secrets; these two
# are created here because only this script ever sees the generated password.
SECRET_DB_PASSWORD="krishimitra-db-password"
SECRET_DATABASE_URL="agrotech-database-url"

# Superseded model versions are kept this long before deletion. This only ever
# removes NONCURRENT versions — live objects are never touched.
: "${MODELS_NONCURRENT_RETENTION_DAYS:=90}"

print_plan_header "Provision KrishiMitra infrastructure"

cat <<PLAN
This script will CREATE (and never delete):

  Artifact Registry
    ${AR_HOST}/${PROJECT_ID}/${AR_REPO}            (docker, ${REGION})

  Cloud Storage
    gs://${MODELS_BUCKET}                          (${BUCKET_LOCATION}, versioned)
    gs://${UPLOADS_BUCKET}                         (${BUCKET_LOCATION})
    gs://${SATELLITE_BUCKET}                       (${BUCKET_LOCATION}, versioned)
    gs://${PROJECT_ID}_cloudbuild                  (Cloud Build source staging)

  Cloud SQL for PostgreSQL   [~10 minutes, and the main recurring cost]
    instance   ${SQL_INSTANCE}   ${SQL_VERSION} / ${SQL_TIER} / ${SQL_STORAGE_SIZE_GB}GB ${SQL_STORAGE_TYPE}
    connection ${SQL_CONNECTION_NAME}
    database   ${SQL_DB}
    user       ${SQL_USER}   (password generated here, stored in Secret Manager)
    availability ${SQL_AVAILABILITY}, daily backup at ${SQL_BACKUP_START_TIME} UTC, deletion protection ON

  Service accounts
    ${API_SA_EMAIL}
    ${WEB_SA_EMAIL}
    ${SATELLITE_SA_EMAIL}
    ${SCHEDULER_SA_EMAIL}
    ${BUILD_SA_EMAIL}

  Secret Manager
    ${SECRET_DB_PASSWORD}
    ${SECRET_DATABASE_URL}

PLAN

confirm "Create these resources in ${PROJECT_ID}?" || die "aborted"

# =============================================================================
# 1. Artifact Registry
# =============================================================================
banner "Artifact Registry"

if gc artifacts repositories describe "${AR_REPO}" --location "${REGION}" >/dev/null 2>&1; then
  skip "repository ${AR_REPO} exists in ${REGION}"
else
  gc artifacts repositories create "${AR_REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="KrishiMitra container images (api, web, satellite)" >/dev/null
  ok "created Docker repository ${IMAGE_BASE}"
fi

# Lets `docker push` work from a workstation. Harmless and idempotent.
if [[ "${CONFIGURE_DOCKER_AUTH:-1}" == "1" ]]; then
  if gcloud auth configure-docker "${AR_HOST}" --quiet >/dev/null 2>&1; then
    ok "local docker configured for ${AR_HOST}"
  else
    warn "could not configure local docker auth (fine if docker is not installed)"
  fi
fi

# =============================================================================
# 2. Cloud Storage buckets
# =============================================================================
banner "Cloud Storage"

# ensure_gcs_bucket <name> <purpose>
#   --uniform-bucket-level-access : disables per-object ACLs, so IAM is the one
#                                   and only access-control surface.
#   --public-access-prevention    : hard block on ever making it public. Farmer
#                                   uploads must not be world-readable.
ensure_gcs_bucket() {
  local bucket="$1" purpose="$2"
  if gc storage buckets describe "gs://${bucket}" >/dev/null 2>&1; then
    skip "bucket gs://${bucket} exists"
  else
    gc storage buckets create "gs://${bucket}" \
      --location="${BUCKET_LOCATION}" \
      --uniform-bucket-level-access \
      --public-access-prevention >/dev/null
    ok "created gs://${bucket} (${purpose})"
  fi
}

ensure_gcs_bucket "${MODELS_BUCKET}"    "trained model artifacts"
ensure_gcs_bucket "${UPLOADS_BUCKET}"   "farmer uploads (pest photos, soil reports)"
ensure_gcs_bucket "${SATELLITE_BUCKET}" "satellite maps, figures and advisory tables"
ensure_gcs_bucket "${PROJECT_ID}_cloudbuild" "Cloud Build source staging"

# Object versioning: a bad retrain, or a satellite run over a cloudy week, is
# rolled back by restoring the previous generation rather than regenerating.
# The satellite job overwrites the same object names every run, so versioning is
# the only thing that keeps last week's advisory maps recoverable.
for bucket in "${MODELS_BUCKET}" "${SATELLITE_BUCKET}"; do
  gc storage buckets update "gs://${bucket}" --versioning >/dev/null
  ok "object versioning enabled on gs://${bucket}"
done

# Age out superseded versions. Scoped to isLive=false so the CURRENT object is
# never a candidate for deletion, no matter how old it is.
lifecycle_file="$(mktemp)"
trap 'rm -f "${lifecycle_file}"' EXIT
cat > "${lifecycle_file}" <<JSON
{
  "lifecycle": {
    "rule": [
      {
        "action": { "type": "Delete" },
        "condition": {
          "daysSinceNoncurrentTime": ${MODELS_NONCURRENT_RETENTION_DAYS},
          "isLive": false
        }
      }
    ]
  }
}
JSON
for bucket in "${MODELS_BUCKET}" "${SATELLITE_BUCKET}"; do
  gc storage buckets update "gs://${bucket}" --lifecycle-file="${lifecycle_file}" >/dev/null
  ok "gs://${bucket}: superseded versions deleted after ${MODELS_NONCURRENT_RETENTION_DAYS} days (live objects untouched)"
done

# =============================================================================
# 3. Service accounts
# =============================================================================
banner "Service accounts"

ensure_service_account "${API_SA}" \
  "KrishiMitra API (Cloud Run)" \
  "Runtime identity for the FastAPI ml-service on Cloud Run"

ensure_service_account "${WEB_SA}" \
  "KrishiMitra Web (Cloud Run)" \
  "Runtime identity for the Next.js frontend; calls the API through /api/ml"

ensure_service_account "${SATELLITE_SA}" \
  "KrishiMitra Satellite Job" \
  "Runtime identity for the satellite-ml Cloud Run Job; talks to Earth Engine"

ensure_service_account "${SCHEDULER_SA}" \
  "KrishiMitra Scheduler" \
  "Cloud Scheduler identity that triggers the satellite Cloud Run Job"

ensure_service_account "${BUILD_SA}" \
  "KrishiMitra Cloud Build" \
  "Builds and deploys the container images"

# =============================================================================
# 4. Cloud SQL for PostgreSQL
# =============================================================================
banner "Cloud SQL for PostgreSQL"

if gc sql instances describe "${SQL_INSTANCE}" >/dev/null 2>&1; then
  skip "instance ${SQL_INSTANCE} exists"
else
  warn "creating a Cloud SQL instance takes roughly 10 minutes. Do not interrupt."
  # Notes on the flags that matter:
  #   --no-assign-ip is deliberately NOT used: Cloud Run reaches Cloud SQL
  #     through the built-in connector over a Unix socket, which needs no VPC
  #     connector and no authorized networks. The instance has a public IP but
  #     an EMPTY authorized-network list, so nothing on the internet can open a
  #     connection to it.
  #   --ssl-mode=ENCRYPTED_ONLY rejects any unencrypted connection.
  #   --deletion-protection makes `gcloud sql instances delete` fail until an
  #     operator explicitly removes the flag. This is the single most valuable
  #     setting in this file.
  gc sql instances create "${SQL_INSTANCE}" \
    --database-version="${SQL_VERSION}" \
    --edition=ENTERPRISE \
    --tier="${SQL_TIER}" \
    --region="${REGION}" \
    --storage-type="${SQL_STORAGE_TYPE}" \
    --storage-size="${SQL_STORAGE_SIZE_GB}" \
    --storage-auto-increase \
    --availability-type="${SQL_AVAILABILITY}" \
    --backup \
    --backup-start-time="${SQL_BACKUP_START_TIME}" \
    --retained-backups-count=7 \
    --enable-point-in-time-recovery \
    --retained-transaction-log-days=7 \
    --maintenance-window-day=SUN \
    --maintenance-window-hour=20 \
    --maintenance-release-channel=production \
    --ssl-mode=ENCRYPTED_ONLY \
    --deletion-protection \
    --database-flags=max_connections=100
  ok "created Cloud SQL instance ${SQL_CONNECTION_NAME}"
fi

if gc sql databases describe "${SQL_DB}" --instance="${SQL_INSTANCE}" >/dev/null 2>&1; then
  skip "database ${SQL_DB} exists"
else
  gc sql databases create "${SQL_DB}" --instance="${SQL_INSTANCE}" >/dev/null
  ok "created database ${SQL_DB}"
fi

# --- application user + generated password -----------------------------------
# The password is generated here and immediately written to Secret Manager. It
# is never echoed and never written to a file on disk.
#
# One honest caveat: `gcloud sql users create` has no stdin/file password
# option, so the value does appear in this process's argv for the lifetime of
# that single call and is visible to `ps` on the machine running the script. It
# does not enter shell history (the script is not typed interactively). If that
# window is unacceptable in your environment, create the user by hand with
# `gcloud sql users create --prompt-for-password` and re-run this script, which
# will then find the user and skip the create.
#
# On re-runs an existing secret is reused rather than rotated, so this script
# stays safe to run repeatedly against a live deployment.
if secret_exists "${SECRET_DB_PASSWORD}"; then
  skip "reusing existing secret ${SECRET_DB_PASSWORD} (no rotation on re-run)"
  DB_PASSWORD="$(gc secrets versions access latest --secret="${SECRET_DB_PASSWORD}")"
else
  # 32 URL-safe characters: the password is embedded in a postgresql:// URL, so
  # anything needing percent-encoding is excluded up front.
  DB_PASSWORD="$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 32)"
  printf '%s' "${DB_PASSWORD}" \
    | gc secrets create "${SECRET_DB_PASSWORD}" \
        --data-file=- \
        --replication-policy=automatic \
        --labels=app=krishimitra,component=database >/dev/null
  ok "generated database password and stored it as secret ${SECRET_DB_PASSWORD}"
fi

if gc sql users list --instance="${SQL_INSTANCE}" \
     --format='value(name)' | grep -qx "${SQL_USER}"; then
  skip "database user ${SQL_USER} exists (password left as-is)"
else
  gc sql users create "${SQL_USER}" \
    --instance="${SQL_INSTANCE}" \
    --password="${DB_PASSWORD}" >/dev/null
  ok "created database user ${SQL_USER}"
fi

# --- the connection string the API actually consumes -------------------------
# Unix-socket form. Cloud Run mounts the connector socket at
# /cloudsql/<INSTANCE_CONNECTION_NAME>; libpq/psycopg accept it through the
# `host` query parameter, with an empty host section before the slash.
DATABASE_URL="${SQL_URL_SCHEME}://${SQL_USER}:${DB_PASSWORD}@/${SQL_DB}?host=/cloudsql/${SQL_CONNECTION_NAME}"

if secret_exists "${SECRET_DATABASE_URL}"; then
  # Add a new version rather than replacing, so a bad rotation can be rolled
  # back by pointing the service at the previous version.
  existing="$(gc secrets versions access latest --secret="${SECRET_DATABASE_URL}" 2>/dev/null || echo '')"
  if [[ "${existing}" == "${DATABASE_URL}" ]]; then
    skip "secret ${SECRET_DATABASE_URL} already current"
  else
    printf '%s' "${DATABASE_URL}" \
      | gc secrets versions add "${SECRET_DATABASE_URL}" --data-file=- >/dev/null
    ok "added a new version of ${SECRET_DATABASE_URL}"
  fi
else
  printf '%s' "${DATABASE_URL}" \
    | gc secrets create "${SECRET_DATABASE_URL}" \
        --data-file=- \
        --replication-policy=automatic \
        --labels=app=krishimitra,component=database >/dev/null
  ok "stored AGROTECH_DATABASE_URL as secret ${SECRET_DATABASE_URL}"
fi

# =============================================================================
# 5. IAM — least privilege, role by role
# =============================================================================
banner "IAM bindings"

# --- API runtime -------------------------------------------------------------
info "API service account (${API_SA_EMAIL})"
# cloudsql.client: required by the Cloud Run <-> Cloud SQL connector. It grants
# "connect to instances", NOT "read data" and NOT "administer instances".
ensure_project_role "${API_SA_EMAIL}" "roles/cloudsql.client"
# Cloud Run writes request logs as the service agent, but application logs and
# custom metrics are written as the runtime identity.
ensure_project_role "${API_SA_EMAIL}" "roles/logging.logWriter"
ensure_project_role "${API_SA_EMAIL}" "roles/monitoring.metricWriter"
ensure_project_role "${API_SA_EMAIL}" "roles/cloudtrace.agent"
# Bucket-scoped, not project-scoped: read-only on models, read/write on uploads.
# (roles/storage.objectUser is a slightly tighter fit than objectAdmin for the
# uploads bucket if your org has it available — objectAdmin additionally allows
# object-level IAM changes, which uniform bucket-level access already disables.)
ensure_bucket_role "${MODELS_BUCKET}"    "${API_SA_EMAIL}" "roles/storage.objectViewer"
ensure_bucket_role "${UPLOADS_BUCKET}"   "${API_SA_EMAIL}" "roles/storage.objectAdmin"
# Read-only on satellite products: the API serves the maps and advisory tables
# the batch job produces, but must never be able to alter them.
ensure_bucket_role "${SATELLITE_BUCKET}" "${API_SA_EMAIL}" "roles/storage.objectViewer"

# --- Web runtime -------------------------------------------------------------
info "Web service account (${WEB_SA_EMAIL})"
ensure_project_role "${WEB_SA_EMAIL}" "roles/logging.logWriter"
ensure_project_role "${WEB_SA_EMAIL}" "roles/monitoring.metricWriter"
# roles/run.invoker on the API is granted in 30-deploy.sh, scoped to the API
# SERVICE rather than the project, once that service actually exists.

# --- Satellite job -----------------------------------------------------------
info "Satellite service account (${SATELLITE_SA_EMAIL})"
ensure_project_role "${SATELLITE_SA_EMAIL}" "roles/logging.logWriter"
ensure_project_role "${SATELLITE_SA_EMAIL}" "roles/monitoring.metricWriter"
# The job mounts this bucket at /app/outputs through a Cloud Run Cloud Storage
# volume, so it needs read/write on objects. It gets no access at all to the
# models or uploads buckets.
ensure_bucket_role "${SATELLITE_BUCKET}" "${SATELLITE_SA_EMAIL}" "roles/storage.objectAdmin"

# Earth Engine. serviceUsageConsumer is the one people forget: without
# serviceusage.services.use, ee.Initialize(project=...) fails with a 403 that
# says nothing about Service Usage.
info "Earth Engine roles"
if gc services list --enabled --format='value(config.name)' \
     | grep -qx 'earthengine.googleapis.com'; then
  ensure_project_role "${SATELLITE_SA_EMAIL}" "roles/earthengine.writer"
  ensure_project_role "${SATELLITE_SA_EMAIL}" "roles/serviceusage.serviceUsageConsumer"
else
  warn "earthengine.googleapis.com is not enabled — skipping Earth Engine roles."
  warn "Register the project at https://console.cloud.google.com/earth-engine,"
  warn "re-run ./deploy/00-enable-apis.sh, then re-run this script."
fi

# --- Cloud Build -------------------------------------------------------------
info "Build service account (${BUILD_SA_EMAIL})"
# Push images.
ensure_project_role "${BUILD_SA_EMAIL}" "roles/artifactregistry.writer"
# Create/update Cloud Run services and jobs, and execute the migrate job.
ensure_project_role "${BUILD_SA_EMAIL}" "roles/run.admin"
# Required to deploy a service that RUNS AS another service account. Without
# this, `gcloud run deploy --service-account=...` fails with a PERMISSION_DENIED
# on iam.serviceAccounts.actAs that reads like an unrelated problem.
ensure_project_role "${BUILD_SA_EMAIL}" "roles/iam.serviceAccountUser"
# Mandatory when a build uses a user-specified service account: such a build
# must write logs to Cloud Logging (options.logging: CLOUD_LOGGING_ONLY in
# cloudbuild.yaml) and therefore needs logWriter.
ensure_project_role "${BUILD_SA_EMAIL}" "roles/logging.logWriter"
# Read the uploaded source tarball. Bucket-scoped rather than project-wide
# storage.admin, which is what most tutorials grant.
ensure_bucket_role "${PROJECT_ID}_cloudbuild" "${BUILD_SA_EMAIL}" "roles/storage.objectAdmin"

# --- Scheduler ---------------------------------------------------------------
info "Scheduler service account (${SCHEDULER_SA_EMAIL})"
# run.invoker on the satellite JOB is granted in 40-satellite-job.sh, scoped to
# that single job resource.
skip "run.invoker is granted per-job by 40-satellite-job.sh"

# =============================================================================
# Summary
# =============================================================================
banner "Provisioned"

cat <<SUMMARY
  Artifact Registry   ${IMAGE_BASE}
  Models bucket       gs://${MODELS_BUCKET}
  Uploads bucket      gs://${UPLOADS_BUCKET}
  Satellite bucket    gs://${SATELLITE_BUCKET}
  Cloud SQL           ${SQL_CONNECTION_NAME}   (db: ${SQL_DB}, user: ${SQL_USER})
  DB URL secret       ${SECRET_DATABASE_URL}

  Next: ./deploy/20-secrets.sh
SUMMARY
