# =============================================================================
# KrishiMitra — durable GCP infrastructure.
#
# Scope: exactly what deploy/10-provision.sh creates — registry, buckets,
# Cloud SQL, service accounts, IAM and the database secrets.
#
# Deliberately OUT of scope: the Cloud Run services and jobs. They depend on
# container images that do not exist until Cloud Build has run, and Terraform
# would fight the deploy pipeline for ownership of the revision on every push.
# Build and deploy with cloudbuild.yaml or deploy/30-deploy.sh; let Terraform
# own the things that outlive a deploy.
#
#   terraform init
#   terraform plan  -var project_id=YOUR_PROJECT
#   terraform apply -var project_id=YOUR_PROJECT
# =============================================================================

locals {
  models_bucket    = var.models_bucket_name != "" ? var.models_bucket_name : "${var.project_id}-${var.name_prefix}-models"
  uploads_bucket   = var.uploads_bucket_name != "" ? var.uploads_bucket_name : "${var.project_id}-${var.name_prefix}-uploads"
  satellite_bucket = var.satellite_bucket_name != "" ? var.satellite_bucket_name : "${var.project_id}-${var.name_prefix}-satellite"
  build_bucket     = "${var.project_id}_cloudbuild"

  service_accounts = {
    api = {
      account_id   = "${var.name_prefix}-api"
      display_name = "KrishiMitra API (Cloud Run)"
      description  = "Runtime identity for the FastAPI ml-service"
    }
    web = {
      account_id   = "${var.name_prefix}-web"
      display_name = "KrishiMitra Web (Cloud Run)"
      description  = "Runtime identity for the Next.js frontend"
    }
    satellite = {
      account_id   = "${var.name_prefix}-satellite"
      display_name = "KrishiMitra Satellite Job"
      description  = "Runtime identity for the satellite-ml Cloud Run Job"
    }
    scheduler = {
      account_id   = "${var.name_prefix}-scheduler"
      display_name = "KrishiMitra Scheduler"
      description  = "Cloud Scheduler identity that triggers the satellite job"
    }
    build = {
      account_id   = "${var.name_prefix}-build"
      display_name = "KrishiMitra Cloud Build"
      description  = "Builds and deploys the container images"
    }
  }

  sa_email = { for k, v in google_service_account.this : k => v.email }

  # Project-level roles, one flat map so the whole grant surface is readable in
  # a single place and shows up as discrete resources in `terraform plan`.
  project_roles = merge(
    {
      # Connect to Cloud SQL. Grants "open a connection", not "read data".
      "api-cloudsql"   = { sa = "api", role = "roles/cloudsql.client" }
      "api-logging"    = { sa = "api", role = "roles/logging.logWriter" }
      "api-metrics"    = { sa = "api", role = "roles/monitoring.metricWriter" }
      "api-trace"      = { sa = "api", role = "roles/cloudtrace.agent" }

      "web-logging"    = { sa = "web", role = "roles/logging.logWriter" }
      "web-metrics"    = { sa = "web", role = "roles/monitoring.metricWriter" }

      "sat-logging"    = { sa = "satellite", role = "roles/logging.logWriter" }
      "sat-metrics"    = { sa = "satellite", role = "roles/monitoring.metricWriter" }

      # Push images.
      "build-ar"       = { sa = "build", role = "roles/artifactregistry.writer" }
      # Create/update Cloud Run services and jobs and execute the migrate job.
      "build-run"      = { sa = "build", role = "roles/run.admin" }
      # Required to deploy a service that RUNS AS another service account.
      "build-actas"    = { sa = "build", role = "roles/iam.serviceAccountUser" }
      # Mandatory for a build using a user-specified service account, which must
      # write its logs to Cloud Logging.
      "build-logging"  = { sa = "build", role = "roles/logging.logWriter" }
    },
    var.enable_earth_engine ? {
      # Create Earth Engine computations and assets.
      "sat-ee"         = { sa = "satellite", role = "roles/earthengine.writer" }
      # serviceusage.services.use — the permission everyone forgets. Without it
      # ee.Initialize(project=...) returns a 403 that never mentions Service Usage.
      "sat-serviceuse" = { sa = "satellite", role = "roles/serviceusage.serviceUsageConsumer" }
    } : {}
  )
}

