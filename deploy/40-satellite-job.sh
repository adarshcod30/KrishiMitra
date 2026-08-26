#!/usr/bin/env bash
# =============================================================================
# 40 — Deploy satellite-ml as a Cloud Run JOB and schedule it.
#
#   ./deploy/40-satellite-job.sh                 # build, deploy, schedule
#   ./deploy/40-satellite-job.sh --skip-build
#   ./deploy/40-satellite-job.sh --no-schedule   # deploy the job, no cron
#   ./deploy/40-satellite-job.sh --run-now       # deploy, then execute once
#
# A Cloud Run JOB rather than a service, because the pipeline is a batch: it
# ingests a season of Sentinel-1/2 imagery, classifies crops, computes moisture
# stress and FAO-56 irrigation advisories, writes maps and tables, and exits.
# It has no HTTP surface, so a service would be the wrong shape (and would be
# billed for an idle container).
#
# The image is built from satellite-ml/Dockerfile, which is owned by the
# satellite-ml module — this script does not define its own. That Dockerfile
# already handles Earth Engine credentials (EE_SERVICE_ACCOUNT_JSON as raw JSON
# or a file path, EE_PROJECT, ADC fallback) inside the application, so there is
# no credential wrapper here either.
#
# Outputs: the job mounts gs://${SATELLITE_BUCKET} at /app/outputs through a
# Cloud Run Cloud Storage volume, so maps, figures and advisory tables are
# written straight to GCS with no upload step and no extra dependency. The
# bucket is versioned, so each week's products supersede the previous ones
# without destroying them.
#
# Optional. Skipping this leaves the rest of the platform fully functional.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

load_env
require_cmd gcloud
require_project

SKIP_BUILD=0
DO_SCHEDULE=1
RUN_NOW=0
IMAGE_TAG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-build)  SKIP_BUILD=1; shift ;;
    --no-schedule) DO_SCHEDULE=0; shift ;;
    --run-now)     RUN_NOW=1; shift ;;
    --tag)         IMAGE_TAG="${2:?--tag needs a value}"; shift 2 ;;
    -h|--help)     sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *)             die "unknown argument: $1" ;;
  esac
done

if [[ -z "${IMAGE_TAG}" ]]; then
  if git -C "${REPO_ROOT}" rev-parse --git-dir >/dev/null 2>&1; then
    IMAGE_TAG="$(git -C "${REPO_ROOT}" rev-parse --short=12 HEAD)"
  else
    IMAGE_TAG="$(date -u +%Y%m%d%H%M%S)"
  fi
fi

SATELLITE_DIR="${REPO_ROOT}/satellite-ml"
SATELLITE_DOCKERFILE="${SATELLITE_DIR}/Dockerfile"

# Name for the volume, referenced by both --add-volume and --add-volume-mount.
OUTPUTS_VOLUME="satellite-outputs"

# Cloud Run Jobs v2 REST endpoint. Cloud Scheduler calls this as a Google API,
# which is why the authentication below is OAuth and not OIDC — OIDC is for
# calling your own services, OAuth is for calling *.googleapis.com.
JOB_RUN_URI="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${SATELLITE_JOB}:run"

print_plan_header "Satellite pipeline — Cloud Run Job"

cat <<PLAN
  dockerfile   satellite-ml/Dockerfile   (owned by the satellite-ml module)
  extras       ${SATELLITE_EXTRAS}
  image        ${SATELLITE_IMAGE}:${IMAGE_TAG}
  job          ${SATELLITE_JOB}   (${REGION})
  identity     ${SATELLITE_SA_EMAIL}
  resources    ${SATELLITE_CPU} vCPU / ${SATELLITE_MEMORY}, timeout ${SATELLITE_TASK_TIMEOUT}, retries ${SATELLITE_MAX_RETRIES}
  args         ${SATELLITE_ARGS}
  outputs      gs://${SATELLITE_BUCKET} mounted at /app/outputs
  Earth Engine project ${EE_PROJECT}, key mode: $( [[ "${EE_USE_KEY}" == "true" ]] && echo "Secret Manager JSON key" || echo "Workload Identity (recommended)" )
