# deploy/models — optional offline model bake

`Dockerfile.api` copies everything in this directory into `/app/artifacts`
inside the API image. It ships empty (just `.gitkeep`), so by default this is a
no-op and the image stays small.

## The production path is GCS, not this directory

Trained artifacts are ~170 MB:

| File | Size |
|---|---|
| `crop_model.joblib` | ~117 MB |
| `irrigation_model.joblib` | ~44 MB |
| `fertilizer_model.joblib` | ~13 MB |
| `disease_model.joblib` | ~27 KB |
| `model_metadata.json` | ~3 KB |

Baking those into the image means every Cloud Run cold start pulls them as part
of the container layer and every retrain needs a rebuild-and-redeploy. Instead,
upload them once to the models bucket and set `AGROTECH_MODELS_GCS_URI`; the API
downloads them into `AGROTECH_ARTIFACTS_DIR` at startup:

```bash
gcloud storage cp /tmp/agrotech_artifacts/*.joblib      gs://PROJECT-krishimitra-models/artifacts/
gcloud storage cp /tmp/agrotech_artifacts/*.json        gs://PROJECT-krishimitra-models/artifacts/
gcloud run services update krishimitra-api --region REGION \
  --update-env-vars AGROTECH_MODELS_GCS_URI=gs://PROJECT-krishimitra-models/artifacts
```

## When baking is the right call

- Air-gapped or on-premises deployment with no GCS reachability.
- A demo image that must run with zero configuration.
- Pinning a specific model version to a specific image digest for reproducible
  evaluation.

To bake, copy the artifacts here and rebuild:

```bash
cp /tmp/agrotech_artifacts/*.joblib deploy/models/
cp /tmp/agrotech_artifacts/model_metadata.json deploy/models/
docker build -f Dockerfile.api -t krishimitra-api .
```

`.gitignore` at the repo root already ignores `*.joblib`, so baked artifacts are
not accidentally committed. **Do not** commit model binaries to git — use the
models bucket, which is versioned by `deploy/10-provision.sh`.

> Note: this directory exists instead of copying `ml-service/artifacts/`
> directly. That path is a developer's working directory — it has been a symlink
> to `/tmp/agrotech_artifacts` on some checkouts, and Docker cannot follow
> symlinks out of the build context — so it is excluded in `.dockerignore` and
> the image gets an explicit, reviewable bake directory instead.
