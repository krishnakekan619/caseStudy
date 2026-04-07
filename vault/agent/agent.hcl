# ─── Vault Agent Configuration ───────────────────────────────────────────────
# Vault Agent runs as a sidecar alongside each app container.
# It authenticates to Vault using AppRole, fetches secrets, writes them to
# a shared volume as environment files that the app reads at startup.
#
# The app container waits for /vault/secrets/.ready before starting
# (enforced by the entrypoint wrapper in each service Dockerfile).

vault {
  address = "http://vault:8200"
}

# AppRole authentication — role_id and secret_id are injected as env vars
# by Docker Compose from the host .env file (never baked into the image).
auto_auth {
  method "approle" {
    config = {
      role_id_env_var    = "VAULT_ROLE_ID"
      secret_id_env_var  = "VAULT_SECRET_ID"
      secret_id_response_wrapping_path = "auth/approle/role/app-runtime/secret-id"
    }
  }

  sink "file" {
    config = {
      path = "/vault/secrets/.vault-token"
    }
  }
}

# Write DB credentials as a shell-sourceable env file
template {
  contents = <<EOT
{{- with secret "secret/data/db/stocksdb" -}}
export DATABASE_URL="postgresql://{{ .Data.data.username }}:{{ .Data.data.password }}@{{ .Data.data.host }}:{{ .Data.data.port }}/{{ .Data.data.name }}"
export DB_PASSWORD="{{ .Data.data.password }}"
{{- end }}
EOT
  destination = "/vault/secrets/db.env"
  perms       = "0600"
}

# Signal readiness after all templates are rendered
template {
  contents    = "ready"
  destination = "/vault/secrets/.ready"
}
