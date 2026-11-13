locals {
  # Every API the other stacks use. Enabling an API is free; only the resources cost money.
  services = [
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudbuild.googleapis.com", # Cloud Run functions build the function image with Cloud Build
    "cloudfunctions.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "compute.googleapis.com",
    "container.googleapis.com",
    "dataproc.googleapis.com",
    "eventarc.googleapis.com", # delivers Pub/Sub messages to the Alert function
    "firestore.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com", # Workload Identity token exchange
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com", # Kafka credentials + runtime config, read by External Secrets
    "serviceusage.googleapis.com",
    "sqladmin.googleapis.com", # also used by the Cloud SQL connector inside the registries
    "storage.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.services)

  service = each.value
  # Destroying this stack must not switch APIs off underneath the other stacks.
  disable_on_destroy = false
}

# Remote state for every stack. Versioned so a bad apply can be rolled back to the
# previous state file; private because state holds connection details.
resource "google_storage_bucket" "tfstate" {
  name     = "${var.project_id}-tfstate"
  location = upper(var.region)

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 10
      with_state         = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}

data "google_project" "this" {
  project_id = var.project_id
}

# Budget alerts e-mail the billing admins at 30 / 60 / 80 % of the budget.
# Alerts never stop spending; they only warn.
resource "google_billing_budget" "s1" {
  count = var.billing_account_id == "" ? 0 : 1

  billing_account = var.billing_account_id
  display_name    = "s1-${var.project_id}"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
    # Count spend BEFORE credits. With the default (credits included) our net cost stays
    # ~0 until the free credit is gone, so the alerts would fire too late to be useful.
    credit_types_treatment = "EXCLUDE_ALL_CREDITS"
  }

  amount {
    specified_amount {
      currency_code = var.budget_currency
      units         = tostring(var.budget_amount)
    }
  }

  dynamic "threshold_rules" {
    for_each = [0.3, 0.6, 0.8]
    content {
      threshold_percent = threshold_rules.value
    }
  }

  depends_on = [google_project_service.apis]
}
