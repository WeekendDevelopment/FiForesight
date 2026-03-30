variable "tenancy_ocid" {
  description = "OCI tenancy OCID"
  type        = string
}

variable "user_ocid" {
  description = "OCI user OCID"
  type        = string
}

variable "fingerprint" {
  description = "OCI API key fingerprint"
  type        = string
}

variable "private_key" {
  description = "OCI API private key content"
  type        = string
  sensitive   = true
}

variable "region" {
  description = "OCI region"
  type        = string
  default     = "us-ashburn-1"
}

variable "compartment_id" {
  description = "OCI compartment OCID"
  type        = string
}

variable "ssh_public_key" {
  description = "SSH public key for worker nodes"
  type        = string
}

variable "kubernetes_version" {
  description = "Kubernetes version for OKE cluster"
  type        = string
  default     = "v1.31.1" # Update to a supported version in your region
}

variable "node_shape" {
  description = "Shape for the worker nodes"
  type        = string
  default     = "VM.Standard.E4.Flex"
}

variable "node_ocpus" {
  description = "Number of OCPUs for the worker nodes"
  type        = number
  default     = 1
}

variable "node_memory_in_gbs" {
  description = "Memory in GBs for the worker nodes"
  type        = number
  default     = 16
}

variable "github_username" {
  description = "GitHub username for GHCR"
  type        = string
}

variable "github_pat" {
  description = "GitHub Personal Access Token for GHCR"
  type        = string
  sensitive   = true
}
