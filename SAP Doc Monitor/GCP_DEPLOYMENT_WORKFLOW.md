# SAP Doc Monitor — Complete GCP Workflow Guide

## Table of Contents

1. [GCP Services Used & Their Purpose](#1-gcp-services-used--their-purpose)
2. [One-Time Deployment Workflow (Step-by-Step)](#2-one-time-deployment-workflow-step-by-step)
3. [Runtime Workflow (When Cloud Scheduler Fires)](#3-runtime-workflow-when-cloud-scheduler-fires)
4. [Visual Diagrams](#4-visual-diagrams)

---

## 1. GCP Services Used & Their Purpose

| # | GCP Service | Purpose in This Project | Used During |
|---|-------------|------------------------|-------------|
| 1 | **Cloud Build** | Builds the Docker image from the Dockerfile on Google's servers | Deployment only |
| 2 | **Artifact Registry / Container Registry** | Stores the built Docker image (`gcr.io/{PROJECT_ID}/sap-doc-monitor`) | Deployment (image storage for Cloud Run) |
| 3 | **Cloud Run** | Runs the containerized Python app (Flask HTTP server) that performs the actual monitoring | Deployment + Runtime |
| 4 | **Cloud Storage (GCS)** | Persistently stores document snapshots (`.txt` files) between runs — because Cloud Run containers are **ephemeral** (destroyed after each run) | Runtime only |
| 5 | **Secret Manager** | Securely stores the email SMTP password (`email-password`). Cloud Run injects it as the `EMAIL_PASSWORD` environment variable at runtime | Runtime only |
| 6 | **Service Account** (`sap-monitor-scheduler`) | An identity that gives Cloud Scheduler permission to invoke the **private** (unauthenticated access blocked) Cloud Run service using OIDC tokens | Runtime only |
| 7 | **Cloud Scheduler** | The **trigger** — sends an HTTP POST request to Cloud Run on a cron schedule (twice daily at 9 AM and 6 PM) to start the monitoring job | Runtime only |

### Key Clarification

> **GCS, Secret Manager, Service Account, and Cloud Scheduler are NOT part of the Docker build/push/deploy process.**
> They are **runtime infrastructure** — they exist so the app can function correctly every time Cloud Run executes it.

---

## 2. One-Time Deployment Workflow (Step-by-Step)

Below is the **exact sequence** from the deployment script. Each step must complete before the next one starts.

---

### Step 1: Configure gcloud CLI

Sets your GCP project and region so all subsequent commands target the correct project.

---

### Step 2: Enable Required GCP APIs

Activates 5 GCP APIs — Cloud Run, Cloud Build, Cloud Storage, Cloud Scheduler, and Secret Manager. Without this, none of the services can be used.

---

### Step 3: Create Cloud Storage (GCS) Bucket

Creates a GCS bucket for persistent snapshot storage.

- Cloud Run containers are **ephemeral** — files are destroyed when the container shuts down.
- GCS provides **persistent storage** that survives across container restarts.
- **Before each run:** Previous snapshots are **downloaded** from GCS (the "last known state").
- **After each run:** Updated snapshots are **uploaded** back to GCS for the next comparison cycle.
- Grants the Cloud Run service account read/write/delete access to the bucket.

---

### Step 4: Create Secret in Secret Manager

Stores the email SMTP password securely in Secret Manager.

- Avoids hardcoding passwords in code or environment variables.
- Secret Manager encrypts and securely stores the password.
- Cloud Run injects it as an environment variable at runtime.
- Grants the service account permission to access the secret.

---

### Step 5: Build Docker Image (Cloud Build)

Builds the application Docker image on Google's servers using Cloud Build.

- Source code is uploaded to Cloud Build.
- Cloud Build reads the Dockerfile and builds the image (Python, Chrome, application code).
- The built image is automatically stored in **Artifact Registry / Container Registry**.

---

### Step 6: Deploy to Cloud Run

Deploys the Docker image as a managed Cloud Run service.

- Only authenticated requests can invoke the service (public access is blocked).
- Allocates sufficient resources for running the browser-based scraper.
- Injects email configuration and documentation URL as environment variables.
- Mounts the Secret Manager secret as an environment variable.
- Returns a **Service URL** that Cloud Scheduler will use to trigger runs.

---

### Step 7: Create Service Account for Cloud Scheduler

Creates a dedicated service account for Cloud Scheduler.

- Cloud Run is deployed as **private** (no public access).
- Cloud Scheduler needs an authenticated identity to call Cloud Run.
- This service account is granted the **Cloud Run Invoker** role.
- Cloud Scheduler uses it to generate authentication tokens for each request.

---

### Step 8: Create Cloud Scheduler Job

Creates a scheduled job that triggers the monitoring automatically.

- Runs on a **daily schedule** at 9:00 AM and 6:00 PM.
- Sends an authenticated HTTP request to the Cloud Run service URL.
- Uses the service account created in Step 7 for authentication.
- This is what makes the entire system fully automated.

---

### Step 9: Test the Deployment

Manually triggers the scheduler job to verify the full pipeline works end-to-end.

---

## 3. Runtime Workflow (When Cloud Scheduler Fires)

Every time Cloud Scheduler triggers (daily at 9 AM and 6 PM, or manually), here is the **exact sequence of events**:

---

### Stage 1: Cloud Scheduler → Cloud Run (THE TRIGGER)

```
Cloud Scheduler fires at 9:00 AM or 6:00 PM
    │
    ├── Generates an OIDC token (signed as sap-monitor-scheduler service account)
    ├── Sends HTTP POST to Cloud Run service URL
    │
    ▼
Cloud Run receives the authenticated HTTP POST request
    │
    ├── Verifies OIDC token → authenticated ✓
    ├── Spins up a fresh container (cold start if no warm instance)
    ├── Flask app (cloud_run_app.py) handles request at route '/'
    ├── Calls main.main() — starts the monitoring logic
    │
    ▼
```

---

### Stage 2: Download Previous Snapshots from GCS

```
main.main() starts
    │
    ├── Checks: is GCS_BUCKET_NAME env var set? (is_gcs_enabled())
    │
    ├── YES → GCS Mode (Cloud Run):
    │   ├── Wipes any local .txt snapshots baked into the Docker image
    │   ├── Downloads ALL previous .txt snapshot files from GCS bucket
    │   │   (gs://{PROJECT_ID}-sap-snapshots/snapshots/*.txt)
    │   └── These represent the "last known state" of each SAP doc page
    │
    ├── NO → Local Mode (development):
    │   └── Uses snapshots already in the local snapshots/ directory
    │
    ▼
```

**Why this stage exists:**
Cloud Run containers are ephemeral — every container starts fresh with no memory of previous runs. GCS acts as the "persistent memory" between runs.

---

### Stage 3: Discover & Fetch SAP Documentation Pages

```
    │
    ├── Auto-discovers all documentation page URLs from SAP Help TOC
    │   (Uses Selenium + headless Chrome to load the TOC page)
    │
    ├── For each discovered page:
    │   ├── Fetches the full HTML content (headless Chrome)
    │   ├── Extracts text content from HTML (parser/parse_content.py)
    │   └── Validates content (rejects pages with < 100 chars — likely rendering failures)
    │
    ▼
```

---

### Stage 4: Compare Current vs. Previous Content

```
    │
    ├── For each page:
    │   ├── If NO previous snapshot exists → marks as NEW PAGE
    │   ├── If previous snapshot exists → compares old text vs. new text
    │   │   ├── Detects additions (new lines)
    │   │   ├── Detects removals (deleted lines)
    │   │   ├── Detects structural warnings
    │   │   └── Validates: blocks suspicious changes (>70% shrinkage = rendering failure)
    │   └── Collects all changes into a report
    │
    ▼
```

---

### Stage 5: Save Updated Snapshots & Upload to GCS

```
    │
    ├── Saves updated/new snapshots to local filesystem inside container
    │
    ├── If GCS is enabled:
    │   ├── Uploads ALL local snapshots to GCS bucket
    │   └── Deletes stale GCS files that no longer exist locally (sync)
    │
    ▼
```

**Why this stage exists:**
The updated snapshots must be persisted to GCS so the **next** run (at 6 PM the same day, or 9 AM the next day) can download them and compare again.

---

### Stage 6: Send Email Notification (Secret Manager provides password)

```
    │
    ├── Builds email notification (HTML + plain text) with:
    │   ├── Summary of changes detected (or "no changes")
    │   ├── Details of additions/removals per page
    │   └── Links to changed pages
    │
    ├── Reads EMAIL_PASSWORD from environment variable
    │   (injected by Secret Manager via Cloud Run's --update-secrets)
    │
    ├── Connects to SMTP server (smtp.office365.com:587)
    ├── Sends email to configured recipients
    │
    ▼
```

---

### Stage 7: Cloud Run Returns Response

```
    │
    ├── Returns HTTP 200 (success) or HTTP 500 (error) to Cloud Scheduler
    ├── Container may be kept warm briefly or shut down
    │
    ▼ DONE
```

---

## 4. Visual Diagrams

### Deployment Flow (One-Time Setup)

```mermaid
flowchart TD
    Start(["🚀 Start Deployment"])
    Start --> S1

    S1["Step 1 — Configure gcloud CLI<br/>Set project & region"]
    S1 --> S2

    S2["Step 2 — Enable GCP APIs<br/>Cloud Run, Cloud Build, GCS,<br/>Secret Manager, Cloud Scheduler"]
    S2 --> S3

    S3["Step 3 — Create GCS Bucket<br/>Persistent snapshot storage"]
    S3 --> S4

    S4["Step 4 — Create Secret<br/>Store email password<br/>in Secret Manager"]
    S4 --> S5

    S5["Step 5 — Cloud Build<br/>Build Docker image<br/>from source code"]
    S5 --> S5a

    S5a["Artifact Registry<br/>Stores built Docker image"]
    S5a --> S6

    S6["Step 6 — Deploy to Cloud Run<br/>Pulls image from registry<br/>Mounts secret as env var<br/>Connects to GCS bucket"]
    S6 --> S7

    S7["Step 7 — Create Service Account<br/>sap-monitor-scheduler<br/>Grant Cloud Run invoker role"]
    S7 --> S8

    S8["Step 8 — Create Cloud Scheduler<br/>Cron: 9 AM & 6 PM daily<br/>Points to Cloud Run URL<br/>Uses Service Account for auth"]
    S8 --> S9

    S9["Step 9 — Test Run<br/>Manually trigger scheduler"]
    S9 --> Done(["✅ Deployment Complete"])

    style Start fill:#059669,color:#fff,stroke:none
    style Done fill:#059669,color:#fff,stroke:none
    style S1 fill:#EFF6FF,stroke:#3B82F6,color:#1E293B
    style S2 fill:#EFF6FF,stroke:#3B82F6,color:#1E293B
    style S3 fill:#FFF7ED,stroke:#F97316,color:#1E293B
    style S4 fill:#F0FDF4,stroke:#22C55E,color:#1E293B
    style S5 fill:#EDE9FE,stroke:#7C3AED,color:#1E293B
    style S5a fill:#EDE9FE,stroke:#7C3AED,color:#1E293B
    style S6 fill:#DBEAFE,stroke:#2563EB,color:#1E293B
    style S7 fill:#FEF3C7,stroke:#F59E0B,color:#1E293B
    style S8 fill:#FEF3C7,stroke:#F59E0B,color:#1E293B
    style S9 fill:#FCE7F3,stroke:#EC4899,color:#1E293B
```

### Runtime Flow (Every Scheduled Run)

```mermaid
flowchart TD
    Scheduler(["☁️ Cloud Scheduler<br/>Triggers twice daily"])
    Scheduler --> CloudRun

    CloudRun["☁️ Cloud Run<br/>Starts the application"]
    CloudRun --> Download

    Download["☁️ Cloud Storage — GCS<br/>Download previous snapshots"]
    Download --> Discover

    Discover["Discover SAP documentation pages<br/>via Selenium — Web Automation"]
    Discover --> Fetch

    Fetch["Fetch all pages from SAP Help Portal<br/>via Chrome Browser — Headless"]
    Fetch --> Compare

    Compare["Compare current content<br/>with previous snapshots<br/>via Comparator Engine"]
    Compare --> Changed

    Changed{"Any changes<br/>detected?"}
    Changed -->|No| DoneIdle(["✅ Done — No Changes"])
    Changed -->|Yes| Save

    Save["Save updated snapshots"]
    Save --> Upload

    Upload["☁️ Cloud Storage — GCS<br/>Upload new snapshots"]
    Upload --> Secret

    Secret["☁️ Secret Manager<br/>Retrieve email credentials"]
    Secret --> Email

    Email["Send email notification<br/>with change report"]
    Email --> DoneChanges(["✅ Done — Report Sent"])

    style Scheduler fill:#4285F4,color:#fff,stroke:none
    style CloudRun fill:#4285F4,color:#fff,stroke:none
    style Download fill:#F4B400,color:#1E293B,stroke:none
    style Discover fill:#E8F0FE,stroke:#4285F4,color:#1E293B
    style Fetch fill:#E8F0FE,stroke:#4285F4,color:#1E293B
    style Compare fill:#E8F0FE,stroke:#4285F4,color:#1E293B
    style Changed fill:#FEF3C7,stroke:#F59E0B,color:#1E293B
    style Save fill:#E8F0FE,stroke:#4285F4,color:#1E293B
    style Upload fill:#F4B400,color:#1E293B,stroke:none
    style Secret fill:#34A853,color:#fff,stroke:none
    style Email fill:#EA4335,color:#fff,stroke:none
    style DoneIdle fill:#059669,color:#fff,stroke:none
    style DoneChanges fill:#059669,color:#fff,stroke:none
```

### Complete GCP Services Interaction Map

```mermaid
flowchart LR
    subgraph DEPLOYMENT["🔧 DEPLOYMENT TIME — One-Time Setup"]
        direction LR
        Src["Source Code<br/>+ Dockerfile"] --> CB["☁️ Cloud Build<br/>Builds image"]
        CB --> AR["☁️ Artifact Registry<br/>Stores image"]
        AR --> CR1["☁️ Cloud Run<br/>Deploys service"]
    end

    subgraph RUNTIME["⚡ RUNTIME — Every Scheduled Run"]
        direction LR
        CS["☁️ Cloud Scheduler<br/>Trigger"] --> CR2["☁️ Cloud Run<br/>Execute"]
        SA["☁️ Service Account<br/>Authenticate"] -.->|OIDC Token| CS
        CR2 --> GCS["☁️ Cloud Storage<br/>Snapshots"]
        CR2 --> SM["☁️ Secret Manager<br/>Email Password"]
        CR2 --> SMTP["Email Server<br/>Office 365"]
    end

    style DEPLOYMENT fill:#EFF6FF,stroke:#3B82F6,color:#1E293B
    style RUNTIME fill:#F0FDF4,stroke:#22C55E,color:#1E293B
    style Src fill:#F1F5F9,stroke:#64748B,color:#1E293B
    style CB fill:#4285F4,color:#fff,stroke:none
    style AR fill:#4285F4,color:#fff,stroke:none
    style CR1 fill:#4285F4,color:#fff,stroke:none
    style CS fill:#F4B400,color:#1E293B,stroke:none
    style CR2 fill:#4285F4,color:#fff,stroke:none
    style SA fill:#7C3AED,color:#fff,stroke:none
    style GCS fill:#F4B400,color:#1E293B,stroke:none
    style SM fill:#34A853,color:#fff,stroke:none
    style SMTP fill:#EA4335,color:#fff,stroke:none
```

---

## Summary: Why Each Service Exists

| Service | One-Line Purpose |
|---------|-----------------|
| **Cloud Build** | Builds the Docker image from source code on Google's servers (replaces local `docker build` + `docker push`) |
| **Artifact Registry** | Stores the built Docker image so Cloud Run can pull it |
| **Cloud Run** | Runs the containerized Flask app that performs the monitoring logic |
| **GCS Bucket** | Persistent storage for snapshots — because Cloud Run containers are destroyed after each run and lose all local files |
| **Secret Manager** | Securely stores the email password — injected into Cloud Run as an env var at runtime |
| **Service Account** | Gives Cloud Scheduler an authenticated identity to call the private (no public access) Cloud Run endpoint |
| **Cloud Scheduler** | The automated trigger — sends HTTP POST to Cloud Run on a cron schedule (9 AM & 6 PM daily) so the monitoring runs automatically twice a day |

> **Bottom line:** Cloud Build + Artifact Registry + Cloud Run = **Deployment chain**. GCS + Secret Manager + Service Account + Cloud Scheduler = **Runtime infrastructure** that makes the app work automatically and securely every day.