# =============================================================================
# Service accounts
# =============================================================================
resource "google_service_account" "this" {
  for_each = local.service_accounts

  account_id   = each.value.account_id
  display_name = each.value.display_name
  description  = each.value.description
}

resource "google_project_iam_member" "roles" {
  for_each = local.project_roles

  project = var.project_id
  role    = each.value.role
  member  = "serviceAccount:${local.sa_email[each.value.sa]}"
}

# =============================================================================
# Artifact Registry
# =============================================================================
resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = var.ar_repo
  format        = "DOCKER"
  description   = "KrishiMitra container images (api, web, satellite)"
  labels        = var.labels

  docker_config {
    # Tags stay mutable so `:latest` can be re-pointed by the build pipeline.
    # Deployments always reference the immutable :<git-sha> tag, so this does
    # not weaken traceability.
    immutable_tags = false
  }
}

# =============================================================================
# Cloud Storage
# =============================================================================

# Trained model artifacts, downloaded by the API at startup via
# AGROTECH_MODELS_GCS_URI.
resource "google_storage_bucket" "models" {
  name     = local.models_bucket
  location = var.bucket_location
  labels   = var.labels

  # IAM is the one and only access-control surface: no per-object ACLs.
  uniform_bucket_level_access = true
  # Hard block on ever making this public.
  public_access_prevention = "enforced"

  # A bad retrain is rolled back by restoring the previous generation.
  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      # Scoped to superseded versions only. `with_state = "ARCHIVED"` is what
      # keeps the live artifact out of the deletion candidate set no matter how
      # old it gets.
      days_since_noncurrent_time = var.models_noncurrent_retention_days
      with_state                 = "ARCHIVED"
    }
  }

  # Terraform must not be able to delete a bucket holding trained models.
  # Remove this block deliberately if you really mean to tear it down.
  lifecycle {
    prevent_destroy = true
  }
}

# Farmer uploads: pest photographs, soil-test reports. Personal data.
resource "google_storage_bucket" "uploads" {
  name     = local.uploads_bucket
  location = var.bucket_location
  labels   = var.labels

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  # Uploads are referenced by rows in Cloud SQL, so no lifecycle deletion rule:
  # expiring an object out from under a live advisory record would produce a
  # broken link with no warning.

  lifecycle {
    prevent_destroy = true
  }
}

# Satellite products: crop maps, moisture-stress figures, FAO-56 advisory
# tables. Mounted into the satellite Cloud Run Job at /app/outputs through a
# Cloud Storage volume, so the pipeline writes here directly.
resource "google_storage_bucket" "satellite" {
  name     = local.satellite_bucket
  location = var.bucket_location
  labels   = var.labels

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  # Each run overwrites the same object names, so versioning is the only thing
  # that keeps last week's advisory maps recoverable.
  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      days_since_noncurrent_time = var.models_noncurrent_retention_days
      with_state                 = "ARCHIVED"
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Cloud Build source staging. Disposable — no prevent_destroy.
resource "google_storage_bucket" "build_source" {
  name     = local.build_bucket
  location = var.bucket_location
  labels   = var.labels

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      # Source tarballs are worthless a month after the build.
      age = 30
    }
  }
}

# --- Bucket IAM: scoped per bucket, never project-wide storage.admin ---------

resource "google_storage_bucket_iam_member" "api_models_read" {
  bucket = google_storage_bucket.models.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${local.sa_email["api"]}"
}

resource "google_storage_bucket_iam_member" "api_uploads_write" {
  bucket = google_storage_bucket.uploads.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.sa_email["api"]}"
}

# The job mounts this bucket at /app/outputs, so it needs object read/write. It
# gets no access at all to the models or uploads buckets.
resource "google_storage_bucket_iam_member" "satellite_outputs_write" {
  bucket = google_storage_bucket.satellite.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.sa_email["satellite"]}"
}

# The API serves satellite maps and advisory tables, but must never alter them.
resource "google_storage_bucket_iam_member" "api_satellite_read" {
  bucket = google_storage_bucket.satellite.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${local.sa_email["api"]}"
}

resource "google_storage_bucket_iam_member" "build_source_rw" {
  bucket = google_storage_bucket.build_source.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.sa_email["build"]}"
}

