# Stocks App — Comprehensive DevOps Pipeline Guide

This document is the definitive guide for the CI/CD lifecycle of the Stocks App. It covers architecture, deployment strategies, environment promotion, secrets management, and troubleshooting.

---

## 1. Pipeline Architecture & Flow

The pipeline is defined in `.github/workflows/ci-cd.yml` and uses a **Research → Strategy → Execution** model with strict quality gates.

### Pipeline Stages
1.  **fetch-secrets**: Authenticates to Vault and acts as a pre-flight check. (Note: For security and reliability, actual jobs fetch their own secrets directly).
2.  **paths-filter**: Detects which microservices (`stock-listing` or `trade`) have changed.
3.  **test**: Runs unit tests (`pytest`) inside an isolated container.
4.  **sonarqube**: Performs static analysis and checks the Quality Gate.
5.  **build**: Builds Docker images using **BuildKit**, signs them with **Cosign**, and generates an **SBOM** with **Trivy**.
6.  **scan**: Uses **Trivy** to scan the pushed images for HIGH/CRITICAL vulnerabilities.
7.  **deploy-[dev/stage/prod]**: Deploys to the target environment based on the git branch or tag.

---

## 2. The Matrix Strategy

The pipeline uses GitHub Actions' `matrix` strategy to dynamically scale jobs based on what changed in the repository.

*   **Detection**: The `paths-filter` job outputs a JSON array of changed services (e.g., `["stock-listing", "trade"]` or just `["trade"]`).
*   **Execution**: Jobs like `test` and `sonarqube` use `matrix: service: ${{ fromJson(needs.paths-filter.outputs.changed) }}`.
*   **Benefits**:
    *   **Efficiency**: If only `trade` is modified, tests and scans run *only* for `trade`.
    *   **Parallelism**: If both services change, their tests and scans run concurrently.
    *   **Build/Scan**: The `build` and `scan` jobs always run for *both* services (`matrix: service: [stock-listing, trade]`). BuildKit's registry cache ensures unchanged services rebuild in seconds, guaranteeing both images are always available for deployment.

---

## 3. Triggering the Pipeline

### 3a. Automated Branch Triggers
*   **Push to `develop`**: Triggers full build and deploys to **Dev**.
*   **Push to `release/**`**: Triggers full build and deploys to **Stage**.
*   **Push tag `v*.*.*`**: Triggers full build and deploys to **Prod**.

### 3b. Manual Workflow Dispatch
You can trigger the pipeline manually via the GitHub UI:
1. Go to the **Actions** tab.
2. Select **Stocks App — CI/CD Pipeline**.
3. Click **Run workflow**. You can specify a branch and a reason.

### 3c. Forcing a Run via Code (Static Content)
If you need to force SonarQube, Trivy, and a Dev deployment to run for *both* services without altering application code, modify any of these global trigger files:
*   `pipeline-guide.md` (this file)
*   `error.log`
*   `db/init.sql`

The `paths-filter` is configured to mark all services as "changed" when these global files are modified, initiating the full suite of tasks.

---

## 4. Image Tagging & Promotion Strategy

Images are built *once* and promoted across environments to guarantee that the exact code tested in Dev is what runs in Prod.

### 4a. Initial Build (The Immutable Tag)
When the `build` job runs, it creates a human-readable, immutable tag:
*   **Format**: `[service]-[dd-mm-yy]-git-[sha]`
*   **Example**: `trade-09-04-26-git-5bf2686`
This tag is pushed to the container registry.

### 4b. Environment Promotion (Tagging)
During deployment jobs, the pipeline pulls the immutable image and applies environment-specific tags:
*   **Dev Deployment**: Pulls `...git-5bf2686`, tags and pushes as `...dev-5bf2686`.
*   **Stage Deployment**: Pulls `...git-5bf2686`, tags and pushes as `...stage-5bf2686`.
*   **Prod Deployment**: Pulls `...git-5bf2686`, tags and pushes as `...v1.0.0` and `...latest`.

This ensures we always have a clear lineage of which commit is running in which environment.

---

## 5. Environment Promotion & Git Flow

Promoting code through environments relies on standard Git operations.

### 5a. Deploying to Dev
1. Create a feature branch: `git checkout -b feature/new-api`
2. Make changes and commit.
3. Merge into `develop`:
   ```bash
   git checkout develop
   git merge feature/new-api
   git push origin develop
   ```
   *Result*: Pipeline runs and deploys to Dev (`http://localhost:8000`).

