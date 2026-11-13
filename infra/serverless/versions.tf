terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.11"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.8"
    }
  }

  backend "gcs" {
    prefix = "s1/serverless"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region

  default_labels = {
    app        = "s1"
    managed-by = "terraform"
  }
}

data "terraform_remote_state" "foundation" {
  backend = "gcs"
  config = {
    bucket = "${var.project_id}-tfstate"
    prefix = "s1/foundation"
  }
}

locals {
  foundation = data.terraform_remote_state.foundation.outputs
}
