variable "project_id" {
  description = "GCP project that hosts the whole S1 stack."
  type        = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"

  validation {
    condition     = startswith(var.zone, var.region)
    error_message = "zone must be inside region."
  }
}

# --- GKE ---

variable "cluster_name" {
  type    = string
  default = "s1-gke"
}

variable "machine_type" {
  description = "GKE node size. e2-standard-2 = 2 vCPU / 8 GB, enough for ArgoCD + Prometheus next to the app."
  type        = string
  default     = "e2-standard-2"
}

variable "min_nodes" {
  type    = number
  default = 2
}

variable "max_nodes" {
  description = "Cluster autoscaler ceiling: the cost cap while HPAs scale pods out."
  type        = number
  default     = 4
}

variable "spot_nodes" {
  description = "Spot VMs are ~60-90% cheaper but can be reclaimed at any time. Keep false for the demo."
  type        = bool
  default     = false
}

# --- Dataproc (Flink) ---

variable "enable_dataproc" {
  description = "Create the Dataproc Flink cluster. Turn off when nobody works on the Flink job."
  type        = bool
  default     = true
}

variable "dataproc_machine_type" {
  description = "Single Dataproc node running YARN + Flink JobManager and TaskManager."
  type        = string
  default     = "e2-standard-4"
}

variable "dataproc_idle_delete_ttl" {
  description = "Dataproc deletes itself after this long with no job running (null = never)."
  type        = string
  default     = "7200s"
}
