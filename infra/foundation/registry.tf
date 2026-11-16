# Docker images: <region>-docker.pkg.dev/<project>/s1/<service>:<tag>
resource "google_artifact_registry_repository" "s1" {
  repository_id = "s1"
  location      = var.region
  format        = "DOCKER"
  description   = "S1 Smart Agriculture service images"

  # Storage above 0.5 GB is billed; keep the newest 5 versions of each image and
  # drop anything older than 14 days.
  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      tag_state  = "ANY"
      older_than = "14d"
    }
  }
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 5
    }
  }
}

# GKE nodes pull images with the node service account.
resource "google_artifact_registry_repository_iam_member" "nodes_read" {
  repository = google_artifact_registry_repository.s1.name
  location   = google_artifact_registry_repository.s1.location
  role       = "roles/artifactregistry.reader"
  member     = google_service_account.sa["gke-nodes"].member
}

resource "google_artifact_registry_repository_iam_member" "team_push" {
  for_each = toset(var.team_members)

  repository = google_artifact_registry_repository.s1.name
  location   = google_artifact_registry_repository.s1.location
  role       = "roles/artifactregistry.writer"
  member     = each.value
}
