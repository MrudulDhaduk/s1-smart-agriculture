variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "source_dir" {
  description = "Alert function code (Person 2). Must contain main.py and requirements.txt."
  type        = string
  default     = "../../services/alert-function"
}

variable "entry_point" {
  description = "Python function the trigger calls (decorated with @functions_framework.cloud_event)."
  type        = string
  default     = "handle_alert"
}