PLAN

if [[ "${DO_SCHEDULE}" == "1" ]]; then
  cat <<PLAN
  schedule     ${SATELLITE_SCHEDULE_NAME}  "${SATELLITE_CRON}"  ${SATELLITE_TIMEZONE}
               via ${SCHEDULER_SA_EMAIL} -> POST ${JOB_RUN_URI}
PLAN
fi
printf '\n'

confirm "Deploy the satellite job to ${PROJECT_ID}?" || die "aborted"

# =============================================================================
# 1. Preflight
# =============================================================================
banner "Preflight"

[[ -f "${SATELLITE_DOCKERFILE}" ]] \
  || die "satellite-ml/Dockerfile is missing. This script builds the image the satellite-ml module defines; it does not define its own."
ok "found satellite-ml/Dockerfile"

gc iam service-accounts describe "${SATELLITE_SA_EMAIL}" >/dev/null 2>&1 \
  || die "service account ${SATELLITE_SA_EMAIL} is missing. Run ./deploy/10-provision.sh."
ok "satellite service account exists"

gc storage buckets describe "gs://${SATELLITE_BUCKET}" >/dev/null 2>&1 \
  || die "bucket gs://${SATELLITE_BUCKET} is missing. Run ./deploy/10-provision.sh."
ok "outputs bucket gs://${SATELLITE_BUCKET} exists"

# GeoTIFF writers seek within a file; gcsfuse does not support random writes.
# The pipeline falls back to PNG + .npy when rasterio is absent, which is
# append-only and safe over a mounted bucket.
if [[ "${SATELLITE_EXTRAS}" == *"geo"* ]]; then
  warn "SATELLITE_EXTRAS includes 'geo', which installs rasterio."
  warn "GeoTIFF output performs random writes, which the Cloud Storage volume"
  warn "mount (gcsfuse) does not support. Either drop 'geo', or set"
  warn "output.save_geotiff: false in satellite-ml/config/pilot_area.yaml."
  confirm "Continue anyway?" || die "aborted"
fi

if [[ "${SATELLITE_ARGS}" == *"gee"* ]]; then
  # Only the real-imagery path needs Earth Engine; --source simulate runs
  # entirely offline and is the default.
  if gc services list --enabled --format='value(config.name)' | grep -qx 'earthengine.googleapis.com'; then
    ok "earthengine.googleapis.com is enabled"
  else
    warn "SATELLITE_ARGS requests the Earth Engine data source, but"
    warn "earthengine.googleapis.com is not enabled on ${PROJECT_ID}."
    warn "Register the project at https://console.cloud.google.com/earth-engine"
    warn "and re-run ./deploy/00-enable-apis.sh, or set SATELLITE_ARGS=--source,simulate."
    confirm "Deploy anyway (the job will fail at ingestion time)?" || die "aborted"
  fi

  if [[ "${EE_USE_KEY}" == "true" ]]; then
    secret_exists ee-service-account-json \
      || die "EE_USE_KEY=true but the secret 'ee-service-account-json' does not exist. Run ./deploy/20-secrets.sh."
    ok "Earth Engine key secret present"
  else
    info "Earth Engine will authenticate as ${SATELLITE_SA_EMAIL} via ADC."
    info "That service account needs roles/earthengine.writer and"
    info "roles/serviceusage.serviceUsageConsumer (granted by 10-provision.sh)."
  fi
else
  skip "SATELLITE_ARGS uses the offline simulator; Earth Engine not required"
fi

# =============================================================================
# 2. Build
# =============================================================================
if [[ "${SKIP_BUILD}" == "1" ]]; then
  banner "Build (skipped)"
  skip "--skip-build: reusing ${SATELLITE_IMAGE}:${IMAGE_TAG}"
