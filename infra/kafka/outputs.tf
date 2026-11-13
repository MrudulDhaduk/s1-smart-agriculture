output "bootstrap_servers" {
  value = local.bootstrap
}

output "topics" {
  value = keys(aiven_kafka_topic.t)
}

output "state" {
  description = "POWEROFF after 24 h without traffic: power it on in the Aiven Console (Terraform cannot)."
  value       = aiven_kafka.s1.state
}

output "secrets" {
  value = {
    env_json   = google_secret_manager_secret.kafka["kafka-client"].id
    properties = google_secret_manager_secret.kafka["kafka-client-properties"].id
  }
}
