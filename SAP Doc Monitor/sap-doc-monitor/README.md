# SAP APM Documentation Monitor

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GCP Cloud Run](https://img.shields.io/badge/GCP-Cloud%20Run-4285F4.svg)](https://cloud.google.com/run)

An automated Python tool that monitors **SAP Asset Performance Management (APM)** Help Portal documentation pages and sends email notifications when changes are detected. Designed for teams who need to stay current with SAP documentation updates without manual checking.

## 🆕 Auto-Discovery Feature

**NEW!** Now you can monitor ALL documentation pages with just ONE URL!

Instead of manually listing 25+ URLs, simply provide the main documentation page URL and the system will automatically discover and monitor all pages from the table of contents.

## What Does This Project Do?

This tool automatically:
1. **Discovers** all documentation pages from a single base URL (or monitors specific URLs)
2. **Fetches** SAP documentation from all discovered/specified URLs
3. **Extracts** all meaningful text content from each page
4. **Compares** current content with previous snapshots
5. **Detects** any changes (additions, modifications, or deletions)
6. **Sends** professional email notifications to multiple recipients when changes occur
7. **Updates** the snapshots for future comparisons

## Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Auto-Discover URLs (OR use manual list)                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│ 2. Fetch Pages (using Selenium for JavaScript-rendered)     │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│ 3. Parse Content (extract all visible text)                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│ 4. Compare with Previous Snapshots                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
              ┌────────▼────────┐
              │ Changes Found?  │
              └────┬────────┬───┘
                   │        │
              Yes  │        │ No
                   │        │
      ┌────────────▼──┐  ┌──▼──────────────┐
      │ Send Email    │  │ Display "No     │
      │ Notification  │  │ Changes"        │
      └────────────┬──┘  └─────────────────┘
                   │
      ┌────────────▼──────────────┐
      │ Update Snapshots          │
      └───────────────────────────┘
```

## Project Structure & File Descriptions

```
sap-doc-monitor/
│
├── main.py                          # MAIN EXECUTION FILE
│   └── Orchestrates the entire workflow
│   └── Formats email messages with change summaries
│   └── Handles initial snapshot creation
│
├── config/
│   ├── settings.py                  # CONFIGURATION FILE
│   │   └── URL to monitor
│   │   └── Email credentials (sender, receivers, SMTP)
│   │   └── Snapshot file path
│   │
│   └── settings.example.py          # TEMPLATE FILE
│       └── Example configuration for reference
│
├── fetcher/
│   ├── fetch_page.py                # WEB SCRAPING MODULE
│   │   └── Uses requests library for simple pages
│   │   └── Uses Selenium (headless Chrome) for JavaScript-heavy SAP pages
│   │   └── Returns complete HTML content
│   │
│   └── discover_urls.py             # AUTO-DISCOVERY MODULE (NEW!)
│       └── Extracts all documentation links from table of contents
│       └── Parses navigation structure
│       └── Returns dictionary of {page_name: url}
│
├── parser/
│   └── parse_content.py             # CONTENT EXTRACTION MODULE
│       └── Extracts ALL visible text from HTML
│       └── Captures headings, paragraphs, lists, divs, spans
│       └── Preserves structure with markers ([H1], [H2], etc.)
│       └── Removes scripts, styles, and non-content elements
│
├── comparator/
│   └── compare_content.py           # CHANGE DETECTION MODULE
│       └── Uses difflib to compare old vs new content
│       └── Returns unified diff showing additions/removals
│       └── Line-by-line comparison
│
├── notifier/
│   └── send_email.py                # EMAIL NOTIFICATION MODULE
│       └── Sends formatted email notifications
│       └── Supports multiple recipients (comma-separated)
│       └── Uses SMTP (Gmail) for delivery
│
├── snapshots/
│   ├── Page_Title_1.txt             # INDIVIDUAL SNAPSHOTS
│   ├── Page_Title_2.txt             # Each page has its own snapshot
│   └── ...                          # Auto-created on first run
│
├── test_discovery.py                # URL DISCOVERY TEST (NEW!)
│   └── Tests auto-discovery functionality
│   └── Shows which pages will be monitored
│   └── Run: python test_discovery.py
│
├── test_email.py                    # EMAIL TESTING UTILITY
│   └── Tests email configuration
│   └── Sends test email to verify SMTP settings
│   └── Run: python test_email.py
│
└── test_documentation.html          # LOCAL TEST FILE
    └── Sample HTML for testing without internet
    └── Edit this file to simulate documentation changes
```

## Installation

**1. Clone the Repository:**
```bash
git clone https://github.com/Daxesh-Asint/SAP-APM-Doc-Monitor.git
cd SAP-APM-Doc-Monitor/SAP\ Doc\ Monitor/sap-doc-monitor
```

**2. Install Python 3.7+**

**3. Create Virtual Environment (Recommended):**
```bash
python -m venv .venv

# Activate on Windows:
.venv\Scripts\activate

# Activate on Linux/Mac:
source .venv/bin/activate
```

**4. Install Required Libraries:**
```bash
pip install -r requirements.txt
```

**5. Chrome Browser:**
- Selenium requires Chrome/Chromium
- ChromeDriver downloads automatically

## Configuration

**Create `config/settings.py` from the example:**
```bash
# Copy the example file
cp config/settings.example.py config/settings.py
```

**Edit `config/settings.py`:**

### Option 1: Auto-Discovery Mode (Recommended) 🆕

```python
# Set the main documentation page URL (with table of contents)
BASE_DOCUMENTATION_URL = "https://help.sap.com/docs/SAP_APM/2602f93216bb4530ba169c75be619edf/0840fd102be84f3ab8f8662a91f949a3.html"

# Leave DOCUMENT_URLS empty to enable auto-discovery
DOCUMENT_URLS = {}

# Email Settings
EMAIL_SENDER = "your-gmail@gmail.com"
EMAIL_PASSWORD = "your-app-password"
EMAIL_RECEIVER = "recipient1@example.com, recipient2@example.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
```

### Option 2: Manual Mode (Legacy)

```python
# Leave BASE_DOCUMENTATION_URL as is or comment it out

# Manually specify pages to monitor
DOCUMENT_URLS = {
    "Page 1 Title": "https://help.sap.com/docs/.../page1.html",
    "Page 2 Title": "https://help.sap.com/docs/.../page2.html",
    # Add more pages...
}

# Email Settings (same as above)
EMAIL_SENDER = "your-gmail@gmail.com"
EMAIL_PASSWORD = "your-app-password"
EMAIL_RECEIVER = "recipient1@example.com, recipient2@example.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
```

**Gmail App Password Setup:**
1. Enable 2-Factor Authentication on Google Account
2. Go to: Google Account → Security → 2-Step Verification → App passwords
3. Generate password for "Mail"
4. Use generated password in `EMAIL_PASSWORD`

## How to Use

**Test URL Discovery (Recommended First Step):** 🆕
```bash
python test_discovery.py
```
This will show you all the pages that will be monitored.

**First Run (Create Initial Snapshots):**
```bash
python main.py
```
Output: "Initial snapshot saved for 'Page Title'" for each page

**Subsequent Runs (Detect Changes):**
```bash
python main.py
```
- If changes detected: Email sent + snapshots updated
- If no changes: "No changes detected in any monitored pages"

**Test Email Configuration:**
```bash
python test_email.py
```

## Email Notification Format

When changes are detected, recipients receive:

```
Subject: SAP Documentation Update - Action Required

SAP Documentation Update Detected!
=====================================

URL: https://help.sap.com/docs/...
Date: 2026-01-30 13:45:20

SUMMARY:
--------
Total Meaningful Changes: 5 modifications detected
New Content Added: 3 items
Content Removed: 2 items

✅ NEW CONTENT ADDED:
============================================================
1. New feature: Real-time Alerts
2. Enhanced monitoring capabilities
3. Version updated to 2.0

❌ CONTENT REMOVED:
============================================================
1. Deprecated feature removed
2. Old configuration step

=====================================
This is an automated notification from SAP Documentation Monitor.
```

## For Other Users

**To use this project:**

1. **Clone the Repository:**
   ```bash
   git clone <repository-url>
   cd sap-doc-monitor
   ```

2. **Set Up Virtual Environment:**
   ```bash
   python -m venv .venv
   
   # Windows:
   .venv\Scripts\activate
   
   # Linux/Mac:
   source .venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Update Configuration:**
   ```bash
   # Create your settings file from the example
   cp config/settings.example.py config/settings.py
   ```
   - Open `config/settings.py`
   - Set your SAP documentation URL
   - Add your email credentials (Gmail App Password)
   - Add recipient email addresses

5. **Run Initial Setup:**
   ```bash
   python main.py
   ```

4. **Set Up Automated Monitoring** (Optional):
   - **Local:** Use Task Scheduler (Windows) or cron jobs (Linux/Mac)
   - **Cloud (Recommended):** Deploy to GCP Cloud Run — see [QUICKSTART_GCP.md](../QUICKSTART_GCP.md)
   - Example: Run every weekday at 9 AM automatically

## Troubleshooting

**"Extracted 0 characters"**
- SAP pages need Selenium (JavaScript rendering)
- Solution: Already handled automatically for help.sap.com URLs

**Email Not Received**
- Check spam/junk folder
- Verify Gmail App Password is correct
- For organizational emails: Ask IT to whitelist sender

**"No changes detected" but page changed**
- Delete `snapshots/previous_content.txt`
- Run `python main.py` again

## Requirements

- Python 3.7+
- selenium >= 4.0.0
- beautifulsoup4 >= 4.9.0
- requests >= 2.25.0
- Chrome/Chromium browser

## Notes

- **Selenium automatically downloads ChromeDriver** (no manual setup needed)
- **Supports multiple recipients** (comma-separated in EMAIL_RECEIVER)
- **Works with any public URL** (not just SAP)
- **Detects every visible text change** on the page

## Cloud Deployment

This project supports fully automated cloud deployment on Google Cloud Platform:

- **Serverless execution** via Cloud Run (pay only when running)
- **Automatic scheduling** via Cloud Scheduler
- **Persistent snapshots** via Cloud Storage
- **Secure credentials** via Secret Manager

See the [GCP Deployment Guide](../GCP_DEPLOYMENT_GUIDE.md) or the [Quick Start](../QUICKSTART_GCP.md) for setup instructions.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'Add your feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

## License

MIT License - See [LICENSE](LICENSE) file for details
