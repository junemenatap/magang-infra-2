# VPC
resource "google_compute_network" "vpc_network" {
    name = var.network_name
    auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "network_subnet" {
  name          = "magang-subnet-us"
  ip_cidr_range = "10.0.1.0/24"
  region        = "${var.gcp_region}"
  network       = google_compute_network.vpc_network.id
}

# VM
resource "google_compute_instance" "vm_instance" {
    name = var.instance_name
    machine_type = "e2-standard-2" 
    zone = "${var.gcp_region}-b"
    tags = ["allow-ssh"]

    boot_disk {
        initialize_params {
            image = "debian-cloud/debian-11"
        }
    }

    network_interface {
        network = google_compute_network.vpc_network.name
        subnetwork = google_compute_subnetwork.network_subnet.name
        access_config {
            # no conf = public ip
        }
    }

    # Conn to Ansible
    metadata = {
        ssh-keys = "${var.ssh_user}:${file(var.public_key_path)}"
    }

    labels = {
        environment = "magang"
        managed_by = "terraform"
    }

}

# SSH for Ansible
resource "google_compute_firewall" "allow_ssh" {
    name = "allow-ssh"
    network = google_compute_network.vpc_network.name

    allow {
        protocol = "tcp"
        ports = ["22", "80", "443", "8000"]
    }

    source_ranges = ["0.0.0.0/0"]
    target_tags = ["allow-ssh"]
}

resource "local_file" "gcp_inventory" {
  content = <<EOT
[gcp_servers]
gcp_vm ansible_host=${google_compute_instance.vm_instance.network_interface.0.access_config.0.nat_ip} ansible_user=${var.ssh_user} ansible_ssh_private_key_file=./gcp/gcp_ssh_key
EOT
  filename = "../ansible/inventories/gcp.ini"
}
