terraform {
  required_version = ">= 1.9"

  required_providers {
    aiven = {
      source  = "aiven/aiven"
      version = "~> 4.65"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 8.11"
    }
  }

  backend "gcs" {
    prefix = "s1/kafka"
  }
}

# Reads the API token from the AIVEN_TOKEN environment variable (never put it in a file).
provider "aiven" {}

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
  sa_member = { for k, email in data.terraform_remote_state.foundation.outputs.service_account_emails : k => "serviceAccount:${email}" }
}
