terraform {
  cloud {
    organization = "weekend-development"
    workspaces {
      name = "fi-foresight-oracle"
    }
  }
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 4.0.0"
    }
  }
}

provider "oci" {
  tenancy_ocid = var.tenancy_ocid
  user_ocid    = var.user_ocid
  fingerprint  = var.fingerprint
  private_key  = var.private_key
  region       = var.region
}

# VCN for OKE
resource "oci_core_vcn" "oke_vcn" {
  cidr_block     = "10.0.0.0/16"
  compartment_id = var.compartment_id
  display_name   = "fiforesight-oke-vcn"
  dns_label      = "okevcn"
}

# Internet Gateway
resource "oci_core_internet_gateway" "oke_igw" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.oke_vcn.id
  display_name   = "fiforesight-oke-igw"
}

# Route Table for Public Subnets
resource "oci_core_route_table" "oke_rt" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.oke_vcn.id
  display_name   = "fiforesight-oke-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.oke_igw.id
  }
}

# Security List for Worker Nodes
resource "oci_core_security_list" "worker_sec_list" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.oke_vcn.id
  display_name   = "fiforesight-worker-seclist"

  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }

  ingress_security_rules {
    protocol = "all"
    source   = "10.0.0.0/16" # Allow intra-VCN traffic
  }

  ingress_security_rules {
    protocol = "6" # SSH
    source   = "0.0.0.0/0"
    tcp_options {
      min = 22
      max = 22
    }
  }
}

# Subnet for Load Balancer
resource "oci_core_subnet" "lb_subnet" {
  cidr_block        = "10.0.20.0/24"
  display_name      = "fiforesight-lb-subnet"
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.oke_vcn.id
  route_table_id    = oci_core_route_table.oke_rt.id
  security_list_ids = [oci_core_security_list.worker_sec_list.id] # Usually has its own SL, but reusable for now
}

# Subnet for Worker Nodes
resource "oci_core_subnet" "worker_subnet" {
  cidr_block        = "10.0.10.0/24"
  display_name      = "fiforesight-worker-subnet"
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.oke_vcn.id
  route_table_id    = oci_core_route_table.oke_rt.id
  security_list_ids = [oci_core_security_list.worker_sec_list.id]
}

# OKE Cluster
resource "oci_containerengine_cluster" "oke_cluster" {
  compartment_id     = var.compartment_id
  kubernetes_version = var.kubernetes_version
  name               = "fiforesight-cluster"
  vcn_id             = oci_core_vcn.oke_vcn.id

  options {
    service_lb_subnet_ids = [oci_core_subnet.lb_subnet.id]
    add_ons {
      is_kubernetes_dashboard_enabled = false
      is_tiller_enabled               = false
    }
  }
}

# OKE Node Pool
resource "oci_containerengine_node_pool" "oke_node_pool" {
  cluster_id         = oci_containerengine_cluster.oke_cluster.id
  compartment_id     = var.compartment_id
  kubernetes_version = var.kubernetes_version
  name               = "fiforesight-nodepool"
  node_shape         = var.node_shape

  node_shape_config {
    memory_in_gbs = var.node_memory_in_gbs
    ocpus         = var.node_ocpus
  }

  node_source_details {
    image_id    = data.oci_core_images.oracle_linux.images[0].id
    source_type = "IMAGE"
  }

  node_config_details {
    placement_configs {
      availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
      subnet_id           = oci_core_subnet.worker_subnet.id
    }
    size = 1 # Number of nodes
  }

  ssh_public_key = var.ssh_public_key
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_id
}

data "oci_core_images" "oracle_linux" {
  compartment_id           = var.compartment_id
  operating_system         = "Oracle Linux"
  operating_system_version = "8"
  shape                    = var.node_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}
