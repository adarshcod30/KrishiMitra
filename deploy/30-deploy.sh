#!/usr/bin/env bash
# =============================================================================
# 30 — Build the images and deploy the API + frontend to Cloud Run.
#
#   ./deploy/30-deploy.sh                      # build everything, deploy, wire
#   ./deploy/30-deploy.sh --skip-build         # redeploy the current images
#   ./deploy/30-deploy.sh --skip-migrate       # deploy without touching the DB
#   ./deploy/30-deploy.sh --tag v1.4.0         # explicit image tag
#
# What it does, in order:
#   1. build + push  api / web images  (Cloud Build; no local docker needed)
#   2. run database migrations as a one-shot Cloud Run Job
#   3. deploy the API service   (Cloud SQL connector, secrets, GCS wiring)
#   4. deploy the web service   (pointed at the API's real URL)
#   5. re-wire the API's AGROTECH_CORS_ORIGINS / AGROTECH_PUBLIC_BASE_URL to the
#      real URLs, which are only knowable after step 3 and 4
#   6. grant the web identity permission to invoke the API
#
# Everything is idempotent. Cloud Run deploys create a new revision and shift
# traffic to it; the previous revision stays available for instant rollback
# (see docs/DEPLOY_GCP.md, "Rollback").
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

load_env
require_cmd gcloud
require_project

SKIP_BUILD=0
SKIP_MIGRATE=0
IMAGE_TAG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-build)   SKIP_BUILD=1; shift ;;
    --skip-migrate) SKIP_MIGRATE=1; shift ;;
    --tag)          IMAGE_TAG="${2:?--tag needs a value}"; shift 2 ;;
    -h|--help)      sed -n '2,26p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *)              die "unknown argument: $1" ;;
  esac
done

# Default tag: short git SHA, so a running revision can always be traced back to
# a commit. Falls back to a timestamp outside a git checkout, and gains a
# "-dirty" suffix when the tree has uncommitted changes — a deployed image that
# does not correspond to any commit should say so.
if [[ -z "${IMAGE_TAG}" ]]; then
  if git -C "${REPO_ROOT}" rev-parse --git-dir >/dev/null 2>&1; then
    IMAGE_TAG="$(git -C "${REPO_ROOT}" rev-parse --short=12 HEAD)"
    if ! git -C "${REPO_ROOT}" diff --quiet HEAD 2>/dev/null; then
      IMAGE_TAG="${IMAGE_TAG}-dirty-$(date -u +%Y%m%d%H%M%S)"
    fi
  else
    IMAGE_TAG="$(date -u +%Y%m%d%H%M%S)"
  fi
fi

# -----------------------------------------------------------------------------
# Preflight: refuse to deploy a production config that cannot possibly start.
# get_settings() raises at import time when AGROTECH_ENVIRONMENT=production and
# AGROTECH_JWT_SECRET is missing, so the container would crash-loop with an
# error buried in the revision logs. Catch it here instead.
# -----------------------------------------------------------------------------
secret_ready() {
  gc secrets versions list "$1" --filter='state:ENABLED' --limit=1 \
    --format='value(name)' 2>/dev/null | grep -q .
}

banner "Preflight"

for s in agrotech-database-url agrotech-jwt-secret; do
  secret_ready "${s}" || die "secret '${s}' has no enabled version. Run ./deploy/20-secrets.sh first."
done
ok "required secrets have versions"

if [[ "${AGROTECH_REQUIRE_WRITE_AUTH}" == "true" ]]; then
  secret_ready agrotech-admin-password-hash \
    || die "AGROTECH_REQUIRE_WRITE_AUTH=true but 'agrotech-admin-password-hash' has no version. Run ./deploy/20-secrets.sh."
  ok "admin credentials present for write auth"
fi

gc sql instances describe "${SQL_INSTANCE}" >/dev/null 2>&1 \
  || die "Cloud SQL instance '${SQL_INSTANCE}' not found. Run ./deploy/10-provision.sh first."
ok "Cloud SQL ${SQL_CONNECTION_NAME} reachable"

