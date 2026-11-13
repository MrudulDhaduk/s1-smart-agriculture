# infra/cluster reads these through terraform_remote_state; the rest is for the team handoff.

output "project_id" {
  value = var.project_id
}

output "region" {
  value = var.region
}

output "zone" {
  value = var.zone
}

output "network" {
  value = google_compute_network.vpc.self_link
}

output "subnetwork" {
  value = google_compute_subnetwork.main.self_link
}

output "pods_range_name" {
  value = "pods"
}

output "services_range_name" {
  value = "services"
}

output "artifact_registry" {
  description = "Image prefix: <this>/<service>:<tag>"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.s1.repository_id}"
}

output "firestore_location" {
  value = google_firestore_database.default.location_id
}

output "sql_connection_name" {
  description = "Used by the Cloud SQL connector in the registry services."
  value       = google_sql_database_instance.main.connection_name
}

output "sql_iam_users" {
  description = "Database user name per registry service (IAM login)."
  value       = { for k, u in google_sql_user.registry : k => u.name }
}

output "buckets" {
  value = { for k, b in google_storage_bucket.b : k => b.name }
}

output "alerts_topic" {
  value = google_pubsub_topic.alerts.id
}

output "service_account_emails" {
  value = { for k, sa in google_service_account.sa : k => sa.email }
}

output "service_account_names" {
  description = "Fully-qualified names, needed for IAM bindings on the service accounts."
  value       = { for k, sa in google_service_account.sa : k => sa.name }
}

output "workload_identity" {
  description = "GSA key -> Kubernetes service account (namespace/name)."
  value       = local.workload_identity
}
