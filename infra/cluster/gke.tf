# Zonal Standard cluster: one control plane in one zone. GKE's free-tier credit covers the
# management fee of exactly one zonal (not regional) cluster per billing account.
resource "google_container_cluster" "s1" {
  name     = var.cluster_name
  location = var.zone

  network    = local.foundation.network
  subnetwork = local.foundation.subnetwork

  # No default node pool: the pool below is a separate resource, so it can be resized or
  # replaced without recreating the cluster. (Omitting initial_node_count/node_config does
  # this on GKE >= 1.36.4-gke.1469000.)

  networking_mode = "VPC_NATIVE"
  ip_allocation_policy {
    cluster_secondary_range_name  = local.foundation.pods_range_name
    services_secondary_range_name = local.foundation.services_range_name
  }

  # Dataplane V2 (eBPF) enforces Kubernetes NetworkPolicy, e.g. "only Partition Manager may
  # call Sensor Store". Without it GKE accepts NetworkPolicies but ignores them.
  datapath_provider = "ADVANCED_DATAPATH"

  # Pods get Google credentials from their Kubernetes service account; no JSON keys.
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  release_channel {
    channel = "REGULAR"
  }

  # Container stdout goes to Cloud Logging (the GKE default). Prometheus is our own
  # kube-prometheus-stack, so Google Managed Prometheus stays off (no double collection).
  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus {
      enabled = false
    }
  }

  deletion_protection = false # this stack is destroyed whenever we stop working
}

resource "google_container_node_pool" "main" {
  name     = "main"
  cluster  = google_container_cluster.s1.name
  location = var.zone

  # The cluster autoscaler adds nodes when HPA-created pods no longer fit.
  initial_node_count = var.min_nodes
  autoscaling {
    min_node_count = var.min_nodes
    max_node_count = var.max_nodes
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type = var.machine_type
    spot         = var.spot_nodes

    # pd-standard: cheapest, and new projects have a small SSD quota (pd-balanced counts
    # against it).
    boot_disk {
      disk_type = "pd-standard"
      size_gb   = 30
    }

    service_account = local.sa_email["gke-nodes"]
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]

    # Serve pods the GKE metadata server, which hands out Workload Identity tokens.
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }

  lifecycle {
    # The autoscaler changes the node count; that must not look like drift.
    ignore_changes = [initial_node_count]
  }
}
