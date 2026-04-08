# Stocks App — Microservices CI/CD on Docker

A containerized microservices application for stock trading, deployed through a
full DevOps pipeline: GitHub Actions (self-hosted runners on Docker) → Docker Hub
registry → Trivy image scanning → SonarQube static analysis → Docker-based
Dev / Stage / Prod environments with tag-based rollback.

Secrets are managed by **HashiCorp Vault** running in a Docker container.
Only two bootstrap credentials (Vault AppRole IDs) ever touch GitHub Secrets —
every real secret (Registry password, SonarQube token, DB password) lives in Vault.

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
│  │   Scanner   │──►│  + Registry  │──►│ (HIGH/CRIT   │                 │
│  │  Container  │   │    Push      │   │  block)      │                 │
│  └─────────────┘   └──────────────┘   └──────┬───────┘                 │
└────────────────────────────────────────────────┼────────────────────────┘
                                                 │ pull image
                   ┌─────────────────────────────┼──────────────────────┐
                   │         Docker Hub          │                      │
                   │   docker.io                 │                      │
                   │   <namespace>/stock-listing │                      │
                   │   <namespace>/trade         │                      │
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

 All platform services (SonarQube, Trivy, Runner, Vault) run in Docker containers.
 All app environments run in Docker containers on isolated Docker networks.
```

---

## 2. Microservices

### 2.1 Stock Listing Service

**Source:** `services/stock-listing/`
**Port:** 8000 (dev) · 8010 (stage) · 8020 (prod)
**Image:** `stock-listing`

### 2.2 Trade Service

**Source:** `services/trade/`
**Port:** 8001 (dev) · 8011 (stage) · 8021 (prod)
**Image:** `trade`

---

## 3. Infrastructure Services

All infrastructure runs as Docker containers defined in
[`docker-compose.infra.yml`](docker-compose.infra.yml).

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| SonarQube DB | `sonarqube-db` | — | PostgreSQL backend for SonarQube |
| SonarQube | `sonarqube` | `9000` | Static analysis server |
| Trivy | `trivy` | — | CVE image scanner (kept alive) |
| GitHub Runner | `github-runner` | — | Self-hosted Actions runner |

---

## 4. Image Tagging Convention

| Tag Pattern | Example | Produced when |
|-------------|---------|---------------|
| `git-<sha7>` | `git-a1b2c3d` | Every push (base tag, always first) |
| `dev-<sha7>` | `dev-a1b2c3d` | Successful deploy to Dev |
| `stage-<sha7>` | `stage-a1b2c3d` | Successful deploy to Stage |
| `v<semver>` | `v1.4.2` | Git tag push (Prod release) |
| `latest` | `latest` | Floating alias — updated on each Prod deploy |

---

## 6. GitHub Actions Pipeline

### Workflow file: [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml)

**BuildKit registry cache explained:**
We use Docker Hub (or any OCI registry) to store intermediate build layers via `--cache-from/--cache-to type=registry`.

---

## 7. Rollback

Separate `workflow_dispatch` workflow — no code changes needed to roll back.

---

## 8. Secrets Management

### Vault-based secrets flow (this project)

```
┌────────────────────────────────────────────────────────────────────┐
│                   HashiCorp Vault (Docker container)                │
│   secret/ci/pipeline      ← Registry creds, SonarQube token        │
│   secret/db/stocksdb      ← DB username + password                  │
│                                                                      │
│   Auth method: AppRole                                               │
└───────────┬────────────────────────────┬────────────────────────────┘
            │                            │
            │ CI AppRole                 │ App AppRole
            │                            │
            ▼                            ▼
 ┌──────────────────────┐    ┌───────────────────────────────┐
 │  GitHub Actions       │    │  Vault Agent (sidecar)        │
 │  fetch-secrets job    │    │  runs beside each app         │
 │                       │    │  container in docker compose  │
 └──────────────────────┘
```

---

## 9. Quick Start

### Step 2 — Start infrastructure + Vault

```bash
docker compose -f docker-compose.infra.yml -f docker-compose.vault.yml up -d
```

### Step 3 — Bootstrap Vault

Seed the registry secrets:
```bash
vault kv patch secret/ci/pipeline \
  registry_url="docker.io" \
  registry_user="your-user" \
  registry_pass="your-token" \
  registry_ns="your-namespace"
```

---

## 11. Project Structure

- `.github/workflows/`: CI/CD and Rollback pipeline definitions.
- `services/`: Source code for microservices.
- `vault/`: Vault configuration and bootstrap.
- `docker-compose.infra.yml`: SonarQube + Trivy + Runner.
- `docker-compose.vault.yml`: HashiCorp Vault.
- `docker-compose.{dev,stage,prod}.yml`: Environment deployments.