### 5b. Promoting to Stage (Release Candidate)
1. Create a release branch from `develop`:
   ```bash
   git checkout develop
   git pull
   git checkout -b release/1.1.0
   git push origin release/1.1.0
   ```
   *Result*: Pipeline detects `release/**` branch and deploys to Stage (`http://localhost:8010`).

### 5c. Promoting to Production (Creating a Tag)
Once Stage is verified, deploy to Production by tagging the release commit.
1. Merge release into main (optional but recommended for GitFlow):
   ```bash
   git checkout main
   git merge release/1.1.0
   git push origin main
   ```
2. Create and push a semantic version tag:
   ```bash
   git tag v1.1.0
   git push origin v1.1.0
   ```
   *Result*: Pipeline detects the `v*.*.*` tag, extracts the semver, tags the images appropriately, and deploys to Prod (`http://localhost:8020`).

---

## 6. Rollback Procedures

If an issue is detected in an environment, you can quickly roll back using the dedicated `rollback.yml` workflow.

### 6a. How Rollback Works
1. Go to the **Actions** tab in GitHub.
2. Select the **Rollback** workflow.
3. Click **Run workflow**.
4. Input the target environment (`dev`, `stage`, or `prod`).
5. Input the exact image tag you want to revert to (e.g., `dev-a1b2c3d` or `v1.0.0`).

### 6b. What the Workflow Does
1. Authenticates with Vault to get registry credentials.
2. Verifies the requested rollback tag actually exists in the registry for both services.
3. Updates the environment variables and runs `docker compose pull && docker compose up -d` against the specified environment using the old tag.
4. Runs smoke tests to verify the rollback succeeded.

---

## 7. Vault Environment Integration

Vault is the "Single Source of Truth" for all sensitive data.

### 7a. CI/CD (Pipeline Time)
Every job in the pipeline explicitly uses the `hashicorp/vault-action` to authenticate via an AppRole (`ci-runner`) and fetch only the secrets it needs (e.g., registry credentials, sonar tokens).

### 7b. Runtime (Environment Deployment)
When the app is deployed via Docker Compose, it uses a **Vault Agent Sidecar**.
1. **Authentication**: The Agent uses an AppRole (`app-runtime`) to get a Vault token.
2. **Template Rendering**: It reads `vault/agent/agent.hcl` and fetches DB credentials from `secret/data/db/stocksdb`.
3. **Local Storage**: It writes these secrets to a shared volume at `/vault/secrets/db.env` and creates a `.ready` file.
4. **App Injection**: The app containers wait for the `.ready` file, then `source /vault/secrets/db.env` before starting their primary processes.

---

## 8. SonarQube & Trivy Integration

### SonarQube (Static Analysis)
*   **Config**: Defined in `sonar-project.properties` in each service directory.
*   **Execution**: The pipeline mounts the workspace to a Docker container running `sonar-scanner-cli`.
*   **Quality Gate**: The pipeline blocks (`-Dsonar.qualitygate.wait=true`) until SonarQube confirms the code passes quality checks.

### Trivy (Vulnerability Scanning)
*   **SBOM**: During the build phase, Trivy generates a CycloneDX SBOM which is attached to the image using Cosign.
*   **Image Scan**: Before deployment, Trivy scans the pushed image for `HIGH` and `CRITICAL` vulnerabilities. If any are found, the pipeline fails.

---

## 9. Historical Troubleshooting & Fixes

### "requirements.txt not found" or "missing sonar.projectKey"
These errors occurred on Windows-based self-hosted runners when Git Bash "mangled" paths during volume mounting.
*   **The Fix**:
    1.  **Enforce Bash Shell**: `defaults: run: shell: bash`.
    2.  **Path Normalization**: Used a script to fix the path: `WS_PATH=$(echo "/${{ github.workspace }}" | sed 's/\\/\//g' | sed 's/://')`.
    3.  **Double-Slash Trick**: Used `//${WS_PATH}/...` in mounts to tell Git Bash to pass the path literally to Docker.

### Empty Secrets / Docker Login Failure
*   **The Fix**: Refactored to **Decentralized Secret Fetching**. Jobs no longer try to pass secrets via `GITHUB_OUTPUT` (which fails due to security masking). Each job now authenticates and fetches its own secrets from Vault directly.

### Image Signing Failure (expired_token)
*   **The Fix**: Added `permissions: id-token: write` to the workflow and set `COSIGN_YES="true"` to enable non-interactive, keyless OIDC signing.

any improvements?