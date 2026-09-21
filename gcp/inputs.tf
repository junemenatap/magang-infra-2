variable "gcp_key_file" {
  description = "Path to the GCP service account credentials file"
  type        = string
}

variable "gcp_project_id" {
  description = "GCP project ID"
  type        = string
}

variable "gcp_region" {
  description = "GCP region for deployed resources"
  type        = string
}

variable "instance_name" {
  description = "Name of the Compute Engine instance"
  type        = string
}

variable "network_name" {
  description = "Name of the VPC network"
  type        = string
}

variable "public_key_path" {
  description = "Path to the SSH public key installed on the instance"
  type        = string
}

variable "ssh_user" {
  description = "SSH user configured for Ansible access"
  type        = string
}
