output "cluster_name" {
  value = google_container_cluster.s1.name
}

output "get_credentials" {
  value = "gcloud container clusters get-credentials ${google_container_cluster.s1.name} --zone ${var.zone} --project ${var.project_id}"
}

output "workload_pool" {
  value = google_container_cluster.s1.workload_identity_config[0].workload_pool
}

output "dataproc_cluster" {
  value = var.enable_dataproc ? google_dataproc_cluster.flink[0].name : null
}

output "dataproc_web_uis" {
  description = "Component Gateway URLs (Flink, YARN)."
  value       = var.enable_dataproc ? google_dataproc_cluster.flink[0].cluster_config[0].endpoint_config[0].http_ports : null
}
