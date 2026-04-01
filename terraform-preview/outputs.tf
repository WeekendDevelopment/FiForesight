output "public_ip" {
  description = "The public IP of the compute instance"
  value       = oci_core_instance.vm.public_ip
}

output "ssh_command" {
  description = "Command to SSH into the instance"
  value       = "ssh -i <path-to-private-key> ubuntu@${oci_core_instance.vm.public_ip}"
}
