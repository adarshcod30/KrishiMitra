#!/usr/bin/env bash
# =============================================================================
# 00 — Enable the Google Cloud APIs the KrishiMitra deployment needs.
#
#   ./deploy/00-enable-apis.sh
#
# Idempotent: `gcloud services enable` on an already-enabled service is a no-op.
# Safe: enabling an API costs nothing by itself and this script creates no
# resources and deletes nothing.
#
# Run once per project, before 10-provision.sh. Newly enabled APIs can take
# 1-2 minutes to become usable — if the next script reports "API not enabled",
# wait a moment and retry rather than re-running this one.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

load_env
require_cmd gcloud
require_project

# -----------------------------------------------------------------------------
# Required. Every one of these is load-bearing for some part of the deployment;
# the comment says which part, so nobody has to guess later whether an API can
# be turned back off.
# -----------------------------------------------------------------------------
REQUIRED_APIS=(
  cloudresourcemanager.googleapis.com  # read/modify project IAM policy
  serviceusage.googleapis.com          # enable other APIs; also the permission
                                       # Earth Engine clients need at runtime
  iam.googleapis.com                   # create service accounts
  iamcredentials.googleapis.com        # SA impersonation + token minting
  artifactregistry.googleapis.com      # Docker image registry
  cloudbuild.googleapis.com            # build the three images
  run.googleapis.com                   # API + web services, migrate + satellite jobs
  sqladmin.googleapis.com              # Cloud SQL for PostgreSQL
  secretmanager.googleapis.com         # JWT secret, DB password, third-party keys
  storage.googleapis.com               # models bucket, uploads bucket, build source
  logging.googleapis.com               # request + application logs
  monitoring.googleapis.com            # Cloud Run built-in metrics, alerting
)

# -----------------------------------------------------------------------------
# Feature-specific. Enabled by default because the full deployment uses them,
# but listed separately so a minimal API-only deployment can skip them with
# SKIP_OPTIONAL_APIS=1.
# -----------------------------------------------------------------------------
OPTIONAL_APIS=(
  cloudscheduler.googleapis.com        # weekly trigger for the satellite job
  earthengine.googleapis.com           # Sentinel-1/2 ingestion (satellite-ml)
  compute.googleapis.com               # underlying networking for Cloud SQL
  cloudtrace.googleapis.com            # latency traces from Cloud Run
  containerscanning.googleapis.com     # Artifact Registry vulnerability scanning
)

print_plan_header "Enable Google Cloud APIs"

info "This script will ENABLE the following services on ${PROJECT_ID}:"
printf '\n'
for api in "${REQUIRED_APIS[@]}"; do dim "required  ${api}"; done
if [[ "${SKIP_OPTIONAL_APIS:-0}" != "1" ]]; then
  for api in "${OPTIONAL_APIS[@]}"; do dim "optional  ${api}"; done
fi
printf '\n'
info "It will not create, modify or delete any resource."
printf '\n'

confirm "Enable these APIs on ${PROJECT_ID}?" || die "aborted"

log "Enabling required APIs (this can take a couple of minutes)"
# One call so the API-enablement operations run concurrently server-side.
gc services enable "${REQUIRED_APIS[@]}"
ok "required APIs enabled"

if [[ "${SKIP_OPTIONAL_APIS:-0}" == "1" ]]; then
  skip "SKIP_OPTIONAL_APIS=1 — skipping optional APIs"
else
  log "Enabling optional APIs"
  for api in "${OPTIONAL_APIS[@]}"; do
    # Enabled one at a time: earthengine.googleapis.com in particular fails on
    # projects that have not been registered for Earth Engine, and a batch call
    # would take the whole set down with it.
    if gc services enable "${api}" 2>/dev/null; then
      ok "${api}"
    else
      warn "could not enable ${api}"
      if [[ "${api}" == "earthengine.googleapis.com" ]]; then
        warn "  Earth Engine requires the Cloud project to be REGISTERED first."
        warn "  Register ${PROJECT_ID} at https://console.cloud.google.com/earth-engine"
        warn "  then re-run this script. Everything except the satellite job"
        warn "  works fine without it."
      fi
    fi
  done
fi

printf '\n'
log "Currently enabled services on ${PROJECT_ID}"
gc services list --enabled --format='table(config.name, config.title)' \
  | grep -Ei 'run|sql|secret|artifact|build|storage|scheduler|earthengine' || true

printf '\n'
ok "Done. Next: ./deploy/10-provision.sh"
