# Alert Service (task b): a Cloud Run function that runs only when a message arrives on the
# Pub/Sub topic "alerts" (asynchronous, event-driven), and costs nothing while idle.

# Zip the code; the md5 in the object name makes every code change a new deployment.
data "archive_file" "alert" {
  type        = "zip"
  source_dir  = "${path.module}/${var.source_dir}"
  output_path = "${path.module}/.build/alert-function.zip"
  excludes    = ["README.md", "__pycache__", ".pytest_cache", "test_main.py"]
}

resource "google_storage_bucket_object" "alert_source" {
  name   = "functions/alert-function-${data.archive_file.alert.output_md5}.zip"
  bucket = local.foundation.buckets["artifacts"]
  source = data.archive_file.alert.output_path

  lifecycle {
    precondition {
      condition     = fileexists("${path.module}/${var.source_dir}/main.py")
      error_message = "services/alert-function/main.py does not exist yet (Person 2's code)."
    }
  }
}

resource "google_cloudfunctions2_function" "alert" {
  name     = "alert-service"
  location = var.region

  build_config {
    runtime     = "python312"
    entry_point = var.entry_point
    source {
      storage_source {
        bucket = google_storage_bucket_object.alert_source.bucket
        object = google_storage_bucket_object.alert_source.name
      }
    }
  }

  service_config {
    min_instance_count    = 0 # scale to zero: no cost between alerts
    max_instance_count    = 3
    available_memory      = "256M"
    timeout_seconds       = 60
    service_account_email = local.foundation.service_account_emails["alert-function"]
    ingress_settings      = "ALLOW_INTERNAL_ONLY" # only Eventarc can call it, not the internet
    environment_variables = {
      GOOGLE_CLOUD_PROJECT = var.project_id
      ARCHIVE_BUCKET       = local.foundation.buckets["archive"]
      ALERTS_COLLECTION    = "alerts"
    }
  }

  event_trigger {
    trigger_region        = var.region
    event_type            = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic          = local.foundation.alerts_topic
    retry_policy          = "RETRY_POLICY_RETRY" # a failed run is retried: the function must be idempotent
    service_account_email = local.foundation.service_account_emails["alert-function"]
  }
}

# Eventarc delivers each message by calling the function's Cloud Run service as the trigger's
# service account, which therefore needs the invoker role on that service.
resource "google_cloud_run_v2_service_iam_member" "trigger_invoker" {
  location = var.region
  name     = google_cloudfunctions2_function.alert.service_config[0].service
  role     = "roles/run.invoker"
  member   = "serviceAccount:${local.foundation.service_account_emails["alert-function"]}"
}