# Optional secrets: mapped into the API only when they actually hold a value, so
# a missing Sarvam key degrades the translation feature instead of crash-looping
# the whole service on a Secret Manager 404.
OPTIONAL_SECRET_MAP=()
for pair in \
    "AGROTECH_SARVAM_API_KEY=agrotech-sarvam-api-key" \
    "AGROTECH_BRAVE_SEARCH_API_KEY=agrotech-brave-search-api-key" \
    "AGROTECH_MYSCHEME_API_KEY=agrotech-myscheme-api-key"; do
  env_name="${pair%%=*}"; secret_name="${pair#*=}"
  if secret_ready "${secret_name}"; then
    OPTIONAL_SECRET_MAP+=("${env_name}=${secret_name}:latest")
    ok "${env_name} <- ${secret_name}"
  else
    skip "${env_name} not configured (feature will degrade gracefully)"
  fi
done

print_plan_header "Deploy to Cloud Run"

cat <<PLAN
  image tag        ${IMAGE_TAG}
  api image        ${API_IMAGE}:${IMAGE_TAG}
  web image        ${WEB_IMAGE}:${IMAGE_TAG}

  api service      ${API_SERVICE}   as ${API_SA_EMAIL}
                   ${API_CPU} vCPU / ${API_MEMORY} / ${API_MIN_INSTANCES}-${API_MAX_INSTANCES} instances
                   public: ${API_ALLOW_UNAUTHENTICATED}
  web service      ${WEB_SERVICE}   as ${WEB_SA_EMAIL}
                   ${WEB_CPU} vCPU / ${WEB_MEMORY} / ${WEB_MIN_INSTANCES}-${WEB_MAX_INSTANCES} instances
                   public: ${WEB_ALLOW_UNAUTHENTICATED}

  cloud sql        ${SQL_CONNECTION_NAME}
  models           gs://${MODELS_BUCKET}/artifacts
  uploads          gs://${UPLOADS_BUCKET}
  build            $( [[ "${SKIP_BUILD}" == "1" ]] && echo "SKIPPED" || echo "Cloud Build" )
  migrations       $( [[ "${SKIP_MIGRATE}" == "1" ]] && echo "SKIPPED" || echo "job ${MIGRATE_JOB}" )
PLAN

confirm "Deploy to ${PROJECT_ID}?" || die "aborted"

# =============================================================================
# 1. Build
# =============================================================================
# Cloud Build is used rather than a local `docker build` so that the deployment
# works from any workstation, produces linux/amd64 images even on an Apple
# Silicon Mac, and leaves an auditable build record in the project.
#
# `gcloud builds submit --tag` always uses a file literally named "Dockerfile",
# so each image gets a small generated build config naming the right one.
# =============================================================================
build_image() {
  local dockerfile="$1" image="$2" shortname="$3"
  shift 3
  local build_args=("$@")

  local cfg; cfg="$(mktemp "${TMPDIR:-/tmp}/km-build-XXXXXX.yaml")"
  local arg_lines=""
  local a
  for a in "${build_args[@]:-}"; do
    [[ -z "${a}" ]] && continue
    arg_lines+="      - '--build-arg'"$'\n'"      - '${a}'"$'\n'
  done

  cat > "${cfg}" <<YAML
steps:
  - name: 'gcr.io/cloud-builders/docker'
    id: 'build-${shortname}'
    args:
      - 'build'
      - '-f'
      - '${dockerfile}'
      - '-t'
      - '${image}:${IMAGE_TAG}'
      - '-t'
      - '${image}:latest'
${arg_lines}      - '.'
images:
  - '${image}:${IMAGE_TAG}'
  - '${image}:latest'
options:
  machineType: 'E2_HIGHCPU_8'
  logging: CLOUD_LOGGING_ONLY
timeout: '2400s'
YAML

  log "Building ${shortname} -> ${image}:${IMAGE_TAG}"
  # --gcs-source-staging-dir keeps the uploaded tarball in the bucket that
  # 10-provision.sh granted the build service account access to.
  gc builds submit "${REPO_ROOT}" \
    --config="${cfg}" \
    --service-account="projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA_EMAIL}" \
    --gcs-source-staging-dir="gs://${PROJECT_ID}_cloudbuild/source" \
    --region="${REGION}"
  rm -f "${cfg}"
  ok "${shortname} image pushed"
}

if [[ "${SKIP_BUILD}" == "1" ]]; then
  banner "Build (skipped)"
  skip "--skip-build: reusing ${IMAGE_TAG}"
else
  banner "Build"
  build_image "Dockerfile.api" "${API_IMAGE}" "api"
  # NEXT_PUBLIC_ML_API_URL is inlined into the client bundle here and cannot be
  # changed later by a Cloud Run env var. Default "/api/ml" keeps browser calls
  # same-origin through the Next.js proxy.
  build_image "Dockerfile.web" "${WEB_IMAGE}" "web" \
    "NEXT_PUBLIC_ML_API_URL=${NEXT_PUBLIC_ML_API_URL}"
