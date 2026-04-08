# ─── CI/CD Pipeline Policy ───────────────────────────────────────────────────
# Granted to the GitHub Actions runner via AppRole.
# Read-only access to CI secrets: Harbor credentials, SonarQube token.

# KV v2 Data Path
path "secret/data/ci/*" {
  capabilities = ["read", "list"]
}

# KV v2 Metadata Path (required for path validation)
path "secret/metadata/ci/*" {
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
