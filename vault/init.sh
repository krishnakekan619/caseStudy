#!/usr/bin/env bash
# ─── Vault Bootstrap Script ───────────────────────────────────────────────────
# Run ONCE after the Vault container first starts.
# Initialises Vault, stores the unseal keys and root token, loads policies,
# creates AppRole auth for CI and each app service, and seeds all secrets.
#
# Usage:
#   docker compose -f docker-compose.vault.yml exec \
#     -e REGISTRY_USER="user" \
#     -e REGISTRY_PASS="pass" \
#     -e REGISTRY_NS="ns" \
#     -e SONAR_TOKEN="token" \
#     -e DB_PASSWORD="password" \
#     vault sh /vault/scripts/init.sh
#
# Output:  /vault/data/vault-init.json  (KEEP THIS SAFE — contains unseal keys)

set -euo pipefail

VAULT_ADDR="http://localhost:8200"
INIT_FILE="/vault/data/vault-init.json"
export VAULT_ADDR

# --- Validation: Ensure required secrets are provided via Env Vars ---
: "${REGISTRY_USER:?REGISTRY_USER environment variable must be set}"
: "${REGISTRY_PASS:?REGISTRY_PASS environment variable must be set}"
: "${REGISTRY_NS:?REGISTRY_NS (namespace) environment variable must be set}"
: "${SONAR_TOKEN:?SONAR_TOKEN environment variable must be set}"
: "${DB_PASSWORD:?DB_PASSWORD environment variable must be set}"

# ── 1. Initialise (only if not already initialised) ──────────────────────────
IS_INIT=$(vault status -format=json 2>/dev/null | jq -r '.initialized' || echo "false")

if [ "$IS_INIT" = "true" ]; then
  echo "[init] Vault already initialised — skipping init step"
  if [ ! -f "$INIT_FILE" ]; then
    echo "[error] Vault is initialised but $INIT_FILE is missing!"
    exit 1
  fi
else
  echo "[init] Initialising Vault..."
  vault operator init -key-shares=5 -key-threshold=3 -format=json > "$INIT_FILE"
  echo "[init] Init complete. Keys written to $INIT_FILE"
fi

# ── 2. Unseal (needs 3 of 5 keys) ────────────────────────────────────────────
echo "[unseal] Unsealing Vault..."
for i in 0 1 2; do
  KEY=$(jq -r ".unseal_keys_b64[$i]" "$INIT_FILE")
  vault operator unseal "$KEY"
done

ROOT_TOKEN=$(jq -r ".root_token" "$INIT_FILE")
export VAULT_TOKEN="$ROOT_TOKEN"
echo "[unseal] Vault unsealed and authenticated as root"

# ── 3. Enable secrets engine ──────────────────────────────────────────────────
echo "[secrets] Enabling KV v2 secrets engine at 'secret/'..."
vault secrets enable -path=secret kv-v2 2>/dev/null || echo "[secrets] Already enabled"

# ── 4. Enable AppRole auth ────────────────────────────────────────────────────
echo "[auth] Enabling AppRole auth method..."
vault auth enable approle 2>/dev/null || echo "[auth] AppRole already enabled"

# ── 5. Load policies ─────────────────────────────────────────────────────────
echo "[policy] Loading policies..."
vault policy write admin   /vault/policies/admin-policy.hcl
vault policy write ci      /vault/policies/ci-policy.hcl
vault policy write app     /vault/policies/app-policy.hcl

# ── 6. Create AppRoles ────────────────────────────────────────────────────────
echo "[approle] Creating AppRoles..."
vault write auth/approle/role/ci-runner \
  policies="ci" token_ttl="1h" token_max_ttl="4h" secret_id_ttl="24h" secret_id_num_uses=0

vault write auth/approle/role/app-runtime \
  policies="app" token_ttl="12h" token_max_ttl="24h" secret_id_ttl="0" secret_id_num_uses=0

# ── 7. Retrieve AppRole credentials ──────────────────────────────────────────
echo "[approle] Retrieving role IDs and secret IDs..."
CI_ROLE_ID=$(vault read -field=role_id auth/approle/role/ci-runner/role-id)
CI_SECRET_ID=$(vault write -f -field=secret_id auth/approle/role/ci-runner/secret-id)
APP_ROLE_ID=$(vault read -field=role_id auth/approle/role/app-runtime/role-id)
APP_SECRET_ID=$(vault write -f -field=secret_id auth/approle/role/app-runtime/secret-id)

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  VAULT_ROLE_ID       = $CI_ROLE_ID"
echo "  VAULT_SECRET_ID     = $CI_SECRET_ID"
echo "  APP_VAULT_ROLE_ID   = $APP_ROLE_ID"
echo "  APP_VAULT_SECRET_ID = $APP_SECRET_ID"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── 8. Seed secrets ───────────────────────────────────────────────────────────
echo "[secrets] Seeding secret values from environment variables..."

# Container registry credentials
vault kv put secret/registry/config \
  username="$REGISTRY_USER" \
  password="$REGISTRY_PASS" \
  registry="${REGISTRY_URL:-docker.io}" \
  namespace="$REGISTRY_NS"

# SonarQube token
vault kv put secret/sonarqube/token \
  token="$SONAR_TOKEN"

# CI bundle (convenience)
vault kv put secret/ci/pipeline \
  registry_user="$REGISTRY_USER" \
  registry_pass="$REGISTRY_PASS" \
  registry_url="${REGISTRY_URL:-docker.io}" \
  registry_ns="$REGISTRY_NS" \
  sonar_token="$SONAR_TOKEN"

# Shared database credentials
vault kv put secret/db/stocksdb \
  username="stocks" \
  password="$DB_PASSWORD" \
  host="db" \
  port="5432" \
  name="stocksdb"

# App-specific configs
vault kv put secret/app/stock-listing/config \
  database_url="postgresql://stocks:$DB_PASSWORD@db:5432/stocksdb" \
  app_env="dev"

vault kv put secret/app/trade/config \
  database_url="postgresql://stocks:$DB_PASSWORD@db:5432/stocksdb" \
  app_env="dev"

# ── 9. Enable audit log ───────────────────────────────────────────────────────
echo "[audit] Enabling file audit log..."
vault audit enable file file_path=/vault/logs/audit.log 2>/dev/null || echo "[audit] Already enabled"

echo ""
echo "[done] Vault bootstrap complete."
