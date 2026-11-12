variable "project_id" {
  description = "GCP project that hosts the whole S1 stack."
  type        = string
}

variable "region" {
  description = "Region for every regional resource. Firestore's location follows it and can never change."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Zone for zonal resources (Cloud SQL, and the GKE/Dataproc clusters in infra/cluster)."
  type        = string
  default     = "us-central1-a"

  validation {
    condition     = startswith(var.zone, var.region)
    error_message = "zone must be inside region."
  }
}

variable "team_members" {
  description = "Teammates' Google accounts, e.g. [\"user:someone@gmail.com\"]. Keep the real list in terraform.tfvars (git-ignored)."
  type        = list(string)
  default     = []
}

variable "sql_activation_policy" {
  description = "ALWAYS = Cloud SQL running. NEVER = stopped between work sessions (only storage is billed)."
  type        = string
  default     = "ALWAYS"

  validation {
    condition     = contains(["ALWAYS", "NEVER"], var.sql_activation_policy)
    error_message = "Use ALWAYS or NEVER."
  }
}
