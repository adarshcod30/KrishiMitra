#!/usr/bin/env bash
# =============================================================================
# Shared helpers for the deploy/*.sh scripts.
#
# Sourced, never executed:   source "$(dirname "$0")/lib/common.sh"
#
# Everything here is idempotent-by-construction: `ensure_*` helpers describe
# first and only create when the resource is absent, so re-running any script
# converges rather than erroring or duplicating.
# =============================================================================

# Guard against double-sourcing.
if [[ -n "${KM_COMMON_SH_LOADED:-}" ]]; then
  return 0
fi
KM_COMMON_SH_LOADED=1

# -----------------------------------------------------------------------------
# Output helpers. Colour only when stdout is a terminal, so Cloud Build and
# CI logs stay free of escape sequences.
# -----------------------------------------------------------------------------
if [[ -t 1 ]]; then
  _C_RESET=$'\033[0m'; _C_BOLD=$'\033[1m'; _C_DIM=$'\033[2m'
  _C_RED=$'\033[31m'; _C_GREEN=$'\033[32m'; _C_YELLOW=$'\033[33m'; _C_BLUE=$'\033[34m'
else
  _C_RESET=''; _C_BOLD=''; _C_DIM=''
  _C_RED=''; _C_GREEN=''; _C_YELLOW=''; _C_BLUE=''
fi

log()   { printf '%s==>%s %s\n' "${_C_BLUE}${_C_BOLD}" "${_C_RESET}" "$*"; }
info()  { printf '    %s\n' "$*"; }
dim()   { printf '%s    %s%s\n' "${_C_DIM}" "$*" "${_C_RESET}"; }
ok()    { printf '%s  ✓%s %s\n' "${_C_GREEN}" "${_C_RESET}" "$*"; }
skip()  { printf '%s  ·%s %s\n' "${_C_DIM}" "${_C_RESET}" "$*"; }
warn()  { printf '%s  !%s %s\n' "${_C_YELLOW}" "${_C_RESET}" "$*" >&2; }
die()   { printf '%s  ✗ ERROR:%s %s\n' "${_C_RED}${_C_BOLD}" "${_C_RESET}" "$*" >&2; exit 1; }

banner() {
  printf '\n%s%s%s\n' "${_C_BOLD}" "$*" "${_C_RESET}"
  printf '%s%s%s\n' "${_C_DIM}" "$(printf '%.0s-' $(seq 1 ${#1}))" "${_C_RESET}"
}

# -----------------------------------------------------------------------------
# Preconditions
# -----------------------------------------------------------------------------
require_cmd() {
  local cmd
  for cmd in "$@"; do
    command -v "${cmd}" >/dev/null 2>&1 \
      || die "required command not found on PATH: ${cmd}"
  done
}

require_var() {
  local name
  for name in "$@"; do
    if [[ -z "${!name:-}" ]]; then
      die "${name} is not set. Fill it in ${DEPLOY_ENV_FILE:-deploy/env} (copy from deploy/env.example)."
    fi
  done
}

# -----------------------------------------------------------------------------
# Configuration loading
# -----------------------------------------------------------------------------
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${DEPLOY_DIR}/.." && pwd)"
export DEPLOY_DIR REPO_ROOT

