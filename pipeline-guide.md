# Stocks App — Pipeline & Vault Integration Guide

This document provides a detailed technical breakdown of the CI/CD pipeline, the recent troubleshooting steps taken to fix the deployment, and how HashiCorp Vault manages secrets across environments.

---

## 1. Pipeline Architecture

The pipeline is defined in `.github/workflows/ci-cd.yml` and follows a **Research → Strategy → Execution** model with strict quality gates.

### Pipeline Stages
1.  **fetch-secrets**: Authenticates to Vault using AppRole and retrieves registry/sonar credentials. (Acts as a pre-flight check).
2.  **paths-filter**: Detects which microservices (`stock-listing` or `trade`) have changed to optimize the run.
3.  **test**: Runs unit tests (`pytest`) inside an isolated container.
4.  **sonarqube**: Performs static analysis and checks the Quality Gate.
5.  **build**: Builds Docker images using **BuildKit**, signs them with **Cosign**, and generates an **SBOM**.
6.  **scan**: Uses **Trivy** to scan the pushed images for HIGH/CRITICAL vulnerabilities.
7.  **deploy-[dev/stage/prod]**: Deploys to the target environment based on the branch or tag.

---

## 2. Why the Pipeline Failed (Root Cause Analysis)

The application was not deploying to the Dev environment due to two critical issues:

### Issue A: Empty Secrets in Build/Deploy Stages
*   **The Symptom**: `docker login` failed with an error stating `--username` was missing.
*   **The Cause**: The pipeline attempted to "pass" secrets from the `fetch-secrets` job to subsequent jobs using `GITHUB_OUTPUT`. However, GitHub Actions handles secrets with high sensitivity, and the `vault-action` outputs were not being correctly mapped or exported due to syntax errors (`${{ env.VAR }}` vs `$VAR`) and inconsistent aliasing.
*   **The Fix**: Refactored the pipeline to use a **Decentralized Secret Fetching** pattern. Each job now fetches its own required secrets directly from Vault. This is more robust and eliminates the "empty output" race condition.

### Issue B: Image Signing Failure (expired_token)
*   **The Symptom**: `cosign sign` failed with an `expired_token` error and prompted for an interactive browser login.
*   **The Cause**: Keyless signing requires an OIDC token from GitHub. The workflow lacked the `id-token: write` permission. Without it, `cosign` fell back to "Device Flow," which cannot be completed in an automated CI environment.
*   **The Fix**: 
    1.  Added `permissions: id-token: write` to the workflow.
    2.  Set `COSIGN_YES: "true"` to force non-interactive mode.

---

## 3. Vault Environment Integration

Vault is the "Single Source of Truth" for all sensitive data. It interacts with the app in two ways:

### 3a. CI/CD (Pipeline Time)
The GitHub Actions runner uses a **Vault AppRole** named `ci-runner`.
*   **Policy**: `ci-policy.hcl` (Allowed to read registry and sonar secrets).
*   **Usage**: The pipeline fetches `registry_user`, `registry_pass`, and `sonar_token` to build and scan images.

### 3b. Runtime (Environment Deployment)
When the app is deployed via Docker Compose (e.g., `docker-compose.dev.yml`), it uses a **Vault Agent Sidecar**.

1.  **Authentication**: The Agent uses an AppRole (`app-runtime`) to get a Vault token.
2.  **Template Rendering**: The Agent reads a template (`vault/agent/agent.hcl`) and fetches DB credentials from `secret/data/db/stocksdb`.
3.  **Local Secret Storage**: It writes these secrets to a shared volume at `/vault/secrets/db.env`.
4.  **Readiness Signal**: It writes a `.ready` file once secrets are written.
5.  **App Injection**: The app containers (`stock-listing`/`trade`) wait for the `.ready` file, then `source /vault/secrets/db.env` before starting their main process.

### Environment Isolation
Vault paths are structured to prevent cross-environment leakage:
*   `secret/data/app/stock-listing/config` (Development configs)
*   `secret/data/db/stocksdb` (Database credentials)
*   `secret/data/ci/pipeline` (Global CI credentials)

---

## 5. Image Tagging Strategy

The pipeline uses a human-readable naming convention for Docker images to ensure clear traceability:
*   **Format**: `[service]-[dd-mm-yy]-git-[sha]`
*   **Example**: `trade-09-04-26-git-5bf2686`
*   **Purpose**: Allows instant identification of the service, build date, and exact source code version without checking git logs.

---

## 6. How to Trigger the Pipeline

The pipeline is event-driven but can be manually triggered through specific file changes:

### Automated Triggers
*   **Dev Deployment**: Push to `develop`.
*   **Stage Deployment**: Push to `release/**`.
*   **Prod Deployment**: Push a git tag (e.g., `v1.0.0`).

### Forcing a Full Run (SonarQube + Trivy + Dev Deploy)
If you need to trigger a full re-scan and deployment of **both** services without changing application code, simply modify any of the following "trigger" files:
1.  `pipeline-guide.md` (this file)
2.  `error.log`
3.  `db/init.sql` (Global database schema)

Modifying these files causes the `paths-filter` job to mark both `stock-listing` and `trade` as "changed," initiating the full suite of tests, analysis, and deployment.
