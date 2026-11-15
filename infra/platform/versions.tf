terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.11"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.3"
    }
  }

  backend "gcs" {
    prefix = "s1/platform"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "terraform_remote_state" "foundation" {
  backend = "gcs"
  config = {
    bucket = "${var.project_id}-tfstate"
    prefix = "s1/foundation"
  }
}

# The cluster is created by infra/cluster (a separate state), so it is read here, not created:
# destroying this stack never touches the cluster itself.
data "google_container_cluster" "s1" {
  name     = var.cluster_name
  location = var.zone
}

data "google_client_config" "current" {}

provider "helm" {
  kubernetes = {
    host                   = "https://${data.google_container_cluster.s1.endpoint}"
    token                  = data.google_client_config.current.access_token
    cluster_ca_certificate = base64decode(data.google_container_cluster.s1.master_auth[0].cluster_ca_certificate)
  }
}

locals {
  sa_email = data.terraform_remote_state.foundation.outputs.service_account_emails
}
