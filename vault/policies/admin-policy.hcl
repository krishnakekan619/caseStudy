# ─── Admin Policy ────────────────────────────────────────────────────────────
# Human operators only. Full read/write on all secret paths.
# Rotate credentials, manage AppRole, enable audit.
# Never granted to any automated system.

path "secret/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "auth/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

path "sys/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

path "audit/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}
