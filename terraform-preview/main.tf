terraform {
  cloud {
    organization = "weekend-development"
    workspaces {
      name = "fi-foresight-oracle-preview"
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

# VCN
resource "oci_core_vcn" "fiforesight-preview_vcn" {
  cidr_block     = "10.0.0.0/16"
  compartment_id = var.compartment_id
  display_name   = "fiforesight-preview-vcn"
  dns_label      = "fifoprev"
}

# Internet Gateway
resource "oci_core_internet_gateway" "igw" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.fiforesight-preview_vcn.id
  display_name   = "fiforesight-preview-igw"
}

# Route Table
resource "oci_core_route_table" "rt" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.fiforesight-preview_vcn.id
  display_name   = "fiforesight-preview-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.igw.id
  }
}

# Security List
resource "oci_core_security_list" "sl" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.fiforesight-preview_vcn.id
  display_name   = "fiforesight-preview-sl"

  ingress_security_rules {
    protocol = "6" # TCP
    source   = "0.0.0.0/0"
    tcp_options {
      min = 22
      max = 22
    }
  }

  ingress_security_rules {
    protocol = "6" # TCP
    source   = "0.0.0.0/0"
    tcp_options {
      min = 443
      max = 443
    }
  }

  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
}

# Subnet
resource "oci_core_subnet" "subnet" {
  cidr_block        = "10.0.1.0/24"
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.fiforesight-preview_vcn.id
  route_table_id    = oci_core_route_table.rt.id
  security_list_ids = [oci_core_security_list.sl.id]
  display_name      = "fiforesight-preview-subnet"
}

# Compute Instance
resource "oci_core_instance" "vm" {
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[var.availability_domain_index].name
  compartment_id      = var.compartment_id
  shape               = "VM.Standard.E2.1.Micro" # Always Free
  display_name        = "fiforesight-preview-vm"

  create_vnic_details {
    subnet_id        = oci_core_subnet.subnet.id
    assign_public_ip = true
    display_name     = "primary-vnic"
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu.images[0].id
    boot_volume_size_in_gbs = 50
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data           = base64encode(file("${path.module}/scripts/setup.sh"))
  }
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_id
}

data "oci_core_images" "ubuntu" {
  compartment_id           = var.compartment_id
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "22.04"
  shape                    = "VM.Standard.E2.1.Micro"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}
