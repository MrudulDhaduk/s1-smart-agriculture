variable "project_id" {
  description = "GCP project (for the Secret Manager copies of the connection details)."
  type        = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "aiven_project" {
  description = "Aiven project name (created with the Aiven account; Console > Projects)."
  type        = string
}

variable "service_name" {
  type    = string
  default = "s1-kafka"
}

variable "plan" {
  description = "free-0 = Aiven free tier (no card): 5 topics x 2 partitions, ~250 KiB/s, powers off after 24 h idle."
  type        = string
  default     = "free-0"
}

variable "kafka_version" {
  type    = string
  default = "4.0"
}

variable "topics" {
  description = "Topic name -> partitions. Contracts: contracts/kafka/."
  type        = map(number)
  default = {
    readings   = 2 # Telemetry Ingestion -> Flink
    results    = 2 # Flink 1-minute aggregates -> Farm Analytics
    irrigation = 2 # Irrigation Controller watering decisions -> Flink / Farm Analytics
  }
}

variable "topic_replication" {
  type    = number
  default = 2
}

variable "dedicated_user" {
  description = "true = clients use their own user 's1-app' (read/write on topics only). false = the service's admin user, if the free tier refuses extra users/ACLs."
  type        = bool
  default     = true
}

variable "team_members" {
  description = "Teammates who may read the connection details (for local development against Aiven)."
  type        = list(string)
  default     = []
}
