# ─── Application Runtime Policy ──────────────────────────────────────────────
# Granted to each microservice container via AppRole at startup.
# Services can only read their own secrets and the shared DB credentials.
# No cross-service secret access.

# Shared DB credentials (all services need DB access)
path "secret/data/db/*" {
  capabilities = ["read"]
}

# Stock Listing service — its own secrets only
path "secret/data/app/stock-listing/*" {
  capabilities = ["read"]
}

# Trade service — its own secrets only
path "secret/data/app/trade/*" {
  capabilities = ["read"]
}

# Allow services to renew their own lease/token
path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}
