output "realm_id" {
  description = "Realm id used for nebari resources"
  value       = keycloak_realm.main.id
}

output "keycloak-read-only-user-credentials" {
  description = "Credentials for user that can read users/groups, but not modify them"
  sensitive   = true
  value = {
    username  = keycloak_user.read-only-user.username
    password  = var.keycloak_view_only_user_password
    client_id = "admin-cli"
    realm     = data.keycloak_realm.master.realm
  }
}
