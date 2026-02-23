# GCP Deployment Workflow — High-Level Overview

> This document explains the full deployment and runtime workflow of the SAP Documentation Monitor on Google Cloud Platform (GCP). It is written for beginners and non-technical readers — no cloud knowledge is required.

---

## Table of Contents

1. [Deployment-Time Flowchart](#1-deployment-time-flowchart)
2. [Runtime Flowchart](#2-runtime-flowchart)
3. [GCP Services Table](#3-gcp-services-table)

---

## 1. Deployment-Time Flowchart

Deployment is the one-time process of setting up the application so it can run automatically on Google's servers. Think of it as "installing the application in the cloud." This only needs to happen once (or when the application is updated).

Here is the step-by-step flow of what happens during deployment:

---

**Step 1 — Select the Project**

The deployment begins by selecting which Google Cloud project to use. This is like choosing which workspace or account everything will be set up under. All the services created in later steps will belong to this project.

⬇️

**Step 2 — Activate the Required Services**

Google Cloud has many services, but they are not turned on by default. Before anything can be set up, the specific services needed by this application are activated. This is a one-time switch — once turned on, these services are ready to use.

⬇️

**Step 3 — Create a Storage Space for Document Snapshots**

A dedicated storage space is created in the cloud. This is where the application will save copies of the SAP documentation pages it monitors. These saved copies are called "snapshots." The storage space ensures that snapshots are preserved between runs, even though the application itself shuts down after each run.

⬇️

**Step 4 — Store the Email Password Securely**

The application needs to send email notifications. Instead of placing the email password directly inside the application, it is stored in a secure vault provided by Google Cloud. The application can retrieve the password from this vault whenever it needs to send an email. This keeps the password safe and separate from the application itself.

⬇️

**Step 5 — Build the Application Package**

The application and all its requirements (including a web browser used for reading SAP pages) are packaged together into a single unit called an "image." This packaging happens on Google's servers, not on the developer's computer. Once built, the packaged image is automatically saved in a storage area designed for application packages.

⬇️

**Step 6 — Deploy the Application**

The packaged image from the previous step is now deployed — meaning Google Cloud takes the package and makes it ready to run. The application is configured so that only authorized requests can start it (it is not publicly accessible to anyone on the internet). The email settings and connection to the secure vault are also linked at this point. After this step, the application has a unique web address that can be used to start it.

⬇️

**Step 7 — Create an Identity for the Scheduler**

Since the application is private (not open to the public), something needs permission to start it. A dedicated identity is created specifically for the scheduler (set up in the next step). This identity is granted the right to start the application. Without this identity, the scheduler would be blocked from triggering the application.

⬇️

**Step 8 — Set Up the Automatic Scheduler**

A scheduled job is created that will automatically start the application at specific times each day (for example, at 9:00 AM and 6:00 PM). The scheduler uses the identity created in the previous step to prove it has permission to start the application. From this point on, the application will run automatically without any human involvement.

⬇️

**Step 9 — Verify Everything Works**

The scheduler is triggered manually one time to confirm that the entire system works end-to-end — from the scheduler starting the application, to the application checking SAP documentation, to the email notification being sent. If this test succeeds, the deployment is complete.

---

### Deployment Summary (at a Glance)

> Developer prepares the application → Required cloud services are activated → Storage and security are set up → Application is packaged and built → Application is deployed to the cloud → A scheduler is configured to run it automatically → A test run confirms everything works

---

## 2. Runtime Flowchart

Runtime is what happens every time the application runs — either triggered automatically by the scheduler or started manually. This is the repeating cycle that happens twice a day (or on whatever schedule is configured).

Here is the step-by-step flow of what happens during each run:

---

**Stage 1 — The Scheduler Triggers the Application**

At the scheduled time (e.g., 9:00 AM), the scheduler sends a request to the application's web address. This request includes proof of identity (the identity created during deployment) so that the application knows it is an authorized request. The application receives the request and starts up.

⬇️

**Stage 2 — Retrieve Previous Snapshots from Storage**

The first thing the application does is download all previously saved document snapshots from cloud storage. These snapshots represent the "last known state" of each SAP documentation page. The application needs these to compare against the current state of the pages. If this is the very first run, there will be no previous snapshots, and everything will be treated as new.

⬇️

**Stage 3 — Discover All Documentation Pages**

The application visits the SAP Help Portal and reads the table of contents to find all the documentation pages that need to be monitored. This discovery process ensures that if SAP adds new pages, they are automatically picked up without anyone needing to update the application.

⬇️

**Stage 4 — Fetch and Read Each Page**

For each page discovered in the previous stage, the application opens the page using a built-in web browser, waits for the content to fully load, and then extracts the readable text from the page. Pages that fail to load properly (too little text) are flagged and skipped to avoid false results.

⬇️

**Stage 5 — Compare Current Content with Previous Snapshots**

For each page, the application compares the text it just fetched with the previously saved snapshot:

- If no previous snapshot exists, the page is marked as **newly discovered**.
- If a previous snapshot exists, the old and new content are compared line by line.
- Any additions (new text), removals (deleted text), or structural changes are recorded.
- The application also checks for suspicious changes (for example, if a page appears to have lost most of its content, it is likely a loading error rather than a real change).

⬇️

**Stage 6 — Save Updated Snapshots**

After comparison, all the current page contents are saved as the new snapshots. These updated snapshots are then uploaded to cloud storage, replacing the old ones. This way, the next scheduled run will compare against today's content.

⬇️

**Stage 7 — Send an Email Report**

The application builds a summary of all changes found (or reports that no changes were detected). It retrieves the email password from the secure vault and sends the report to the configured recipients. The email includes details about which pages changed, what was added, and what was removed.

⬇️

**Stage 8 — Shut Down**

The application sends a success signal back to the scheduler, confirming that the run completed. The application then shuts down and releases all its resources. It will start up again at the next scheduled time.

---

### Runtime Summary (at a Glance)

> Scheduler triggers the application → Previous snapshots are downloaded from storage → SAP documentation pages are discovered and fetched → Current content is compared with previous snapshots → Updated snapshots are saved back to storage → An email report is sent with any changes → Application shuts down until the next run

---

## 3. GCP Services Table

The table below lists every Google Cloud service used in this project, explains its role in simple language, and indicates when it is used.

| GCP Service | Purpose in This Project | Used During |
|---|---|---|
| **Cloud Build** | Takes the application source code and packages it into a ready-to-run unit on Google's servers. Think of it as a factory that assembles the application. | Deployment |
| **Artifact Registry** | Stores the packaged application created by Cloud Build. Acts like a warehouse where the finished package is kept until it is needed. | Deployment |
| **Cloud Run** | Runs the application whenever it is triggered. It starts the application, lets it do its work, and then shuts it down. No permanent server is needed — resources are only used while the application is running. | Deployment and Runtime |
| **Cloud Storage** | Provides a persistent storage space for document snapshots. Since the application shuts down after each run and loses all its temporary files, this storage preserves snapshots so they can be used for comparison in the next run. | Runtime |
| **Secret Manager** | Securely stores sensitive information (the email password). The application retrieves the password from this vault at runtime instead of having it written directly in the application. | Runtime |
| **Service Account** | A dedicated identity that gives the scheduler permission to start the application. Since the application is private (not publicly accessible), the scheduler needs this identity to prove it is authorized. | Runtime |
| **Cloud Scheduler** | An automatic timer that starts the application at set times each day (e.g., 9:00 AM and 6:00 PM). It removes the need for anyone to manually trigger the application. | Runtime |

---

> **In Simple Terms:**
>
> - **Deployment services** (Cloud Build, Artifact Registry, Cloud Run) work together to build, store, and set up the application in the cloud.
> - **Runtime services** (Cloud Storage, Secret Manager, Service Account, Cloud Scheduler) work together to keep the application running automatically, securely, and reliably every day.
