# The connection details live in GCP Secret Manager, never in git:
#   kafka-client             JSON of KAFKA_* env vars -> External Secrets -> Kubernetes Secret
#                            "kafka-client" in namespace s1 (pods use envFrom)
#   kafka-client-properties  Java properties file -> the Flink job on Dataproc reads it
resource "google_secret_manager_secret" "kafka" {
  for_each = toset(["kafka-client", "kafka-client-properties"])

  secret_id = each.value
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "kafka_client" {
  secret      = google_secret_manager_secret.kafka["kafka-client"].id
  secret_data = jsonencode(local.client_env)
}

resource "google_secret_manager_secret_version" "kafka_properties" {
  secret      = google_secret_manager_secret.kafka["kafka-client-properties"].id
  secret_data = local.java_properties
}

locals {
  secret_readers = {
    "kafka-client"            = concat([local.sa_member["external-secrets"]], var.team_members)
    "kafka-client-properties" = concat([local.sa_member["dataproc"]], var.team_members)
  }
}

resource "google_secret_manager_secret_iam_member" "read" {
  for_each = merge([
    for secret, members in local.secret_readers : {
      for m in members : "${secret}/${m}" => { secret = secret, member = m }
    }
  ]...)

  secret_id = google_secret_manager_secret.kafka[each.value.secret].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value.member
}
