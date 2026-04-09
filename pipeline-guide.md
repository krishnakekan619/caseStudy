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

## 7. SonarQube Setup & Configuration

SonarQube is used for static code analysis, identifying bugs, vulnerabilities, and code smells before deployment.

### 7a. Configuration Files
Each service contains a `sonar-project.properties` file in its root directory (e.g., `services/stock-listing/sonar-project.properties`). This file defines:
*   `sonar.projectKey`: Unique identifier for the project in SonarQube.
*   `sonar.sources`: Directory containing the source code (typically `app`).
*   `sonar.tests`: Directory containing the tests (typically `tests`).
*   `sonar.python.version`: Target Python version (3.12).

### 7b. Pipeline Integration
The `sonarqube` job in the pipeline performs the following steps:
1.  **Secret Retrieval**: Fetches the `sonar_token` from Vault at `secret/data/ci/pipeline`.
2.  **Containerized Scan**: Runs the `sonarsource/sonar-scanner-cli` Docker image.
3.  **Volume Mounting**: The entire workspace is mounted to `/src` inside the container.
4.  **Execution**: The scanner is executed with `-Dsonar.projectBaseDir` pointed to the specific service directory (e.g., `/src/services/stock-listing`).

### 7c. Quality Gate
The scanner is configured with `-Dsonar.qualitygate.wait=true`. This means the pipeline job will **block and wait** for SonarQube to process the results and return a status. If the code fails the defined Quality Gate (e.g., too many new bugs, insufficient test coverage), the pipeline job will fail, preventing the `build` stage from starting.

---

## 8. Troubleshooting Common Errors

### "requirements.txt not found" or "missing sonar.projectKey"
These errors occur on Windows-based self-hosted runners because backslashes (`\`) and drive letters (`D:\`) in paths like `${{ github.workspace }}` break Docker's volume mounting parser.

**The Fix implemented in this pipeline**:
1.  **Enforce Bash Shell**: All jobs use `defaults: run: shell: bash`.
2.  **Path Normalization**: We use `ABS_DIR=$(pwd -W | sed 's/\\/\//g')`. This Bash command converts the current directory to a Windows-style path with forward slashes (e.g., `D:/path/to/repo`), which is the most reliable format for Docker on Windows.
3.  **Strict Quoting**: Volume mounts are always quoted to handle spaces: `-v "${ABS_DIR}/services/...:/app"`.
