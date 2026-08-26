---
title: KrishiMitra API
emoji: 🌾
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: FastAPI crop / fertilizer / irrigation advisory service for KrishiMitra
---

# KrishiMitra ML API

FastAPI backend for [KrishiMitra](https://github.com/adarshdwivedi/KrishiMitra) — crop
recommendation, fertilizer and irrigation advisories, pest/disease triage, market prices
and government-scheme lookup for Indian smallholder farms.

This Space runs the API only. The user-facing Next.js app is deployed separately on
Vercel and proxies to this Space server-side, so the browser never calls this URL
directly (no CORS, and the backend can be repointed without a frontend rebuild).

```
Browser ──► Vercel (Next.js)  ──► /api/ml proxy ──► this Space ──► Neon Postgres
```

## Endpoints

| Path | Purpose |
| --- | --- |
| `GET /health` | liveness + which models are loaded |
| `GET /docs` | interactive OpenAPI docs |
| `POST /predict` | crop recommendation from soil + weather features |
| `POST /fertilizer`, `POST /irrigation` | derived advisories |
| `POST /uploads` | pest/disease image upload |

The full surface is in `/docs` on the running Space.

## Configuration

Everything is optional — with no configuration at all the service runs on SQLite and
local directories inside the container. Set these as **Space secrets**
(Settings ▸ Variables and secrets) to make it durable:

| Secret | Effect when set |
| --- | --- |
| `AGROTECH_DATABASE_URL` | Store rows in Neon Postgres instead of the ephemeral SQLite file. **Set this** — see below. |
| `AGROTECH_JWT_SECRET` | Required when `AGROTECH_ENVIRONMENT=production`. |
| `AGROTECH_S3_ENDPOINT_URL`, `AGROTECH_S3_BUCKET`, `AGROTECH_S3_ACCESS_KEY_ID`, `AGROTECH_S3_SECRET_ACCESS_KEY`, `AGROTECH_S3_PUBLIC_BASE_URL` | Store uploads in any S3-compatible bucket (Cloudflare R2, Supabase, MinIO) instead of the ephemeral disk. |
| `AGROTECH_CORS_ORIGINS` | Only needed if the browser calls this Space directly. |
| `AGROTECH_SARVAM_API_KEY`, `AGROTECH_BRAVE_SEARCH_API_KEY`, `AGROTECH_MYSCHEME_API_KEY` | Enable translation / search / scheme lookup. Each feature degrades gracefully when unset. |

> **A Space's disk is ephemeral.** Everything written inside the container is lost on
> every restart and rebuild. Without `AGROTECH_DATABASE_URL` the SQLite file — and every
> farmer record in it — disappears when the Space sleeps and wakes. Without the
> `AGROTECH_S3_*` variables, uploaded images do the same.

## Deploying

See `DEPLOY.md` next to this file in the KrishiMitra repository, and
`docs/DEPLOY_FREE.md` for the full three-service runbook.

## Model artifacts

The trained ensembles (`crop_model.joblib` and friends, ~170 MB) are committed to this
Space repo through `git-lfs` and copied into the image at build time. Baking them in
trades image size for cold-start latency, which is the right trade on hardware that
sleeps: a woken Space answers in seconds instead of re-training from
`ml-service/data/Crop_dataset.csv`.

If the artifacts are absent the service still starts — it trains them on first boot and
keeps them in memory until the next restart.
