output "keycloak_credentials" {
  description = "keycloak admin credentials"
  sensitive   = true
  value       = module.kubernetes-keycloak-helm.credentials
}

# At this point this might be redundant, see `nebari-bot-password` in ./modules/kubernetes/keycloak-helm/variables.tf
output "keycloak_nebari_bot_password" {
  description = "keycloak nebari-bot credentials"
  sensitive   = true
  value       = var.keycloak_nebari_bot_password
}

output "existing_realm" {
  description = "value which represents whether or not an existing nebari realm has been deployed"
  value = var.existing_realm
}
