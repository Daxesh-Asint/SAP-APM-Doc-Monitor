# ==============================================================================
# SAP DOCUMENTATION MONITORING CONFIGURATION
# ==============================================================================

# ------------------------------------------------------------------------------
# AUTO-DISCOVERY MODE (Recommended)
# ------------------------------------------------------------------------------
# Set BASE_DOCUMENTATION_URL to automatically discover all pages from the TOC
# The system will extract all documentation links from the table of contents
# Example: The main documentation page that shows the table of contents

BASE_DOCUMENTATION_URL = "https://help.sap.com/docs/SAP_APM/2602f93216bb4530ba169c75be619edf/0840fd102be84f3ab8f8662a91f949a3.html"

# ------------------------------------------------------------------------------
# MANUAL MODE (Alternative)
# ------------------------------------------------------------------------------
# Or manually specify URLs if you prefer
# If DOCUMENT_URLS is empty ({}), the system will use BASE_DOCUMENTATION_URL for auto-discovery
# If you add URLs here, auto-discovery will be skipped

DOCUMENT_URLS = {
    # Leave empty to enable auto-discovery, or add specific pages manually:
    # "Page Title": "https://help.sap.com/docs/...",
    # Example:
    # "Creating Service Instances": "https://help.sap.com/docs/SAP_APM/.../bfbe1443c6264d86a87171483fe30aa8.html",
}

# Snapshots directory - each page will have its own snapshot file
SNAPSHOTS_DIR = "snapshots"

# Email Configuration (Optional)
# For Gmail: Use App Password, not your regular password
# To generate an App Password:
# 1. Enable 2-factor authentication on your Google account
# 2. Go to: Google Account → Security → 2-Step Verification → App passwords
# 3. Generate a new app password for "Mail"
# Leave these as default values to disable email notifications

EMAIL_SENDER = "yourgmail@gmail.com"
EMAIL_PASSWORD = "your_app_password"
EMAIL_RECEIVER = "yourgmail@gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
