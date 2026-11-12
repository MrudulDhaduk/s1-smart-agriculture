terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.11"
    }
  }

  # State lives in the bucket this stack creates. The bucket name is passed at init time
  # (-backend-config=bucket=<project>-tfstate) so the same code works in any project.
  # First run in a new project: see infra/README.md ("Bootstrap a new project").
  backend "gcs" {
    prefix = "s1/bootstrap"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region

  # The Billing Budgets API rejects calls made with user credentials unless they are billed
  # to a project that has the API enabled.
  user_project_override = true
  billing_project       = var.project_id

  default_labels = {
    app        = "s1"
    managed-by = "terraform"
  }
}
