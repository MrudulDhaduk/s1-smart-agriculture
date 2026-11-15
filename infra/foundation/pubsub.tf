# Dry-soil and failure events (format: contracts/pubsub/alert.example.json).
# Publishers: Irrigation Controller (DRY_SOIL, SENSOR_SILENT) and Partition Manager
# (STORAGE_NODE_DOWN). Consumer: the Alert function, through an Eventarc trigger that creates
# its own push subscription.
resource "google_pubsub_topic" "alerts" {
  name = "alerts"
}

resource "google_pubsub_topic_iam_member" "publishers" {
  for_each = toset(["irrigation-controller", "partition-manager"])

  topic  = google_pubsub_topic.alerts.id
  role   = "roles/pubsub.publisher"
  member = google_service_account.sa[each.value].member
}
