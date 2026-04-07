# Complete DevOps Guide — Stocks App

Step-by-step guide covering everything from pushing code to a fresh repository
through branching strategy, environment promotion (Dev → Stage → Prod),
Docker deployment, and validating every pipeline stage.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Repository Setup (first time)](#2-repository-setup-first-time)
3. [Branching Strategy](#3-branching-strategy)
4. [Infrastructure Bootstrap](#4-infrastructure-bootstrap)
5. [Vault Bootstrap](#5-vault-bootstrap)
6. [GitHub Repository Configuration](#6-github-repository-configuration)
7. [Local Development Workflow](#7-local-development-workflow)
8. [Promote to Dev](#8-promote-to-dev)
9. [Promote to Stage](#9-promote-to-stage)
10. [Promote to Production](#10-promote-to-production)
11. [Validating Every Pipeline Stage](#11-validating-every-pipeline-stage)
12. [Rollback Procedures](#12-rollback-procedures)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Prerequisites

### Software required on the host machine

```bash
# Verify versions before starting
docker --version          # Docker Engine 24+
docker compose version    # Docker Compose v2.20+
git --version             # Git 2.40+
gh --version              # GitHub CLI 2.40+ (optional but recommended)
curl --version
jq --version              # used in validation scripts
```

Install GitHub CLI if missing:
```bash
# Linux
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
  https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list
sudo apt update && sudo apt install gh

# macOS
brew install gh

# Windows (choco)
choco install gh
```

### Ports that must be free on the host

| Port | Service |
|------|---------|
| 5000 | Harbor registry |
| 8080 | Harbor portal UI |
| 8200 | Vault UI + API |
| 9000 | SonarQube |
| 8000 / 8001 | Dev app (stock-listing / trade) |
| 8010 / 8011 | Stage app |
| 8020 / 8021 | Prod app |
| 5432 / 5433 / 5434 | Dev / Stage / Prod PostgreSQL |

---

## 2. Repository Setup (first time)

### 2a. Create the GitHub repository

```bash
# Option A — using GitHub CLI (recommended)
gh auth login
gh repo create stocks-app \
  --private \
  --description "Stocks microservices app with full DevOps pipeline" \
  --clone

cd stocks-app
```

```bash
# Option B — manual
# 1. Go to https://github.com/new and create a private repo named stocks-app
# 2. Then clone:
git clone https://github.com/<your-org>/stocks-app.git
cd stocks-app
```

### 2b. Copy project files into the repo

```bash
# If you have the project files in a separate directory:
cp -r /path/to/caseStudy/. .

# Verify structure
ls -la
```

Expected top-level:
```
.env.example
.gitignore
.github/
db/
docker-compose.infra.yml
docker-compose.vault.yml
docker-compose.dev.yml
docker-compose.stage.yml
docker-compose.prod.yml
services/
vault/
README.md
DEVOPS_GUIDE.md
```

### 2c. Set up Git identity and initial commit

```bash
git config user.name  "Your Name"
git config user.email "you@example.com"

# Initialise branching model
git checkout -b main

# Stage all project files
git add .

# Verify nothing sensitive is staged
git status
# vault/vault-init.json must NOT appear (protected by .gitignore)
# .env must NOT appear (protected by .gitignore)

git commit -m "chore: initial project scaffold — stocks microservices CI/CD"
git push -u origin main
```

### 2d. Create the develop branch

```bash
git checkout -b develop
git push -u origin develop
```

---

## 3. Branching Strategy

This project uses a **GitFlow-inspired model** with direct environment mapping.

```
                              ┌─────────────────────────────────┐
                              │         BRANCH MODEL            │
                              └─────────────────────────────────┘

  feature/xxx ──► develop ──────────────────────────────────────► main
                    │                                               ▲
                    │  (when ready for QA)                         │
                    ├──► release/1.x.x ───────────────────────────┤
                    │         │                                     │
                    │         │  (tag v1.x.x on main)              │
                    │         │                                     │
 hotfix/yyy ────────┼─────────┼────────────────────────────────────┘
                    │         │
                    └─────────┘ (hotfix merged back to develop too)

Branch          Deploys to     Trigger
──────────────────────────────────────────────────────────────
develop         Dev            push to develop
release/x.y.z   Stage          push to release/**
v*.*.*  (tag)   Prod           git tag push
feature/*       nowhere        PR only — runs test+sonar, no deploy
hotfix/*        nowhere        PR only — runs test+sonar, no deploy
main            nowhere        merge target only, no direct push
```

### Branch naming convention

| Branch type | Pattern | Example |
|-------------|---------|---------|
| Feature | `feature/<ticket>-<short-desc>` | `feature/STOCK-42-add-dividend-endpoint` |
| Bug fix | `fix/<ticket>-<short-desc>` | `fix/STOCK-99-sell-validation` |
| Release | `release/<major>.<minor>.<patch>` | `release/1.4.0` |
| Hotfix | `hotfix/<ticket>-<short-desc>` | `hotfix/STOCK-201-prod-crash` |
| Chore | `chore/<desc>` | `chore/upgrade-dependencies` |

### Commit message convention (Conventional Commits)

```
<type>(<scope>): <short description>

Types: feat | fix | chore | docs | refactor | test | perf | ci
Scope: stock-listing | trade | db | vault | pipeline | deps

Examples:
  feat(trade): add stop-loss order type
  fix(stock-listing): handle null sector in filter query
  chore(deps): bump fastapi to 0.112.0
  ci(pipeline): add path filter for db/ directory
```

---

## 4. Infrastructure Bootstrap

Run this **once** when setting up a new host. All services run as Docker containers.

### 4a. Create the .env file

```bash
cp .env.example .env
```

Edit `.env` — fill in these values now (Vault values come after step 5):

```bash
# GitHub
GITHUB_ORG=your-github-org-or-username
GITHUB_REPO=stocks-app
RUNNER_TOKEN=                    # get from step 6a

# Vault address (runner must reach this)
VAULT_ADDR=http://vault:8200

# Leave these blank until vault/init.sh prints them (step 5)
VAULT_ROLE_ID=
VAULT_SECRET_ID=
APP_VAULT_ROLE_ID=
APP_VAULT_SECRET_ID=
```

### 4b. Start all infrastructure

```bash
docker compose \
  -f docker-compose.infra.yml \
  -f docker-compose.vault.yml \
  up -d

# Watch all containers come up
docker compose \
  -f docker-compose.infra.yml \
  -f docker-compose.vault.yml \
  ps
```

Expected output (all containers `Up (healthy)` or `Up`):
```
NAME                STATUS
harbor-db           Up (healthy)
harbor-core         Up
harbor-registry     Up
harbor-portal       Up
sonarqube-db        Up (healthy)
sonarqube           Up
trivy               Up
github-runner       Up
vault               Up (healthy)
```

### 4c. Wait for services to initialise

```bash
# SonarQube takes ~60s to fully start
echo "Waiting for SonarQube..."
until curl -sf http://localhost:9000/api/system/status | grep -q '"status":"UP"'; do
  sleep 5; printf "."
done
echo " SonarQube ready"

# Harbor portal
echo "Waiting for Harbor..."
until curl -sf http://localhost:8080 > /dev/null; do
  sleep 3; printf "."
done
echo " Harbor ready"

# Vault
echo "Waiting for Vault..."
until curl -sf http://localhost:8200/v1/sys/health > /dev/null 2>&1; do
  sleep 2; printf "."
done
echo " Vault ready"
```

### 4d. Create Harbor project

```bash
curl -s -X POST http://localhost:8080/api/v2.0/projects \
  -u admin:Harbor12345 \
  -H 'Content-Type: application/json' \
  -d '{"project_name":"stocks","public":false}' \
  && echo "Harbor project 'stocks' created"
```

### 4e. Create Harbor robot account for CI

```bash
ROBOT=$(curl -s -X POST "http://localhost:8080/api/v2.0/robots" \
  -u admin:Harbor12345 \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "ci-robot",
    "level": "system",
    "permissions": [{
      "kind": "project",
      "namespace": "stocks",
      "access": [
        {"resource":"repository","action":"pull"},
        {"resource":"repository","action":"push"},
        {"resource":"tag","action":"create"},
        {"resource":"tag","action":"delete"}
      ]
    }]
  }')

echo "Robot name:   $(echo $ROBOT | jq -r .name)"
echo "Robot secret: $(echo $ROBOT | jq -r .secret)"
# Save the secret — you will need it in step 5 to seed Vault
HARBOR_ROBOT_SECRET=$(echo $ROBOT | jq -r .secret)
```

### 4f. Create SonarQube project and token

```bash
# Create project
curl -s -X POST "http://localhost:9000/api/projects/create" \
  -u admin:admin \
  -d "name=Stocks+App&project=stocks_stock-listing&visibility=private" > /dev/null

curl -s -X POST "http://localhost:9000/api/projects/create" \
  -u admin:admin \
  -d "name=Trade+Service&project=stocks_trade&visibility=private" > /dev/null

# Generate analysis token
SONAR_TOKEN=$(curl -s -X POST "http://localhost:9000/api/user_tokens/generate" \
  -u admin:admin \
  -d "name=ci-token" | jq -r .token)

echo "SonarQube token: $SONAR_TOKEN"
# Save this — you will seed it into Vault in step 5
```

---

## 5. Vault Bootstrap

Run **once** on a fresh Vault container.

### 5a. Run the bootstrap script

```bash
docker compose -f docker-compose.vault.yml exec vault \
  sh /vault/scripts/init.sh
```

The script:
1. Initialises Vault (creates 5 unseal keys, threshold 3)
2. Unseals using the first 3 keys
3. Enables KV v2 secrets engine
4. Enables AppRole auth
5. Loads `ci`, `app`, and `admin` policies
6. Creates two AppRoles (`ci-runner`, `app-runtime`)
7. Seeds placeholder secrets
8. Enables the audit log

**Save the output** — it prints:
```
═══════════════════════════════════════════════════════
  Store these two values as GitHub Actions secrets:
  VAULT_ROLE_ID   = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
  VAULT_SECRET_ID = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

  Store these in app container env / .env:
  APP_VAULT_ROLE_ID   = yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
  APP_VAULT_SECRET_ID = yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
═══════════════════════════════════════════════════════
```

Copy all 4 values into `.env` now.

### 5b. Seed real secret values

```bash
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=$(cat vault/vault-init.json | jq -r .root_token)

# Harbor robot credentials (from step 4e)
vault kv patch secret/ci/pipeline \
  harbor_username="robot\$ci-robot" \
  harbor_password="${HARBOR_ROBOT_SECRET}" \
  harbor_registry="localhost:5000"

# SonarQube token (from step 4f)
vault kv patch secret/ci/pipeline \
  sonar_token="${SONAR_TOKEN}"

# Database password
vault kv patch secret/db/stocksdb \
  password="$(openssl rand -base64 24)"

# Verify
vault kv get secret/ci/pipeline
vault kv get secret/db/stocksdb
```

### 5c. Store unseal keys safely

```bash
# vault/vault-init.json contains the root token and all unseal keys.
# It is gitignored. Copy it to a secure offline location NOW.
cp vault/vault-init.json ~/secure-backup/stocks-vault-init.json
chmod 600 ~/secure-backup/stocks-vault-init.json

# Verify it is gitignored
git status vault/vault-init.json
# Expected: nothing (not tracked)
```

---

## 6. GitHub Repository Configuration

### 6a. Register the self-hosted runner

```bash
# Get a runner registration token from:
# GitHub repo → Settings → Actions → Runners → New self-hosted runner → Linux
# Copy the token shown, then:

# Update .env
sed -i "s/^RUNNER_TOKEN=.*/RUNNER_TOKEN=<paste-token-here>/" .env

# Restart the runner container so it picks up the new token
docker compose -f docker-compose.infra.yml restart github-runner

# Verify it registered
gh api repos/<your-org>/stocks-app/actions/runners \
  --jq '.runners[].name'
# Expected: docker-runner-01
```

### 6b. Set GitHub Actions Secrets

```bash
gh auth login   # if not already logged in

REPO="<your-org>/stocks-app"

# Load values from .env
source .env

gh secret set VAULT_ADDR           --body "$VAULT_ADDR"            --repo $REPO
gh secret set VAULT_ROLE_ID        --body "$VAULT_ROLE_ID"         --repo $REPO
gh secret set VAULT_SECRET_ID      --body "$VAULT_SECRET_ID"       --repo $REPO
gh secret set APP_VAULT_ROLE_ID    --body "$APP_VAULT_ROLE_ID"     --repo $REPO
gh secret set APP_VAULT_SECRET_ID  --body "$APP_VAULT_SECRET_ID"   --repo $REPO

# Verify (values are masked but names are visible)
gh secret list --repo $REPO
```

Expected:
```
APP_VAULT_ROLE_ID       Updated ...
APP_VAULT_SECRET_ID     Updated ...
VAULT_ADDR              Updated ...
VAULT_ROLE_ID           Updated ...
VAULT_SECRET_ID         Updated ...
```

### 6c. Configure branch protection rules

```bash
REPO="<your-org>/stocks-app"

# Protect main — no direct push, require PR, require CI
gh api repos/$REPO/branches/main/protection \
  -X PUT \
  -H "Accept: application/vnd.github+json" \
  --input - << 'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Tests [stock-listing]",
      "Tests [trade]",
      "SonarQube [stock-listing]",
      "SonarQube [trade]"
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true
  },
  "restrictions": null
}
EOF

# Protect develop — require CI to pass on PRs
gh api repos/$REPO/branches/develop/protection \
  -X PUT \
  -H "Accept: application/vnd.github+json" \
  --input - << 'EOF'
{
  "required_status_checks": {
    "strict": false,
    "contexts": [
      "Tests [stock-listing]",
      "Tests [trade]"
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null
}
EOF
```

### 6d. Configure GitHub Environments with approval gates

```bash
REPO="<your-org>/stocks-app"

# dev — no approval needed (auto-deploy)
gh api repos/$REPO/environments/dev -X PUT \
  -f wait_timer=0

# stage — no approval needed
gh api repos/$REPO/environments/stage -X PUT \
  -f wait_timer=0

# prod — requires manual approval before deploy
gh api repos/$REPO/environments/prod -X PUT \
  -f wait_timer=0 \
  --input - << EOF
{
  "reviewers": [{"type": "User", "id": $(gh api user --jq .id)}],
  "deployment_branch_policy": {
    "protected_branches": false,
    "custom_branch_policies": true
  }
}
EOF
```

---

## 7. Local Development Workflow

### 7a. Create a feature branch

```bash
# Always branch from develop
git checkout develop
git pull origin develop

git checkout -b feature/STOCK-42-add-market-cap-sort

# Make your changes
code services/stock-listing/app/routes.py
```

### 7b. Test locally before pushing

```bash
# Run tests in the same container the pipeline uses
docker run --rm \
  -v pip-cache:/root/.cache/pip \
  -v "$(pwd)/services/stock-listing:/app" \
  -w /app \
  python:3.12-slim \
  sh -c "pip install -q -r requirements.txt && pytest tests/ -v"

# Same for trade service
docker run --rm \
  -v pip-cache:/root/.cache/pip \
  -v "$(pwd)/services/trade:/app" \
  -w /app \
  python:3.12-slim \
  sh -c "pip install -q -r requirements.txt && pytest tests/ -v"
```

### 7c. Build images locally

```bash
# Build without pushing (local smoke-test)
docker build -t stocks/stock-listing:local services/stock-listing
docker build -t stocks/trade:local         services/trade

# Run locally without Vault (direct env vars for quick testing)
docker network create dev-net 2>/dev/null || true

docker run -d --name local-db \
  --network dev-net \
  -e POSTGRES_USER=stocks \
  -e POSTGRES_PASSWORD=localtest \
  -e POSTGRES_DB=stocksdb \
  -p 5432:5432 \
  postgres:15-alpine

sleep 5

docker run -d --name local-stock-listing \
  --network dev-net \
  -e DATABASE_URL=postgresql://stocks:localtest@local-db:5432/stocksdb \
  -e APP_ENV=local \
  -p 8000:8000 \
  stocks/stock-listing:local

docker run -d --name local-trade \
  --network dev-net \
  -e DATABASE_URL=postgresql://stocks:localtest@local-db:5432/stocksdb \
  -e APP_ENV=local \
  -p 8001:8001 \
  stocks/trade:local

# Quick validation
sleep 5
curl http://localhost:8000/health
curl http://localhost:8001/health

# Cleanup
docker rm -f local-db local-stock-listing local-trade
docker network rm dev-net
```

### 7d. Commit and open a pull request

```bash
git add services/stock-listing/app/routes.py
git add services/stock-listing/tests/test_routes.py   # always add tests

git commit -m "feat(stock-listing): add sort by market cap query param"

git push -u origin feature/STOCK-42-add-market-cap-sort

# Open PR targeting develop
gh pr create \
  --base develop \
  --title "feat(stock-listing): add sort by market cap query param" \
  --body "## What
Adds \`?sort=market_cap\` query parameter to GET /stocks.

## Why
Users want to quickly find the largest companies.

## Tests
- Added \`test_sort_by_market_cap\` in test_routes.py
- All existing tests pass"
```

**At this point the pipeline runs `test` + `sonarqube` for the changed service only (path filtering). No image is built, no deployment happens — it is a PR validation run.**

Check PR status:
```bash
gh pr checks
# Expected:
# Tests [stock-listing]   pass    2m
# SonarQube [stock-listing] pass  4m
```

### 7e. Merge the PR into develop

```bash
# After review approval and CI passes:
gh pr merge --squash --delete-branch

# This push to develop triggers the Dev deployment pipeline
```

---

## 8. Promote to Dev

A push to `develop` triggers: `fetch-secrets → paths-filter → test → sonarqube → build → scan → deploy-dev`

### 8a. Watch the pipeline

```bash
# Follow the live run
gh run list --branch develop --limit 1
gh run watch $(gh run list --branch develop --limit 1 --json databaseId --jq '.[0].databaseId')
```

### 8b. What happens at each job

```
Job 0a: fetch-secrets (~5s)
  → Vault AppRole login
  → Harbor creds + SonarQube token fetched and masked

Job 0b: paths-filter (~3s)
  → Compares changed files against services/*/
  → Outputs dynamic matrix e.g. ["stock-listing"]

Job 1: test[stock-listing] (~30s warm / ~75s cold)
  → python:3.12-slim container
  → pip install (from pip-cache volume — warm: 3s)
  → pytest tests/ -v
  → 15 tests must pass

Job 2: sonarqube[stock-listing] (~2m)
  → sonar-scanner-cli:5.0.1 container
  → Scans only changed service
  → sonar-cache volume used
  → Quality gate must pass

Job 3: build[stock-listing, trade] (~15s warm / ~2m cold)
  → docker buildx with --cache-from Harbor:buildcache
  → Unchanged service: cache hit, done in ~5s
  → Changed service: only COPY app/ re-runs (~10s)
  → Pushes git-<sha7> tag to Harbor
  → cosign signs the image
  → Trivy generates CycloneDX SBOM

Job 4: scan[stock-listing, trade] (~45s)
  → trivy:0.51.4 scans each Harbor image
  → trivy-cache warm: DB not re-downloaded
  → Fails if HIGH/CRITICAL CVE found

Job 5: deploy-dev
  → Re-tags to dev-<sha7>
  → docker compose -f docker-compose.dev.yml pull
  → docker compose -f docker-compose.dev.yml up -d --remove-orphans
  → Smoke tests /health on ports 8000 and 8001
```

### 8c. Validate Dev deployment manually

```bash
# Health checks
curl -s http://localhost:8000/health | jq .
# {"status":"ok","service":"stock-listing"}

curl -s http://localhost:8001/health | jq .
# {"status":"ok","service":"trade"}

# Seed stocks (first time only)
curl -s -X POST http://localhost:8000/stocks \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"AAPL","name":"Apple Inc.","sector":"Technology","current_price":189.50,"change_pct":1.2,"volume":54321000,"market_cap":2940000}'

# Verify seed worked
curl -s http://localhost:8000/stocks | jq '.[] | {symbol,current_price}'

# Test buy order
curl -s -X POST http://localhost:8001/trades/buy \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"test-001","symbol":"AAPL","quantity":10,"price":189.50}' | jq .

# Verify portfolio
curl -s http://localhost:8001/portfolio/test-001 | jq .

# Verify image tag in running container
docker inspect dev-stock-listing \
  --format '{{ index .Config.Labels "service" }}: {{ index .Config.Labels "org.opencontainers.image.revision" }}'

# Check Vault Agent wrote the DB env file (secret not visible in compose)
docker exec dev-stock-listing \
  env | grep DATABASE_URL
# Expected: DATABASE_URL=postgresql://stocks:***@db:5432/stocksdb
# (actual password comes from Vault — not visible in compose file)

# Check running image tag matches pipeline tag
docker ps --filter name=dev-stock-listing \
  --format "{{.Image}}"
```

### 8d. Check all pipeline stages passed

```bash
gh run view $(gh run list --branch develop --limit 1 --json databaseId --jq '.[0].databaseId') \
  --json jobs --jq '.jobs[] | {name,conclusion}'
```

Expected:
```json
{"name":"Fetch Secrets from Vault",   "conclusion":"success"}
{"name":"Detect Changed Services",    "conclusion":"success"}
{"name":"Tests [stock-listing]",      "conclusion":"success"}
{"name":"SonarQube [stock-listing]",  "conclusion":"success"}
{"name":"Build & Push [stock-listing]","conclusion":"success"}
{"name":"Build & Push [trade]",       "conclusion":"success"}
{"name":"Trivy Scan [stock-listing]", "conclusion":"success"}
{"name":"Trivy Scan [trade]",         "conclusion":"success"}
{"name":"Deploy → Dev",               "conclusion":"success"}
```

---

## 9. Promote to Stage

When Dev is validated and the feature/sprint is ready for QA, create a release branch.

### 9a. Create the release branch

```bash
git checkout develop
git pull origin develop

# Choose the next semantic version
RELEASE_VERSION="1.4.0"

git checkout -b release/${RELEASE_VERSION}

# Optional: update version metadata in code (not required for this project)
# sed -i "s/version=\".*\"/version=\"${RELEASE_VERSION}\"/" services/*/app/main.py
# git commit -am "chore: bump version to ${RELEASE_VERSION}"

git push -u origin release/${RELEASE_VERSION}
```

This push triggers: `fetch-secrets → paths-filter → test → sonarqube → build → scan → deploy-stage`

### 9b. Watch Stage pipeline

```bash
gh run list --branch release/${RELEASE_VERSION} --limit 1
gh run watch $(gh run list --branch release/${RELEASE_VERSION} --limit 1 --json databaseId --jq '.[0].databaseId')
```

### 9c. Validate Stage deployment

```bash
# Health checks on Stage ports (8010, 8011)
curl -s http://localhost:8010/health | jq .
curl -s http://localhost:8011/health | jq .

# Full API regression test against Stage
echo "=== Testing Stock Listing Service ==="
curl -sf http://localhost:8010/stocks | jq length
curl -sf http://localhost:8010/stocks/AAPL | jq '{symbol, current_price}'
curl -sf "http://localhost:8010/stocks?sector=Technology" | jq length

echo "=== Testing Trade Service ==="
# Buy
BUY=$(curl -sf -X POST http://localhost:8011/trades/buy \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"stage-qa","symbol":"AAPL","quantity":5,"price":189.50}')
echo $BUY | jq '{action,status,total}'

TRADE_ID=$(echo $BUY | jq .id)

# Verify trade recorded
curl -sf http://localhost:8011/trades/${TRADE_ID} | jq '{id,action,status}'

# Portfolio
curl -sf http://localhost:8011/portfolio/stage-qa | jq .

# Sell half
curl -sf -X POST http://localhost:8011/trades/sell \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"stage-qa","symbol":"AAPL","quantity":2,"price":191.00}' | jq '{action,total}'

# Verify portfolio reduced
curl -sf http://localhost:8011/portfolio/stage-qa | jq '.[0].quantity'
# Expected: 3

# Validate image tag
docker inspect stage-stock-listing \
  --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' \
  | cut -c1-7
# Must match HEAD of release branch

echo "=== Stage validation complete ==="
```

### 9d. Verify image is signed and has SBOM

```bash
# Verify cosign signature
cosign verify \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp "https://github.com/<your-org>/stocks-app" \
  localhost:5000/stocks/stock-listing:stage-$(git rev-parse --short=7 HEAD)

# List SBOM attached to image
cosign download sbom \
  localhost:5000/stocks/stock-listing:stage-$(git rev-parse --short=7 HEAD)
```

### 9e. Merge release branch into main (after Stage sign-off)

```bash
# Open a PR: release → main
gh pr create \
  --base main \
  --head release/${RELEASE_VERSION} \
  --title "release: v${RELEASE_VERSION}" \
  --body "Stage validated. All smoke tests passed. Promoting to production."

# After approval, merge (no squash — keep history)
gh pr merge --merge --delete-branch
```

---

## 10. Promote to Production

Production is triggered by pushing a **git tag** on `main`.

### 10a. Create and push the version tag

```bash
git checkout main
git pull origin main

RELEASE_VERSION="1.4.0"

# Annotated tag (records tagger name, date, message)
git tag -a v${RELEASE_VERSION} \
  -m "release: v${RELEASE_VERSION} — stock-listing sort by market_cap, trade stop-loss"

git push origin v${RELEASE_VERSION}
```

This push triggers: `fetch-secrets → paths-filter → test → sonarqube → build → scan → deploy-prod`

**But `deploy-prod` waits for a required reviewer to approve** (GitHub Environment protection).

### 10b. Approve the production deployment

**Option A — GitHub web UI:**
1. Go to Actions → the triggered run
2. Find `Deploy → Prod` — it shows "Waiting for approval"
3. Click **Review deployments → Approve and deploy**

**Option B — GitHub CLI:**
```bash
# Get the run ID
RUN_ID=$(gh run list --ref v${RELEASE_VERSION} --limit 1 --json databaseId --jq '.[0].databaseId')

# List pending deployments
gh api repos/<your-org>/stocks-app/actions/runs/${RUN_ID}/pending_deployments \
  --jq '.[].environment.name'

# Get environment ID
ENV_ID=$(gh api repos/<your-org>/stocks-app/environments \
  --jq '.environments[] | select(.name=="prod") | .id')

# Approve
gh api repos/<your-org>/stocks-app/actions/runs/${RUN_ID}/pending_deployments \
  -X POST \
  -f "environment_ids[]=${ENV_ID}" \
  -f state=approved \
  -f comment="Stage validated, approved for production"
```

### 10c. Watch the Prod deployment

```bash
gh run watch $RUN_ID
```

### 10d. Validate Production

```bash
echo "=== Production Health ==="
curl -sf http://localhost:8020/health | jq .
curl -sf http://localhost:8021/health | jq .

echo "=== Verify version tag on running containers ==="
docker inspect prod-stock-listing \
  --format '{{index .Config.Labels "app.version"}}'
# Expected: v1.4.0

docker inspect prod-trade \
  --format '{{index .Config.Labels "app.version"}}'
# Expected: v1.4.0

echo "=== Verify 'latest' tag updated ==="
docker pull localhost:5000/stocks/stock-listing:latest --quiet
docker inspect localhost:5000/stocks/stock-listing:latest \
  --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' \
  | cut -c1-7
# Must match git rev-parse --short=7 v${RELEASE_VERSION}^{}

echo "=== Full Prod API test ==="
# List stocks
curl -sf http://localhost:8020/stocks | jq 'length'

# Buy
curl -sf -X POST http://localhost:8021/trades/buy \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"prod-smoke","symbol":"NVDA","quantity":1,"price":875.00}' \
  | jq '{status,total}'

# Portfolio
curl -sf http://localhost:8021/portfolio/prod-smoke | jq .

echo "=== Check Vault audit log (confirm secret was read) ==="
docker exec vault cat /vault/logs/audit.log | tail -5 | jq '{time,type,request:.request.path}'
```

### 10e. Merge main back into develop (keep branches in sync)

```bash
git checkout develop
git merge main --no-ff -m "chore: sync develop with main after v${RELEASE_VERSION}"
git push origin develop
```

---

## 11. Validating Every Pipeline Stage

Use this checklist after every pipeline run.

### Stage 1 — Vault secrets fetch

```bash
# Check the job completed in <10s with no errors
gh run view $RUN_ID --json jobs \
  --jq '.jobs[] | select(.name | contains("Fetch Secrets")) | {conclusion, duration: (.completedAt - .startedAt)}'

# Confirm no secrets were leaked in logs
gh run view $RUN_ID --log 2>/dev/null | grep -i "harbor_password\|sonar_token" || echo "PASS: no secrets in logs"
```

### Stage 2 — Path filter

```bash
# See which services were detected as changed
gh run view $RUN_ID --json jobs \
  --jq '.jobs[] | select(.name | contains("Detect")) | .steps[] | {name, conclusion}'
```

### Stage 3 — Unit tests

```bash
# Check all test matrix entries passed
gh run view $RUN_ID --json jobs \
  --jq '.jobs[] | select(.name | startswith("Tests")) | {name, conclusion}'

# View test output
gh run view $RUN_ID --log 2>/dev/null | grep -A5 "pytest tests/"
```

Manual re-run tests locally to confirm same result:
```bash
for SVC in stock-listing trade; do
  echo "=== $SVC ==="
  docker run --rm \
    -v pip-cache:/root/.cache/pip \
    -v "$(pwd)/services/${SVC}:/app" \
    -w /app \
    python:3.12-slim \
    sh -c "pip install -q -r requirements.txt && pytest tests/ -v --tb=short 2>&1" \
    | tail -5
done
```

### Stage 4 — SonarQube quality gate

```bash
# Check SonarQube project status via API
for PROJECT in stocks_stock-listing stocks_trade; do
  STATUS=$(curl -sf "http://localhost:9000/api/qualitygates/project_status?projectKey=${PROJECT}" \
    -u admin:admin | jq -r .projectStatus.status)
  echo "${PROJECT}: ${STATUS}"
done
# Expected: stocks_stock-listing: OK
#           stocks_trade:         OK

# View full quality gate detail
curl -sf "http://localhost:9000/api/qualitygates/project_status?projectKey=stocks_stock-listing" \
  -u admin:admin | jq .projectStatus.conditions
```

### Stage 5 — Docker build + Harbor

```bash
SHA7=$(git rev-parse --short=7 HEAD)

# Confirm images exist in Harbor for current SHA
for SVC in stock-listing trade; do
  STATUS=$(curl -sf \
    "http://localhost:8080/api/v2.0/projects/stocks/repositories/${SVC}/artifacts/git-${SHA7}" \
    -u admin:Harbor12345 | jq -r .digest)
  echo "stocks/${SVC}:git-${SHA7} → digest: ${STATUS:0:20}..."
done

# Verify image labels
docker pull localhost:5000/stocks/stock-listing:git-${SHA7} --quiet
docker inspect localhost:5000/stocks/stock-listing:git-${SHA7} \
  --format '{{json .Config.Labels}}' | jq .

# Verify image runs as non-root
docker run --rm --entrypoint "" \
  localhost:5000/stocks/stock-listing:git-${SHA7} \
  id
# Expected: uid=999(appuser) gid=999(appgroup) — NOT root
```

### Stage 6 — Cosign signature

```bash
SHA7=$(git rev-parse --short=7 HEAD)
SVC=stock-listing

cosign verify \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp "https://github.com/<your-org>/stocks-app/.github/workflows/ci-cd.yml" \
  localhost:5000/stocks/${SVC}:git-${SHA7} \
  && echo "PASS: image signature valid" \
  || echo "FAIL: signature missing or invalid"
```

### Stage 7 — SBOM

```bash
SHA7=$(git rev-parse --short=7 HEAD)

# Download and inspect SBOM
cosign download sbom \
  localhost:5000/stocks/stock-listing:git-${SHA7} \
  | jq '{bomFormat, specVersion, components: (.components | length)}'

# Or download from workflow artifacts
gh run download $RUN_ID --name sbom-stock-listing --dir /tmp/sboms
cat /tmp/sboms/sbom-stock-listing.cdx.json | jq '{bomFormat, components: (.components | length)}'
```

### Stage 8 — Trivy CVE scan

```bash
SHA7=$(git rev-parse --short=7 HEAD)

# Re-run scan locally to verify
for SVC in stock-listing trade; do
  echo "=== Scanning ${SVC} ==="
  docker run --rm \
    -v trivy-cache:/root/.cache/trivy \
    aquasec/trivy:0.51.4 \
    image \
      --severity HIGH,CRITICAL \
      --ignore-unfixed \
      --format table \
      localhost:5000/stocks/${SVC}:git-${SHA7}
  echo ""
done

# Check scan result in pipeline
gh run view $RUN_ID --json jobs \
  --jq '.jobs[] | select(.name | startswith("Trivy")) | {name, conclusion}'
```

### Stage 9 — Deployed environment

```bash
# Function to validate an environment
validate_env() {
  local ENV=$1
  local SL_PORT=$2
  local TR_PORT=$3
  local TAG=$4

  echo "=============================="
  echo " Validating: ${ENV} (tag: ${TAG})"
  echo "=============================="

  # Health
  curl -sf http://localhost:${SL_PORT}/health | jq "{env:\"${ENV}\", service:.service, status:.status}"
  curl -sf http://localhost:${TR_PORT}/health | jq "{env:\"${ENV}\", service:.service, status:.status}"

  # Running image tag
  IMG_TAG=$(docker inspect ${ENV}-stock-listing \
    --format '{{index .Config.Labels "app.version"}}' 2>/dev/null \
    || docker inspect ${ENV}-stock-listing \
         --format '{{.Config.Image}}' 2>/dev/null | cut -d: -f2)
  echo "Running image tag: ${IMG_TAG}"

  # Vault agent wrote secrets (process can connect to DB)
  VAULT_READY=$(docker exec ${ENV}-vault-agent \
    test -f /vault/secrets/.ready 2>/dev/null && echo "YES" || echo "NO")
  echo "Vault Agent ready: ${VAULT_READY}"

  # DB connectivity (via app)
  STOCK_COUNT=$(curl -sf http://localhost:${SL_PORT}/stocks | jq length 2>/dev/null || echo "ERROR")
  echo "Stocks in DB: ${STOCK_COUNT}"

  echo ""
}

validate_env dev   8000 8001 "dev-$(git rev-parse --short=7 HEAD)"
validate_env stage 8010 8011 "stage-$(git rev-parse --short=7 HEAD)"
validate_env prod  8020 8021 "v${RELEASE_VERSION}"
```

### Stage 10 — Vault audit trail

```bash
# Confirm every pipeline run left an audit entry
docker exec vault sh -c \
  "cat /vault/logs/audit.log | tail -20 | jq -c '{time,op:.request.operation,path:.request.path}'"

# Confirm DB password was never logged in plain text
docker exec vault sh -c \
  "cat /vault/logs/audit.log | grep -i password" \
  && echo "WARN: password may appear in audit log" \
  || echo "PASS: no plaintext password in audit log"
```

---

## 12. Rollback Procedures

### When to roll back

| Symptom | Action |
|---------|--------|
| Health endpoint returns non-200 after deploy | Immediate rollback |
| Error rate spike observed in logs | Rollback then investigate |
| Smoke test failed but deploy already running | Force-rollback to previous tag |
| Security CVE discovered post-deploy | Patch, re-pipeline, re-deploy |

### Find the previous good tag

```bash
# List recent tags (most recent first)
git tag --sort=-version:refname | head -10

# List images in Harbor for a service
curl -sf \
  "http://localhost:8080/api/v2.0/projects/stocks/repositories/stock-listing/artifacts?page_size=10" \
  -u admin:Harbor12345 \
  | jq '.[].tags[].name' | sort

# Find the previous prod image tag
PREV_TAG=$(git tag --sort=-version:refname | sed -n '2p')
echo "Previous prod tag: ${PREV_TAG}"
```

### Rollback via GitHub Actions (recommended)

```bash
# Interactive rollback (choose environment and tag)
gh workflow run rollback.yml \
  -f environment=prod \
  -f rollback_tag=${PREV_TAG}

# Watch it
gh run watch $(gh run list --workflow=rollback.yml --limit 1 --json databaseId --jq '.[0].databaseId')
```

### Emergency manual rollback (no pipeline)

```bash
PREV_TAG="v1.3.2"
source .env

# Pull known-good images
docker pull ${HARBOR_REGISTRY}/stocks/stock-listing:${PREV_TAG}
docker pull ${HARBOR_REGISTRY}/stocks/trade:${PREV_TAG}

# Redeploy prod
IMAGE_TAG=${PREV_TAG} \
HARBOR_REGISTRY=${HARBOR_REGISTRY} \
APP_VAULT_ROLE_ID=${APP_VAULT_ROLE_ID} \
APP_VAULT_SECRET_ID=${APP_VAULT_SECRET_ID} \
VAULT_ADDR=${VAULT_ADDR} \
  docker compose -f docker-compose.prod.yml up -d --remove-orphans

# Validate
sleep 10
curl -sf http://localhost:8020/health | jq .
curl -sf http://localhost:8021/health | jq .

# Confirm running tag
docker inspect prod-stock-listing \
  --format '{{.Config.Image}}' | cut -d: -f2
```

---

## 13. Troubleshooting

### Pipeline fails at fetch-secrets

```bash
# Check Vault is reachable from the runner container
docker exec github-runner \
  curl -sf http://vault:8200/v1/sys/health | jq .

# Check Vault is unsealed
curl -sf http://localhost:8200/v1/sys/health | jq '{initialized,sealed,standby}'
# sealed: false expected

# If sealed, re-unseal with 3 of 5 keys
KEYS=$(cat vault/vault-init.json)
for i in 0 1 2; do
  KEY=$(echo $KEYS | jq -r ".unseal_keys_b64[$i]")
  curl -sf -X PUT http://localhost:8200/v1/sys/unseal \
    -d "{\"key\":\"$KEY\"}" | jq .sealed
done
```

### Pipeline fails at test (pip install slow / fails)

```bash
# Check pip-cache volume exists and has content
docker volume inspect pip-cache
docker run --rm -v pip-cache:/cache alpine sh -c "du -sh /cache"

# If empty (first run), it will be slow — that's expected
# If failing due to network, check DNS from runner
docker exec github-runner curl -sf https://pypi.org/simple/ | head -5
```

### SonarQube quality gate fails

```bash
# See which rule triggered
curl -sf "http://localhost:9000/api/qualitygates/project_status?projectKey=stocks_stock-listing" \
  -u admin:admin \
  | jq '.projectStatus.conditions[] | select(.status != "OK")'

# Common causes:
# - Coverage below threshold → add more tests
# - Code smells/bugs → fix the flagged code or mark as false positive
# - Duplications → refactor duplicated logic
```

### Docker build fails (BuildKit cache miss causing timeout)

```bash
# Inspect buildcache tag exists in Harbor
curl -sf \
  "http://localhost:8080/api/v2.0/projects/stocks/repositories/stock-listing/tags" \
  -u admin:Harbor12345 | jq '.[].name'
# buildcache should be in the list after first successful build

# Force a fresh build without cache (use when cache is corrupted)
docker buildx build \
  --no-cache \
  --tag localhost:5000/stocks/stock-listing:manual-test \
  --push \
  services/stock-listing
```

### Vault Agent not ready (app containers won't start)

```bash
# Check vault-agent container logs
docker logs dev-vault-agent --tail 30

# Common cause: APP_VAULT_ROLE_ID or APP_VAULT_SECRET_ID wrong
# Regenerate secret ID
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=$(cat vault/vault-init.json | jq -r .root_token)
NEW_SECRET_ID=$(vault write -f -field=secret_id auth/approle/role/app-runtime/secret-id)
echo "New APP_VAULT_SECRET_ID: $NEW_SECRET_ID"
# Update .env and GitHub Secret APP_VAULT_SECRET_ID

# Restart vault-agent
docker compose -f docker-compose.dev.yml restart vault-agent
```

### Harbor push fails (403 Forbidden)

```bash
# Verify robot account has push access to stocks project
curl -sf "http://localhost:8080/api/v2.0/projects/stocks" \
  -u admin:Harbor12345 | jq '{name, repo_count}'

# Re-create robot account if needed (step 4e)
# Then update Vault secret
vault kv patch secret/ci/pipeline harbor_password="new-robot-secret"
```

### Container running as root (security check fails)

```bash
# Verify the Dockerfile USER instruction is present
grep -n "USER\|adduser\|addgroup" services/stock-listing/Dockerfile
grep -n "USER\|adduser\|addgroup" services/trade/Dockerfile

# Test
docker run --rm --entrypoint "" \
  localhost:5000/stocks/stock-listing:git-$(git rev-parse --short=7 HEAD) \
  id
# Must NOT show uid=0(root)
```

---

## Quick Reference Card

```
BRANCHING
  New feature:    git checkout -b feature/TICKET-description develop
  To Dev:         git push origin develop
  To Stage:       git checkout -b release/x.y.z && git push origin release/x.y.z
  To Prod:        git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z
  Hotfix:         git checkout -b hotfix/desc main → PR to main AND develop

PORTS
  Harbor UI:      http://localhost:8080   (admin / Harbor12345)
  Vault UI:       http://localhost:8200   (root token from vault-init.json)
  SonarQube:      http://localhost:9000   (admin / admin)
  Dev   app:      http://localhost:8000 (stock-listing)  :8001 (trade)
  Stage app:      http://localhost:8010 (stock-listing)  :8011 (trade)
  Prod  app:      http://localhost:8020 (stock-listing)  :8021 (trade)

PIPELINE WATCH
  gh run list --branch develop --limit 3
  gh run watch <run-id>
  gh run view <run-id> --json jobs --jq '.jobs[] | {name, conclusion}'

ROLLBACK
  gh workflow run rollback.yml -f environment=prod -f rollback_tag=v1.3.0

VAULT
  export VAULT_ADDR=http://localhost:8200
  export VAULT_TOKEN=$(cat vault/vault-init.json | jq -r .root_token)
  vault kv get secret/ci/pipeline
  vault kv patch secret/ci/pipeline harbor_password="new-value"
  vault kv rollback -version=2 secret/ci/pipeline

DOCKER CACHE
  # Inspect pip cache size
  docker run --rm -v pip-cache:/c alpine du -sh /c
  # Clear BuildKit cache in Harbor
  docker buildx prune --all
```
