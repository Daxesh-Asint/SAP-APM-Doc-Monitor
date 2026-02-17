# Auto-Discovery Feature - Quick Start Guide

## What Changed?

Instead of manually maintaining a list of 25+ URLs in `settings.py`, you can now provide **just ONE base URL** and the system will automatically discover all documentation pages from the table of contents.

## How It Works

1. You provide the main documentation page URL (the one with the table of contents)
2. The system fetches that page
3. It extracts all documentation links from the navigation/TOC
4. It monitors ALL those pages for changes automatically

## Setup (Auto-Discovery Mode)

**1. Edit `config/settings.py`:**

```python
# Set your base URL (main page with table of contents)
BASE_DOCUMENTATION_URL = "https://help.sap.com/docs/SAP_APM/2602f93216bb4530ba169c75be619edf/0840fd102be84f3ab8f8662a91f949a3.html"

# Leave this empty to enable auto-discovery
DOCUMENT_URLS = {}

# Configure your email settings
EMAIL_SENDER = "youremail@gmail.com"
EMAIL_PASSWORD = "your-app-password"
EMAIL_RECEIVER = "recipient@example.com"
```

**2. Test discovery:**

```bash
python test_discovery.py
```

Expected output:
```
================================================================================
RESULTS: 24 pages discovered
================================================================================

Discovered Documentation Pages:
--------------------------------------------------------------------------------

1. Target Audience
   URL: https://help.sap.com/docs/SAP_APM/.../a4226898318146e488d5c35ab4d99fad.html

2. General Information
   URL: https://help.sap.com/docs/SAP_APM/.../3516f55fe8054d238ddca3f0661421cb.html

... (and 22 more pages)

✓ These 24 pages will be monitored for changes
```

**3. Run the monitor:**

```bash
python main.py
```

First run creates snapshots for all discovered pages.
Subsequent runs detect changes.

## Manual Mode (Still Available)

If you prefer to specify exact pages, add them to `DOCUMENT_URLS`:

```python
DOCUMENT_URLS = {
    "Page 1": "https://...",
    "Page 2": "https://...",
}
```

When `DOCUMENT_URLS` is not empty, auto-discovery is skipped.

## Benefits

✅ No need to manually list all URLs
✅ Automatically monitors new pages added to the TOC
✅ Less maintenance required
✅ One URL to rule them all!

## What Gets Discovered?

The system finds all `.html` documentation links that:
- Are in the same documentation set (same path pattern)
- Are listed in the table of contents/navigation
- Have valid page titles

## Detecting New TOC Items

**Question:** What if a new section is added to the table of contents?

**Answer:** 
- On the next run, the discovery will find the new page
- A new snapshot will be created for it
- You'll get notified about it in the next monitoring cycle

This means **new documentation pages are automatically included** without any configuration changes!
