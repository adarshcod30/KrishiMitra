# Deploying the API to a Hugging Face Space

Ten minutes end to end. The full three-service runbook (Neon + Space + Vercel) is
[`docs/DEPLOY_FREE.md`](../../docs/DEPLOY_FREE.md); this file is only the API half.

> **Read this before you start.** Hugging Face's own docs state: *"Static Spaces are
> free for everyone. Gradio and Docker Spaces run on compute and require a paid plan to
> create: PRO for personal accounts, Team or Enterprise for organizations."*
> The **CPU Basic hardware itself costs nothing per hour** — but *creating* a Docker
> Space on a personal account currently needs [PRO, $9/month](https://huggingface.co/pricing).
> If you do not have PRO, the same image runs unchanged on any container host that
> injects `PORT` (see "If you cannot use a Space" at the end).

---

## 0. Prerequisites

```bash
git lfs install                 # brew install git-lfs / apt install git-lfs
pip install -U "huggingface_hub[cli]"   # optional, for the `hf` CLI route
```

Trained models are optional but strongly recommended — without them the Space trains on
first boot, which turns every cold start into a multi-minute wait:

```bash
npm run train:ml                # writes ml-service/artifacts/*.joblib (~170 MB)
```

## 1. Create the Space

Web UI: <https://huggingface.co/new-space> → **SDK: Docker** → **Blank** template →
hardware **CPU basic (free)**. Visibility *public* keeps model storage on the free
best-effort public tier.

Or from the CLI:

```bash
hf auth login
hf repo create <space-name> --repo-type space --space_sdk docker
```

## 2. Clone the Space and fill it from this repo

The Space repo needs `Dockerfile` at its **root** — Hugging Face does not read
`spaces/api/Dockerfile`, and it must not receive this repo's Next.js app or
`node_modules`. `sync.sh` lays out exactly the right subset:

```bash
git clone https://huggingface.co/spaces/<user>/<space-name> ../krishimitra-space
./spaces/api/sync.sh ../krishimitra-space --with-artifacts
```

`sync.sh` writes `Dockerfile`, `README.md` (with the Space YAML front-matter),
`.gitattributes` (git-lfs rules for `*.joblib`), `.dockerignore` and the `ml-service/`
subset, then commits. It deliberately **does not push**. Check `--dry-run` first if you
want to see the plan.

`agrotech.db` and `ml-service/uploads/` are never copied: they hold farmer PII, and a
public Space repo is world-readable.

## 3. Set the Space secrets

Space page → **Settings** → **Variables and secrets**. Secrets are injected as ordinary
environment variables at runtime; nothing is baked into the image.

| Name | Kind | Value |
| --- | --- | --- |
| `AGROTECH_DATABASE_URL` | secret | Neon pooled connection string, `?sslmode=require`. **Without this every row is lost on each restart.** |
| `AGROTECH_JWT_SECRET` | secret | `openssl rand -hex 32`. Required whenever `AGROTECH_ENVIRONMENT=production`. |
| `AGROTECH_ENVIRONMENT` | variable | `production` |
| `AGROTECH_PUBLIC_BASE_URL` | variable | `https://<user>-<space-name>.hf.space` |
| `AGROTECH_REQUIRE_WRITE_AUTH` | variable | `true` to require a token on writes (then also set `AGROTECH_ADMIN_USERNAME` + `AGROTECH_ADMIN_PASSWORD_HASH`). |
| `AGROTECH_SARVAM_API_KEY` | secret | optional — Indic translation |
| `AGROTECH_BRAVE_SEARCH_API_KEY` | secret | optional — web search enrichment |
| `AGROTECH_MYSCHEME_API_KEY` | secret | optional — government-scheme lookup |
| `AGROTECH_S3_ENDPOINT_URL` / `AGROTECH_S3_BUCKET` / `AGROTECH_S3_ACCESS_KEY_ID` / `AGROTECH_S3_SECRET_ACCESS_KEY` / `AGROTECH_S3_PUBLIC_BASE_URL` | secrets | optional — durable uploads on any S3-compatible store. All unset ⇒ local (ephemeral) disk. |
| `AGROTECH_CORS_ORIGINS` | variable | only if the browser calls the Space directly; the Vercel proxy does not need it. |

`PORT` is **not** set here — the image defaults to `7860`, which is what `app_port` in
`README.md` declares.

Changing a secret restarts the Space; it does not rebuild the image.

## 4. Push

```bash
cd ../krishimitra-space
git push origin main
```

The Hub builds the image on push (watch the **Logs** tab → *Build*). First build is
5–10 minutes, mostly compiling the scientific stack; later pushes reuse layer cache.

## 5. Verify

```bash
curl https://<user>-<space-name>.hf.space/health
```

Expected: `200` with the loaded-model summary. Then open
`https://<user>-<space-name>.hf.space/docs` for the interactive API.

If `/health` reports Postgres is not in use, `AGROTECH_DATABASE_URL` is missing or
malformed — check the **Logs** tab → *Container*.

## Updating later

```bash
./spaces/api/sync.sh ../krishimitra-space --with-artifacts && \
  (cd ../krishimitra-space && git push origin main)
```

Every push rebuilds and restarts the Space. Because the disk is ephemeral, a rebuild is
also when unpersisted state disappears — one more reason for Neon and S3.

## Alternative: `hf upload` instead of git

For a one-shot upload without cloning (no git-lfs setup needed — the CLI handles large
files):

```bash
./spaces/api/sync.sh /tmp/krishimitra-space --with-artifacts     # assemble only
hf upload <user>/<space-name> /tmp/krishimitra-space . --repo-type space
```

Git is still the better default: it gives you diffs, history and `--dry-run`.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| Build fails on `COPY ml-service/...` | `Dockerfile` is not at the Space repo root, or `sync.sh` was not run. |
| Push rejected, "file exceeds 10 MB" | `git lfs install` was skipped, or `.gitattributes` is missing. Re-run `sync.sh`. |
| Space builds but never becomes *Running* | The app is not listening on `7860`. Check `app_port` in `README.md` and that `PORT` was not overridden to something else. |
| `PermissionError` in the logs | Something writes outside `/home/user/app`. The container runs as UID 1000. |
| Uploads vanish after a while | Expected: the disk is ephemeral. Configure `AGROTECH_S3_*`. |
| First request after idle takes ~30 s | Expected: free Spaces sleep when unused and cold-start on the next request. |

## If you cannot use a Space

`spaces/api/Dockerfile` has no Hugging Face-specific instruction in it — it reads `PORT`,
runs as UID 1000, and stores nothing outside its own directory. It runs unchanged on any
host that can build a Dockerfile and inject `PORT`, and it is the same image
`docker compose` builds locally. Only the front-matter in `README.md` is HF-specific, and
other hosts simply ignore it.
