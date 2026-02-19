# SAP Doc Monitor — Complete Project Workflow Guide

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [Project Architecture & Module Map](#3-project-architecture--module-map)
4. [How the Application Works (End-to-End)](#4-how-the-application-works-end-to-end)
5. [Module Deep Dives](#5-module-deep-dives)
6. [Data Flow Diagrams](#6-data-flow-diagrams)
7. [Execution Modes](#7-execution-modes)
8. [Email Notification System](#8-email-notification-system)
9. [Safety & Validation Mechanisms](#9-safety--validation-mechanisms)
10. [Configuration Reference](#10-configuration-reference)

---

## 1. Project Overview

### What This Project Does

**SAP Doc Monitor** is an automated Python application that monitors SAP Asset Performance Management (APM) Help Portal documentation pages for changes and sends professional email notifications when updates are detected.

### The Problem It Solves

SAP documentation pages are updated without advance notice. Teams relying on these docs need to know about changes immediately — whether it's a new procedure step, a removed prerequisite, or an entirely new page. Manually checking 25+ documentation pages multiple times per day is impractical.

### How It Solves It

The application automatically:

1. **Discovers** all documentation pages from a single base URL (auto-discovery from the Table of Contents)
2. **Fetches** each page using headless Chrome (SAP Help Portal is JavaScript-rendered)
3. **Extracts** clean text content from the HTML, stripping UI noise
4. **Compares** the current content against previously saved snapshots
5. **Classifies** every change by severity — HIGH, MEDIUM, or LOW
6. **Sends** a professional HTML email report with a full breakdown of changes
7. **Persists** updated snapshots for the next comparison cycle

### Key Features

| Feature | Description |
|---------|-------------|
| **Auto-Discovery** | Provide one base URL → system discovers all pages from the SAP sidebar TOC |
| **Smart Comparison** | Normalizes formatting noise (bullets, arrows, whitespace) — only flags real content changes |
| **Severity Classification** | Instruction/prerequisite changes = HIGH, content changes = MEDIUM, cosmetic = LOW |
| **Structural Validation** | Detects numbering gaps, missing prerequisite sections, removed procedure steps |
| **Shrinkage Protection** | Blocks snapshot overwrites when >70% content shrinkage with zero additions (rendering failure) |
| **Content Validation** | Rejects pages with <100 characters of extracted text (incomplete renders) |
| **New Page Detection** | Flags pages that appear in the TOC but have no previous snapshot |
| **Removed Page Detection** | Flags pages that had snapshots but are no longer in the TOC |
| **Dual-Mode Email** | Sends both plain text and premium HTML email (responsive design, works on mobile) |
| **Cloud-Ready** | Designed for GCP Cloud Run with GCS persistent storage and Secret Manager |

---

## 2. Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Language** | Python 3.11 | Core application logic |
| **Browser Automation** | Selenium + headless Chrome | Fetches JavaScript-rendered SAP Help pages |
| **Driver Management** | webdriver-manager | Automatically downloads the correct ChromeDriver version |
| **HTML Parsing** | BeautifulSoup 4 | Extracts and cleans text content from fetched HTML |
| **HTTP Client** | Requests | Simple HTTP fetches for non-JS pages |
| **Email** | smtplib (stdlib) | Sends email via SMTP (Office 365 / Gmail) |
| **Scheduling (local)** | APScheduler | Runs monitoring at configurable intervals locally |
| **Web Framework** | Flask | HTTP endpoint for Cloud Run triggers |
| **Cloud Storage** | google-cloud-storage | Persistent snapshot storage on GCS (Cloud Run mode) |
| **Containerization** | Docker | Packages app + Chrome into a deployable container |
| **CI/CD** | GitHub Actions | Alternative scheduling via GitHub's cron |
| **Cloud Platform** | GCP (Cloud Run, Cloud Scheduler, GCS, Secret Manager) | Production deployment |

### Python Dependencies (`requirements.txt`)

```
selenium>=4.0.0           # Browser automation for JS-rendered pages
beautifulsoup4>=4.9.0     # HTML parsing and content extraction
requests>=2.25.0          # Simple HTTP requests
webdriver-manager>=3.8.0  # Auto-downloads ChromeDriver
APScheduler>=3.10.0       # Local cron-style scheduling
Flask>=2.3.0              # HTTP endpoint for Cloud Run
google-cloud-storage>=2.10.0  # GCS integration for persistent snapshots
```

---

## 3. Project Architecture & Module Map

### Directory Structure

```
SAP Doc Monitor/
│
├── Dockerfile                        # Container definition (Python + Chrome + app)
├── deploy-to-cloud-run.ps1           # PowerShell deployment script for GCP
├── deploy-to-cloud-run.sh            # Bash deployment script for GCP
├── GCP_DEPLOYMENT_WORKFLOW.md        # GCP deployment documentation
├── GCP_DEPLOYMENT_WORKFLOW.html      # Same, as styled HTML
├── PROJECT_WORKFLOW.md               # This document
├── PROJECT_WORKFLOW.html             # Same, as styled HTML
│
├── .github/workflows/
│   └── monitor.yml                   # GitHub Actions workflow (alternative to Cloud Scheduler)
│
└── sap-doc-monitor/                  # Application root
    │
    ├── main.py                       # ORCHESTRATOR — runs the full 5-phase pipeline
    ├── cloud_run_app.py              # Flask HTTP wrapper for Cloud Run
    ├── scheduler.py                  # Local APScheduler runner
    │
    ├── config/
    │   ├── settings.py               # Active configuration (local dev)
    │   ├── settings.cloud.py         # Cloud configuration (reads from env vars)
    │   └── settings.example.py       # Template for new users
    │
    ├── fetcher/
    │   ├── discover_urls.py          # Auto-discovers page URLs from SAP TOC sidebar
    │   └── fetch_page.py             # Fetches HTML using Selenium or Requests
    │
    ├── parser/
    │   └── parse_content.py          # Extracts clean text from raw HTML
    │
    ├── comparator/
    │   └── compare_content.py        # Smart diff engine with severity classification
    │
    ├── notifier/
    │   └── send_email.py             # Sends email via SMTP
    │
    ├── storage/
    │   └── gcs_storage.py            # GCS integration (download/upload snapshots)
    │
    ├── snapshots/                    # Stored .txt snapshots (one per page)
    │   ├── 1_Overview_of_Getting_Started_Steps.txt
    │   ├── 2_Target_Audience.txt
    │   └── ...
    │
    ├── test_discovery.py             # Test: verifies URL auto-discovery
    ├── test_email.py                 # Test: verifies SMTP email sending
    └── test_smtp.py                  # Test: low-level SMTP connection test
```

### Module Responsibility Map

| Module | File | Single Responsibility |
|--------|------|----------------------|
| **Orchestrator** | `main.py` | Runs the 5-phase pipeline: download → discover+fetch → compare → save+upload → email |
| **Configuration** | `config/settings.py` | Stores all configurable values (URLs, email, paths) |
| **URL Discovery** | `fetcher/discover_urls.py` | Loads SAP TOC in headless Chrome, waits for sidebar to render, extracts all doc links with hierarchical numbering |
| **Page Fetcher** | `fetcher/fetch_page.py` | Fetches a single URL with Selenium (JS pages) or Requests (simple pages), validates rendered content, retries on failure |
| **Content Parser** | `parser/parse_content.py` | Strips SAP Help UI (nav, breadcrumbs, banners), extracts headings/paragraphs/lists/tables, deduplicates, handles DITA inline content |
| **Comparator** | `comparator/compare_content.py` | Normalizes text, performs count-aware diff, classifies changes by severity, validates document structure |
| **Email Notifier** | `notifier/send_email.py` | Sends multipart (plain text + HTML) email via SMTP to one or more recipients |
| **Cloud Storage** | `storage/gcs_storage.py` | Downloads/uploads snapshot files to/from GCS bucket; full sync with stale file cleanup |
| **Cloud Run App** | `cloud_run_app.py` | Flask server with `/` (trigger) and `/health` endpoints; calls `main.main()` on POST |
| **Local Scheduler** | `scheduler.py` | APScheduler-based local runner; runs `main.main()` on a configurable interval |

---

## 4. How the Application Works (End-to-End)

The application executes a **5-phase pipeline** every time it runs. Each phase must complete before the next starts.

---

### Phase 1: Download Previous Snapshots

```
main.main() starts
    │
    ├── Is GCS enabled? (GCS_BUCKET_NAME env var set?)
    │
    ├── YES (Cloud Run mode):
    │   ├── Wipe any local .txt files (Docker image may have stale ones)
    │   ├── Download ALL .txt snapshots from GCS bucket
    │   └── gs://{PROJECT_ID}-sap-snapshots/snapshots/*.txt → local snapshots/
    │
    └── NO (Local mode):
        └── Use whatever .txt files are already in snapshots/
    │
    ├── Load ALL local .txt files into memory (dict: normalised_name → content)
    │   e.g. "9.1_Standard_Role_Collections.txt" → key: "standard role collections"
    │
    ▼ previous_snapshots dict ready
```

**Key function:** `load_previous_snapshots()` — reads every `.txt` file in the snapshots directory, strips the page-number prefix and file extension, normalises the name to lowercase, and stores the full text content keyed by that normalised name.

---

### Phase 2: Discover URLs & Fetch All Current Content

```
    │
    ├── Is DOCUMENT_URLS empty? (auto-discovery vs manual mode)
    │
    ├── YES (Auto-Discovery):
    │   ├── Load BASE_DOCUMENTATION_URL in headless Chrome
    │   ├── Wait for SAP sidebar TOC to fully render (≥10 links, stability check)
    │   ├── Parse the sidebar DOM tree (nested <ul>/<li>)
    │   ├── Extract hierarchical page numbers from nesting depth
    │   │   e.g. 1, 2, 3, ..., 9, 9.1, 9.2, 9.3, ..., 12, 12.1, 12.2, ...
    │   ├── Extract page titles from link text
    │   ├── Build full URLs (relative → absolute)
    │   ├── Deduplicate and skip the base URL itself
    │   └── Returns: list of (number, name, url) tuples
    │
    └── NO (Manual mode):
        └── Use URLs from settings.DOCUMENT_URLS dict
    │
    ├── For EACH discovered page:
    │   ├── fetch_page(url) — Selenium with explicit waits
    │   │   ├── Launch headless Chrome
    │   │   ├── Navigate to URL
    │   │   ├── Wait for SAP content selectors (div#page, [role="main"], article)
    │   │   ├── Wait for >100 chars of visible text in content element
    │   │   ├── Stability check: wait until text length stops growing
    │   │   └── Return page source HTML
    │   │
    │   ├── extract_text(html) — BeautifulSoup parsing
    │   │   ├── Target main content area (div#page, [role="main"], etc.)
    │   │   ├── Remove UI noise (nav, header, footer, breadcrumbs, buttons)
    │   │   ├── Pre-process SAP menu cascades (span.menucascade → "A > B > C")
    │   │   ├── Wrap bare inline content in <section> elements into <p> tags
    │   │   ├── Extract text from h1-h6, p, ol, ul, aside, pre, table, dl
    │   │   ├── Deduplicate headings and content lines
    │   │   └── Return clean text string
    │   │
    │   └── Validate: reject if extracted text < 100 chars
    │
    ▼ current_content dict ready (page_name → extracted text)
```

**Key insight:** All pages are fetched FIRST before any comparison happens. This ensures the comparison phase has a complete picture and can detect removed pages (present in snapshots but missing from current fetch).

---

### Phase 3: Compare Previous vs. Current Content

```
    │
    ├── For EACH page in the current page list:
    │   │
    │   ├── Fetch failed? → skip (preserve previous snapshot)
    │   │
    │   ├── No previous snapshot? → mark as NEW PAGE
    │   │   └── Capture first 15 lines as content preview
    │   │
    │   └── Previous snapshot exists? → run compare(old, new)
    │       │
    │       ├── NORMALIZATION (both old and new text):
    │       │   ├── Strip bullet characters (•, ·, -, *, ▶, etc.)
    │       │   ├── Strip leading step numbers ("3. Choose…" → "Choose…")
    │       │   ├── Normalize arrows (→ ► ▶ ➜ ») → " > "
    │       │   ├── Collapse whitespace, lowercase
    │       │   └── Filter out noise lines (separators, empty lines)
    │       │
    │       ├── COUNT-AWARE DIFF:
    │       │   ├── Count occurrences of each normalised line in old and new
    │       │   ├── If old has 3× "choose save" and new has 1× → 2 removals
    │       │   └── Handles duplicate lines correctly (unlike simple set diff)
    │       │
    │       ├── SEMANTIC CLASSIFICATION:
    │       │   ├── Each changed line is classified into a category:
    │       │   │   ├── instruction (starts with action verb) → HIGH severity
    │       │   │   ├── section_header (Prerequisites, Procedure, etc.) → HIGH
    │       │   │   ├── prerequisite (you need, you must, etc.) → HIGH
    │       │   │   ├── note (note:, note block) → MEDIUM
    │       │   │   ├── content (general text) → MEDIUM
    │       │   │   └── noise (separators, blank) → filtered out
    │       │   └── Overall severity = highest severity across all changes
    │       │
    │       ├── STRUCTURAL VALIDATION:
    │       │   ├── Numbering gaps (step 11 → 13 means step 12 missing)
    │       │   ├── Missing sections (procedural docs without Prerequisites/Procedure)
    │       │   ├── Removed prerequisites (prerequisite lines in old but not in new)
    │       │   └── Only reports NEW issues (not pre-existing)
    │       │
    │       └── INTEGRITY CHECK:
    │           ├── If content shrank by >70% with zero additions → rendering failure
    │           └── Skip this page (do NOT overwrite snapshot with bad data)
    │
    ├── DETECT REMOVED PAGES:
    │   ├── For each previous snapshot key NOT in the current page list
    │   └── Mark as REMOVED PAGE (no longer in SAP TOC)
    │
    ▼ all_changes list ready
```

---

### Phase 4: Save Snapshots & Upload to GCS

```
    │
    ├── Clear ALL local .txt files (remove stale filenames)
    │
    ├── For EACH page in the current page list:
    │   ├── If current content was fetched → save to snapshots/{number}_{title}.txt
    │   ├── If fetch failed → fall back to previous snapshot content (preserve it)
    │   └── Validate before saving: reject if < 100 chars
    │
    ├── If GCS is enabled:
    │   ├── Upload ALL local .txt files to gs://{bucket}/snapshots/
    │   └── Delete stale GCS files that no longer exist locally (sync)
    │
    ▼ snapshots persisted
```

---

### Phase 5: Send Email Notification

```
    │
    ├── build_notification() constructs:
    │   ├── Subject line (changes summary or "No Changes Detected")
    │   ├── Plain text body (structured report with tables)
    │   └── HTML body (premium responsive email with):
    │       ├── Dark header with title and timestamp
    │       ├── Status banner (green = no changes, amber/red = changes detected)
    │       ├── 4 metric cards (Pages Checked, New, Modified, Unchanged)
    │       ├── Run detail tiles (Timestamp, Run Status, Next Run, Changes Summary)
    │       ├── New Pages section (blue cards with content preview)
    │       ├── Modified Pages section (amber/red cards with diffs)
    │       ├── Removed Pages section (red cards)
    │       ├── Full pages-monitored table (S.No, Page No, Status, Name, Link)
    │       └── Responsive design (660px, 480px, 375px breakpoints)
    │
    ├── send_email() delivers via SMTP:
    │   ├── Constructs MIMEMultipart with plain + HTML parts
    │   ├── Supports multiple comma/semicolon-separated recipients
    │   ├── TLS encryption on port 587
    │   └── Authenticates with sender credentials
    │
    ▼ DONE — email sent, snapshots persisted
```

---

## 5. Module Deep Dives

### 5.1 URL Auto-Discovery (`fetcher/discover_urls.py`)

**Problem:** SAP documentation has 25+ pages, and the exact URLs change. Manually maintaining a list is fragile.

**Solution:** Load the base documentation page, wait for the JavaScript-rendered sidebar TOC, and scrape all links from it.

**How it works:**

1. **Load page with sidebar wait** — `_fetch_page_with_sidebar()`:
   - Creates headless Chrome instance
   - Navigates to the base URL
   - Waits for the sidebar container (`#d4h5-sidebar`, `aside`, `nav`, etc.)
   - Waits for ≥10 matching doc links to appear (configurable via `MIN_EXPECTED_TOC_LINKS`)
   - Stability check: polls every 1 second, waits until link count stops changing for 2 consecutive checks
   - Returns full page HTML

2. **Extract hierarchical TOC** — `_extract_toc_hierarchy()`:
   - Finds the TOC container in the sidebar
   - Walks the nested `<ul>/<li>` DOM tree recursively
   - Assigns hierarchical page numbers based on DOM nesting depth (e.g., `1`, `9`, `9.1`, `9.2`, `12.1`)
   - Handles non-link group headers (collapsible sections with children but no page)
   - Validates URLs: must match the doc-prefix pattern and end in `.html`
   - Deduplicates URLs

3. **Returns** a list of `(hierarchical_number, page_title, full_url)` tuples.

---

### 5.2 Page Fetcher (`fetcher/fetch_page.py`)

**Challenge:** SAP Help Portal pages are entirely JavaScript-rendered — a simple HTTP GET returns an empty shell.

**Solution:** Use Selenium with headless Chrome and explicit waits.

**Fetch flow:**

| Step | Action | Detail |
|------|--------|--------|
| 1 | Create Chrome driver | Headless, no-sandbox, 1920×1080 viewport |
| 2 | Navigate to URL | `driver.get(url)` |
| 3 | Wait for content | SAP pages: wait for `div#page`, `[role="main"]`, or `article` with >100 chars of text |
| 4 | Content stabilisation | Poll every 0.5s until body text length stops growing (max 5s) |
| 5 | Return HTML | `driver.page_source` |
| 6 | Validate | Check for error markers ("page not found", "503", etc.) and minimum visible text length |
| 7 | Retry | If validation fails, retry up to 3 times with exponential backoff |

**Non-SAP pages** are fetched via simple `requests.get()` as a fast path.

---

### 5.3 Content Parser (`parser/parse_content.py`)

**Challenge:** Raw HTML from SAP Help contains navigation menus, breadcrumbs, cookie banners, feedback widgets, icon SVGs, and duplicated headings — none of which are actual documentation content.

**Extraction pipeline:**

| Step | What It Does |
|------|-------------|
| 1 | Remove `<script>`, `<style>`, `<meta>`, `<svg>`, `<iframe>`, `<noscript>` |
| 2 | Find main content area: `div#page` → `[role="main"]` → `<main>` → `<article>` → `<body>` |
| 3 | Pre-process SAP menu cascades: `<span class="menucascade">` → "Menu > Submenu > Item" |
| 4 | Remove UI elements: `<nav>`, `<header>`, `<footer>`, breadcrumbs, search, cookie banners, buttons |
| 5 | Wrap bare inline text in `<section>` into `<p>` tags (SAP DITA rendering quirk) |
| 6 | Extract text from block elements in order: `h1-h6`, `p`, `ol`, `ul`, `aside`, `pre`, `table`, `dl` |
| 7 | Deduplicate headings and content lines |
| 8 | Return clean, structured text |

---

### 5.4 Smart Comparator (`comparator/compare_content.py`)

**Challenge:** SAP pages have cosmetic differences between fetches (whitespace changes, bullet character variations, arrow symbol variants). A naive diff would produce false positives on every run.

**Comparison pipeline:**

```
Old Text                          New Text
    │                                 │
    ▼                                 ▼
Normalize each line:              Normalize each line:
  • Strip bullets (•·-*)            • Strip bullets
  • Strip step numbers (3.)         • Strip step numbers
  • Normalize arrows (→►▶) → >     • Normalize arrows
  • Collapse whitespace             • Collapse whitespace
  • Lowercase                       • Lowercase
  • Filter noise lines              • Filter noise lines
    │                                 │
    ▼                                 ▼
Count occurrences                 Count occurrences
(Counter dict)                    (Counter dict)
    │                                 │
    └────────────┬────────────────────┘
                 │
                 ▼
        Count-aware diff:
        For each unique normalised line:
          old_count vs new_count
          Δ > 0 → additions
          Δ < 0 → removals
                 │
                 ▼
        Classify each change:
          instruction → HIGH
          prerequisite → HIGH
          section_header → HIGH
          note → MEDIUM
          content → MEDIUM
                 │
                 ▼
        Structural validation:
          numbering gaps
          missing sections
          removed prerequisites
                 │
                 ▼
        Return: {has_changes, added[], removed[],
                 structural_warnings[], max_severity}
```

**Severity classification rules:**

| Category | Detection Rule | Severity |
|----------|---------------|----------|
| `instruction` | First word is an action verb (choose, select, click, navigate, etc.) | **HIGH** |
| `section_header` | Line text matches Prerequisites, Procedure, Results, etc. | **HIGH** |
| `prerequisite` | Starts with "you've", "you need", "you must", etc. | **HIGH** |
| `note` | Starts with "note:" | **MEDIUM** |
| `content` | General text content | **MEDIUM** |
| `noise` | Separators, empty lines, table borders | Filtered out |

---

### 5.5 Email Notifier (`notifier/send_email.py`)

Sends a multipart email with both plain text and HTML versions:

- **Plain text:** Structured report with ASCII tables
- **HTML:** Premium responsive email with:
  - Status banners (green/amber/red based on severity)
  - Metric cards
  - Change detail cards with severity badges
  - Full monitoring table with links
  - Responsive breakpoints at 660px, 480px, 375px

**Supports:**
- Multiple recipients (comma or semicolon separated)
- Office 365 SMTP (`smtp.office365.com:587`)
- Gmail SMTP (`smtp.gmail.com:587`)
- TLS encryption

---

### 5.6 Cloud Storage (`storage/gcs_storage.py`)

Handles persistent storage for Cloud Run (where containers are ephemeral):

| Function | What It Does |
|----------|-------------|
| `is_gcs_enabled()` | Checks if `GCS_BUCKET_NAME` env var is set and `google-cloud-storage` is installed |
| `download_all_snapshots()` | Downloads all `snapshots/*.txt` from GCS to local directory |
| `upload_all_snapshots()` | Uploads all local `.txt` files to GCS; deletes stale GCS files not present locally |
| `download_snapshot()` | Downloads a single snapshot file |
| `upload_snapshot()` | Uploads a single snapshot file |

---

## 6. Data Flow Diagrams

### Complete Application Data Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                  TRIGGER                                     │
│  Cloud Scheduler HTTP POST  /  Local scheduler.py  /  Manual python main.py │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     │
                                     ▼
                           ┌─────────────────┐
                           │    main.main()   │
                           │   ORCHESTRATOR   │
                           └────────┬────────┘
                                    │
              ┌─────────────────────┼──────────────────────┐
              ▼                     ▼                      ▼
     ┌────────────────┐   ┌─────────────────┐   ┌──────────────────┐
     │  PHASE 1       │   │  PHASE 2        │   │  config/         │
     │  GCS Download  │   │  Discover +     │   │  settings.py     │
     │  (Cloud mode)  │   │  Fetch Pages    │   │  (all settings)  │
     │                │   │                 │   └──────────────────┘
     │  gcs_storage.py│   │  discover_urls  │
     │  ───────────── │   │  fetch_page     │
     │  GCS Bucket    │   │  parse_content  │
     │  ↓ download    │   │  ───────────── │
     │  snapshots/    │   │  Selenium/Chrome│
     └────────┬───────┘   │  SAP Help Portal│
              │           └────────┬────────┘
              │                    │
              ▼                    ▼
     ┌─────────────────────────────────────┐
     │            PHASE 3                   │
     │     Compare old vs. new content     │
     │                                      │
     │     comparator/compare_content.py   │
     │     ─────────────────────────────── │
     │     Normalize → Diff → Classify →   │
     │     Structural validation           │
     └──────────────────┬──────────────────┘
                        │
              ┌─────────┼─────────┐
              ▼                   ▼
     ┌──────────────────┐  ┌──────────────────┐
     │    PHASE 4       │  │    PHASE 5       │
     │  Save Snapshots  │  │  Send Email      │
     │  + GCS Upload    │  │  Notification    │
     │                  │  │                  │
     │  save_snapshot() │  │  build_notif()   │
     │  gcs_storage.py  │  │  send_email()    │
     │  ──────────────  │  │  ──────────────  │
     │  Local files  →  │  │  SMTP Server     │
     │  GCS bucket      │  │  (Office 365)    │
     └──────────────────┘  └──────────────────┘
```

### Snapshot Lifecycle

```
FIRST RUN (no previous snapshots):
                                                              
  SAP Help ──► Fetch HTML ──► Extract Text ──► Save as .txt   
                                                │              
                                                ▼              
                                        snapshots/1_Overview.txt  
                                        snapshots/2_Target.txt    
                                        snapshots/...             
                                                │              
                                         Upload to GCS        
                                                              

SUBSEQUENT RUNS:

  GCS ──► Download .txt ──► previous_snapshots (in memory)
                                    │
  SAP Help ──► Fetch ──► Extract ──► Compare ──► Changes?
                                    │              │
                                    │         Yes: Email report
                                    │              │
                                    ▼              ▼
                            Save updated .txt   Upload to GCS
```

### Module Interaction Map

```
┌─────────────────────────────────────────────────────────────────┐
│                      main.py (orchestrator)                     │
│                                                                 │
│  Imports and calls ALL other modules in sequence:               │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ config/  │  │ fetcher/ │  │ parser/  │  │  comparator/  │  │
│  │settings  │  │discover  │  │parse     │  │  compare      │  │
│  │          │  │fetch     │  │content   │  │  content      │  │
│  └──────────┘  └──────────┘  └──────────┘  └───────────────┘  │
│                                                                 │
│  ┌──────────┐  ┌──────────┐                                    │
│  │notifier/ │  │ storage/ │                                    │
│  │send_email│  │gcs_store │                                    │
│  └──────────┘  └──────────┘                                    │
└─────────────────────────────────────────────────────────────────┘
         ▲                ▲
         │                │
┌────────────────┐  ┌──────────────┐
│cloud_run_app.py│  │ scheduler.py │
│  Flask wrapper │  │  APScheduler │
│  (Cloud Run)   │  │  (local dev) │
└────────────────┘  └──────────────┘
```

---

## 7. Execution Modes

The application supports three ways to run:

### Mode 1: Direct Execution (Development)

```bash
cd sap-doc-monitor
python main.py
```

- Runs once and exits
- Uses `config/settings.py` for configuration (hardcoded values)
- Stores snapshots in local `snapshots/` directory
- No GCS integration (GCS_BUCKET_NAME not set)

### Mode 2: Local Scheduler

```bash
cd sap-doc-monitor
python scheduler.py
```

- Runs `main.main()` immediately, then repeats on a schedule (default: every 1 hour)
- Uses APScheduler with configurable cron expressions
- Logs to `scheduler.log` and console
- Runs indefinitely until Ctrl+C

### Mode 3: GCP Cloud Run (Production)

```
Cloud Scheduler → HTTP POST → Cloud Run → Flask → main.main()
```

- Container starts on-demand when triggered
- Uses `config/settings.cloud.py` (reads all settings from environment variables)
- Snapshots persisted to GCS bucket between runs
- Email password from Secret Manager
- Container destroyed after each run (ephemeral)

### Mode 4: GitHub Actions (Alternative CI/CD)

```yaml
# .github/workflows/monitor.yml
on:
  schedule:
    - cron: '0 */6 * * *'  # Every 6 hours
  workflow_dispatch:        # Manual trigger from GitHub UI
```

- Runs on GitHub's infrastructure (ubuntu-latest)
- Installs Chrome + dependencies each run
- Reads secrets from GitHub repository secrets
- Snapshots committed back to repo (requires additional setup)

---

## 8. Email Notification System

### Email Subject Lines

| Scenario | Subject |
|----------|---------|
| Changes detected (HIGH) | `SAP APM Doc Monitor — Changes Detected [HIGH]: 2 Modified` |
| Changes detected (MEDIUM) | `SAP APM Doc Monitor — Changes Detected [MEDIUM]: 1 New, 1 Modified` |
| New + modified + removed | `SAP APM Doc Monitor — Changes Detected: 1 New, 2 Modified, 1 Removed` |
| No changes | `SAP APM Doc Monitor — No Changes Detected` |

### Email Body Structure (HTML)

```
┌─────────────────────────────────────────────────┐
│  SAP APM Documentation Monitor  │  Timestamp    │  ← Dark header
├─────────────────────────────────────────────────┤
│  ✓ No Changes Detected (or ⚠ Changes Detected) │  ← Status banner
├─────────────────────────────────────────────────┤
│  [25]        [0]         [0]        [25]        │  ← Metric cards
│  Pages    New Pages   Modified   Unchanged      │
│  Checked    Added      Pages      Pages         │
├─────────────────────────────────────────────────┤
│  Timestamp    │  Run Status                      │  ← Detail tiles
│  Next Run     │  Changes Summary                 │
├─────────────────────────────────────────────────┤
│  New Pages Added: 1                              │  ← Change sections
│  ┌── Page Name ──── Click to view ───┐           │     (if any)
│  │   15 lines of content discovered  │           │
│  │   Preview: 1. First line...       │           │
│  └───────────────────────────────────┘           │
├─────────────────────────────────────────────────┤
│  Modified Pages: 1                               │
│  ┌── Page Name ───────── [HIGH] ──────┐          │
│  │   +3 additions · -1 removals       │          │
│  │   + [HIGH] New instruction text    │          │
│  │   - [HIGH] Removed step text       │          │
│  └────────────────────────────────────┘          │
├─────────────────────────────────────────────────┤
│  Pages Monitored: 25                             │  ← Full table
│  S.No. │ Page No. │ Status │ Page Name │ Link   │
│    1   │    1     │  ● OK  │ Overview  │ Open   │
│    2   │    2     │  ● OK  │ Target... │ Open   │
│   ...  │   ...   │  ...   │    ...    │  ...   │
├─────────────────────────────────────────────────┤
│  Automated Notification          │  Timestamp    │  ← Footer
└─────────────────────────────────────────────────┘
```

### Next Run Scheduling Logic

The email displays the next scheduled run time:

```python
current_hour = run_timestamp.hour
if current_hour < 10:
    next_run = today at 10:00 AM
elif current_hour < 18:
    next_run = today at 6:00 PM
else:
    next_run = tomorrow at 10:00 AM
```

---

## 9. Safety & Validation Mechanisms

The application has multiple safety layers to prevent false alerts and data corruption:

### Layer 1: Fetch Validation

| Check | Threshold | Action |
|-------|-----------|--------|
| HTML is None or empty | Any | Skip page, log warning |
| Error markers in HTML | "page not found", "503", "access denied", etc. | Retry (up to 3 times) |
| Visible text too short | < 100 characters | Retry, then skip |
| Content element not found | SAP selectors timeout | Retry, then skip |

### Layer 2: Content Validation

| Check | Threshold | Action |
|-------|-----------|--------|
| Extracted text too short | < 100 characters (`MIN_SNAPSHOT_LENGTH`) | Do NOT save snapshot, do NOT report as change |
| Content is None | Any | Skip page entirely |

### Layer 3: Snapshot Integrity

| Check | Condition | Action |
|-------|-----------|--------|
| Suspicious shrinkage | Content shrank >70% AND zero additions | Block snapshot overwrite — likely rendering failure |
| Fetch failure | `fetch_page()` raised RuntimeError | Preserve previous snapshot, skip comparison |

### Layer 4: Comparison Normalization

| Normalization | What It Strips | Why |
|---------------|---------------|-----|
| Bullet removal | `•`, `·`, `-`, `*`, `▶`, etc. | SAP inconsistently uses different bullet chars |
| Step number removal | `3.`, `1)`, etc. | Step renumbering is not a content change |
| Arrow normalization | `→`, `►`, `▶`, `➜`, `»` → `>` | SAP uses different arrow symbols interchangeably |
| Whitespace collapse | Multiple spaces/tabs → single space | Formatting differences are not content changes |
| Case normalization | Lowercase everything | "Choose SAVE" vs "Choose Save" is the same instruction |

### Layer 5: Structural Validation (New Issues Only)

The comparator only reports structural warnings that are **new** — if a numbering gap already existed in the previous snapshot, it won't be re-reported every run.

---

## 10. Configuration Reference

### `config/settings.py` (Local Development)

```python
# Auto-discovery: provide one base URL
BASE_DOCUMENTATION_URL = "https://help.sap.com/docs/SAP_APM/..."

# Manual mode: list specific URLs (leave empty for auto-discovery)
DOCUMENT_URLS = {}

# Local snapshot storage
SNAPSHOTS_DIR = "snapshots"

# Email configuration
EMAIL_SENDER = "sender@example.com"
EMAIL_PASSWORD = "app-password"
EMAIL_RECEIVER = "recipient1@example.com, recipient2@example.com"
SMTP_SERVER = "smtp.office365.com"
SMTP_PORT = 587
```

### `config/settings.cloud.py` (Cloud Run — reads from env vars)

```python
BASE_DOCUMENTATION_URL = os.getenv('BASE_DOCUMENTATION_URL', "...")
DOCUMENT_URLS = {}
SNAPSHOTS_DIR = os.getenv('SNAPSHOTS_DIR', "snapshots")
EMAIL_SENDER = os.getenv('EMAIL_SENDER', "...")
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', "...")  # From Secret Manager
EMAIL_RECEIVER = os.getenv('EMAIL_RECEIVER', "...")
SMTP_SERVER = os.getenv('SMTP_SERVER', "smtp.office365.com")
SMTP_PORT = int(os.getenv('SMTP_PORT', "587"))
```

### Environment Variables (Cloud Run)

| Variable | Source | Purpose |
|----------|--------|---------|
| `BASE_DOCUMENTATION_URL` | `--set-env-vars` | SAP documentation base URL |
| `SNAPSHOTS_DIR` | `--set-env-vars` | Local path for snapshots (usually `/app/snapshots`) |
| `EMAIL_SENDER` | `--set-env-vars` | SMTP sender email address |
| `EMAIL_PASSWORD` | Secret Manager (`--update-secrets`) | SMTP password (securely stored) |
| `EMAIL_RECEIVER` | `--set-env-vars` | Comma-separated recipient list |
| `SMTP_SERVER` | `--set-env-vars` | SMTP server hostname |
| `SMTP_PORT` | `--set-env-vars` | SMTP port (usually 587) |
| `GCS_BUCKET_NAME` | `--set-env-vars` | GCS bucket for persistent snapshots |
| `PORT` | Cloud Run (auto) | HTTP port for Flask (default 8080) |

---

## Summary: How the Entire System Fits Together

```
┌─── DEVELOPMENT ────────────────────────────────────────────────────┐
│                                                                     │
│   python main.py  →  Discover pages  →  Fetch  →  Compare         │
│                      →  Save snapshots locally  →  Send email      │
│                                                                     │
│   python scheduler.py  →  Same thing, every N hours                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─── PRODUCTION (GCP Cloud Run) ─────────────────────────────────────┐
│                                                                     │
│   Cloud Scheduler ──(HTTP POST)──► Cloud Run container:            │
│     │                                                               │
│     ├── Flask receives request                                     │
│     ├── Phase 1: Download snapshots from GCS                       │
│     ├── Phase 2: Discover + fetch all SAP doc pages                │
│     ├── Phase 3: Compare old vs new (smart diff + severity)        │
│     ├── Phase 4: Save snapshots + upload to GCS                    │
│     ├── Phase 5: Send HTML email report                            │
│     └── Return HTTP 200/500                                        │
│                                                                     │
│   Supporting services:                                              │
│     GCS Bucket ────── persistent snapshot storage                  │
│     Secret Manager ── email password                               │
│     Service Account ─ OIDC authentication for scheduler            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

> **The core logic is identical regardless of execution mode.** The only differences are: how the app is triggered (manual / scheduler / HTTP), where settings come from (file / env vars), and where snapshots are stored (local filesystem / GCS).