load_env() {
  local env_file="${DEPLOY_ENV_FILE:-${DEPLOY_DIR}/env}"

  # Values already exported in the caller's shell win over an empty entry in the
  # file, so `PROJECT_ID=foo ./deploy/10-provision.sh` works for one-off runs
  # and for CI where the config lives in the pipeline rather than on disk.
  local preset_project="${PROJECT_ID:-}"

  if [[ -f "${env_file}" ]]; then
    # `set -a` exports everything the file assigns, so child gcloud processes
    # and the other scripts see it without a second export list.
    set -a
    # The path is intentionally dynamic (DEPLOY_ENV_FILE), so shellcheck cannot
    # follow it.
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
    DEPLOY_ENV_FILE="${env_file}"
  else
    warn "no config file at ${env_file}; falling back to the current environment"
    warn "create one with:  cp ${DEPLOY_DIR}/env.example ${env_file}"
  fi

  if [[ -z "${PROJECT_ID:-}" && -n "${preset_project}" ]]; then
    PROJECT_ID="${preset_project}"
  fi
  require_var PROJECT_ID

  # Defaults for anything the operator left out, so a minimal env file with just
  # PROJECT_ID still produces a complete, working deployment.
  : "${REGION:=asia-south1}"
  : "${BUCKET_LOCATION:=${REGION}}"
  : "${SCHEDULER_REGION:=${REGION}}"

  : "${AR_REPO:=krishimitra}"
  : "${API_SERVICE:=krishimitra-api}"
  : "${WEB_SERVICE:=krishimitra-web}"
  : "${MIGRATE_JOB:=krishimitra-migrate}"
  : "${SATELLITE_JOB:=krishimitra-satellite}"
  : "${SATELLITE_SCHEDULE_NAME:=krishimitra-satellite-weekly}"

  : "${SQL_INSTANCE:=krishimitra-pg}"
  : "${SQL_DB:=agrotech}"
  : "${SQL_USER:=agrotech}"
  : "${SQL_VERSION:=POSTGRES_17}"
  : "${SQL_TIER:=db-g1-small}"
  : "${SQL_STORAGE_TYPE:=PD_HDD}"
  : "${SQL_STORAGE_SIZE_GB:=10}"
  : "${SQL_AVAILABILITY:=zonal}"
  : "${SQL_BACKUP_START_TIME:=18:00}"

  # Bucket names are globally unique, so they carry the project id.
  : "${MODELS_BUCKET:=${PROJECT_ID}-krishimitra-models}"
  : "${UPLOADS_BUCKET:=${PROJECT_ID}-krishimitra-uploads}"
  : "${SATELLITE_BUCKET:=${PROJECT_ID}-krishimitra-satellite}"

  : "${API_SA:=krishimitra-api}"
  : "${WEB_SA:=krishimitra-web}"
  : "${SATELLITE_SA:=krishimitra-satellite}"
  : "${SCHEDULER_SA:=krishimitra-scheduler}"
  : "${BUILD_SA:=krishimitra-build}"

  : "${API_CPU:=2}";        : "${API_MEMORY:=2Gi}"
  : "${API_MIN_INSTANCES:=0}"; : "${API_MAX_INSTANCES:=5}"
  : "${API_CONCURRENCY:=20}";  : "${API_TIMEOUT:=300}"

  : "${WEB_CPU:=1}";        : "${WEB_MEMORY:=512Mi}"
  : "${WEB_MIN_INSTANCES:=0}"; : "${WEB_MAX_INSTANCES:=5}"
  : "${WEB_CONCURRENCY:=80}";  : "${WEB_TIMEOUT:=60}"

  : "${SATELLITE_CPU:=2}";  : "${SATELLITE_MEMORY:=4Gi}"
  : "${SATELLITE_TASK_TIMEOUT:=3600s}"
  : "${SATELLITE_MAX_RETRIES:=1}"
  : "${SATELLITE_CRON:=30 2 * * 1}"
  : "${SATELLITE_TIMEZONE:=Asia/Kolkata}"
  : "${SATELLITE_ARGS:=--source,simulate}"
  : "${SATELLITE_EXTRAS:=gee}"

  : "${EE_PROJECT:=${PROJECT_ID}}"
  : "${EE_USE_KEY:=false}"

  : "${AGROTECH_ENVIRONMENT:=production}"
  : "${AGROTECH_REQUIRE_WRITE_AUTH:=true}"
  : "${AGROTECH_ADMIN_USERNAME:=admin}"
  : "${NEXT_PUBLIC_ML_API_URL:=/api/ml}"
  : "${EXTRA_CORS_ORIGINS:=}"
  : "${AGROTECH_PUBLIC_BASE_URL:=}"

  : "${WEB_ALLOW_UNAUTHENTICATED:=true}"
  : "${API_ALLOW_UNAUTHENTICATED:=false}"

  # Derived, used everywhere downstream.
  AR_HOST="${REGION}-docker.pkg.dev"
  IMAGE_BASE="${AR_HOST}/${PROJECT_ID}/${AR_REPO}"
  API_IMAGE="${IMAGE_BASE}/${API_SERVICE}"
  WEB_IMAGE="${IMAGE_BASE}/${WEB_SERVICE}"
  SATELLITE_IMAGE="${IMAGE_BASE}/${SATELLITE_JOB}"
  SQL_CONNECTION_NAME="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"

  API_SA_EMAIL="$(sa_email "${API_SA}")"
  WEB_SA_EMAIL="$(sa_email "${WEB_SA}")"
  SATELLITE_SA_EMAIL="$(sa_email "${SATELLITE_SA}")"
  SCHEDULER_SA_EMAIL="$(sa_email "${SCHEDULER_SA}")"
  BUILD_SA_EMAIL="$(sa_email "${BUILD_SA}")"

  export AR_HOST IMAGE_BASE API_IMAGE WEB_IMAGE SATELLITE_IMAGE SQL_CONNECTION_NAME
  export API_SA_EMAIL WEB_SA_EMAIL SATELLITE_SA_EMAIL SCHEDULER_SA_EMAIL BUILD_SA_EMAIL
}

sa_email() { printf '%s@%s.iam.gserviceaccount.com' "$1" "${PROJECT_ID}"; }

# -----------------------------------------------------------------------------
# gcloud wrapper — every call is pinned to the configured project so a stray
# `gcloud config set project` in the operator's shell can never redirect a
# deployment to the wrong place. This is the single most valuable safety rail
# in the whole script set.
# -----------------------------------------------------------------------------
gc() { gcloud --project "${PROJECT_ID}" --quiet "$@"; }

# Same, but without --quiet, for commands whose interactive output matters.
gc_loud() { gcloud --project "${PROJECT_ID}" "$@"; }

