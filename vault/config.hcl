# ─── HashiCorp Vault Server Configuration ────────────────────────────────────
# Used by docker-compose.vault.yml

# Storage backend — file-based (swap for Consul/Raft in real HA setups)
storage "file" {
  path = "/vault/data"
}

# TCP listener — plain HTTP inside Docker network (TLS terminated at reverse proxy)
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = true           # Enable TLS in production with a proper cert
}

# Allow Vault UI
ui = true

# Cluster address (used when running Vault in HA/Raft mode)
api_addr     = "http://vault:8200"
cluster_addr = "http://vault:8201"

# Audit log — write every request/response to a file
# Enable after init: vault audit enable file file_path=/vault/logs/audit.log
