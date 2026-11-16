# One Google service account (GSA) per workload, each with only the roles it needs.
# Pods use them through Workload Identity: the binding "Kubernetes SA -> GSA" is made in
# infra/cluster, because GKE creates the identity pool together with the first cluster.
locals {
  service_accounts = {
    gke-nodes = {
      description = "GKE node VMs: write logs/metrics, pull images"
      roles       = ["roles/container.defaultNodeServiceAccount"]
    }
    dataproc = {
      description = "Dataproc VMs running the Flink job"
      roles       = ["roles/dataproc.worker", "roles/logging.logWriter", "roles/monitoring.metricWriter"]
    }
    alert-function = {
      description = "Alert Service (Cloud Run function)"
      roles       = ["roles/datastore.user", "roles/eventarc.eventReceiver"]
    }
    partition-manager = {
      description = "Partition Manager pods: ring membership in Firestore"
      roles       = ["roles/datastore.user"]
    }
    farm-registry = {
      description = "Farm Registry pods: Cloud SQL via IAM login"
      roles       = ["roles/cloudsql.client", "roles/cloudsql.instanceUser"]
    }
    sensor-registry = {
      description = "Sensor Registry pods: Cloud SQL via IAM login"
      roles       = ["roles/cloudsql.client", "roles/cloudsql.instanceUser"]
    }
    irrigation-controller = {
      description = "Irrigation Controller pods: watering cooldown in Firestore, publish alerts"
      roles       = ["roles/datastore.user"] # + topic-level publisher role in pubsub.tf
    }
    farm-analytics = {
      description = "Farm Analytics pods: write summaries to Firestore"
      roles       = ["roles/datastore.user"]
    }
    grafana = {
      description = "Grafana: read Cloud Logging and Cloud Monitoring"
      roles       = ["roles/logging.viewer", "roles/monitoring.viewer"]
    }
    external-secrets = {
      description = "External Secrets Operator: copy Secret Manager secrets into Kubernetes"
      roles       = [] # accessor on individual secrets only (runtime-config here, kafka-* in infra/kafka)
    }
  }

  # Which Kubernetes service account (namespace/name) may act as which GSA.
  # monitoring/monitoring-grafana = kube-prometheus-stack installed as release "monitoring";
  # external-secrets/external-secrets = External Secrets Operator installed as release "external-secrets".
  workload_identity = {
    partition-manager     = "s1/partition-manager"
    farm-registry         = "s1/farm-registry"
    sensor-registry       = "s1/sensor-registry"
    irrigation-controller = "s1/irrigation-controller"
    farm-analytics        = "s1/farm-analytics"
    grafana               = "monitoring/monitoring-grafana"
    external-secrets      = "external-secrets/external-secrets"
  }

  sa_roles = merge([
    for sa, cfg in local.service_accounts : {
      for role in cfg.roles : "${sa}/${role}" => { sa = sa, role = role }
    }
  ]...)

  team_roles = [
    "roles/viewer",              # read-only console access
    "roles/container.developer", # kubectl get/logs/exec (deploys still go through ArgoCD)
    "roles/dataproc.editor",     # submit and cancel the Flink job
  ]
}

resource "google_service_account" "sa" {
  for_each = local.service_accounts

  account_id   = "s1-${each.key}"
  display_name = "s1 ${each.key}"
  description  = each.value.description
}

resource "google_project_iam_member" "sa" {
  for_each = local.sa_roles

  project = var.project_id
  role    = each.value.role
  member  = google_service_account.sa[each.value.sa].member
}

resource "google_project_iam_member" "team" {
  for_each = {
    for pair in setproduct(var.team_members, local.team_roles) : "${pair[0]}/${pair[1]}" => {
      member = pair[0]
      role   = pair[1]
    }
  }

  project = var.project_id
  role    = each.value.role
  member  = each.value.member
}
