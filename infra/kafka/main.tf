# Managed Kafka on Aiven (task e allows a managed Kafka outside GCP). Reached over the public
# internet with TLS: GKE nodes and the Dataproc VM have public IPs, so no NAT or peering.
resource "aiven_kafka" "s1" {
  project      = var.aiven_project
  service_name = var.service_name
  plan         = var.plan # cloud_name omitted: the free tier picks the cloud itself

  kafka_user_config {
    kafka_version = var.kafka_version
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
