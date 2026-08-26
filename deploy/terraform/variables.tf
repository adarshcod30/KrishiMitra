variable "project_id" {
  description = "GCP project that owns every resource."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run, Cloud SQL and Artifact Registry. Cloud Run and Cloud SQL must share it for the connector to work without a VPC connector."
  type        = string
  default     = "asia-south1"
}

variable "bucket_location" {
  description = "Location for the GCS buckets. Match `region` to keep egress free."
  type        = string
  default     = "asia-south1"
}

variable "name_prefix" {
  description = "Prefix for every resource name."
  type        = string
  default     = "krishimitra"
}

# --- Artifact Registry --------------------------------------------------------

variable "ar_repo" {
  description = "Artifact Registry Docker repository name."
  type        = string
  default     = "krishimitra"
}

# --- Cloud SQL ----------------------------------------------------------------

variable "sql_database_version" {
  description = "Cloud SQL PostgreSQL version."
  type        = string
  default     = "POSTGRES_17"
}

variable "sql_tier" {
  description = "Cloud SQL machine tier. db-f1-micro (dev), db-g1-small (small pilot), db-custom-1-3840 (first tier with an SLA)."
  type        = string
  default     = "db-g1-small"
}

variable "sql_disk_type" {
  description = "PD_HDD is ~4x cheaper and fine for a low-QPS advisory workload."
  type        = string
  default     = "PD_HDD"

  validation {
    condition     = contains(["PD_HDD", "PD_SSD"], var.sql_disk_type)
    error_message = "sql_disk_type must be PD_HDD or PD_SSD."
  }
}

variable "sql_disk_size_gb" {
  description = "Initial disk size. Autoresize is enabled, so this only sets the floor."
  type        = number
  default     = 10
}

variable "sql_availability_type" {
  description = "ZONAL (single AZ, cheap) or REGIONAL (automatic failover, roughly double the cost)."
  type        = string
  default     = "ZONAL"

  validation {
    condition     = contains(["ZONAL", "REGIONAL"], var.sql_availability_type)
    error_message = "sql_availability_type must be ZONAL or REGIONAL."
  }
}

variable "sql_database_name" {
  description = "Application database name."
  type        = string
  default     = "agrotech"
}

variable "sql_user" {
  description = "Application database user."
  type        = string
  default     = "agrotech"
}

variable "sql_url_scheme" {
  description = "URL scheme for AGROTECH_DATABASE_URL. Use postgresql+psycopg if ml-service moves to SQLAlchemy with psycopg 3."
  type        = string
  default     = "postgresql"
}

variable "sql_deletion_protection" {
  description = "Blocks `terraform destroy` and `gcloud sql instances delete` on the database. Leave true outside throwaway environments."
  type        = bool
  default     = true
}

# --- Storage ------------------------------------------------------------------

variable "models_bucket_name" {
  description = "Override the models bucket name. Empty means <project>-<prefix>-models."
  type        = string
  default     = ""
}

variable "uploads_bucket_name" {
  description = "Override the uploads bucket name. Empty means <project>-<prefix>-uploads."
  type        = string
  default     = ""
}

variable "satellite_bucket_name" {
  description = "Override the satellite outputs bucket name. Empty means <project>-<prefix>-satellite. Mounted into the satellite Cloud Run Job at /app/outputs."
  type        = string
  default     = ""
}

variable "models_noncurrent_retention_days" {
  description = "Days a superseded model version is kept before deletion. Live objects are never affected."
  type        = number
  default     = 90
}

# --- Earth Engine -------------------------------------------------------------

variable "enable_earth_engine" {
  description = "Grant the satellite service account Earth Engine roles. Requires the project to be registered at https://console.cloud.google.com/earth-engine and earthengine.googleapis.com enabled."
  type        = bool
  default     = false
}

# --- Labels -------------------------------------------------------------------

variable "labels" {
  description = "Labels applied to every resource that supports them."
  type        = map(string)
  default = {
    app        = "krishimitra"
    managed-by = "terraform"
  }
}
