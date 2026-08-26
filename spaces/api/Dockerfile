# syntax=docker/dockerfile:1.7
# =============================================================================
# KrishiMitra / AgroTech ML API — Hugging Face Space (Docker SDK)
#
# ONE Dockerfile serves two hosts, deliberately:
#
#   Hugging Face Space   build context = the Space repo root, which
#                        spaces/api/sync.sh lays out as  Dockerfile + ml-service/
#   docker compose       build context = this repository root
#                        (see docker-compose.yml: dockerfile: spaces/api/Dockerfile)
#
# Both contexts expose the same relative paths (ml-service/...), so there is a
# single image definition and no chance of the local image drifting away from
# the deployed one. There is no second root-level Dockerfile.api any more.
#
# Local smoke test (from the repository root):
#   docker build -f spaces/api/Dockerfile -t krishimitra-api .
#   docker run --rm -p 7860:7860 krishimitra-api
#   curl localhost:7860/health
#
# Hugging Face contract (https://huggingface.co/docs/hub/spaces-sdks-docker):
#   * The app must listen on the port declared as `app_port` in README.md — 7860.
#   * The container is executed with UID 1000, so the runtime user is created
#     with `useradd -m -u 1000 user` and everything it must read or write is
#     COPY'd with --chown=user.
#   * The filesystem is EPHEMERAL. Anything written under /home/user/app/uploads
#     is gone on the next restart, which is why the optional S3 backend
#     (AGROTECH_S3_*) and Neon Postgres (AGROTECH_DATABASE_URL) exist.
#   * Secrets set in Space Settings arrive as ordinary env vars at RUNTIME. None
#     of them are baked here.
#
# Design notes
#   * Two stages. The builder carries a C toolchain (some scientific wheels
#     still fall back to sdists on new CPython); the runtime carries only
#     libgomp1, which LightGBM / XGBoost dlopen at import time.
#   * Dependencies resolve into a self-contained venv at /opt/venv that is
#     copied wholesale into the runtime stage. No pip, no apt lists in the
#     final image.
#   * Model artifacts are BAKED IN (~170 MB) rather than downloaded at boot:
#     a Space cold-starts often, and a boot-time download is the difference
#     between a 20 s and a 3 min first response. See "Model artifacts" below.
# =============================================================================

ARG PYTHON_VERSION=3.13

# ---------------------------------------------------------------------------
# Stage 1 — builder: resolve and compile the Python dependency tree.
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONDONTWRITEBYTECODE=1

# build-essential: fallback compiler for any dependency without a cp313 wheel.
# This whole stage is discarded, so none of it reaches the shipped image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /build

# Extras from ml-service/pyproject.toml:
#   postgres -> psycopg[binary]   (needed whenever AGROTECH_DATABASE_URL is set)
#   s3       -> boto3             (only for the OPTIONAL S3-compatible uploads
#                                  backend: Cloudflare R2 / Supabase / MinIO)
#   cloud    -> both, as one name
# pip only WARNS on an unknown extra, so a rename in pyproject cannot break this
# build; the explicit `import` checks below are what actually guarantee the
# drivers are present.
ARG PIP_EXTRAS="postgres"

# --build-arg WITH_S3=0 drops boto3 (~50 MB) for a local-disk-only image.
ARG WITH_S3=1

# Metadata first: this layer is cached until pyproject.toml actually changes,
# so editing ml-service/src does not re-resolve the whole ML dependency tree.
COPY ml-service/pyproject.toml ml-service/README.md ./
COPY ml-service/src ./src

RUN python -m pip install --upgrade pip setuptools wheel \
 && EXTRAS="${PIP_EXTRAS}" \
 && if [ "${WITH_S3}" = "1" ]; then EXTRAS="${EXTRAS:+${EXTRAS},}s3"; fi \
 && if [ -n "${EXTRAS}" ]; then pip install ".[${EXTRAS}]"; else pip install "."; fi \
 && if ! python -c "import psycopg" 2>/dev/null; then \
        echo ">> psycopg not provided by the extras; installing it explicitly"; \
        pip install "psycopg[binary]>=3.2,<4"; \
    fi \
 && if [ "${WITH_S3}" = "1" ] && ! python -c "import boto3" 2>/dev/null; then \
        echo ">> boto3 not provided by the extras; installing it explicitly"; \
        pip install "boto3>=1.34,<2"; \
    fi \
 && python -c "import agrotech_ml, fastapi, uvicorn; print('builder import OK')"

