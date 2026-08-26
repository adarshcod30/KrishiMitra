# =============================================================================
# KrishiMitra-RS satellite pipeline — portable BATCH container
#
# This is a run-to-completion job, not a service: it runs the season end to end,
# writes maps/figures/tables under /app/outputs and exits. There is no HTTP
# listener and no $PORT, so it runs anywhere a container runs — a laptop, CI, a
# cron host, or any batch/job runner — with no host-specific assumptions.
#
#   docker build -t krishimitra-satellite satellite-ml/
#   docker run --rm krishimitra-satellite                        # simulated pilot
#   docker run --rm -v "$PWD/outputs:/app/outputs" \
#              -e EE_SERVICE_ACCOUNT_JSON="$(cat key.json)" \
#              -e EE_PROJECT=my-earthengine-project \
#              krishimitra-satellite --source gee                # real Sentinel-1/2
#
# Or through the repo's compose file, which mounts a named volume for outputs:
#   docker compose --profile satellite run --rm satellite
#
# Environment (all optional; the default simulated run needs none):
#   EE_SERVICE_ACCOUNT_JSON  Earth Engine service-account key — raw JSON or a
#                            path to a mounted key file.
#   EE_PROJECT               Earth Engine project to bill; falls back to
#                            GOOGLE_CLOUD_PROJECT, then to the key's project_id.
#
# Earth Engine is the satellite DATA SOURCE (free for research and
# non-commercial use), not deployment infrastructure. It is entirely optional:
# without it the pipeline runs `--source simulate` offline, and the package
# imports fine with earthengine-api absent.
#
# Results are written to /app/outputs. Mount a host directory or a volume there;
# nothing is uploaded anywhere by this image.
#
# Python 3.12 rather than 3.13: the geospatial extras (geopandas / pyogrio /
# rasterio) publish 3.12 binary wheels far more reliably, and building GDAL
# from source in a batch image is not worth the interpreter-version delta.
#
# No `# syntax=` directive on purpose: nothing here needs a BuildKit-only
# instruction, and pinning a remote frontend makes the build fail on hosts that
# cannot reach the registry for it.
# =============================================================================

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------------------
# Stage 1 — builder: resolve and install into a self-contained venv
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /build

# Optional extras from pyproject.toml:
#   gee -> earthengine-api, geemap, geopandas  (real Sentinel-1/2 ingestion)
#   geo -> rasterio, shapely, pyproj           (GeoTIFF output; the pipeline
#                                               falls back to PNG without it)
# Build with `--build-arg EXTRAS=` for a ~350 MB smaller simulate-only image.
ARG EXTRAS=gee

# pyproject declares readme = "README.md", so the build needs it present.
COPY pyproject.toml README.md ./
COPY src ./src

# Non-editable install: the default pilot_area.yaml ships as package data
# (krishimitra_rs/config/pilot_area.yaml), so the console script resolves its
# config from any working directory.
RUN python -m pip install --upgrade pip setuptools wheel \
 && if [ -n "${EXTRAS}" ]; then pip install ".[${EXTRAS}]"; else pip install "."; fi

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

# libgomp1: XGBoost's OpenMP runtime, dlopen'd at import time.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# Non-root, UID 1000 — the id most job runners and bind-mounted host directories
# expect, so files written to a mounted outputs/ are owned by the calling user.
RUN groupadd --gid 1000 app \
 && useradd --uid 1000 --gid app --create-home --home-dir /home/app app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# The editable pilot config + helper scripts (handy for `--config` overrides and
# for `python /app/scripts/make_pilot_dataset.py`). The package already carries
# its own copy, so the image runs fine without these.
COPY --chown=app:app config ./config
COPY --chown=app:app scripts ./scripts

# krishimitra_rs writes outputs under the CWD for an installed package, so
# /app/outputs is the artifact directory — mount a host path or volume there.
RUN mkdir -p /app/outputs /app/data/processed && chown -R app:app /app

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MPLBACKEND=Agg

USER app

# Console script from [project.scripts]; arguments are forwarded, so any runner
# can override them (e.g. `docker run ... krishimitra-satellite --source gee`).
ENTRYPOINT ["krishimitra-rs"]

# Default: the fully offline simulated pilot, so `docker run` with no arguments
# is a valid end-to-end smoke test.
CMD ["--source", "simulate"]
