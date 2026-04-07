# Stocks App — Microservices CI/CD on Docker

A containerized microservices application for stock trading, deployed through a
full DevOps pipeline: GitHub Actions (self-hosted runners on Docker) → Harbor
registry → Trivy image scanning → SonarQube static analysis → Docker-based
Dev / Stage / Prod environments with tag-based rollback.

Secrets are managed by **HashiCorp Vault** running in a Docker container.
Only two bootstrap credentials (Vault AppRole IDs) ever touch GitHub Secrets —
every real secret (Harbor password, SonarQube token, DB password) lives in Vault.

---

## Table of Contents

1. [Architecture](#1-architecture)
2. [Microservices](#2-microservices)
3. [Infrastructure Services](#3-infrastructure-services)
4. [Image Tagging Convention](#4-image-tagging-convention)
5. [Environment Overview](#5-environment-overview)
6. [GitHub Actions Pipeline](#6-github-actions-pipeline)
7. [Rollback](#7-rollback)
8. [Secrets Management](#8-secrets-management)
9. [Quick Start](#9-quick-start)
10. [API Reference](#10-api-reference)
11. [Project Structure](#11-project-structure)
12. [Secrets Reference](#12-secrets-reference)

---

## 1. Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        GitHub Repository                                │
│   develop branch  ──────────────────────────────────────► Dev Deploy   │
│   release/** branch ────────────────────────────────────► Stage Deploy │
│   v*.*.* tag ───────────────────────────────────────────► Prod Deploy  │
└───────────────────────────┬─────────────────────────────────────────────┘
                            │ webhook
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              GitHub Actions Self-Hosted Runner (Docker container)        │
│                                                                         │
│  ┌─────────────┐   ┌──────────────┐   ┌──────────────┐                 │
│  │  SonarQube  │   │ Docker Build │   │ Trivy Scan   │                 │
│  │   Scanner   │──►│  + Harbor    │──►│ (HIGH/CRIT   │                 │
│  │  Container  │   │    Push      │   │  block)      │                 │
│  └─────────────┘   └──────────────┘   └──────┬───────┘                 │
└────────────────────────────────────────────────┼────────────────────────┘
                                                 │ pull image
                   ┌─────────────────────────────┼──────────────────────┐
                   │         Harbor Registry      │  (Docker container)  │
                   │   myregistry.local:5000      │                      │
                   │   stocks/stock-listing:<tag> │                      │
                   │   stocks/trade:<tag>         │                      │
                   └──────────────────────────────┘
                                  │
          ┌───────────────────────┼─────────────────────┐
          ▼                       ▼                      ▼
   ┌─────────────┐       ┌──────────────┐       ┌──────────────┐
   │   Dev Env   │       │  Stage Env   │       │   Prod Env   │
   │  dev-net    │       │  stage-net   │       │   prod-net   │
   │  port 8000  │       │  port 8010   │       │  port 8020   │
   │  port 8001  │       │  port 8011   │       │  port 8021   │
   └─────────────┘       └──────────────┘       └──────────────┘

 All platform services (Harbor, SonarQube, Trivy, Runner) run in Docker containers.
 All app environments run in Docker containers on isolated Docker networks.
```

---

## 2. Microservices

### 2.1 Stock Listing Service

**Source:** `services/stock-listing/`
**Port:** 8000 (dev) · 8010 (stage) · 8020 (prod)
**Image:** `stocks/stock-listing`

Provides read access to the stock market catalogue — symbols, names, sectors,
live prices, and market data.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/stocks` | List all stocks (filter by `?sector=`, paginate with `?skip=&limit=`) |
| `GET` | `/stocks/{symbol}` | Get full details for one ticker |
| `GET` | `/stocks/{symbol}/price` | Get current price + change% only |
| `POST` | `/stocks` | Add a new stock (admin/seed use) |
| `PUT` | `/stocks/{symbol}/price` | Update live price (market-data feed) |
| `GET` | `/health` | Health check |

**Tech stack:** Python 3.12 · FastAPI · SQLAlchemy 2 · PostgreSQL · Uvicorn

---

### 2.2 Trade Service

**Source:** `services/trade/`
**Port:** 8001 (dev) · 8011 (stage) · 8021 (prod)
**Image:** `stocks/trade`

Handles all transactional operations — buying, selling, trade history, and
portfolio management. Enforces business rules (e.g. can't sell more than held).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/trades/buy` | Execute a buy order |
| `POST` | `/trades/sell` | Execute a sell order (validates holdings) |
| `GET` | `/trades?user_id=` | Trade history for a user |
| `GET` | `/trades/{trade_id}` | Single trade by ID |
| `GET` | `/portfolio/{user_id}` | All open positions for a user |
| `GET` | `/health` | Health check |

**Tech stack:** Python 3.12 · FastAPI · SQLAlchemy 2 · PostgreSQL · Uvicorn

---

### 2.3 DB Service (PostgreSQL)

**Source:** `db/init.sql`
**Image:** `postgres:15-alpine`

Shared PostgreSQL instance per environment. Each service creates its own tables
via SQLAlchemy on startup. `db/init.sql` seeds 10 stock symbols on first boot.

| Table | Owned by | Description |
|-------|----------|-------------|
| `stocks` | stock-listing | Stock catalogue + live prices |
| `trades` | trade | Executed buy/sell orders |
| `portfolio` | trade | Open positions per user |

---

## 3. Infrastructure Services

All infrastructure runs as Docker containers defined in
[`docker-compose.infra.yml`](docker-compose.infra.yml).

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| Harbor DB | `harbor-db` | — | PostgreSQL backend for Harbor |
| Harbor Core | `harbor-core` | — | Harbor API |
| Harbor Registry | `harbor-registry` | `5000` | OCI image store |
| Harbor Portal | `harbor-portal` | `8080` | Harbor web UI |
| SonarQube DB | `sonarqube-db` | — | PostgreSQL backend for SonarQube |
| SonarQube | `sonarqube` | `9000` | Static analysis server |
| Trivy | `trivy` | — | CVE image scanner (kept alive) |
| GitHub Runner | `github-runner` | — | Self-hosted Actions runner |

All services share the `infra-net` Docker network so the runner can reach
SonarQube and Harbor by container name.

```bash
# Start all infrastructure
docker compose -f docker-compose.infra.yml up -d

# Check status
docker compose -f docker-compose.infra.yml ps
```

---

## 4. Image Tagging Convention

Every push produces an immutable layer. Multiple tags point to the same digest.

| Tag Pattern | Example | Produced when |
|-------------|---------|---------------|
| `git-<sha7>` | `git-a1b2c3d` | Every push (base tag, always first) |
| `dev-<sha7>` | `dev-a1b2c3d` | Successful deploy to Dev |
| `stage-<sha7>` | `stage-a1b2c3d` | Successful deploy to Stage |
| `v<semver>` | `v1.4.2` | Git tag push (Prod release) |
| `latest` | `latest` | Floating alias — updated on each Prod deploy |

Tags are applied in the pipeline **after** the image is already in Harbor, so
rollback is always to a proven artifact.

---

## 5. Environment Overview

| Env | Trigger | Image tag used | Ports (listing / trade / db) | Approval |
|-----|---------|---------------|-------------------------------|----------|
| Dev | push to `develop` | `dev-<sha7>` | 8000 / 8001 / 5432 | None |
| Stage | push to `release/**` | `stage-<sha7>` | 8010 / 8011 / 5433 | None |
| Prod | push `v*.*.*` tag | `v<semver>` / `latest` | 8020 / 8021 / 5434 | Required reviewers |

Each environment has its own:
- Docker Compose file (`docker-compose.{env}.yml`)
- Isolated Docker network (`dev-net`, `stage-net`, `prod-net`)
- PostgreSQL volume (`dev-db-data`, `stage-db-data`, `prod-db-data`)

This mirrors K8s namespaces — no cross-environment networking is possible.

---

## 6. GitHub Actions Pipeline

### Workflow file: [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml)

---

#### Parallelism map (real timeline, push to `develop`)

```
Wall time →  0s        5s        30s       2m        5m        8m        10m
             │         │         │         │         │         │         │
             ├─[fetch-secrets]──────┤       │         │         │         │
             │         │           │       │         │         │         │
             ├─[paths-filter]───────┤       │         │         │         │
             │         │           │       │         │         │         │
             ├─[test stock-listing]──────────────────┤│         │         │
             ├─[test trade]──────────────────────────┤│         │         │
             │         │           │                  │         │         │
             │         ├─[sonar stock-listing]─────────────────┤│         │
             │         ├─[sonar trade]─────────────────────────┤│         │
             │         │           │                  │         │         │
             │         │           │                  │         ├─[build stock-listing]──┤
             │         │           │                  │         ├─[build trade]──────────┤
             │         │           │                  │         │         │               │
             │         │           │                  │         │         ├─[scan sl]───┤ │
             │         │           │                  │         │         ├─[scan trade]┤ │
             │         │           │                  │         │         │              │
             │         │           │                  │         │         │    ├─[deploy-dev]──┤
             │         │           │                  │         │         │
Legend:  sl = stock-listing
```

**What runs truly in parallel (same wall-clock time):**

| Time | What runs together |
|------|--------------------|
| T=0 | `fetch-secrets`, `paths-filter`, `test[stock-listing]`, `test[trade]` — 4 jobs simultaneously |
| T≈5s | `sonarqube[stock-listing]`, `sonarqube[trade]` start (fetch-secrets done) — while tests are still running |
| After slowest of test+sonarqube | `build[stock-listing]`, `build[trade]` — 2 jobs simultaneously |
| After both builds | `scan[stock-listing]`, `scan[trade]` — 2 jobs simultaneously |
| After both scans | One deploy job (determined by branch/tag) |

**Path-based filtering (skips unchanged services entirely):**

`paths-filter` uses `dorny/paths-filter` to detect which `services/` directories changed.
`test` and `sonarqube` jobs use a **dynamic matrix** built from that list — if only `trade` changed, `stock-listing` tests and SonarQube scan are skipped completely.
`build` and `scan` always run for both services, but Docker BuildKit cache makes an unchanged service build in ~5 seconds (a cache hit).

---

#### Cache layers (what is cached, where, how long)

| Cache | Mechanism | Lives on | Cold run | Warm run |
|-------|-----------|----------|----------|----------|
| **Docker layers — builder stage** | BuildKit registry cache pushed to Harbor (`stocks/<svc>:buildcache`) | Harbor volume | ~90s (pip install) | ~5s (cache hit) |
| **Docker layers — runtime stage** | Same BuildKit cache, `mode=max` caches all stages | Harbor volume | ~15s | ~2s |
| **pip packages (test step)** | Named Docker volume `pip-cache` mounted into test container | Runner host disk | ~45s (download) | ~3s (disk read) |
| **Trivy CVE database** | Named Docker volume `trivy-cache` | Runner host disk | ~30s (120 MB download) | 0s (daily update only) |
| **SonarQube scanner** | Named Docker volume `sonar-cache` | Runner host disk | ~20s (parse all files) | ~5s (only changed files) |

**BuildKit registry cache explained:**

```
First run (cold):
  docker buildx build
    --cache-from type=registry,ref=harbor/stocks/trade:buildcache  ← miss (empty)
    --cache-to   type=registry,ref=harbor/stocks/trade:buildcache,mode=max
    ...
  → Executes: FROM python:3.12-slim → pip install (90s) → COPY app/ → done
  → Pushes layer manifests to Harbor as :buildcache

Second run (only requirements.txt unchanged):
  docker buildx build
    --cache-from type=registry,ref=harbor/stocks/trade:buildcache  ← HIT
    ...
  → pip install layer: CACHED (0s) ← biggest win
  → COPY app/: CACHED if app code unchanged, rebuilt if changed
  → Total: ~5s instead of ~90s
```

`mode=max` stores every intermediate layer, not just the final image.
This means the pip-install layer is cached independently from the app copy layer.
Changing only `routes.py` hits the cache for pip install but re-runs the COPY step.

---

#### Pipeline flow diagram

```
git push develop / release/** / v*.*.*
           │
    ┌──────┴───────┐
    ▼              ▼
fetch-secrets   paths-filter    ← parallel at T=0, both ~5s
    │              │
    │         ┌────┴────────────────────────────┐
    │         ▼ dynamic matrix (changed svcs)   ▼
    │    test[changed]        sonarqube[changed] ← parallel, skip unchanged
    │         │                    │
    └────┬────┘                    │
         ▼                         │
    build[stock-listing, trade]←───┘  ← always both, BuildKit cache
         │     (+cosign sign, SBOM)
         ▼
    scan[stock-listing, trade]     ← both parallel, trivy-cache warm
         │
    ┌────┴──────────┬────────────────┐
    ▼               ▼                ▼
deploy-dev     deploy-stage     deploy-prod   ← only ONE fires per run
                                              ← prod requires approval

    (any failure) → notify-failure
```

---

### Job details

| Job | Matrix | Deps | Description |
|-----|--------|------|-------------|
| `fetch-secrets` | — | — | Vault AppRole login; fetches Harbor + Sonar creds as masked outputs |
| `paths-filter` | — | — | Detects which `services/` dirs changed; outputs dynamic matrix list |
| `test` | changed services only | paths-filter | `pytest` in `python:3.12-slim` with `pip-cache` volume; SQLite; no external deps |
| `sonarqube` | changed services only | fetch-secrets + paths-filter | `sonar-scanner-cli:5.0.1` with `sonar-cache` volume; quality gate blocks |
| `build` | both services | fetch-secrets + test + sonarqube | `docker buildx` with BuildKit registry cache (`--cache-from/--cache-to Harbor`); cosign sign; Trivy SBOM |
| `scan` | both services | fetch-secrets + build | `trivy:0.51.4` with `trivy-cache` volume; blocks on HIGH/CRITICAL |
| `deploy-dev` | — | fetch-secrets + build + scan | Re-tags `dev-<sha7>`, compose up, smoke test |
| `deploy-stage` | — | fetch-secrets + build + scan | Re-tags `stage-<sha7>`, compose up, smoke test |
| `deploy-prod` | — | fetch-secrets + build + scan | Re-tags `v<semver>` + `latest`, compose up, smoke test, approval gate |
| `notify-failure` | — | all above | Summary + Slack stub on any failure |

### Rollback workflow: [`.github/workflows/rollback.yml`](.github/workflows/rollback.yml)

Separate `workflow_dispatch` workflow — no code changes needed to roll back.

---

## 7. Rollback

### Option A — GitHub Actions UI (recommended)

1. **Actions → Rollback → Run workflow**
2. Select branch `main`
3. Fill inputs:
   - `environment`: `dev` | `stage` | `prod`
   - `rollback_tag`: the tag to restore (e.g. `v1.3.0`, `stage-a1b2c3d`)
4. Click **Run workflow**

The rollback job:
- Verifies the tag exists in Harbor before doing anything
- Runs `docker compose pull` + `up -d --remove-orphans`
- Runs smoke tests against health endpoints
- Writes a summary to the workflow run page

### Option B — GitHub CLI

```bash
gh workflow run rollback.yml \
  -f environment=prod \
  -f rollback_tag=v1.3.0
```

### Option C — Emergency manual rollback (no pipeline)

```bash
# 1. Pull the known-good image
docker pull myregistry.local:5000/stocks/stock-listing:v1.3.0
docker pull myregistry.local:5000/stocks/trade:v1.3.0

# 2. Redeploy prod with old tag
IMAGE_TAG=v1.3.0 \
  docker compose -f docker-compose.prod.yml up -d --remove-orphans

# 3. Verify
curl http://localhost:8020/health
curl http://localhost:8021/health
```

### List available tags (to choose a rollback target)

```bash
# Via Harbor API
curl -s -u admin:Harbor12345 \
  "http://myregistry.local:5000/api/v2.0/projects/stocks/repositories/stock-listing/artifacts" \
  | jq '.[].tags[].name'
```

---

## 8. Secrets Management

### The problem with plain environment variables

Without a secrets manager every secret travels like this:

```
Developer types password
  → stored in GitHub Settings (encrypted at rest, but GitHub controls the key)
  → injected as env var into runner process
  → passed via -e flag to docker run / docker compose
  → visible in docker inspect, /proc/1/environ inside container
  → no rotation, no audit log, no expiry
```

Every person with repo admin access can see the secret values. There is no
record of *who* read a secret or *when*.

---

### Vault-based secrets flow (this project)

```
┌────────────────────────────────────────────────────────────────────┐
│                   HashiCorp Vault (Docker container)                │
│   secret/ci/pipeline      ← Harbor creds, SonarQube token          │
│   secret/db/stocksdb      ← DB username + password                  │
│   secret/app/*/config     ← Per-service runtime config              │
│                                                                      │
│   Auth method: AppRole                                               │
│   Audit log:   /vault/logs/audit.log  (every read recorded)         │
└───────────┬────────────────────────────┬────────────────────────────┘
            │                            │
            │ CI AppRole                 │ App AppRole
            │ (role_id + secret_id)      │ (role_id + secret_id)
            │                            │
            ▼                            ▼
 ┌──────────────────────┐    ┌───────────────────────────────┐
 │  GitHub Actions       │    │  Vault Agent (sidecar)        │
 │  fetch-secrets job    │    │  runs beside each app         │
 │                       │    │  container in docker compose  │
 │  hashicorp/vault-     │    │                               │
 │  action@v3 fetches    │    │  writes /vault/secrets/db.env │
 │  Harbor + SonarQube   │    │  app sources it before start  │
 │  creds at job start   │    └───────────────────────────────┘
 │                       │
 │  secrets passed as    │
 │  job outputs (masked) │
 └──────────────────────┘

GitHub Secrets stores ONLY:
  VAULT_ADDR        — Vault server address
  VAULT_ROLE_ID     — CI AppRole role_id
  VAULT_SECRET_ID   — CI AppRole secret_id
  APP_VAULT_ROLE_ID    — App AppRole role_id
  APP_VAULT_SECRET_ID  — App AppRole secret_id
```

**What never touches GitHub Secrets:**
- Harbor password
- SonarQube token
- Database password
- Any future secret

---

### Vault concepts used

| Concept | What it does in this project |
|---------|------------------------------|
| **KV v2 secrets engine** | Stores all secrets at `secret/data/<path>`. Versioned — you can roll back to a previous secret version. |
| **AppRole auth** | Machine-to-machine auth. A `role_id` (like a username) + `secret_id` (like a password) exchange for a short-lived Vault token. |
| **Policies** | Fine-grained ACL. `ci-policy` gives the runner read-only access to CI secrets only. `app-policy` gives services read-only access to their own secrets only. |
| **Vault Agent** | Long-running sidecar process. Authenticates once, renews its token automatically, re-fetches secrets when they rotate, writes them to a shared volume as env files. |
| **Audit log** | Every read/write to Vault is written to `/vault/logs/audit.log` with timestamp, caller identity, and the path accessed. |
| **Token TTL** | CI tokens expire after 1 h. App tokens expire after 12 h and auto-renew via Vault Agent. |

---

### Secret paths in Vault

```
secret/
├── ci/
│   └── pipeline          harbor_registry, harbor_username, harbor_password, sonar_token
├── harbor/
│   └── registry          username, password, registry
├── sonarqube/
│   └── token             token
├── db/
│   └── stocksdb          username, password, host, port, name
└── app/
    ├── stock-listing/
    │   └── config        database_url, app_env
    └── trade/
        └── config        database_url, app_env
```

---

### How the CI pipeline fetches secrets

**File:** [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml)

Job `fetch-secrets` runs first, before any build step:

```yaml
- name: Authenticate to Vault and fetch CI secrets
  uses: hashicorp/vault-action@v3
  with:
    url:      ${{ env.VAULT_ADDR }}
    method:   approle
    roleId:   ${{ secrets.VAULT_ROLE_ID }}      # only this leaves GitHub
    secretId: ${{ secrets.VAULT_SECRET_ID }}    # only this leaves GitHub
    secrets: |
      secret/data/ci/pipeline harbor_password | harbor_password ;
      secret/data/ci/pipeline sonar_token     | sonar_token
```

The action:
1. Calls `POST /v1/auth/approle/login` with role_id + secret_id
2. Receives a short-lived Vault token (TTL = 1 h)
3. Calls `GET /v1/secret/data/ci/pipeline` with that token
4. Sets the returned values as **masked** environment variables / step outputs
5. The Vault token is discarded — never stored anywhere

Downstream jobs receive secrets via `needs.fetch-secrets.outputs.*`.
GitHub automatically masks these values in all log output.

---

### How app containers fetch secrets (Vault Agent sidecar)

**File:** [`vault/agent/agent.hcl`](vault/agent/agent.hcl)

Each Docker Compose environment runs a `vault-agent` container alongside the app:

```
docker compose up
  │
  ├─ vault-agent starts
  │    ├─ authenticates to Vault with APP_VAULT_ROLE_ID + APP_VAULT_SECRET_ID
  │    ├─ receives Vault token (auto-renewed before expiry)
  │    ├─ renders template → writes /vault/secrets/db.env
  │    └─ writes /vault/secrets/.ready  (sentinel file)
  │
  ├─ stock-listing waits for vault-agent healthcheck (.ready exists)
  │    └─ entrypoint: source /vault/secrets/db.env → uvicorn starts
  │
  └─ trade waits for vault-agent healthcheck (.ready exists)
       └─ entrypoint: source /vault/secrets/db.env → uvicorn starts
```

`/vault/secrets/db.env` contents (written by Vault Agent template):

```bash
export DATABASE_URL="postgresql://stocks:actualpassword@db:5432/stocksdb"
export DB_PASSWORD="actualpassword"
```

The actual password **never appears** in:
- The Docker Compose file
- The image layers
- `docker inspect` output
- GitHub Actions logs
- The `.env` file on disk

If the DB password is rotated in Vault, Vault Agent automatically re-renders
the env file and the app picks it up on next restart — no redeployment needed.

---

### Secret rotation procedure

```bash
# Rotate DB password in Vault (creates a new version, old version still readable)
vault kv patch secret/db/stocksdb password="new-strong-password"

# Vault Agent detects the new version and re-renders /vault/secrets/db.env
# Restart app containers to pick up the new DATABASE_URL
docker compose -f docker-compose.prod.yml restart stock-listing trade

# Rotate PostgreSQL password to match
docker exec prod-db psql -U stocks -c "ALTER USER stocks PASSWORD 'new-strong-password';"

# Roll back to previous secret version if needed
vault kv rollback -version=2 secret/db/stocksdb
```

---

### Vault setup and bootstrap

**File:** [`docker-compose.vault.yml`](docker-compose.vault.yml)
**Init script:** [`vault/init.sh`](vault/init.sh)

```bash
# 1. Start Vault container
docker compose -f docker-compose.infra.yml -f docker-compose.vault.yml up -d vault

# 2. Run bootstrap (once only)
docker compose -f docker-compose.vault.yml exec vault sh /vault/scripts/init.sh

# 3. The script prints two pairs of credentials:
#    CI_ROLE_ID + CI_SECRET_ID      → add to GitHub Actions Secrets
#    APP_ROLE_ID + APP_VAULT_SECRET_ID → add to GitHub Actions Secrets (for compose)

# 4. Update real secret values (replace CHANGE_ME placeholders)
vault kv patch secret/ci/pipeline   harbor_password="real-password"
vault kv patch secret/db/stocksdb   password="real-db-password"
```

**Vault UI:** http://localhost:8200 (use root token from `vault/vault-init.json`)

---

### Standard practices applied

| Practice | Implementation |
|----------|---------------|
| **Least privilege** | CI policy: read-only, CI paths only. App policy: read-only, own paths only. No cross-service access. |
| **Short-lived credentials** | CI Vault tokens expire in 1 h. No long-lived static tokens in workflows. |
| **Secret versioning** | KV v2 keeps previous versions. Instant rollback with `vault kv rollback`. |
| **Audit trail** | Every Vault read/write logged to `/vault/logs/audit.log` with identity + timestamp. |
| **No secrets in images** | Secrets injected at runtime via Vault Agent. `docker history` shows nothing sensitive. |
| **No secrets in env section** | App containers have no `environment:` block with secrets. They source a file written by Vault Agent. |
| **Minimal GitHub Secrets** | Only 5 values in GitHub (VAULT_ADDR + 2 AppRole pairs). Everything else is in Vault. |
| **Sealed at rest** | Vault data on disk is encrypted. Vault requires 3-of-5 unseal keys to start. |

---

## 9. Quick Start

### Prerequisites

- Docker Engine 24+ and Docker Compose v2
- Git
- A GitHub repository with Actions enabled

### Step 1 — Clone and configure

```bash
git clone https://github.com/<your-org>/stocks-app.git
cd stocks-app
cp .env.example .env
# Edit .env — fill in RUNNER_TOKEN and GITHUB_ORG/REPO only for now
```

### Step 2 — Start infrastructure + Vault

```bash
# Start Harbor, SonarQube, Trivy, Runner AND Vault together
docker compose \
  -f docker-compose.infra.yml \
  -f docker-compose.vault.yml \
  up -d

# Wait ~60 s for SonarQube, ~10 s for Vault
docker compose -f docker-compose.infra.yml logs -f sonarqube | grep -m1 "SonarQube is operational"
```

| UI | URL | Default credentials |
|----|-----|---------------------|
| Harbor | http://localhost:8080 | admin / Harbor12345 |
| SonarQube | http://localhost:9000 | admin / admin |
| Vault | http://localhost:8200 | root token (from init.sh output) |

### Step 3 — Bootstrap Vault (once only)

```bash
# Initialise, unseal, load policies, create AppRoles, seed secrets
docker compose -f docker-compose.vault.yml exec vault sh /vault/scripts/init.sh

# The script prints:
#   VAULT_ROLE_ID + VAULT_SECRET_ID       ← for GitHub Actions (CI)
#   APP_VAULT_ROLE_ID + APP_VAULT_SECRET_ID ← for GitHub Actions (app deploy)

# Update placeholder secret values with real ones
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=<root-token-from-init-output>

vault kv patch secret/ci/pipeline   harbor_password="your-real-harbor-robot-password"
vault kv patch secret/ci/pipeline   sonar_token="your-real-sonar-token"
vault kv patch secret/db/stocksdb   password="your-real-db-password"
```

### Step 4 — Create Harbor project

```bash
curl -X POST http://localhost:8080/api/v2.0/projects \
  -u admin:Harbor12345 \
  -H 'Content-Type: application/json' \
  -d '{"project_name":"stocks","public":false}'
```

### Step 5 — Configure GitHub Secrets

Go to **Settings → Secrets and variables → Actions** and add these 5 values
(printed by `init.sh` — **no actual passwords go here**):

| Name | Value |
|------|-------|
| `VAULT_ADDR` | `http://vault:8200` (or your host IP if Vault is remote) |
| `VAULT_ROLE_ID` | CI AppRole role_id from `init.sh` output |
| `VAULT_SECRET_ID` | CI AppRole secret_id from `init.sh` output |
| `APP_VAULT_ROLE_ID` | App AppRole role_id from `init.sh` output |
| `APP_VAULT_SECRET_ID` | App AppRole secret_id from `init.sh` output |

### Step 6 — Enable Prod environment protection

**Settings → Environments → prod → Required reviewers** — add yourself or a team.

### Step 7 — Trigger the pipeline

```bash
# Push to develop → triggers Dev deploy
git checkout -b develop
git push origin develop

# Create a release branch → triggers Stage deploy
git checkout -b release/1.0.0
git push origin release/1.0.0

# Tag for production → triggers Prod deploy (after approval)
git tag v1.0.0
git push origin v1.0.0
```

### Step 8 — Run locally without pipeline (dev testing)

```bash
# Build images locally
docker build -t stocks/stock-listing:local services/stock-listing
docker build -t stocks/trade:local         services/trade

# Start dev environment pointing at local images
HARBOR_REGISTRY="" IMAGE_TAG=local \
  docker compose -f docker-compose.dev.yml up -d

# Test
curl http://localhost:8000/stocks
curl http://localhost:8001/health
```

---

## 10. API Reference

### Stock Listing Service (port 8000/8010/8020)

```bash
# List all stocks
curl http://localhost:8000/stocks

# Filter by sector
curl "http://localhost:8000/stocks?sector=Technology"

# Get one stock
curl http://localhost:8000/stocks/AAPL

# Get price only
curl http://localhost:8000/stocks/AAPL/price

# Add a stock (seed/admin)
curl -X POST http://localhost:8000/stocks \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"META","name":"Meta Platforms","sector":"Technology","current_price":480.00,"change_pct":1.5,"volume":20000000,"market_cap":1230000}'

# Update live price
curl -X PUT "http://localhost:8000/stocks/AAPL/price?price=191.50&change_pct=0.95"
```

### Trade Service (port 8001/8011/8021)

```bash
# Buy 10 shares of AAPL at $189.50
curl -X POST http://localhost:8001/trades/buy \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"user-001","symbol":"AAPL","quantity":10,"price":189.50}'

# Sell 5 shares of AAPL at $191.00
curl -X POST http://localhost:8001/trades/sell \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"user-001","symbol":"AAPL","quantity":5,"price":191.00}'

# View trade history
curl "http://localhost:8001/trades?user_id=user-001"

# View portfolio
curl http://localhost:8001/portfolio/user-001
```

---

## 11. Project Structure

```
stocks-app/
│
├── .github/
│   └── workflows/
│       ├── ci-cd.yml               ← Main pipeline (fetch-secrets → build/scan/deploy)
│       └── rollback.yml            ← Manual rollback workflow
│
├── services/
│   ├── stock-listing/              ← Stock Listing microservice
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── main.py             ← FastAPI app + lifespan
│   │   │   ├── database.py         ← SQLAlchemy engine + session
│   │   │   ├── models.py           ← Stock ORM model
│   │   │   ├── schemas.py          ← Pydantic request/response models
│   │   │   └── routes.py           ← API endpoints
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── sonar-project.properties
│   │
│   └── trade/                      ← Trade microservice
│       ├── app/
│       │   ├── __init__.py
│       │   ├── main.py             ← FastAPI app + lifespan
│       │   ├── database.py         ← SQLAlchemy engine + session
│       │   ├── models.py           ← Trade + Portfolio ORM models
│       │   ├── schemas.py          ← Pydantic request/response models
│       │   └── routes.py           ← Buy / sell / portfolio endpoints
│       ├── Dockerfile
│       ├── requirements.txt
│       └── sonar-project.properties
│
├── db/
│   └── init.sql                    ← Seed data (10 stock symbols)
│
├── vault/
│   ├── config.hcl                  ← Vault server configuration
│   ├── init.sh                     ← One-time bootstrap: init, unseal, policies, AppRoles, seed secrets
│   ├── policies/
│   │   ├── admin-policy.hcl        ← Human operator: full access
│   │   ├── ci-policy.hcl           ← CI runner: read-only, CI paths only
│   │   └── app-policy.hcl          ← App containers: read-only, own paths only
│   └── agent/
│       └── agent.hcl               ← Vault Agent sidecar config (authenticates + writes env files)
│
├── docker-compose.infra.yml        ← Harbor + SonarQube + Trivy + Runner
├── docker-compose.vault.yml        ← HashiCorp Vault server
├── docker-compose.dev.yml          ← Dev env: db + vault-agent + services (ports 8000/8001)
├── docker-compose.stage.yml        ← Stage env: db + vault-agent + services (ports 8010/8011)
├── docker-compose.prod.yml         ← Prod env: db + vault-agent + services (ports 8020/8021)
│
├── .env.example                    ← Template — only runner token + Vault AppRole IDs
└── README.md
```

---

## 12. Secrets Reference

### GitHub Actions Secrets (5 values only)

| Secret | What it is | Where it comes from |
|--------|------------|---------------------|
| `VAULT_ADDR` | Vault server URL | Your infrastructure setup |
| `VAULT_ROLE_ID` | CI AppRole role_id | `vault/init.sh` output |
| `VAULT_SECRET_ID` | CI AppRole secret_id | `vault/init.sh` output |
| `APP_VAULT_ROLE_ID` | App runtime AppRole role_id | `vault/init.sh` output |
| `APP_VAULT_SECRET_ID` | App runtime AppRole secret_id | `vault/init.sh` output |

No Harbor password. No SonarQube token. No database password. Those live in Vault.

### Vault secret paths

| Path | Keys | Used by |
|------|------|---------|
| `secret/ci/pipeline` | harbor_registry, harbor_username, harbor_password, sonar_token | CI pipeline (`fetch-secrets` job) |
| `secret/harbor/registry` | username, password, registry | Manual Harbor operations |
| `secret/sonarqube/token` | token | Manual SonarQube operations |
| `secret/db/stocksdb` | username, password, host, port, name | Vault Agent → app containers |
| `secret/app/stock-listing/config` | database_url, app_env | Stock Listing service (optional direct fetch) |
| `secret/app/trade/config` | database_url, app_env | Trade service (optional direct fetch) |

### Vault Policies

| Policy file | Granted to | Access |
|-------------|------------|--------|
| [`vault/policies/ci-policy.hcl`](vault/policies/ci-policy.hcl) | CI AppRole | Read `secret/ci/*`, `secret/harbor/*`, `secret/sonarqube/*` |
| [`vault/policies/app-policy.hcl`](vault/policies/app-policy.hcl) | App AppRole | Read `secret/db/*`, `secret/app/*` |
| [`vault/policies/admin-policy.hcl`](vault/policies/admin-policy.hcl) | Human operators | Full read/write on all paths |

### .env file (runner host only)

| Variable | Description |
|----------|-------------|
| `GITHUB_ORG` | Your GitHub org or username |
| `GITHUB_REPO` | Repository name |
| `RUNNER_TOKEN` | GitHub runner registration token |
| `VAULT_ADDR` | Vault server address |
| `APP_VAULT_ROLE_ID` | Passed into docker compose for Vault Agent |
| `APP_VAULT_SECRET_ID` | Passed into docker compose for Vault Agent |

### GitHub Environments

| Environment | Protection |
|-------------|------------|
| `dev` | None — auto-deploy on push to `develop` |
| `stage` | None — auto-deploy on push to `release/**` |
| `prod` | Required reviewers — manual approval before deploy |

---

## Pipeline Quality Gates

| Gate | Tool | Failure behaviour |
|------|------|-------------------|
| Unit tests | pytest (SQLite, in-container) | Pipeline blocked — no image built |
| Code quality | SonarQube quality gate | Pipeline blocked — no image built |
| Vulnerability scan | Trivy (HIGH + CRITICAL) | Pipeline blocked — no deploy |
| Smoke test | `curl /health` with retries | Pipeline blocked — failure summary written |

All four gates must pass in order before any environment receives a new deployment.

---

## Standard Practices Checklist

| Practice | Status | Implementation |
|----------|--------|---------------|
| Secrets in vault, not env vars | Done | HashiCorp Vault AppRole; only 5 bootstrap IDs in GitHub Secrets |
| Least-privilege policies | Done | Separate `ci`, `app`, `admin` Vault policies |
| Unit tests before build | Done | `pytest` in isolated container, SQLite, no external deps |
| Static code analysis | Done | SonarQube quality gate blocks pipeline |
| Container image scanning | Done | Trivy blocks on HIGH/CRITICAL CVE |
| Multi-stage Dockerfiles | Done | Builder stage separate from runtime; smaller attack surface |
| Non-root container user | Done | `appuser` created and set in both Dockerfiles |
| `.dockerignore` | Done | Prevents `.env`, `tests/`, `__pycache__` leaking into images |
| `.gitignore` | Done | `vault/vault-init.json` (unseal keys) never committed |
| Pinned image versions | Done | `trivy:0.51.4`, `sonar-scanner-cli:5.0.1`, `vault-action@v3.0.0` — no floating `:latest` in pipeline |
| Image signing | Done | cosign keyless OIDC signing after each Harbor push |
| SBOM generation | Done | Trivy generates CycloneDX SBOM, attached to image + uploaded as artifact |
| `docker logout` after push | Done | `if: always()` logout in every job that logs in |
| Concurrency control | Done | `concurrency` group cancels stale in-progress runs per branch/tag |
| Rollback uses Vault | Done | `rollback.yml` fetches Harbor creds from Vault (fixed — was using deleted GitHub Secrets) |
| Graceful shutdown | Done | `--timeout-graceful-shutdown 30` in uvicorn CMD |
| Automated dependency updates | Done | Dependabot for GitHub Actions + pip (weekly, Monday) |
| Failure notification | Done | `notify-failure` job writes summary; Slack stub ready to enable |
| Prod deployment approval | Done | GitHub Environment protection rules — required reviewers |
| Immutable image tags | Done | `git-<sha7>` tag never reassigned; semver tags added alongside |
| Audit trail | Done | Vault audit log records every secret read with caller identity |
| Secret rotation | Done | `vault kv patch` + agent re-renders env file without redeploying |
