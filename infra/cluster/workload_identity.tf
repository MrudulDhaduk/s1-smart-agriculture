# "Kubernetes service account X may act as Google service account Y".
# Each workload's manifest adds the annotation
#   iam.gke.io/gcp-service-account: <GSA email>
# to its Kubernetes ServiceAccount. These bindings live here, not in foundation, because
# the identity pool <project>.svc.id.goog only exists once a Workload Identity cluster does.
resource "google_service_account_iam_member" "workload_identity" {
  for_each = local.foundation.workload_identity

  service_account_id = local.foundation.service_account_names[each.key]
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${google_container_cluster.s1.workload_identity_config[0].workload_pool}[${each.value}]"
}
