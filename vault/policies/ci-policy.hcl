# ─── CI/CD Pipeline Policy ───────────────────────────────────────────────────
# Granted to the GitHub Actions runner via AppRole.
# Read-only access to CI secrets: Harbor credentials, SonarQube token.
# No ability to write or delete secrets.

path "secret/data/ci/*" {
  capabilities = ["read", "list"]
}

# Allow reading Container Registry credentials
path "secret/data/registry/*" {
  capabilities = ["read"]
}

# Allow reading SonarQube token
path "secret/data/sonarqube/*" {
  capabilities = ["read"]
}

# Allow the runner to renew its own token
path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}
