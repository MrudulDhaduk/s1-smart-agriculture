output "function" {
  value = google_cloudfunctions2_function.alert.name
}

output "logs" {
  value = "gcloud functions logs read alert-service --region ${var.region} --gen2 --limit 50"
}

output "test_publish" {
  value = "gcloud pubsub topics publish alerts --message \"$(cat contracts/pubsub/alert.example.json)\" --attribute type=DRY_SOIL"
}
