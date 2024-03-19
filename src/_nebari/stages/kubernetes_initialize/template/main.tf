module "kubernetes-initialization" {
  source = "./modules/initialization"

  namespace = var.environment
  secrets   = []
}

module "kubernetes-autoscaling" {
  count = var.cloud_provider == "aws" ? 1 : 0

  source = "./modules/cluster-autoscaler"

  namespace = var.environment

  aws_region   = var.aws_region
  cluster-name = local.cluster_name
}

module "traefik-crds" {
  source = "./modules/traefik_crds"
}

module "nvidia-driver-installer" {
  count = var.gpu_enabled ? 1 : 0

  source = "./modules/nvidia-installer"

  cloud_provider       = var.cloud_provider
  gpu_enabled          = var.gpu_enabled
  gpu_node_group_names = var.gpu_node_group_names
}

module "node-termination-handler" {
  source = "./modules/node-termination-handler"

  namespace = var.environment
  aws_region   = var.aws_region
  cluster_name = local.cluster_name
  #name = var.name
}

module "s3" {
  source = "./modules/s3"
  cluster_name = local.cluster_name
  #region = var.region
}