# =============================================================================
# Cloud SQL for PostgreSQL
# =============================================================================
resource "google_sql_database_instance" "main" {
  name             = "${var.name_prefix}-pg"
  database_version = var.sql_database_version
  region           = var.region

  deletion_protection = var.sql_deletion_protection

  settings {
    tier              = var.sql_tier
    edition           = "ENTERPRISE"
    availability_type = var.sql_availability_type
    disk_type         = var.sql_disk_type
    disk_size         = var.sql_disk_size_gb
    disk_autoresize   = true
    user_labels       = var.labels

    backup_configuration {
      enabled                        = true
      start_time                     = "18:00"
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7

      backup_retention_settings {
        retained_backups = 7
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      # A public IP with an EMPTY authorized-network list. Cloud Run reaches the
      # instance through the built-in connector over a Unix socket, which needs
      # neither a VPC connector nor an allow-listed CIDR — so nothing on the
      # internet can open a connection, and there is no NAT/VPC cost.
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    maintenance_window {
      day          = 7 # Sunday
      hour         = 20
      update_track = "stable"
    }

    database_flags {
      name  = "max_connections"
      value = "100"
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_sql_database" "app" {
  name     = var.sql_database_name
  instance = google_sql_database_instance.main.name
}

# The generated password lands in Terraform state in plaintext. Use a remote GCS
# backend with uniform bucket-level access (see versions.tf) and treat state as
# a secret, or manage the user out of band with deploy/10-provision.sh.
resource "random_password" "db" {
  length = 32
  # Alphanumeric only: the password is embedded in a postgresql:// URL, so
  # anything requiring percent-encoding is excluded up front.
  special = false
}

resource "google_sql_user" "app" {
  name     = var.sql_user
  instance = google_sql_database_instance.main.name
  password = random_password.db.result
}

# =============================================================================
# Secret Manager
# =============================================================================

# --- Database secrets: created WITH values, because only Terraform has them ---

resource "google_secret_manager_secret" "db_password" {
  secret_id = "${var.name_prefix}-db-password"
  labels    = merge(var.labels, { component = "database" })

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db.result
}

resource "google_secret_manager_secret" "database_url" {
  secret_id = "agrotech-database-url"
  labels    = merge(var.labels, { component = "database" })

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "database_url" {
  secret = google_secret_manager_secret.database_url.id
  # Unix-socket form. Cloud Run mounts the connector socket at
  # /cloudsql/<connection_name>; libpq and psycopg accept it via the `host`
  # query parameter, with an empty host section before the slash.
  secret_data = join("", [
    var.sql_url_scheme,
    "://",
    google_sql_user.app.name,
    ":",
    random_password.db.result,
    "@/",
    google_sql_database.app.name,
    "?host=/cloudsql/",
    google_sql_database_instance.main.connection_name,
  ])
}

# --- Application secrets: CONTAINERS only, no versions ------------------------
# Values are added out of band by deploy/20-secrets.sh, which reads them from
# the terminal and pipes them to gcloud on stdin. Putting third-party API keys
# in .tfvars would write them to Terraform state and, sooner or later, to git.

locals {
  app_secrets = {
    "agrotech-jwt-secret"          = "HMAC signing key for API access tokens"
    "agrotech-admin-password-hash" = "Hash of the admin password"
    "agrotech-sarvam-api-key"      = "Sarvam AI translation key"
    "agrotech-brave-search-api-key" = "Brave Search key"
    "agrotech-myscheme-api-key"    = "myScheme.gov.in key"
  }
}

resource "google_secret_manager_secret" "app" {
  for_each = local.app_secrets

  secret_id = each.key
  labels    = var.labels

  replication {
    auto {}
  }
}

# --- Secret IAM: per secret, per identity ------------------------------------

resource "google_secret_manager_secret_iam_member" "api_database_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.sa_email["api"]}"
}

resource "google_secret_manager_secret_iam_member" "api_app_secrets" {
  for_each = google_secret_manager_secret.app

  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.sa_email["api"]}"
}

# Note the absence of any binding for ${name_prefix}-db-password: the raw
# password is operator-only. The API consumes the assembled URL instead.
