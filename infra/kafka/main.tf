# Managed Kafka on Aiven (task e allows a managed Kafka outside GCP). Reached over the public
# internet with TLS: GKE nodes and the Dataproc VM have public IPs, so no NAT or peering.

# Which clouds offer the chosen plan for this project. Without an explicit cloud, Aiven would use
# the project's default cloud, which may not offer the free plan at all ("Invalid cloud").
data "aiven_service_plan_list" "kafka" {
  project      = var.aiven_project
  service_type = "kafka"
}

locals {
  plan_clouds = sort(flatten([
    for p in data.aiven_service_plan_list.kafka.service_plans :
    p.regions != null ? keys(p.regions) : [] if p.service_plan == var.plan
  ]))
  # First preferred cloud that offers the plan (closest to GKE/Dataproc in us-central1), else any.
  cloud_name = var.cloud_name != null ? var.cloud_name : try(
    [for c in var.preferred_clouds : c if contains(local.plan_clouds, c)][0],
    local.plan_clouds[0],
    "",
  )
}

resource "aiven_kafka" "s1" {
  project      = var.aiven_project
  service_name = var.service_name
  plan         = var.plan
  cloud_name   = local.cloud_name

  kafka_user_config {
    kafka_version = var.kafka_version
  }

  lifecycle {
    precondition {
      condition     = contains(local.plan_clouds, local.cloud_name)
      error_message = "Plan ${var.plan} is not offered in cloud '${local.cloud_name}' for this project. Offered: ${join(", ", local.plan_clouds)}"
    }
  }
}

resource "aiven_kafka_topic" "t" {
  for_each = var.topics

  project      = var.aiven_project
  service_name = aiven_kafka.s1.service_name
  topic_name   = each.key
  partitions   = each.value
  replication  = var.topic_replication
}

# Least privilege: the apps get a user that can only read/write topics, not administer Kafka.
resource "aiven_kafka_user" "app" {
  count = var.dedicated_user ? 1 : 0

  project      = var.aiven_project
  service_name = aiven_kafka.s1.service_name
  username     = "s1-app"
}

resource "aiven_kafka_acl" "app" {
  count = var.dedicated_user ? 1 : 0

  project      = var.aiven_project
  service_name = aiven_kafka.s1.service_name
  username     = aiven_kafka_user.app[0].username
  topic        = "*"
  permission   = "readwrite"
}

# CA certificate that signed the Kafka brokers' certificates.
data "aiven_project" "s1" {
  project = var.aiven_project
}

locals {
  # Client-certificate (mutual TLS) login: Aiven's default method on every plan.
  cert      = var.dedicated_user ? aiven_kafka_user.app[0].access_cert : aiven_kafka.s1.kafka[0].access_cert
  key       = var.dedicated_user ? aiven_kafka_user.app[0].access_key : aiven_kafka.s1.kafka[0].access_key
  ca        = data.aiven_project.s1.ca_cert
  bootstrap = "${aiven_kafka.s1.service_host}:${aiven_kafka.s1.service_port}"

  # For Python services (confluent-kafka / librdkafka): one env var per key.
  client_env = {
    KAFKA_BOOTSTRAP_SERVERS = local.bootstrap
    KAFKA_SECURITY_PROTOCOL = "SSL"
    KAFKA_SSL_CA_PEM        = local.ca
    KAFKA_SSL_CERT_PEM      = local.cert
    KAFKA_SSL_KEY_PEM       = local.key
  }

  # For Java / Flink (kafka-clients >= 2.7 accepts PEM inline). In a .properties file "\n"
  # inside a value is read back as a newline, so each PEM fits on one line.
  java_properties = join("\n", [
    "bootstrap.servers=${local.bootstrap}",
    "security.protocol=SSL",
    "ssl.truststore.type=PEM",
    "ssl.truststore.certificates=${replace(trimspace(local.ca), "\n", "\\n")}",
    "ssl.keystore.type=PEM",
    "ssl.keystore.certificate.chain=${replace(trimspace(local.cert), "\n", "\\n")}",
    "ssl.keystore.key=${replace(trimspace(local.key), "\n", "\\n")}",
    "",
  ])
}
