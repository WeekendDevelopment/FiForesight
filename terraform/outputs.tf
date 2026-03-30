output "cluster_id" {
  description = "The OCID of the OKE cluster"
  value       = oci_containerengine_cluster.oke_cluster.id
}

output "vcn_id" {
  description = "The OCID of the VCN"
  value       = oci_core_vcn.oke_vcn.id
}

output "worker_subnet_id" {
  description = "The OCID of the worker subnet"
  value       = oci_core_subnet.worker_subnet.id
}

output "node_pool_id" {
  description = "The OCID of the OKE node pool"
  value       = oci_containerengine_node_pool.oke_node_pool.id
}

output "kubeconfig_command" {
  description = "Command to generate kubeconfig for the cluster"
  value       = "oci ce cluster create-kubeconfig --cluster-id ${oci_containerengine_cluster.oke_cluster.id} --file $HOME/.kube/config --region ${var.region} --token-version 2.0.0"
}
