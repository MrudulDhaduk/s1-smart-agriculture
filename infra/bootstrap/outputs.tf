output "state_bucket" {
  description = "Pass to every stack: terraform init -backend-config=bucket=<this>"
  value       = google_storage_bucket.tfstate.name
}

output "project_number" {
  value = data.google_project.this.number
}
