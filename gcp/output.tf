output "gcp_vm_public_ip" {
    description = "GCP Instance public IP"
    value = google_compute_instance.vm_instance.network_interface.0.access_config.0.nat_ip
}