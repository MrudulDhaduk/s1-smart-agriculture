# Object storage (storage product 3 of 3).
# Dataproc's own staging/temp buckets live in infra/cluster, next to the Dataproc cluster.

locals {
  buckets = {
    # Raw alert payloads archived by the Alert function, plus bulk sensor uploads.
    archive = { expire_days = 30 }
    # Build outputs that cloud services run: the Flink job jar, Cloud Function source zips.
    artifacts = { expire_days = 0 }
  }
}

resource "google_storage_bucket" "b" {
  for_each = local.buckets

  name     = "${var.project_id}-s1-${each.key}"
  location = upper(var.region)

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true # demo data: destroy may delete the objects too

  # No 7-day retention of deleted objects (it is billed and blocks a quick rebuild).
  soft_delete_policy {
    retention_duration_seconds = 0
  }

  dynamic "lifecycle_rule" {
    for_each = each.value.expire_days > 0 ? [each.value.expire_days] : []
    content {
      condition {
        age = lifecycle_rule.value
      }
      action {
        type = "Delete"
      }
    }
  }
}

resource "google_storage_bucket_iam_member" "alert_function_archive" {
  bucket = google_storage_bucket.b["archive"].name
  role   = "roles/storage.objectCreator"
  member = google_service_account.sa["alert-function"].member
}

resource "google_storage_bucket_iam_member" "dataproc_artifacts" {
  bucket = google_storage_bucket.b["artifacts"].name
  role   = "roles/storage.objectViewer" # read the job jar
  member = google_service_account.sa["dataproc"].member
}

resource "google_storage_bucket_iam_member" "team_artifacts" {
  for_each = toset(var.team_members)

  bucket = google_storage_bucket.b["artifacts"].name
  role   = "roles/storage.objectAdmin" # upload the Flink jar
  member = each.value
}
