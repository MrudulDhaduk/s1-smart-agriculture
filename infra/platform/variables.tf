variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  type    = string
  default = "us-central1-a"
}

variable "cluster_name" {
  type    = string
  default = "s1-gke"
}

variable "repo_url" {
  description = "Git repository ArgoCD tracks (public, so no credentials are needed)."
  type        = string
  default     = "https://github.com/MrudulDhaduk/s1-smart-agriculture.git"
}

variable "repo_revision" {
  description = "Branch ArgoCD deploys. main = only reviewed, merged changes reach the cluster."
  type        = string
  default     = "main"
}
