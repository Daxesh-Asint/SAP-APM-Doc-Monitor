# SAP APM Documentation Monitor — Complete System Documentation

> **Note:** This document provides a comprehensive explanation of the system architecture, GCP services used, and the end-to-end automation flow. Replace placeholder values (e.g., `your-project-id`) with your actual GCP project details when deploying.

## Table of Contents

1. [What Is This Project?](#1-what-is-this-project)
2. [How the Automation Works (Step by Step)](#2-how-the-automation-works-step-by-step)
3. [Project Structure & Files Explained](#3-project-structure--files-explained)
4. [GCP Services Used](#4-gcp-services-used)
5. [How GCP Deployment Works](#5-how-gcp-deployment-works)
6. [How Email Notification Works](#6-how-email-notification-works)
7. [How All Services Work Together](#7-how-all-services-work-together)
8. [Complete Flow Walkthrough (Real Example)](#8-complete-flow-walkthrough-real-example)
9. [Configuration Details](#9-configuration-details)
10. [Common Commands Reference](#10-common-commands-reference)

---

## 1. What Is This Project?

**SAP Documentation Monitor** is an automated tool that watches SAP Help Portal documentation pages for any changes (new content added, content removed, or content modified). When changes are detected, it sends an email notification with a detailed summary of what changed.

### The Problem It Solves

SAP frequently updates its documentation — new features, changed procedures, updated configurations. Without this tool, someone would have to manually check 25+ documentation pages to see if anything changed. This tool automates that entire process.

### What It Does (Simple Summary)

```
Every weekday at 9 AM:
  1. Opens all 25 SAP documentation pages (automatically discovered)
  2. Reads the content from each page
  3. Compares with the previously saved version
  4. If something changed → sends email alert
  5. Saves the new version for next time
```

---

## 2. How the Automation Works (Step by Step)

The automation runs through **7 stages** every time it executes:

### Stage 1: Trigger (Cloud Scheduler)

```
Cloud Scheduler sends HTTP POST → Cloud Run container starts
```

- Cloud Scheduler is like an alarm clock — it fires at 9 AM on weekdays
- It sends an HTTP request to Cloud Run, which wakes up the container
- The Flask app (`cloud_run_app.py`) receives this request and calls `main()`

### Stage 2: Download Previous Snapshots (Cloud Storage)

```
Cloud Run → Downloads 25 .txt files from Cloud Storage bucket
```

- Cloud Run containers are **ephemeral** (they don't remember anything between runs)
- So before starting, the app downloads all previously saved snapshots from Google Cloud Storage
- These snapshots are plain text files containing the content from the last run
- File: `storage/gcs_storage.py` → `download_all_snapshots()`

### Stage 3: Auto-Discover Documentation Pages

```
Fetches base URL → Parses Table of Contents → Finds all 25 page URLs
```

- Instead of manually listing 25 URLs, we provide ONE base URL
- The system opens that URL with Selenium (headless Chrome browser)
- It parses the Table of Contents (sidebar navigation) to find all documentation page links
- Returns a dictionary like: `{"Overview of Getting Started Steps": "https://help.sap.com/...", ...}`
- File: `fetcher/discover_urls.py` → `discover_documentation_urls()`

### Stage 4: Fetch Each Page & Extract Text

```
For each of 25 pages:
  Open page with Chrome → Wait for JavaScript to load → Get HTML → Extract clean text
```

**Why Selenium (Chrome)?**  
SAP Help Portal uses heavy JavaScript to render content. A simple HTTP request would get an empty page. Selenium opens a real Chrome browser (headless = no visible window), lets JavaScript execute, then captures the fully rendered HTML.

**Text Extraction:**  
The raw HTML contains navigation menus, buttons, scripts, CSS, cookie banners, etc. The parser strips all of that and extracts ONLY the documentation content — headings, paragraphs, lists, notes, and code blocks.

- File: `fetcher/fetch_page.py` → `fetch_page()` — Opens page with Selenium
- File: `parser/parse_content.py` → `extract_text()` — Cleans HTML to plain text

### Stage 5: Compare with Previous Snapshots

```
For each page:
  Load old snapshot (.txt file) → Compare line by line with new content → Identify changes
```

The comparator uses Python's `difflib` library to do a line-by-line comparison:

- Lines starting with `+` = **new content added**
- Lines starting with `-` = **content removed**
- Unchanged lines are ignored

**Smart Filtering:**  
The comparator also has a false-positive filter. If content merely *moved position* on the page (same text, different line number), it ignores that. Only truly new or truly removed content counts as a change.

- File: `comparator/compare_content.py` → `compare()`

### Stage 6: Send Email Notification (If Changes Found)

```
If any page has changes:
  Build email body with change summary → Connect to SMTP server → Send email
```

The email contains:
- Date and time of the check
- How many pages were monitored (25)
- How many pages had changes
- For each changed page: URL, what was added, what was removed

- File: `notifier/send_email.py` → `send_email()`

### Stage 7: Upload Updated Snapshots (Cloud Storage)

```
Upload all 25 .txt snapshot files back to Cloud Storage
```

After processing, the updated snapshots (with any new content) are saved back to Cloud Storage. Next time the automation runs, it will compare against these updated files.

- File: `storage/gcs_storage.py` → `upload_all_snapshots()`

---

## 3. Project Structure & Files Explained

```
SAP Doc Monitor/
│
├── Dockerfile                    # Container build instructions
├── .dockerignore                 # Files excluded from Docker image
├── deploy-to-cloud-run.ps1      # Automated deployment script (Windows)
├── deploy-to-cloud-run.sh       # Automated deployment script (Linux/Mac)
│
└── sap-doc-monitor/              # Main application code
    │
    ├── cloud_run_app.py          # Flask HTTP server for Cloud Run
    ├── main.py                   # Main orchestration logic
    ├── scheduler.py              # Local scheduler (for non-cloud usage)
    ├── requirements.txt          # Python package dependencies
    │
    ├── config/
    │   ├── settings.py           # Configuration (local development)
    │   └── settings.cloud.py     # Configuration (cloud - reads env vars)
    │
    ├── fetcher/
    │   ├── discover_urls.py      # Auto-discovers all doc pages from TOC
    │   └── fetch_page.py         # Opens web pages with Selenium/Chrome
    │
    ├── parser/
    │   └── parse_content.py      # Extracts clean text from HTML
    │
    ├── comparator/
    │   └── compare_content.py    # Compares old vs new text content
    │
    ├── notifier/
    │   └── send_email.py         # Sends email via SMTP
    │
    ├── storage/
    │   └── gcs_storage.py        # Google Cloud Storage integration
    │
    └── snapshots/                # Local snapshot files (for development)
        ├── 1_Overview_of_Getting_Started_Steps.txt
        ├── 2_Target_Audience.txt
        ├── ... (25 files total)
        └── 25_Data_Return_Post_Contract_Expiry_and_Deletion.txt
```

### What Each File Does

| File | Purpose |
|------|---------|
| `cloud_run_app.py` | Flask web server that listens for HTTP requests. When Cloud Scheduler sends a POST request, it calls `main()` to run the monitor. |
| `main.py` | The brain of the application. Orchestrates all 7 stages: download snapshots, discover URLs, fetch pages, compare, email, upload snapshots. |
| `settings.cloud.py` | Reads configuration from environment variables (set in Cloud Run). Has fallback default values. |
| `discover_urls.py` | Takes a single base URL, opens the page, finds the Table of Contents, and extracts all documentation page URLs. |
| `fetch_page.py` | Opens a URL using Selenium with headless Chrome. Waits for JavaScript to render, then returns the full HTML. |
| `parse_content.py` | Takes raw HTML and strips away navigation, scripts, CSS, buttons — returns only clean documentation text. |
| `compare_content.py` | Compares two text strings line-by-line. Returns only genuine additions and removals (filters out position-only changes). |
| `send_email.py` | Connects to an SMTP server (Microsoft 365) and sends an email with the change summary. |
| `gcs_storage.py` | Downloads/uploads snapshot files to/from Google Cloud Storage bucket for persistence between runs. |
| `Dockerfile` | Instructions to build a Docker container with Python, Chrome, and all dependencies. |

---

## 4. GCP Services Used

We use **7 Google Cloud Platform services**. Here's what each one does and why we need it:

### 4.1 Cloud Run (Container Execution)

**What it is:** A serverless platform that runs Docker containers.

**Why we need it:** Our Python application needs Chrome browser installed to render SAP pages. Cloud Run runs our pre-built Docker container (which has Python + Chrome + our code) on demand.

**How it works:**
- Container sits idle (costs nothing)
- Cloud Scheduler sends HTTP request → container starts
- Application runs (fetches pages, compares, emails)
- Container stops automatically after completion

**Key settings:**
- Memory: 2 GB (Chrome needs significant memory)
- CPU: 2 cores
- Timeout: 900 seconds (15 minutes max per run)
- Max instances: 1 (only one run at a time)

### 4.2 Cloud Scheduler (Cron Timer)

**What it is:** A managed cron job service — like a programmable alarm clock.

**Why we need it:** To automatically trigger the monitoring at scheduled intervals.

**How it works:**
- We configure a cron schedule: `0 9 * * 1-5` (9 AM, Monday-Friday)
- At the scheduled time, Cloud Scheduler sends an HTTP POST request to our Cloud Run service URL
- It uses a service account with `roles/run.invoker` permission to authenticate

**Our schedule:** Weekdays at 9:00 AM IST (Asia/Kolkata timezone)

### 4.3 Cloud Build (Docker Image Builder)

**What it is:** A service that builds Docker images from source code in the cloud.

**Why we need it:** We need to package our Python code + Chrome browser into a Docker image. Cloud Build does this in the cloud (so we don't need Docker installed locally).

**How it works:**
- We run `gcloud builds submit` from our terminal
- It uploads our source code to Google Cloud
- Cloud Build reads our `Dockerfile` and builds the image
- The finished image is stored in Container Registry

### 4.4 Container Registry (GCR) (Image Storage)

**What it is:** A place to store Docker images.

**Why we need it:** Cloud Run needs to pull our Docker image from somewhere. Container Registry stores the image so Cloud Run can access it.

**Our image:** `gcr.io/<your-project-id>/sap-doc-monitor`

### 4.5 Cloud Storage (GCS) (File Storage)

**What it is:** Object storage for files — like Google Drive but for applications.

**Why we need it:** Cloud Run containers are ephemeral (they lose all data when they stop). We need to persist our snapshot files between runs so we can compare old vs new content.

**How it works:**
- Before monitoring: Download all 25 snapshot files from the bucket
- After monitoring: Upload all 25 updated snapshot files back to the bucket
- Files are stored as: `gs://<your-project-id>-sap-snapshots/snapshots/*.txt`

**Our bucket:** `<your-project-id>-sap-snapshots`

### 4.6 Cloud Logging (Automatic)

**What it is:** Centralized logging for all GCP services.

**Why we need it:** To see what the application is doing, debug issues, and verify successful runs.

**How it works:**
- All `print()` statements from our Python code automatically appear in Cloud Logging
- We can filter by service, severity, time range
- Accessible via: `gcloud logging read` or GCP Console

### 4.7 IAM — Identity and Access Management (Security)

**What it is:** Permission system that controls who/what can access which GCP resources.

**Why we need it:** To allow Cloud Scheduler to trigger Cloud Run, and Cloud Run to access Cloud Storage — but nothing more (principle of least privilege).

**Service accounts used:**
- `sap-monitor-scheduler@...` — Used by Cloud Scheduler, has only `roles/run.invoker` permission
- Default Cloud Run service account — Has access to Cloud Storage bucket

---

## 5. How GCP Deployment Works

### 5.1 The Dockerfile (Container Blueprint)

The Dockerfile is a recipe that tells Cloud Build exactly how to build our container:

```
Step 1: Start with Python 3.11 base image (lightweight Linux)
Step 2: Install system libraries needed by Chrome browser
Step 3: Download and install Google Chrome
Step 4: Copy requirements.txt and install Python packages
Step 5: Copy our application code
Step 6: Replace settings.py with cloud version (reads env vars)
Step 7: Set environment variables
Step 8: Define startup command: python cloud_run_app.py
```

The resulting Docker image is ~1.5 GB (mostly Chrome browser) and contains everything needed to run the application.

### 5.2 How Cloud Run Serves Requests

When deployed, Cloud Run creates a URL endpoint:  
`https://<service-name>-<hash>.<region>.run.app`

Inside the container, `cloud_run_app.py` runs a Flask web server on port 8080:

```python
@app.route('/', methods=['GET', 'POST'])
def trigger_monitor():
    run_monitor()   # Calls main() from main.py
    return {'status': 'success'}
```

When Cloud Scheduler sends an HTTP POST to this URL:
1. Cloud Run starts the container (if not already running)
2. Flask receives the request
3. `main()` runs the full monitoring cycle
4. Flask returns "success" or "error"
5. Container goes idle (or shuts down after inactivity)

### 5.3 Environment Variables

Instead of hardcoding secrets in code, Cloud Run injects them as environment variables:

| Variable | Purpose | Example |
|----------|---------|---------|
| `EMAIL_SENDER` | Email "From" address | `ais.support@asint.net` |
| `EMAIL_PASSWORD` | SMTP login password | `(stored securely)` |
| `EMAIL_RECEIVER` | Email "To" address(es) | `learn.sapui5.frontend@gmail.com` |
| `SMTP_SERVER` | Email server hostname | `smtp.office365.com` |
| `SMTP_PORT` | Email server port | `587` |
| `BASE_DOCUMENTATION_URL` | SAP docs base URL | `https://help.sap.com/docs/...` |
| `GCS_BUCKET_NAME` | Cloud Storage bucket | `<your-project-id>-sap-snapshots` |
| `SNAPSHOTS_DIR` | Local snapshot path | `/app/snapshots` |

The `settings.cloud.py` file reads these using `os.getenv()`:

```python
EMAIL_SENDER = os.getenv('EMAIL_SENDER', "default-value")
```

---

## 6. How Email Notification Works

### 6.1 The SMTP Protocol

Email is sent using the **SMTP (Simple Mail Transfer Protocol)** — a standard way for applications to send email through a mail server.

### 6.2 Our Email Setup

```
Our App → SMTP Connection → Microsoft 365 Server → Recipient's Inbox
           (port 587)       (smtp.office365.com)
```

**Connection Steps (inside `send_email.py`):**

```
1. Open TCP connection to smtp.office365.com on port 587
2. Start TLS encryption (so password is sent securely)
3. Login with EMAIL_SENDER + EMAIL_PASSWORD
4. Compose email (From, To, Subject, Body)
5. Send the message
6. Close connection
```

### 6.3 What the Email Contains

When changes are detected, the email includes:

```
Subject: SAP Documentation Update - 2 Page(s) Changed

Body:
  - Date and time
  - Total pages monitored (25)
  - Total pages changed (e.g., 2)
  
  For each changed page:
    - Page name and URL
    - New content count (e.g., "3 items added")
    - Removed content count (e.g., "1 item removed")
    - First 5 items of new content (with text preview)
    - First 5 items of removed content (with text preview)
  
  Recommendation section:
    - Review for new features
    - Check updated procedures
    - Note modified guidelines
```

### 6.4 Multiple Recipients

The system supports sending to multiple recipients:

```python
EMAIL_RECEIVER = "person1@email.com, person2@email.com, person3@email.com"
```

The code splits by comma and sends to all:

```python
recipients = [email.strip() for email in settings.EMAIL_RECEIVER.split(',')]
```

---

## 7. How All Services Work Together

### Complete Flow Diagram

```
                                    GOOGLE CLOUD PLATFORM
┌──────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│   ┌──────────────────┐     HTTP POST      ┌───────────────────────────────────┐ │
│   │  CLOUD SCHEDULER │ ──────────────────► │         CLOUD RUN               │ │
│   │                  │  (authenticated     │                                   │ │
│   │  ⏰ Weekdays     │   via service       │  ┌─────────────────────────────┐ │ │
│   │  at 9 AM IST     │   account)          │  │  Docker Container          │ │ │
│   └──────────────────┘                     │  │                             │ │ │
│                                             │  │  1. Flask receives request  │ │ │
│   ┌──────────────────┐                     │  │  2. Download snapshots ◄────┼─┤─┼── Cloud Storage
│   │  CLOUD BUILD     │                     │  │  3. Discover 25 URLs        │ │ │   (GCS Bucket)
│   │                  │  builds image       │  │  4. Fetch pages (Chrome)    │ │ │
│   │  📦 Builds       │ ──────────────────► │  │  5. Extract text content    │ │ │
│   │  Docker image    │                     │  │  6. Compare with snapshots  │ │ │
│   └──────────────────┘                     │  │  7. Send email (if changes) │ │ │
│                                             │  │  8. Upload snapshots ──────┼─┤─┼─► Cloud Storage
│   ┌──────────────────┐                     │  │                             │ │ │   (GCS Bucket)
│   │  CONTAINER       │  stores image       │  │  Python 3.11 + Chrome +    │ │ │
│   │  REGISTRY (GCR)  │ ◄────────────────── │  │  Selenium + BeautifulSoup  │ │ │
│   │                  │                     │  │                             │ │ │
│   │  💾 Stores       │  pulls image        │  └─────────────────────────────┘ │ │
│   │  Docker image    │ ──────────────────► │                                   │ │
│   └──────────────────┘                     └───────────────────────────────────┘ │
│                                                           │                      │
│   ┌──────────────────┐                                    │                      │
│   │  CLOUD LOGGING   │ ◄─── all output ──────────────────┘                      │
│   │  📋 Logs         │                                                           │
│   └──────────────────┘                                                           │
│                                                                                  │
│   ┌──────────────────┐                                                           │
│   │  IAM             │ ── manages permissions between all services               │
│   │  🔐 Security     │                                                           │
│   └──────────────────┘                                                           │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │ SMTP (smtp.office365.com:587)
                                       ▼
                              ┌───────────────────┐
                              │  MICROSOFT 365     │
                              │  ✉️ Email Server    │
                              └────────┬──────────┘
                                       │
                                       ▼
                              ┌───────────────────┐
                              │  📬 RECIPIENTS     │
                              │  Email Inbox       │
                              └───────────────────┘
```

### Service Communication Summary

| From | To | What | How |
|------|----|------|-----|
| Cloud Scheduler | Cloud Run | Trigger monitoring | HTTP POST with OIDC token |
| Cloud Run | Cloud Storage | Download/Upload snapshots | Google Cloud Storage API |
| Cloud Run | SAP Help Portal | Fetch documentation | HTTPS via Selenium Chrome |
| Cloud Run | Microsoft 365 SMTP | Send email notification | SMTP over TLS (port 587) |
| Cloud Run | Cloud Logging | Write application logs | Automatic (stdout/stderr) |
| Cloud Build | Container Registry | Store built Docker image | Docker push |
| Cloud Run | Container Registry | Pull Docker image | Docker pull |
| IAM | All services | Authenticate & authorize | Service accounts + roles |

---

## 8. Complete Flow Walkthrough (Real Example)

Here's exactly what happens when the automation runs on a typical morning:

### 9:00 AM IST — Cloud Scheduler Fires

```
Cloud Scheduler checks: "Is it 9 AM on a weekday? → YES"
Cloud Scheduler sends: HTTP POST to https://<service-name>-<hash>.<region>.run.app
Authentication: Uses service account sap-monitor-scheduler@<your-project-id>.iam.gserviceaccount.com
                with OIDC token for authentication
```

### 9:00:02 AM — Cloud Run Starts Container

```
Cloud Run pulls image: gcr.io/<your-project-id>/sap-doc-monitor
Cloud Run starts container with environment variables injected
Flask server starts on port 8080
Flask receives the POST request → calls main()
```

### 9:00:03 AM — Download Previous Snapshots

```
main() checks: GCS_BUCKET_NAME is set → GCS is enabled
Downloads 25 .txt files from gs://<your-project-id>-sap-snapshots/snapshots/
Files like: 1_Overview_of_Getting_Started_Steps.txt, 2_Target_Audience.txt, etc.
Saves them to /app/snapshots/ inside the container
```

### 9:00:05 AM — Auto-Discover URLs

```
Opens base URL with Selenium Chrome:
  https://help.sap.com/docs/SAP_APM/2602f93216bb4530ba169c75be619edf/0840fd102be84f3ab8f8662a91f949a3.html

Chrome renders the page (JavaScript executes)
Parser finds the Table of Contents sidebar
Extracts 25 documentation page URLs:
  1. Overview of Getting Started Steps → https://help.sap.com/docs/...
  2. Target Audience → https://help.sap.com/docs/...
  ... (25 total)
```

### 9:00:10 AM — Process Each Page (25 pages, ~5 seconds each)

```
For page "Overview of Getting Started Steps":
  1. Selenium opens: https://help.sap.com/docs/.../0840fd102be84f3ab8f8662a91f949a3.html
  2. Waits 3 seconds for JavaScript to render
  3. Gets full HTML (e.g., 180,000 characters)
  4. Parser extracts clean text (e.g., 4,500 characters)
  5. Loads previous snapshot: /app/snapshots/1_Overview_of_Getting_Started_Steps.txt
  6. Compares line by line using difflib
  7. Result: No changes → moves to next page

For page "Release Schedule and Dates for 2026":
  1. Selenium opens the URL
  2. Gets HTML, extracts text
  3. Loads previous snapshot
  4. Compares: finds 3 new lines added (new release dates!)
  5. Result: Changes detected → adds to change list
  6. Updates local snapshot file with new content

... repeats for all 25 pages ...
```

### 9:02:15 AM — Send Email (If Changes Found)

```
Changes found in 1 page → build email:

Subject: "SAP Documentation Update - 1 Page(s) Changed"
Body: Summary of changes for "Release Schedule and Dates for 2026"
  - 3 new lines added (new Q3 2026 release dates)

Connect to smtp.office365.com:587 → TLS → Login → Send
Email sent to: learn.sapui5.frontend@gmail.com
```

### 9:02:18 AM — Upload Snapshots to Cloud Storage

```
Uploads 25 .txt files back to gs://<your-project-id>-sap-snapshots/snapshots/
The "Release Schedule" snapshot now contains the updated content
Next run will compare against this updated version
```

### 9:02:20 AM — Done

```
Flask returns: {"status": "success"} with HTTP 200
Cloud Run logs: "Monitoring completed successfully"
Container goes idle → eventually shuts down
```

**Total run time: ~2 minutes**

---

## 9. Configuration Details

### 9.1 Current Configuration

| Setting | Value |
|---------|-------|
| **GCP Project ID** | `<your-project-id>` |
| **Region** | `us-central1` |
| **Service Name** | `sap-doc-monitor` |
| **Service URL** | `https://<service-name>-<hash>.<region>.run.app` |
| **Schedule** | Weekdays at 9:00 AM IST |
| **GCS Bucket** | `<your-project-id>-sap-snapshots` |
| **Docker Image** | `gcr.io/<your-project-id>/sap-doc-monitor` |
| **Email From** | `ais.support@asint.net` |
| **Email To** | `learn.sapui5.frontend@gmail.com` |
| **SMTP Server** | `smtp.office365.com:587` |
| **Pages Monitored** | 25 (auto-discovered) |

### 9.2 Python Libraries Used

| Library | Version | Purpose |
|---------|---------|---------|
| `selenium` | ≥4.0.0 | Controls Chrome browser to render JavaScript-heavy pages |
| `beautifulsoup4` | ≥4.9.0 | Parses HTML content and extracts text |
| `requests` | ≥2.25.0 | Simple HTTP requests for non-JavaScript pages |
| `webdriver-manager` | ≥3.8.0 | Auto-downloads correct ChromeDriver version |
| `APScheduler` | ≥3.10.0 | Local scheduling (for non-cloud usage) |
| `Flask` | ≥2.3.0 | HTTP server for Cloud Run endpoint |
| `google-cloud-storage` | ≥2.10.0 | Read/write files to Google Cloud Storage |
| `difflib` | (built-in) | Line-by-line text comparison |
| `smtplib` | (built-in) | Send emails via SMTP protocol |

---

## 10. Common Commands Reference

### Trigger Monitoring Manually
```powershell
gcloud scheduler jobs run sap-doc-monitor-job --location=us-central1
```

### View Recent Logs
```powershell
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=sap-doc-monitor" --limit=30 --format="table(timestamp, textPayload)" --freshness=30m
```

### Change Schedule
```powershell
# Every 3 hours
gcloud scheduler jobs update http sap-doc-monitor-job --location=us-central1 --schedule="0 */3 * * *"

# Daily at 9 AM weekdays
gcloud scheduler jobs update http sap-doc-monitor-job --location=us-central1 --schedule="0 9 * * 1-5"
```

### Update Email Receiver
```powershell
gcloud run services update sap-doc-monitor --region=us-central1 --update-env-vars EMAIL_RECEIVER="newemail@example.com"
```

### Rebuild and Redeploy After Code Changes
```powershell
cd "SAP Doc Monitor"
gcloud builds submit --tag gcr.io/<your-project-id>/sap-doc-monitor
gcloud run deploy sap-doc-monitor --image gcr.io/<your-project-id>/sap-doc-monitor --region=us-central1
```

### Check Service Status
```powershell
gcloud run services describe sap-doc-monitor --region=us-central1
gcloud scheduler jobs describe sap-doc-monitor-job --location=us-central1
```

### View Snapshots in Cloud Storage
```powershell
gsutil ls gs://<your-project-id>-sap-snapshots/snapshots/
```

---

## Summary

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Application** | Python 3.11 | Core monitoring logic |
| **Web Scraping** | Selenium + Chrome | Render JavaScript-heavy SAP pages |
| **Text Parsing** | BeautifulSoup | Extract clean documentation content |
| **Change Detection** | difflib | Compare old vs new content |
| **Email** | smtplib + Microsoft 365 | Send change notifications |
| **Container** | Docker | Package everything (Python + Chrome) |
| **Execution** | GCP Cloud Run | Run containers serverlessly |
| **Scheduling** | GCP Cloud Scheduler | Trigger runs on schedule |
| **Storage** | GCP Cloud Storage | Persist snapshots between runs |
| **Image Storage** | GCP Container Registry | Store Docker images |
| **Building** | GCP Cloud Build | Build Docker images in cloud |
| **Logging** | GCP Cloud Logging | Monitor and debug runs |
| **Security** | GCP IAM | Manage service permissions |

**Monthly Cost: ~$3-5 (for daily weekday runs)**
