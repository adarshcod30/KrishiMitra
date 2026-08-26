output "artifact_registry" {
  description = "Docker image base path. Tag images as <this>/<service>:<tag>."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "models_bucket" {
  description = "AGROTECH_MODELS_GCS_URI points at the artifacts/ prefix of this bucket."
  value       = google_storage_bucket.models.name
}

output "models_gcs_uri" {
  description = "Value for AGROTECH_MODELS_GCS_URI."
  value       = "gs://${google_storage_bucket.models.name}/artifacts"
}

output "uploads_bucket" {
  description = "Value for AGROTECH_UPLOADS_GCS_BUCKET."
  value       = google_storage_bucket.uploads.name
}

output "satellite_bucket" {
  description = "Mounted at /app/outputs in the satellite Cloud Run Job via a Cloud Storage volume."
  value       = google_storage_bucket.satellite.name
}

output "sql_connection_name" {
  description = "PROJECT:REGION:INSTANCE — pass to `gcloud run deploy --add-cloudsql-instances`."
  value       = google_sql_database_instance.main.connection_name
}

output "sql_instance_name" {
  description = "Cloud SQL instance name."
  value       = google_sql_database_instance.main.name
}

output "database_url_secret" {
  description = "Secret Manager secret holding AGROTECH_DATABASE_URL. Map it with --set-secrets, never read it into a variable."
  value       = google_secret_manager_secret.database_url.secret_id
}

output "service_account_emails" {
  description = "Runtime identities, keyed by role."
  value       = { for k, v in google_service_account.this : k => v.email }
}

output "deploy_env_fragment" {
  description = "Paste into deploy/env to make the shell scripts agree with what Terraform created."
  value       = <<-EOT
    PROJECT_ID=${var.project_id}
    REGION=${var.region}
    BUCKET_LOCATION=${var.bucket_location}
    AR_REPO=${google_artifact_registry_repository.images.repository_id}
    MODELS_BUCKET=${google_storage_bucket.models.name}
    UPLOADS_BUCKET=${google_storage_bucket.uploads.name}
    SATELLITE_BUCKET=${google_storage_bucket.satellite.name}
    SQL_INSTANCE=${google_sql_database_instance.main.name}
    SQL_DB=${google_sql_database.app.name}
    SQL_USER=${google_sql_user.app.name}
    API_SA=${google_service_account.this["api"].account_id}
    WEB_SA=${google_service_account.this["web"].account_id}
    SATELLITE_SA=${google_service_account.this["satellite"].account_id}
    SCHEDULER_SA=${google_service_account.this["scheduler"].account_id}
    BUILD_SA=${google_service_account.this["build"].account_id}
  EOT
}

# Deliberately NOT an output: the database password. It is in Terraform state
# and in Secret Manager; adding it to `terraform output` would put it in CI logs
# too. Read it with:
#   gcloud secrets versions access latest --secret=krishimitra-db-password
