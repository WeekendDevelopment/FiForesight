data "oci_containerengine_cluster_kube_config" "oke" {
  cluster_id = oci_containerengine_cluster.oke_cluster.id
}

provider "kubernetes" {
  host                   = oci_containerengine_cluster.oke_cluster.endpoints[0].public_endpoint
  cluster_ca_certificate = base64decode(yamldecode(data.oci_containerengine_cluster_kube_config.oke.content)["clusters"][0]["cluster"]["certificate-authority-data"])
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    args        = ["ce", "cluster", "generate-token", "--cluster-id", oci_containerengine_cluster.oke_cluster.id, "--region", var.region]
    command     = "oci"
  }
}

resource "kubernetes_secret_v1" "ghcr_secret" {
  metadata {
    name      = "ghcr-secret"
    namespace = "default"
  }

  type = "kubernetes.io/dockerconfigjson"

  data = {
    ".dockerconfigjson" = jsonencode({
      auths = {
        "ghcr.io" = {
          auth = base64encode("${var.github_username}:${var.github_pat}")
        }
      }
    })
  }
}
