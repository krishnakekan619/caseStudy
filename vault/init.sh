#!/usr/bin/env bash
# ─── Vault Bootstrap Script ───────────────────────────────────────────────────
# Run ONCE after the Vault container first starts.
# Initialises Vault, stores the unseal keys and root token, loads policies,
# creates AppRole auth for CI and each app service, and seeds all secrets.
#
# Usage:
#   docker compose -f docker-compose.vault.yml exec vault sh /vault/scripts/init.sh
#
# Output:  vault/vault-init.json  (KEEP THIS SAFE — contains unseal keys)

set -euo pipefail

VAULT_ADDR="http://localhost:8200"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INIT_FILE="${SCRIPT_DIR}/vault-init.json"

export VAULT_ADDR

# ── 1. Initialise (only if not already initialised) ──────────────────────────
if vault status 2>&1 | grep -q "Initialized.*true"; then
  echo "[init] Vault already initialised — skipping init step"
else
  echo "[init] Initialising Vault..."
  vault operator init \
    -key-shares=5 \
    -key-threshold=3 \
    -format=json > "$INIT_FILE"
  echo "[init] Init complete. Keys written to vault-init.json"
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

# CI runner role — short TTL tokens, no secret renewal beyond pipeline lifetime
vault write auth/approle/role/ci-runner \
  policies="ci" \
  token_ttl="1h" \
  token_max_ttl="4h" \
  secret_id_ttl="24h" \
  secret_id_num_uses=0

# App runtime role — longer TTL for service lifetime
vault write auth/approle/role/app-runtime \
  policies="app" \
  token_ttl="12h" \
  token_max_ttl="24h" \
  secret_id_ttl="0" \
  secret_id_num_uses=0

# ── 7. Retrieve AppRole credentials ──────────────────────────────────────────
echo "[approle] Retrieving role IDs and secret IDs..."

CI_ROLE_ID=$(vault read -field=role_id auth/approle/role/ci-runner/role-id)
CI_SECRET_ID=$(vault write -f -field=secret_id auth/approle/role/ci-runner/secret-id)

APP_ROLE_ID=$(vault read -field=role_id auth/approle/role/app-runtime/role-id)
APP_SECRET_ID=$(vault write -f -field=secret_id auth/approle/role/app-runtime/secret-id)

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Store these two values as GitHub Actions secrets:"
echo "  VAULT_ROLE_ID   = $CI_ROLE_ID"
echo "  VAULT_SECRET_ID = $CI_SECRET_ID"
echo ""
echo "  Store these in app container env / .env:"
echo "  APP_VAULT_ROLE_ID   = $APP_ROLE_ID"
echo "  APP_VAULT_SECRET_ID = $APP_SECRET_ID"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── 8. Seed secrets ───────────────────────────────────────────────────────────
echo "[secrets] Seeding secret values..."

# Harbor registry credentials
vault kv put secret/harbor/registry \
  username="robot\$stocks" \
  password="CHANGE_ME_harbor_robot_secret" \
  registry="myregistry.local:5000"

# SonarQube token
vault kv put secret/sonarqube/token \
  token="CHANGE_ME_sonar_token"

# CI bundle (convenience — all CI secrets in one path)
vault kv put secret/ci/pipeline \
  harbor_username="robot\$stocks" \
  harbor_password="CHANGE_ME_harbor_robot_secret" \
  harbor_registry="myregistry.local:5000" \
  sonar_token="CHANGE_ME_sonar_token"

# Shared database credentials
vault kv put secret/db/stocksdb \
  username="stocks" \
  password="CHANGE_ME_db_password" \
  host="db" \
  port="5432" \
  name="stocksdb"

# Stock Listing service secrets
vault kv put secret/app/stock-listing/config \
  database_url="postgresql://stocks:CHANGE_ME_db_password@db:5432/stocksdb" \
  app_env="dev"

# Trade service secrets
vault kv put secret/app/trade/config \
  database_url="postgresql://stocks:CHANGE_ME_db_password@db:5432/stocksdb" \
  app_env="dev"

# ── 9. Enable audit log ───────────────────────────────────────────────────────
echo "[audit] Enabling file audit log..."
vault audit enable file file_path=/vault/logs/audit.log 2>/dev/null || echo "[audit] Already enabled"

echo ""
echo "[done] Vault bootstrap complete."
echo "       Root token: $ROOT_TOKEN"
echo "       Unseal keys saved to: $INIT_FILE"
echo "       !! Store vault-init.json in a secure offline location !!"
