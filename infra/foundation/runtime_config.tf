# Values the pods need that only exist after this stack is applied (the Cloud SQL connection
# name has a random suffix). Publishing them in Secret Manager means nothing project-specific
# has to be committed by hand: External Secrets copies this into the Kubernetes Secret
# "gcp-config" in namespace s1 (k8s/gke/external-secrets.yaml). Not secret, just late-bound.
resource "google_secret_manager_secret" "runtime_config" {
  secret_id = "s1-runtime-config"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "runtime_config" {
  secret = google_secret_manager_secret.runtime_config.id
  secret_data = jsonencode({
    GOOGLE_CLOUD_PROJECT         = var.project_id
    SQL_INSTANCE_CONNECTION_NAME = google_sql_database_instance.main.connection_name
    ALERTS_TOPIC                 = google_pubsub_topic.alerts.id
    ARCHIVE_BUCKET               = google_storage_bucket.b["archive"].name
  })
}

resource "google_secret_manager_secret_iam_member" "runtime_config_eso" {
  secret_id = google_secret_manager_secret.runtime_config.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.sa["external-secrets"].member
}
