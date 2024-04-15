module "kubernetes-keycloak-helm" {
  source = "./modules/kubernetes/keycloak-helm"

  namespace = var.environment

  external-url = var.endpoint

  nebari-bot-password = var.keycloak_nebari_bot_password

  initial_root_password = var.initial_root_password

  overrides = var.overrides

  node_group = var.node_group
}
