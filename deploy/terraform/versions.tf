terraform {
  # 1.5 is the floor for `check` blocks and the modern import syntax used in the
  # README's adoption instructions.
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source = "hashicorp/google"
      # Deliberately a range rather than a pin: the resources used here have
      # been stable across 6.x and 7.x. Run `terraform init -upgrade` and commit
      # the resulting .terraform.lock.hcl to pin exactly for your team.
      version = ">= 6.0.0, < 8.0.0"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.5.0"
    }
  }

  # Remote state is strongly recommended: the database password lives in state,
  # in plaintext. Create the bucket first (it cannot be managed by the same
  # configuration that stores its state in it), then uncomment:
  #
  #   gcloud storage buckets create gs://PROJECT-krishimitra-tfstate \
  #     --location=asia-south1 --uniform-bucket-level-access
  #   gcloud storage buckets update gs://PROJECT-krishimitra-tfstate --versioning
  #
  # backend "gcs" {
  #   bucket = "PROJECT-krishimitra-tfstate"
  #   prefix = "krishimitra/infra"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
