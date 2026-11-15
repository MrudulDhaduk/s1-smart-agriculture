# Managed Flink for Farm Analytics (task e): a single-node Dataproc cluster, YARN + Flink.

# Our own staging/temp buckets, so Dataproc does not create unmanaged ones outside Terraform.
resource "google_storage_bucket" "dataproc" {
  for_each = var.enable_dataproc ? toset(["staging", "temp"]) : toset([])

  name     = "${var.project_id}-s1-dataproc-${each.key}"
  location = upper(var.region)

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  soft_delete_policy {
    retention_duration_seconds = 0
  }
}

resource "google_storage_bucket_iam_member" "dataproc" {
  for_each = google_storage_bucket.dataproc

  bucket = each.value.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.sa_email["dataproc"]}"
}

resource "google_dataproc_cluster" "flink" {
  count = var.enable_dataproc ? 1 : 0

  name   = "s1-flink"
  region = var.region

  cluster_config {
    staging_bucket = google_storage_bucket.dataproc["staging"].name
    temp_bucket    = google_storage_bucket.dataproc["temp"].name

    gce_cluster_config {
      zone                   = var.zone
      subnetwork             = local.foundation.subnetwork
      service_account        = local.sa_email["dataproc"]
      service_account_scopes = ["cloud-platform"]
      # Image 2.2+ defaults to internal IPs only. The Flink job must reach Aiven Kafka on
      # the internet, and without an external IP that would need Cloud NAT.
      internal_ip_only = false
    }

    master_config {
      num_instances = 1
      machine_type  = var.dataproc_machine_type
      disk_config {
        boot_disk_type    = "pd-standard"
        boot_disk_size_gb = 30
      }
    }

    # Single-node cluster: the master also runs the YARN containers.
    worker_config {
      num_instances = 0
    }

    software_config {
      image_version       = "2.2-debian12" # ships Flink 1.17
      optional_components = ["FLINK"]
      override_properties = {
        "dataproc:dataproc.allow.zero.workers" = "true"
        # Both default to false. Without them Flink job logs never reach Cloud Logging
        # (task h: logs "including the analytics job").
        "dataproc:dataproc.logging.stackdriver.job.driver.enable"         = "true"
        "dataproc:dataproc.logging.stackdriver.job.yarn.container.enable" = "true"
      }
    }

    # Component Gateway: Flink and YARN web UIs through an authenticated Google URL.
    endpoint_config {
      enable_http_port_access = true
    }

    # Cost guard. Jobs submitted with `gcloud dataproc jobs submit flink` count as
    # activity, so a running streaming job keeps the cluster alive.
    lifecycle_config {
      idle_delete_ttl = var.dataproc_idle_delete_ttl
    }
  }

  depends_on = [google_storage_bucket_iam_member.dataproc]
}