else
  banner "Build"

  # Built from the satellite-ml/ directory, so satellite-ml/.dockerignore
  # applies and the Node/ml-service trees never enter the context.
  cfg="$(mktemp "${TMPDIR:-/tmp}/km-sat-build-XXXXXX.yaml")"
  cat > "${cfg}" <<YAML
steps:
  - name: 'gcr.io/cloud-builders/docker'
    id: 'build-satellite'
    args:
      - 'build'
      - '-f'
      - 'Dockerfile'
      - '--build-arg'
      - 'EXTRAS=${SATELLITE_EXTRAS}'
      - '-t'
      - '${SATELLITE_IMAGE}:${IMAGE_TAG}'
      - '-t'
      - '${SATELLITE_IMAGE}:latest'
      - '.'
images:
  - '${SATELLITE_IMAGE}:${IMAGE_TAG}'
  - '${SATELLITE_IMAGE}:latest'
options:
  machineType: 'E2_HIGHCPU_8'
  logging: CLOUD_LOGGING_ONLY
timeout: '2400s'
YAML

  log "Building the satellite image (the gee extra is large; allow ~10 minutes)"
  gc builds submit "${SATELLITE_DIR}" \
    --config="${cfg}" \
    --service-account="projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA_EMAIL}" \
    --gcs-source-staging-dir="gs://${PROJECT_ID}_cloudbuild/source" \
    --region="${REGION}"
  rm -f "${cfg}"
  ok "satellite image pushed"
fi

# =============================================================================
# 3. Deploy the job
# =============================================================================
banner "Cloud Run Job"

JOB_ENV_PAIRS=(
  "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  "EE_PROJECT=${EE_PROJECT}"
  "MPLBACKEND=Agg"
)

job_secret_flag=()
if [[ "${EE_USE_KEY}" == "true" ]] && secret_exists ee-service-account-json; then
  # The application accepts either raw JSON or a path here; --set-secrets
  # delivers the raw JSON.
  job_secret_flag=(--set-secrets="EE_SERVICE_ACCOUNT_JSON=ee-service-account-json:latest")
fi

# --tasks 1 / --parallelism 1: one pilot area per execution. Scale to a task per
# command area later with --tasks N and CLOUD_RUN_TASK_INDEX inside the config.
#
# The Cloud Storage volume needs the second-generation execution environment;
# gen1 has no FUSE support.
gc run jobs deploy "${SATELLITE_JOB}" \
  --image="${SATELLITE_IMAGE}:${IMAGE_TAG}" \
  --region="${REGION}" \
  --service-account="${SATELLITE_SA_EMAIL}" \
  --cpu="${SATELLITE_CPU}" \
  --memory="${SATELLITE_MEMORY}" \
  --task-timeout="${SATELLITE_TASK_TIMEOUT}" \
  --max-retries="${SATELLITE_MAX_RETRIES}" \
  --tasks=1 \
  --parallelism=1 \
  --execution-environment=gen2 \
  --labels="app=krishimitra,component=satellite" \
  --set-env-vars="^@^$(join_by '@' "${JOB_ENV_PAIRS[@]}")" \
  --args="${SATELLITE_ARGS}" \
  --add-volume="name=${OUTPUTS_VOLUME},type=cloud-storage,bucket=${SATELLITE_BUCKET}" \
  --add-volume-mount="volume=${OUTPUTS_VOLUME},mount-path=/app/outputs" \
  "${job_secret_flag[@]:-}" >/dev/null
ok "job ${SATELLITE_JOB} deployed at ${IMAGE_TAG}"
ok "gs://${SATELLITE_BUCKET} mounted at /app/outputs"

# =============================================================================
# 4. Schedule
# =============================================================================
if [[ "${DO_SCHEDULE}" == "0" ]]; then
  banner "Schedule (skipped)"
  skip "--no-schedule"
