# Terraform (optional)

An alternative to `deploy/10-provision.sh`. Same resources, same names, same IAM
— pick one and stick with it. Running both against the same project is safe
(everything is idempotent and Terraform will import-or-conflict rather than
duplicate), but state drift makes it a bad habit.

## What it covers

| Resource | Managed here |
|---|---|
| Artifact Registry repo | yes |
| GCS buckets (models, uploads, build source) | yes |
| Cloud SQL instance, database, user | yes |
| Service accounts + project IAM | yes |
| Secret Manager containers | yes |
| Secret **values** for third-party keys | no — `deploy/20-secrets.sh` |
| Cloud Run services and jobs | no — `cloudbuild.yaml` / `deploy/30-deploy.sh` |
| Cloud Scheduler | no — `deploy/40-satellite-job.sh` |
| API enablement | no — `deploy/00-enable-apis.sh` |

Cloud Run is excluded on purpose. A service cannot be created before its image
exists, and if Terraform owned the service it would revert every deploy on the
next `apply` — the classic "Terraform fights CI over the image tag" failure.
Terraform owns what outlives a deploy; the pipeline owns the deploy.

## Use

```bash
# 1. APIs first — Terraform cannot enable the APIs it needs to call.
./deploy/00-enable-apis.sh

# 2. Provision
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars          # set project_id

terraform init
terraform plan                    # read this before applying
terraform apply

# 3. Feed the outputs back to the shell scripts
terraform output -raw deploy_env_fragment >> ../env

# 4. Secret values, then deploy
cd ../..
./deploy/20-secrets.sh
./deploy/30-deploy.sh
```

## State holds a password

`random_password.db` generates the database password, so **Terraform state
contains it in plaintext**. Consequences:

- Use the GCS backend (commented out in `versions.tf`), not local state.
- The state bucket must have uniform bucket-level access and public access
  prevention, and its IAM should be limited to the operators who already have
  database access.
- Never commit `terraform.tfstate`, `*.tfstate.backup`, or `.terraform/` — see
  the exclusions in `.gcloudignore`.

If that is unacceptable, delete `random_password.db` and `google_sql_user.app`
from `main.tf` and create the user with `deploy/10-provision.sh` instead, which
never persists the password anywhere but Secret Manager.

## Adopting resources the scripts already created

If you ran `10-provision.sh` first, import instead of recreating:

```bash
terraform import google_sql_database_instance.main            PROJECT/krishimitra-pg
terraform import google_storage_bucket.models                 PROJECT-krishimitra-models
terraform import google_storage_bucket.uploads                PROJECT-krishimitra-uploads
terraform import google_artifact_registry_repository.images   projects/PROJECT/locations/asia-south1/repositories/krishimitra
terraform import 'google_service_account.this["api"]'         projects/PROJECT/serviceAccounts/krishimitra-api@PROJECT.iam.gserviceaccount.com
# ...repeat for web, satellite, scheduler, build
```

Then `terraform plan` until it reports no changes.

## Destroying

`prevent_destroy` is set on the Cloud SQL instance and both data buckets, and
`deletion_protection` is on for the database. Tearing down is therefore a
deliberate three-step act, which is the point:

```bash
# 1. remove the lifecycle { prevent_destroy = true } blocks from main.tf
# 2. terraform apply -var sql_deletion_protection=false
# 3. terraform destroy
```

Buckets containing objects will not delete until emptied. That is also the
point.