fi

# =============================================================================
# 2. Database migrations
# =============================================================================
# Run as a Cloud Run Job on the API image, so migrations execute with exactly
# the code, dependencies and Cloud SQL connectivity the service will have.
#
# The command prefers Alembic when the image ships it, and otherwise falls back
# to importing the app settings — get_settings() calls init_db(), which creates
# and upgrades the schema. Both paths are safe to run repeatedly.
# =============================================================================
MIGRATE_COMMAND='set -e
cd /app
if [ -f /app/alembic.ini ] && command -v alembic >/dev/null 2>&1; then
  echo "[migrate] running alembic upgrade head"
  alembic upgrade head
else
  echo "[migrate] no alembic.ini; bootstrapping schema via init_db()"
  python -c "from agrotech_ml.core.settings import get_settings; get_settings(); print(\"[migrate] schema ready\")"
fi
echo "[migrate] done"'

if [[ "${SKIP_MIGRATE}" == "1" ]]; then
  banner "Migrations (skipped)"
  skip "--skip-migrate"
else
  banner "Database migrations"

  # `^@^` selects @ as the list delimiter so the shell script below, which is
  # full of commas and newlines, survives gcloud's list parsing intact.
  gc run jobs deploy "${MIGRATE_JOB}" \
    --image="${API_IMAGE}:${IMAGE_TAG}" \
    --region="${REGION}" \
    --service-account="${API_SA_EMAIL}" \
    --set-cloudsql-instances="${SQL_CONNECTION_NAME}" \
    --set-secrets="AGROTECH_DATABASE_URL=agrotech-database-url:latest" \
    --set-env-vars="^@^AGROTECH_ENVIRONMENT=development@GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
    --command="/bin/sh" \
    --args="^@^-c@${MIGRATE_COMMAND}" \
    --max-retries=1 \
    --task-timeout=600s \
    --cpu=1 --memory=1Gi >/dev/null
  ok "migrate job updated to ${IMAGE_TAG}"
  # AGROTECH_ENVIRONMENT=development above is deliberate: the migration does not
  # serve traffic and does not need a JWT secret, and production mode would make
  # get_settings() raise before it ever reaches init_db().

  log "Executing ${MIGRATE_JOB} (waiting for completion)"
  if gc run jobs execute "${MIGRATE_JOB}" --region="${REGION}" --wait; then
    ok "migrations applied"
  else
    warn "migration job failed. Inspect it with:"
    warn "  gcloud run jobs executions list --job=${MIGRATE_JOB} --region=${REGION} --project=${PROJECT_ID}"
    die "aborting before deploying a service against an unmigrated database"
  fi
fi

# =============================================================================
# 3. Deploy the API
# =============================================================================
banner "API service"

# First pass uses a placeholder public base URL; step 5 corrects it once Cloud
# Run has assigned the real hostnames.
API_ENV_PAIRS=(
  "AGROTECH_ENVIRONMENT=${AGROTECH_ENVIRONMENT}"
  "AGROTECH_ARTIFACTS_DIR=/app/artifacts"
  "AGROTECH_UPLOADS_DIR=/app/uploads"
  "AGROTECH_MODELS_GCS_URI=gs://${MODELS_BUCKET}/artifacts"
  "AGROTECH_UPLOADS_GCS_BUCKET=${UPLOADS_BUCKET}"
  "AGROTECH_REQUIRE_WRITE_AUTH=${AGROTECH_REQUIRE_WRITE_AUTH}"
  "AGROTECH_ADMIN_USERNAME=${AGROTECH_ADMIN_USERNAME}"
  "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  "WEB_CONCURRENCY=1"
)

API_SECRET_MAP=(
  "AGROTECH_DATABASE_URL=agrotech-database-url:latest"
  "AGROTECH_JWT_SECRET=agrotech-jwt-secret:latest"
)
if secret_ready agrotech-admin-password-hash; then
  API_SECRET_MAP+=("AGROTECH_ADMIN_PASSWORD_HASH=agrotech-admin-password-hash:latest")
fi
API_SECRET_MAP+=("${OPTIONAL_SECRET_MAP[@]:-}")

api_auth_flag="--no-allow-unauthenticated"
[[ "${API_ALLOW_UNAUTHENTICATED}" == "true" ]] && api_auth_flag="--allow-unauthenticated"