else
  banner "Cloud Scheduler"

  # Scoped to this single job: the scheduler identity can run the satellite
  # pipeline and nothing else in Cloud Run.
  gc run jobs add-iam-policy-binding "${SATELLITE_JOB}" \
    --region="${REGION}" \
    --member="serviceAccount:${SCHEDULER_SA_EMAIL}" \
    --role="roles/run.invoker" >/dev/null
  ok "${SCHEDULER_SA_EMAIL} may execute ${SATELLITE_JOB}"

  # --oauth-service-account-email (not --oidc-*): the target is a Google API
  # endpoint (run.googleapis.com), which expects an OAuth access token.
  # --attempt-deadline bounds the :run REQUEST, not the job. :run returns as
  # soon as the execution is created, so 5 minutes is generous.
  scheduler_args=(
    --location="${SCHEDULER_REGION}"
    --schedule="${SATELLITE_CRON}"
    --time-zone="${SATELLITE_TIMEZONE}"
    --uri="${JOB_RUN_URI}"
    --http-method=POST
    --oauth-service-account-email="${SCHEDULER_SA_EMAIL}"
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
    --attempt-deadline=300s
    --max-retry-attempts=1
    --description="Weekly KrishiMitra satellite crop/moisture pipeline"
  )

  if gc scheduler jobs describe "${SATELLITE_SCHEDULE_NAME}" \
       --location="${SCHEDULER_REGION}" >/dev/null 2>&1; then
    gc scheduler jobs update http "${SATELLITE_SCHEDULE_NAME}" "${scheduler_args[@]}" >/dev/null
    ok "updated schedule ${SATELLITE_SCHEDULE_NAME}"
  else
    gc scheduler jobs create http "${SATELLITE_SCHEDULE_NAME}" "${scheduler_args[@]}" >/dev/null
    ok "created schedule ${SATELLITE_SCHEDULE_NAME}: ${SATELLITE_CRON} (${SATELLITE_TIMEZONE})"
  fi
fi

# =============================================================================
# 5. Optional immediate run
# =============================================================================
if [[ "${RUN_NOW}" == "1" ]]; then
  banner "Executing now"
  log "This blocks until the pipeline finishes (up to ${SATELLITE_TASK_TIMEOUT})"
  if gc run jobs execute "${SATELLITE_JOB}" --region="${REGION}" --wait; then
    ok "execution succeeded"
    info "Outputs written to gs://${SATELLITE_BUCKET}:"
    gc storage ls "gs://${SATELLITE_BUCKET}/" 2>/dev/null | head -10 || true
  else
    warn "execution failed. Logs:"
    warn "  gcloud run jobs executions list --job=${SATELLITE_JOB} --region=${REGION} --project=${PROJECT_ID}"
    warn "  gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=${SATELLITE_JOB}' --limit=50 --project=${PROJECT_ID}"
    exit 1
  fi
fi

banner "Satellite job ready"

cat <<SUMMARY
  Run on demand
    gcloud run jobs execute ${SATELLITE_JOB} --region ${REGION} --project ${PROJECT_ID} --wait

  Override the pipeline arguments for one run
    gcloud run jobs execute ${SATELLITE_JOB} --region ${REGION} --project ${PROJECT_ID} \\
      --args=--source,gee --wait

  Watch logs
    gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=${SATELLITE_JOB}' \\
      --limit=100 --project ${PROJECT_ID}

  Outputs (written straight into the bucket by the volume mount)
    gcloud storage ls -r gs://${SATELLITE_BUCKET}/
    gcloud storage cp gs://${SATELLITE_BUCKET}/maps/crop_map.png .

  Recover a previous week's products (the bucket is versioned)
    gcloud storage ls -a gs://${SATELLITE_BUCKET}/maps/crop_map.png

  Pause the schedule (does not delete it)
    gcloud scheduler jobs pause ${SATELLITE_SCHEDULE_NAME} --location ${SCHEDULER_REGION} --project ${PROJECT_ID}
SUMMARY
