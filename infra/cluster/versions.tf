terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.11"
    }
  }

  backend "gcs" {
    prefix = "s1/cluster"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone

  default_labels = {
    app        = "s1"
    managed-by = "terraform"
  }
}

# Network, service accounts and buckets come from the foundation stack.
data "terraform_remote_state" "foundation" {
  backend = "gcs"
  config = {
    bucket = "${var.project_id}-tfstate"
    prefix = "s1/foundation"
  }
}

locals {
  foundation = data.terraform_remote_state.foundation.outputs
  sa_email   = local.foundation.service_account_emails
}
