# Managed SQL (storage product 1 of 3): relational data of Farm Registry and Sensor Registry
# (farms -> plots -> sensors, with foreign keys). One small instance, one database per service.

# Cloud SQL instance names stay reserved for a while after deletion, so a rebuild needs a
# fresh name.
resource "random_id" "sql_suffix" {
  byte_length = 2
}

resource "google_sql_database_instance" "main" {
  name             = "s1-sql-${random_id.sql_suffix.hex}"
  region           = var.region
  database_version = "POSTGRES_16"

  deletion_protection = false # allow terraform destroy

  settings {
    # Postgres 16 defaults to ENTERPRISE_PLUS, which has no small machine types.
    edition           = "ENTERPRISE"
    tier              = "db-f1-micro" # shared core, cheapest tier
    availability_type = "ZONAL"
    activation_policy = var.sql_activation_policy

    disk_type       = "PD_HDD"
    disk_size       = 10
    disk_autoresize = false

    deletion_protection_enabled = false

    location_preference {
      zone = var.zone # same zone as GKE: no cross-zone traffic
    }

    backup_configuration {
      enabled = false # demo data only
    }

    # Public IP but no authorised networks: nothing can connect directly. Pods connect
    # through the Cloud SQL connector, which is authorised by IAM (roles/cloudsql.client)
    # and always uses TLS. This avoids private service access peering.
    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    # Log in with the pod's Google identity instead of a password.
    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }
  }
}

resource "google_sql_database" "registry" {
  for_each = toset(["farm_registry", "sensor_registry"])

  name     = each.value
  instance = google_sql_database_instance.main.name
  # The database is deleted together with the instance; dropping it on its own fails
  # while the service user still owns tables in it.
  deletion_policy = "ABANDON"
}

# One IAM database user per registry service (its Google service account, no password).
# cloudsqlsuperuser lets the service create its own tables on first start. It is broader
# than a per-database GRANT, but a GRANT needs a SQL session, which Terraform cannot open
# without extra tooling.
resource "google_sql_user" "registry" {
  for_each = toset(["farm-registry", "sensor-registry"])

  instance       = google_sql_database_instance.main.name
  type           = "CLOUD_IAM_SERVICE_ACCOUNT"
  name           = trimsuffix(google_service_account.sa[each.value].email, ".gserviceaccount.com")
  database_roles = ["cloudsqlsuperuser"]
  # Postgres refuses to drop a user that owns tables; the instance delete removes it anyway.
  deletion_policy = "ABANDON"
}
