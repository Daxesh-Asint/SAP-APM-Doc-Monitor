# GCP Deployment Workflow — High-Level Overview

> This document explains the full deployment and runtime workflow of the SAP Documentation Monitor on Google Cloud Platform (GCP). It is written for beginners and non-technical readers — no cloud knowledge is required. Light technical hints are included where helpful, but no full configurations or commands are shown.

---

## Table of Contents

1. [Deployment-Time Flowchart](#1-deployment-time-flowchart)
2. [Runtime Flowchart](#2-runtime-flowchart)
3. [Basic Technical Illustration](#3-basic-technical-illustration)
4. [GCP Services Table](#4-gcp-services-table)

---

## 1. Deployment-Time Flowchart

Deployment is the one-time process of setting up the application so it can run automatically on Google's servers. Think of it as "installing the application in the cloud." This only needs to happen once (or whenever the application is updated).

Here is the step-by-step flow of what happens during deployment:

---

**Step 1 — Select the Project**

The deployment begins by selecting which Google Cloud project to use. This is like choosing which workspace or account everything will be set up under. All the services created in later steps will belong to this project.

> *Technical hint:* Every GCP resource lives inside a "project," identified by a unique project ID.

⬇️

**Step 2 — Activate the Required Services**

Google Cloud has many services, but they are not turned on by default. Before anything can be set up, the specific services needed by this application are activated — Cloud Run, Cloud Build, Cloud Storage, Secret Manager, and Cloud Scheduler. This is a one-time switch; once turned on, these services are ready to use.

> *Technical hint:* GCP calls these "APIs." Enabling an API allows that service to be created and managed within the project.

⬇️

**Step 3 — Create a Storage Space for Document Snapshots**

A dedicated storage space (called a "bucket") is created in the cloud. This is where the application will save copies of the SAP documentation pages it monitors. These saved copies are called "snapshots." The storage space ensures that snapshots are preserved between runs, even though the application itself shuts down after each run.

> *Technical hint:* The bucket is a Cloud Storage resource, similar to a folder in the cloud where files can be uploaded and downloaded.

⬇️

**Step 4 — Store the Email Password Securely**

The application needs to send email notifications. Instead of placing the email password directly inside the application, it is stored in a secure vault provided by Google Cloud (Secret Manager). The application can retrieve the password from this vault whenever it needs to send an email. This keeps the password safe and separate from the application itself.

> *Technical hint:* Secret Manager stores the password in an encrypted form. At runtime, Cloud Run injects it into the application as an environment variable.

⬇️

**Step 5 — Build the Application Package**

The application and all its requirements (including a web browser used for reading SAP pages) are packaged together into a single unit called a "container image." This packaging happens on Google's servers using Cloud Build, not on the developer's computer. Once built, the container image is automatically saved in Artifact Registry — a storage area designed for application packages.

> *Technical hint:* A container image bundles the application code, its dependencies, and a web browser (Chrome) into one portable package. Think of it like a shipping container that holds everything the application needs to run.

⬇️

**Step 6 — Deploy the Application**

The container image from the previous step is now deployed to Cloud Run — meaning Google Cloud takes the package and makes it ready to run on demand. The application is configured so that only authorized requests can start it (it is not publicly accessible to anyone on the internet). The email settings and connection to the secure vault are also linked at this point. After this step, the application has a unique service URL that can be used to trigger it.

> *Technical hint:* Cloud Run pulls the container image from Artifact Registry and creates a managed service at a URL like `https://sap-doc-monitor-xxxxx.run.app`.

⬇️

**Step 7 — Create an Identity for the Scheduler**

Since the application is private (not open to the public), something needs permission to start it. A dedicated identity — called a "service account" — is created specifically for the scheduler (set up in the next step). This identity is granted the right to invoke the Cloud Run service. Without this identity, the scheduler would be blocked from triggering the application.

> *Technical hint:* The service account acts like a username that Cloud Scheduler uses to authenticate itself when calling Cloud Run.

⬇️

**Step 8 — Set Up the Automatic Scheduler**

A scheduled job is created in Cloud Scheduler that will automatically start the application at specific times each day (for example, at 9:00 AM and 6:00 PM). The scheduler sends an HTTP request to the Cloud Run service URL, using the identity created in the previous step to prove it has permission. From this point on, the application will run automatically without any human involvement.

> *Technical hint:* Cloud Scheduler uses a cron-style schedule and sends an authenticated HTTP POST request to the service URL on each trigger.

⬇️

**Step 9 — Verify Everything Works**

The scheduler is triggered manually one time to confirm that the entire system works end-to-end — from the scheduler starting the application, to the application checking SAP documentation, to the email notification being sent. If this test succeeds, the deployment is complete.

---

### Deployment Summary (at a Glance)

> Developer prepares application → Application is built (container image created) → Image stored in Artifact Registry → Service deployed to Cloud Run → Scheduler configured to trigger it → Service becomes fully automated

---

## 2. Runtime Flowchart

Runtime is what happens every time the application runs — either triggered automatically by the scheduler or started manually. This is the repeating cycle that happens twice a day (or on whatever schedule is configured).

Here is the step-by-step flow of what happens during each run:

---

**Stage 1 — Scheduler Triggers the Application**

At the scheduled time (e.g., 9:00 AM), Cloud Scheduler sends an authenticated HTTP POST request to the Cloud Run service URL. Cloud Run receives the request, verifies the identity, and spins up the application.

> *Technical hint:* The request includes an authentication token signed by the service account. Cloud Run validates it before starting the container.

⬇️

**Stage 2 — Application Starts and Receives the Request**

Cloud Run starts a fresh instance of the application. The HTTP request is received by the application's web server, which kicks off the monitoring logic.

> *Technical hint:* The application runs a lightweight web server (Flask). When a request arrives at the root route (`/`), it calls the main monitoring function.

⬇️

**Stage 3 — Retrieve Previous Snapshots from Storage**

The first thing the application does is download all previously saved document snapshots from Cloud Storage. These snapshots represent the "last known state" of each SAP documentation page. The application needs these to compare against the current state of the pages. If this is the very first run, there will be no previous snapshots, and everything will be treated as new.

> *Technical hint:* Snapshots are `.txt` files stored in a Cloud Storage bucket. They are downloaded into the container's local filesystem at the start of each run.

⬇️

**Stage 4 — Discover All Documentation Pages**

The application visits the SAP Help Portal and reads the table of contents to find all the documentation pages that need to be monitored. This discovery process ensures that if SAP adds new pages, they are automatically picked up without anyone needing to update the application.

> *Technical hint:* The application uses a headless web browser (Chrome) to load the SAP Help page, then extracts all documentation links from the table of contents.

⬇️

**Stage 5 — Fetch and Read Each Page**

For each page discovered in the previous stage, the application opens the page using the built-in web browser, waits for the content to fully load, and then extracts the readable text. Pages that fail to load properly (too little text) are flagged and skipped to avoid false results.

> *Technical hint:* Each page is loaded in headless Chrome. The HTML content is parsed and converted to plain text. Pages with fewer than 100 characters of text are treated as rendering failures and excluded.

⬇️

**Stage 6 — Compare Current Content with Previous Snapshots**

For each page, the application compares the text it just fetched with the previously saved snapshot:

- If no previous snapshot exists, the page is marked as **newly discovered**.
- If a previous snapshot exists, the old and new content are compared line by line.
- Any additions (new text), removals (deleted text), or structural changes are recorded.
- The application also checks for suspicious changes (for example, if a page appears to have lost more than 70% of its content, it is likely a loading error rather than a real change).

⬇️

**Stage 7 — Save Updated Snapshots and Upload to Storage**

After comparison, all the current page contents are saved as the new snapshots. These updated snapshots are then uploaded to Cloud Storage, replacing the old ones. This way, the next scheduled run will compare against today's content. Any snapshots that no longer correspond to an existing page are cleaned up.

> *Technical hint:* The application syncs the local snapshot files to the Cloud Storage bucket — uploading new/updated files and removing stale ones.

⬇️

**Stage 8 — Send an Email Report**

The application builds a summary of all changes found (or reports that no changes were detected). It retrieves the email password from Secret Manager and sends the report to the configured recipients via email. The email includes details about which pages changed, what was added, and what was removed.

> *Technical hint:* The email password is available as an environment variable injected by Secret Manager. The application connects to the SMTP email server to send the notification.

⬇️

**Stage 9 — Return Response and Shut Down**

The application sends an HTTP response (success or failure) back to Cloud Scheduler, confirming how the run went. The application then shuts down and releases all its resources. It will start up again at the next scheduled time.

> *Technical hint:* A successful run returns HTTP 200. An error returns HTTP 500. Cloud Run may keep the container warm briefly, but it is eventually shut down.

---

### Runtime Summary (at a Glance)

> Scheduler triggers request → Cloud Run service starts → Previous snapshots downloaded from storage → SAP pages discovered and fetched → Current content compared with snapshots → Updated snapshots uploaded to storage → Email report sent → Application shuts down

---

## 3. Basic Technical Illustration

This section provides minimal illustrative examples to help visualize the key concepts. These are **simplified representations**, not real configurations or commands.

---

### Container Image Reference

When the application is built, it is stored as a container image with a reference like:

    gcr.io/your-project-id/sap-doc-monitor

This is simply an address that tells Cloud Run where to find the packaged application. The format is:

    registry-location/project-id/image-name

---

### Service Request Flow

When the system runs, the interaction between services follows this pattern:

    Cloud Scheduler
        ⬇️  (sends authenticated HTTP POST)
    Cloud Run (sap-doc-monitor)
        ⬇️  (downloads snapshots)
    Cloud Storage (snapshot bucket)
        ⬇️  (retrieves password)
    Secret Manager (email password)
        ⬇️  (sends email)
    Email Server (SMTP)
        ⬇️  (returns result)
    Cloud Scheduler (receives HTTP response)

---

### Service Configuration Concept

Below is a simplified view of how each service relates to the project. This is **not real configuration** — it is just an illustration of the roles.

    Service:    Cloud Run
    Role:       Hosts and runs the application
    Trigger:    HTTP request from Cloud Scheduler
    Inputs:     Container image, environment variables, secrets
    Outputs:    Logs, email notifications

    Service:    Cloud Scheduler
    Role:       Automatic timer
    Trigger:    Cron schedule (e.g., 9:00 AM and 6:00 PM daily)
    Target:     Cloud Run service URL
    Auth:       Service account identity

    Service:    Cloud Storage
    Role:       Persistent file storage
    Contents:   Document snapshot files (.txt)
    Access:     Read and write by Cloud Run

    Service:    Secret Manager
    Role:       Secure credential storage
    Contents:   Email password
    Access:     Read-only by Cloud Run at runtime

---

### Deployment vs. Runtime — What Runs When

    DEPLOYMENT (one-time setup):
        Cloud Build  →  builds the container image
        Artifact Registry  →  stores the container image
        Cloud Run  →  receives the deployed service

    RUNTIME (every scheduled run):
        Cloud Scheduler  →  triggers the application
        Cloud Run  →  executes the application logic
        Cloud Storage  →  stores and retrieves snapshots
        Secret Manager  →  provides the email password

---

## 4. GCP Services Table

The table below lists every Google Cloud service used in this project, explains its role in simple language, and indicates when it is used.

| GCP Service | Purpose in This Project | Used During |
|---|---|---|
| **Cloud Build** | Builds the application into a container image on Google's servers. Think of it as a factory that assembles the application and all its parts into one package. | Deployment |
| **Artifact Registry** | Stores the container image created by Cloud Build. Acts like a warehouse where the finished package is kept so Cloud Run can pull it when deploying. | Deployment |
| **Cloud Run** | Hosts and runs the application whenever it is triggered. It starts the application, lets it do its work, and then shuts it down. No permanent server is needed — resources are only used while the application is running. | Deployment and Runtime |
| **Cloud Storage** | Provides a persistent storage space (a "bucket") for document snapshot files. Since the application shuts down after each run and loses all its temporary files, this storage preserves snapshots so they can be used for comparison in the next run. | Runtime |
| **Secret Manager** | Securely stores sensitive information (the email password) in an encrypted vault. The application retrieves the password at runtime instead of having it written directly in the code. | Runtime |
| **Service Account** | A dedicated identity that gives Cloud Scheduler permission to start the application. Since the application is private (not publicly accessible), the scheduler needs this identity to authenticate its requests. | Runtime |
| **Cloud Scheduler** | An automatic timer that sends an HTTP request to start the application at set times each day (e.g., 9:00 AM and 6:00 PM). It removes the need for anyone to manually trigger the application. | Runtime |

---

> **In Simple Terms:**
>
> - **Deployment services** (Cloud Build, Artifact Registry, Cloud Run) work together to build, store, and set up the application in the cloud.
> - **Runtime services** (Cloud Storage, Secret Manager, Service Account, Cloud Scheduler) work together to keep the application running automatically, securely, and reliably every day.