gc run deploy "${API_SERVICE}" \
  --image="${API_IMAGE}:${IMAGE_TAG}" \
  --region="${REGION}" \
  --platform=managed \
  --service-account="${API_SA_EMAIL}" \
  --add-cloudsql-instances="${SQL_CONNECTION_NAME}" \
  --port=8080 \
  --cpu="${API_CPU}" \
  --memory="${API_MEMORY}" \
  --min-instances="${API_MIN_INSTANCES}" \
  --max-instances="${API_MAX_INSTANCES}" \
  --concurrency="${API_CONCURRENCY}" \
  --timeout="${API_TIMEOUT}" \
  --execution-environment=gen2 \
  --cpu-boost \
  --ingress=all \
  --labels="app=krishimitra,component=api" \
  --set-env-vars="^@^$(join_by '@' "${API_ENV_PAIRS[@]}")" \
  --set-secrets="^@^$(join_by '@' "${API_SECRET_MAP[@]}")" \
  --startup-probe="httpGet.path=/health,httpGet.port=8080,initialDelaySeconds=10,periodSeconds=5,timeoutSeconds=5,failureThreshold=30" \
  --liveness-probe="httpGet.path=/health,httpGet.port=8080,periodSeconds=30,timeoutSeconds=5,failureThreshold=3" \
  "${api_auth_flag}" >/dev/null
# failureThreshold=30 x periodSeconds=5 + 10s initial delay = up to 160 seconds
# to become healthy. The API downloads ~170 MB of joblib artifacts from GCS and
# unpickles four ensembles on first boot; the Cloud Run default (4 failures at
# 240s total but a 1s period) is generous enough, but pinning the numbers makes
# the budget explicit instead of accidental.

API_URL="$(service_url "${API_SERVICE}")"
[[ -n "${API_URL}" ]] || die "could not read the API service URL"
ok "API deployed: ${API_URL}"

# =============================================================================
# 4. Deploy the frontend
# =============================================================================
banner "Web service"

WEB_ENV_PAIRS=(
  "ML_API_URL=${API_URL}"
  "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  "NODE_ENV=production"
)
# ML_API_URL is read server-side only, by the /api/ml route handler. It is NOT
# NEXT_PUBLIC_*, so it never reaches the browser and can be changed with a
# redeploy rather than a rebuild.

web_auth_flag="--no-allow-unauthenticated"
[[ "${WEB_ALLOW_UNAUTHENTICATED}" == "true" ]] && web_auth_flag="--allow-unauthenticated"

gc run deploy "${WEB_SERVICE}" \
  --image="${WEB_IMAGE}:${IMAGE_TAG}" \
  --region="${REGION}" \
  --platform=managed \
  --service-account="${WEB_SA_EMAIL}" \
  --port=3000 \
  --cpu="${WEB_CPU}" \
  --memory="${WEB_MEMORY}" \
  --min-instances="${WEB_MIN_INSTANCES}" \
  --max-instances="${WEB_MAX_INSTANCES}" \
  --concurrency="${WEB_CONCURRENCY}" \
  --timeout="${WEB_TIMEOUT}" \
  --execution-environment=gen2 \
  --cpu-boost \
  --ingress=all \
  --labels="app=krishimitra,component=web" \
  --set-env-vars="^@^$(join_by '@' "${WEB_ENV_PAIRS[@]}")" \
  --startup-probe="httpGet.path=/api/health,httpGet.port=3000,initialDelaySeconds=2,periodSeconds=3,timeoutSeconds=3,failureThreshold=20" \
  --liveness-probe="httpGet.path=/api/health,httpGet.port=3000,periodSeconds=30,timeoutSeconds=5,failureThreshold=3" \
  "${web_auth_flag}" >/dev/null

WEB_URL="$(service_url "${WEB_SERVICE}")"
[[ -n "${WEB_URL}" ]] || die "could not read the web service URL"
ok "Web deployed: ${WEB_URL}"

# =============================================================================
# 5. Wire the real URLs back into the API
# =============================================================================
# Cloud Run assigns the hostname, so CORS and the public base URL can only be
# set correctly after both services exist. This creates one extra API revision
# on a first deploy and is a no-op on subsequent runs.
# =============================================================================
banner "Cross-wiring URLs"

PUBLIC_BASE_URL="${AGROTECH_PUBLIC_BASE_URL:-${API_URL}}"

# The frontend's own origin always belongs in the allow-list. EXTRA_CORS_ORIGINS
# covers custom domains and preview deployments.
CORS_ORIGINS="$(join_by ',' "${WEB_URL}" "${EXTRA_CORS_ORIGINS}")"

