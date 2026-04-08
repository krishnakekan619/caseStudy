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

### Ports that must be free on the host

| Port | Service |
|------|---------|
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

### 2b. Set up Git identity and initial commit

```bash
git config user.name  "Your Name"
git config user.email "you@example.com"

# Initialise branching model
git checkout -b main
git add .
git commit -m "chore: initial project scaffold — stocks microservices CI/CD"
git push -u origin main

# Create the develop branch
git checkout -b develop
git push -u origin develop
```

---

## 3. Branching Strategy

This project uses a **GitFlow-inspired model** with direct environment mapping.

Branch          Deploys to     Trigger
──────────────────────────────────────────────────────────────
develop         Dev            push to develop
release/x.y.z   Stage          push to release/**
v*.*.*  (tag)   Prod           git tag push
feature/*       nowhere        PR only — runs test+sonar, no deploy
main            nowhere        merge target only, no direct push

---

## 4. Infrastructure Bootstrap

### 4a. Create the .env file

```bash
cp .env.example .env
```

Edit `.env` — fill in `GITHUB_ORG`, `GITHUB_REPO`, and `RUNNER_TOKEN`.

### 4b. Start all infrastructure

```bash
# Create networks once
docker network create infra-net || true
docker network create dev-net   || true
docker network create stage-net || true
docker network create prod-net  || true

docker compose \
  -f docker-compose.infra.yml \
  -f docker-compose.vault.yml \
  up -d
```
docker compose -f docker-compose.infra.yml -f docker-compose.vault.yml up -d
docker compose -f docker-compose.infra.yml -f docker-compose.vault.yml up -d --force-recreate github-runner
---

## 5. Vault Bootstrap

### 5a. Fix Volume Permissions (First time on Linux/WSL)
Vault requires specific ownership (UID 100) for its data volume.
```bash
docker run --rm -v casestudy_vault-data:/data alpine chown -R 100:100 /data
docker run --rm -v casestudy_vault-logs:/logs alpine chown -R 100:100 /logs
```

### 5b. Run the bootstrap script
```bash
# Ensure jq is installed in the container
docker compose -f docker-compose.vault.yml exec -u root vault apk add jq

# Run bootstrap
docker compose -f docker-compose.vault.yml exec vault sh /vault/scripts/init.sh
```

### 5c. Seed Registry secrets (Docker Hub)
```bash
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=$(docker compose -f docker-compose.vault.yml exec vault cat /tmp/vault-init.json | jq -r .root_token)

# Seed real registry credentials
vault kv patch secret/ci/pipeline \
  registry_url="docker.io" \
  registry_user="your-user" \
  registry_pass="your-token" \
  registry_ns="your-namespace"
```

---

## 6. GitHub Repository Configuration

Set the 5 bootstrap secrets in GitHub Settings:
1. `VAULT_ADDR` (e.g., `http://vault:8200`)
2. `VAULT_ROLE_ID` (from init.sh output)
3. `VAULT_SECRET_ID` (from init.sh output)
4. `APP_VAULT_ROLE_ID` (from init.sh output)
5. `APP_VAULT_SECRET_ID` (from init.sh output)

---

## 8. Promote to Dev

### 8b. What happens at each job
1. **test**: Runs pytest in an isolated `python:3.12-slim` container.
2. **sonarqube**: Scans code and checks the Quality Gate at `http://localhost:9000`.
3. **build**: Uses BuildX to build images and pushes to Docker Hub. Uses registry cache for speed.
4. **scan**: Trivy scans the pushed image for HIGH/CRITICAL vulnerabilities.
5. **deploy-dev**: Triggers `docker compose pull` on the runner and starts services.

---

## 11. Validating Every Pipeline Stage

### Stage 9 — Deployed environment
Validate that the Vault Agent has successfully written the credentials:
```bash
# Check for the sentinel file
docker exec dev-vault-agent test -f /vault/secrets/.ready && echo "Vault Agent Ready"

# Verify app has source DB credentials
docker exec dev-stock-listing env | grep DATABASE_URL
```

---

## 12. Rollback Procedures

### Rollback via GitHub Actions (recommended)
1. Go to **Actions** → **Rollback** workflow.
2. Select the environment and the tag (e.g., `v1.3.0` or `dev-a1b2c3d`).
3. Click **Run workflow**.

---

## 13. Troubleshooting

### Runner 404 Error
If the `github-runner` logs show a 404 on registration, your `RUNNER_TOKEN` has likely expired. Generate a new one in GitHub Settings and update `.env`.

### Vault Unhealthy
If Vault is unhealthy, ensure you ran the `chown` commands in step 5a. Check logs:
```bash
docker compose -f docker-compose.vault.yml logs vault
```
