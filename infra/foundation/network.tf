# Our own VPC instead of the "default" network, so the network itself is defined in code.
# GKE and Dataproc nodes get public IPs, which gives them internet access (Aiven Kafka,
# Docker Hub) without Cloud NAT, which would be an extra hourly charge.
resource "google_compute_network" "vpc" {
  name                    = "s1-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main" {
  name          = "s1-${var.region}"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.10.0.0/20" # nodes (GKE + Dataproc)

  # Lets VMs reach Google APIs over Google's network; free.
  private_ip_google_access = true

  # VPC-native GKE: pods and Services get IPs from these ranges.
  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.20.0.0/16"
  }
  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.30.0.0/20"
  }
}

# A custom VPC starts with no firewall rules, so allow traffic between our own VMs
# (Dataproc needs it; GKE adds its own rules automatically).
resource "google_compute_firewall" "internal" {
  name    = "s1-allow-internal"
  network = google_compute_network.vpc.name

  source_ranges = [google_compute_subnetwork.main.ip_cidr_range]

  allow {
    protocol = "tcp"
  }
  allow {
    protocol = "udp"
  }
  allow {
    protocol = "icmp"
  }
}