info "AGROTECH_PUBLIC_BASE_URL = ${PUBLIC_BASE_URL}"
info "AGROTECH_CORS_ORIGINS    = ${CORS_ORIGINS}"

gc run services update "${API_SERVICE}" \
  --region="${REGION}" \
  --update-env-vars="^@^AGROTECH_PUBLIC_BASE_URL=${PUBLIC_BASE_URL}@AGROTECH_CORS_ORIGINS=${CORS_ORIGINS}" >/dev/null
ok "API CORS + public base URL updated"

# =============================================================================
# 6. Service-to-service authorisation
# =============================================================================
banner "Service-to-service IAM"

if [[ "${API_ALLOW_UNAUTHENTICATED}" == "true" ]]; then
  warn "the API is PUBLIC (API_ALLOW_UNAUTHENTICATED=true)."
  warn "Anyone can call it directly. Keep AGROTECH_REQUIRE_WRITE_AUTH=true, or"
  warn "set API_ALLOW_UNAUTHENTICATED=false so only the frontend can reach it."
else
  # Scoped to this one service, not the project: the web identity gains the
  # right to invoke the API and nothing else in Cloud Run.
  gc run services add-iam-policy-binding "${API_SERVICE}" \
    --region="${REGION}" \
    --member="serviceAccount:${WEB_SA_EMAIL}" \
    --role="roles/run.invoker" >/dev/null
  ok "${WEB_SA_EMAIL} may invoke ${API_SERVICE}"
  info "The /api/ml route handler must attach a Google-signed ID token whose"
  info "audience is ${API_URL}. On Cloud Run it can fetch one from the metadata"
  info "server at:"
  dim  "  http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience=${API_URL}"
  dim  "  (header: Metadata-Flavor: Google)"
fi

if [[ "${WEB_ALLOW_UNAUTHENTICATED}" == "true" ]]; then
  gc run services add-iam-policy-binding "${WEB_SERVICE}" \
    --region="${REGION}" \
    --member="allUsers" \
    --role="roles/run.invoker" >/dev/null
  ok "${WEB_SERVICE} is publicly reachable"
fi

# =============================================================================
# 7. Smoke test
# =============================================================================
banner "Smoke test"

if command -v curl >/dev/null 2>&1; then
  if [[ "${WEB_ALLOW_UNAUTHENTICATED}" == "true" ]]; then
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "${WEB_URL}/api/health" || echo 000)"
    if [[ "${code}" == "200" ]]; then
      ok "GET ${WEB_URL}/api/health -> 200"
    else
      warn "GET ${WEB_URL}/api/health -> ${code}"
    fi
  fi

  if [[ "${API_ALLOW_UNAUTHENTICATED}" == "true" ]]; then
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 "${API_URL}/health" || echo 000)"
  else
    # Private service: authenticate with the operator's own identity token.
    token="$(gcloud auth print-identity-token 2>/dev/null || echo '')"
    if [[ -n "${token}" ]]; then
      code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 60 \
               -H "Authorization: Bearer ${token}" "${API_URL}/health" || echo 000)"
    else
      code="skipped"
    fi
  fi
  case "${code}" in
    200)     ok "GET ${API_URL}/health -> 200" ;;
    403|401) warn "GET ${API_URL}/health -> ${code} (expected for a private service unless your account has run.invoker)" ;;
    skipped) skip "no identity token available; skipping the API probe" ;;
    *)       warn "GET ${API_URL}/health -> ${code}. Check: gcloud run services logs read ${API_SERVICE} --region ${REGION}" ;;
  esac
else
  skip "curl not installed; skipping smoke test"
fi

# =============================================================================
banner "Deployed"

cat <<SUMMARY
  Frontend   ${WEB_URL}
  API        ${API_URL}
  Image tag  ${IMAGE_TAG}

  Logs
    gcloud run services logs read ${API_SERVICE} --region ${REGION} --project ${PROJECT_ID}
    gcloud run services logs read ${WEB_SERVICE} --region ${REGION} --project ${PROJECT_ID}

  Upload trained models so the API can load them:
    gcloud storage cp <artifacts>/*.joblib gs://${MODELS_BUCKET}/artifacts/
    gcloud storage cp <artifacts>/model_metadata.json gs://${MODELS_BUCKET}/artifacts/

  Next (optional): ./deploy/40-satellite-job.sh
SUMMARY