require_project() {
  require_cmd gcloud
  gcloud projects describe "${PROJECT_ID}" >/dev/null 2>&1 \
    || die "project '${PROJECT_ID}' does not exist or you lack access. Run 'gcloud auth login' and check PROJECT_ID."

  local account
  account="$(gcloud config get-value account 2>/dev/null || true)"
  [[ -n "${account}" && "${account}" != "(unset)" ]] \
    || die "no active gcloud credentials. Run: gcloud auth login"
  dim "authenticated as ${account}"
}

require_billing() {
  require_cmd gcloud
  local enabled
  enabled="$(gcloud beta billing projects describe "${PROJECT_ID}" \
              --format='value(billingEnabled)' 2>/dev/null || echo '')"
  if [[ "${enabled}" != "True" ]]; then
    warn "billing does not appear to be enabled on ${PROJECT_ID}."
    warn "Cloud Run, Cloud SQL and Artifact Registry all require it. Link an account with:"
    warn "  gcloud billing projects link ${PROJECT_ID} --billing-account=\$BILLING_ACCOUNT"
    confirm "Continue anyway?" || die "aborted"
  fi
}

# -----------------------------------------------------------------------------
# Confirmation. Destructive or costly steps route through this.
#
# Non-interactive runs (CI) must set ASSUME_YES=1 explicitly — defaulting to
# "yes" when there is no TTY is how automation deletes production databases.
# -----------------------------------------------------------------------------
confirm() {
  local prompt="${1:-Continue?}"
  if [[ "${ASSUME_YES:-0}" == "1" ]]; then
    dim "${prompt} [auto-yes]"
    return 0
  fi
  if [[ ! -t 0 ]]; then
    warn "${prompt}"
    die "no TTY to confirm on. Re-run with ASSUME_YES=1 if this is intentional."
  fi
  local reply
  read -r -p "${_C_YELLOW}?${_C_RESET} ${prompt} [y/N] " reply
  [[ "${reply}" =~ ^[Yy]$ ]]
}

# -----------------------------------------------------------------------------
# Plan printing — every script echoes exactly what it is about to touch before
# it touches anything, so an operator can Ctrl-C on a wrong project id.
# -----------------------------------------------------------------------------
print_plan_header() {
  banner "$1"
  info "project        ${PROJECT_ID}"
  info "region         ${REGION}"
  info "config         ${DEPLOY_ENV_FILE:-<environment>}"
  printf '\n'
}

# -----------------------------------------------------------------------------
# Idempotent resource helpers
# -----------------------------------------------------------------------------

# ensure_service_account <id> <display-name> <description>
ensure_service_account() {
  local sa_id="$1" display="$2" description="$3"
  local email; email="$(sa_email "${sa_id}")"
  if gc iam service-accounts describe "${email}" >/dev/null 2>&1; then
    skip "service account ${email} exists"
  else
    gc iam service-accounts create "${sa_id}" \
      --display-name="${display}" \
      --description="${description}" >/dev/null
    ok "created service account ${email}"
  fi
}

# ensure_project_role <member-email> <role>
# add-iam-policy-binding is inherently idempotent (re-adding an existing binding
# is a no-op), but the describe-first check keeps the log readable and avoids
# needlessly bumping the policy etag.
ensure_project_role() {
  local member="$1" role="$2"
  if gcloud projects get-iam-policy "${PROJECT_ID}" \
       --flatten='bindings[].members' \
       --filter="bindings.role=${role} AND bindings.members=serviceAccount:${member}" \
       --format='value(bindings.role)' 2>/dev/null | grep -q .; then
    skip "${member} already has ${role}"
  else
    gc projects add-iam-policy-binding "${PROJECT_ID}" \
      --member="serviceAccount:${member}" \
      --role="${role}" \
      --condition=None >/dev/null
    ok "granted ${role} to ${member}"
  fi
}

# ensure_bucket_role <bucket> <member-email> <role>
# Bucket-level bindings, not project-level: this is what keeps "read the models"
# and "write the uploads" from collapsing into one broad storage.admin grant.
ensure_bucket_role() {
  local bucket="$1" member="$2" role="$3"
  gc storage buckets add-iam-policy-binding "gs://${bucket}" \
    --member="serviceAccount:${member}" \
    --role="${role}" >/dev/null
  ok "granted ${role} on gs://${bucket} to ${member}"
}

# ensure_secret_accessor <secret-name> <member-email>
ensure_secret_accessor() {
  local secret="$1" member="$2"
  gc secrets add-iam-policy-binding "${secret}" \
    --member="serviceAccount:${member}" \
    --role="roles/secretmanager.secretAccessor" >/dev/null
  ok "granted secretAccessor on ${secret} to ${member}"
}

# secret_exists <name>
secret_exists() { gc secrets describe "$1" >/dev/null 2>&1; }

# service_url <cloud-run-service-name> — empty string if not deployed yet.
service_url() {
  gc run services describe "$1" --region "${REGION}" \
    --format='value(status.url)' 2>/dev/null || true
}

# join_by <delimiter> <items...>
join_by() {
  local delim="$1"; shift
  local out=""
  local item
  for item in "$@"; do
    [[ -z "${item}" ]] && continue
    if [[ -z "${out}" ]]; then out="${item}"; else out="${out}${delim}${item}"; fi
  done
  printf '%s' "${out}"
}