# ---------------------------------------------------------------------------
# Train the models AT BUILD TIME from the committed dataset (random_state=42,
# pure-sklearn zoo, ~40 s). Rationale:
#   * ml-service/artifacts/ is gitignored, so a git-based build (Render, CI)
#     has no models to COPY — and the API deliberately does NOT train at
#     startup (that was removed as a security/cold-start fix; missing models
#     mean /predict returns 503 with a clear message).
#   * Builders run on full CPU; a 0.1-vCPU free dyno would take many minutes.
# The SQLite side-effect of init_db stays in /build and never ships.
# ---------------------------------------------------------------------------
COPY ml-service/data ./data
COPY ml-service/scripts ./scripts
RUN AGROTECH_ARTIFACTS_DIR=/build/artifacts \
    AGROTECH_UPLOADS_DIR=/build/uploads \
    AGROTECH_DATA_PATH=/build/data/Crop_dataset.csv \
    python -m agrotech_ml.services.train \
 && rm -f /build/artifacts/*.db /build/artifacts/*.db-wal /build/artifacts/*.db-shm \
 && ls -la /build/artifacts \
 && python -c "import json,pathlib; md=json.loads(pathlib.Path('/build/artifacts/model_metadata.json').read_text()); have={p.name for p in pathlib.Path('/build/artifacts').glob('*.joblib')}; need={'crop_model.joblib','fertilizer_model.joblib','irrigation_model.joblib','disease_model.joblib'}; assert md['best_model'] and not (need-have), f'artifact check failed: {need-have}'; print('build-time training OK: best=' + md['best_model'])"

# ---------------------------------------------------------------------------
# Stage 2 — runtime: slim, non-root, no toolchain, no package manager state.
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

# libgomp1 is the OpenMP runtime that LightGBM and XGBoost load dynamically.
# Without it `import lightgbm` fails with "libgomp.so.1: cannot open shared
# object file" — a classic slim-image production break.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# UID 1000 exactly: Hugging Face executes the container as user 1000, and a
# mismatch turns every write into EACCES. The same user works fine locally.
RUN useradd --create-home --uid 1000 user

# Root-owned and read-only to the app — nothing in the venv is ever written to.
COPY --from=builder --chown=root:root /opt/venv /opt/venv

ENV HOME=/home/user
WORKDIR /home/user/app

# Runtime data the service actually reads:
#   data/    — Crop_dataset.csv, used by /retrain and first-run training
#   scripts/ — bootstrap_datasets.py, run by operators via `docker exec`
COPY --chown=user:user ml-service/data ./data
COPY --chown=user:user ml-service/scripts ./scripts

# Model artifacts: trained during the builder stage from the committed
# dataset, so a git clone builds a fully working image with no binary blobs in
# version control. (The runtime API does not train — missing models are a hard
# 503, by design.) No *.db ships: the builder deletes its SQLite side-effect.
COPY --from=builder --chown=user:user /build/artifacts ./artifacts

# Writable state. On a Space this is EPHEMERAL — wiped on every restart and
# rebuild. Set AGROTECH_S3_* to keep uploads, AGROTECH_DATABASE_URL to keep rows.
RUN mkdir -p /home/user/app/artifacts /home/user/app/uploads \
 && chown user:user /home/user/app/artifacts /home/user/app/uploads

ENV PATH="/opt/venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 7860 is the Hugging Face default and matches `app_port` in README.md. Any
# other host that injects PORT (or `docker run -e PORT=8080`) overrides it.
ENV PORT=7860

# Real directories inside the image, created above. The contract requires
# AGROTECH_ARTIFACTS_DIR to be a real directory, never a symlink out of tree.
ENV AGROTECH_ARTIFACTS_DIR=/home/user/app/artifacts
ENV AGROTECH_UPLOADS_DIR=/home/user/app/uploads
ENV AGROTECH_DATA_PATH=/home/user/app/data/Crop_dataset.csv

# Deliberately NOT set here: AGROTECH_ENVIRONMENT, AGROTECH_DATABASE_URL,
# AGROTECH_JWT_SECRET, AGROTECH_CORS_ORIGINS, AGROTECH_S3_*, AGROTECH_*_API_KEY.
# Baking `production` in would make the image unrunnable without secrets and
# break local smoke tests. They arrive from Space secrets / compose env.

USER user

EXPOSE 7860

# Container-level probe for docker compose. Hugging Face ignores HEALTHCHECK and
# decides readiness by polling app_port itself, so this is written with the
# interpreter already in the image rather than by adding curl and its libs.
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','7860'), timeout=4)"]

# `exec` so uvicorn becomes PID 1 and receives SIGTERM directly, giving it the
# full shutdown window to drain in-flight requests.
# --proxy-headers / --forwarded-allow-ips: the Space (and any other host)
# terminates TLS upstream and forwards X-Forwarded-Proto; without these,
# generated absolute URLs come out as http://.
# WEB_CONCURRENCY defaults to 1: each worker re-loads the ensembles at ~200 MB.
CMD ["sh", "-c", "exec uvicorn agrotech_ml.api:app --host 0.0.0.0 --port \"${PORT:-7860}\" --workers \"${WEB_CONCURRENCY:-1}\" --timeout-keep-alive 65 --proxy-headers --forwarded-allow-ips '*'"]
