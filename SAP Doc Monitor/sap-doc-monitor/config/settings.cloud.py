import os

# ==============================================================================
# DOCUMENTATION MONITORING CONFIGURATION
# ==============================================================================

# AUTO-DISCOVERY MODE: Set BASE_DOCUMENTATION_URL to automatically discover all pages from TOC
# The system will extract all documentation links from the table of contents
BASE_DOCUMENTATION_URL = os.getenv(
    'BASE_DOCUMENTATION_URL',
    "https://help.sap.com/docs/SAP_APM/2602f93216bb4530ba169c75be619edf/0840fd102be84f3ab8f8662a91f949a3.html"
)

# MANUAL MODE: Or manually specify URLs if you prefer (leave as empty dict to use auto-discovery)
# If DOCUMENT_URLS is empty, the system will use BASE_DOCUMENTATION_URL for auto-discovery
DOCUMENT_URLS = {
    # Leave empty to enable auto-discovery, or add specific pages manually:
    # "Page Title": "https://help.sap.com/docs/...",
} 

# Snapshots directory - each page will have its own snapshot file
SNAPSHOTS_DIR = os.getenv('SNAPSHOTS_DIR', "snapshots")

# ==============================================================================
# EMAIL CONFIGURATION
# ==============================================================================

# Email settings - reads from environment variables first, falls back to defaults
EMAIL_SENDER = os.getenv('EMAIL_SENDER', "ais.support@asint.net")
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', "Q&043192219237oh")  # Use Secret Manager in production!
EMAIL_RECEIVER = os.getenv('EMAIL_RECEIVER', "learn.sapui5.frontend@gmail.com")
SMTP_SERVER = os.getenv('SMTP_SERVER', "smtp.office365.com")
SMTP_PORT = int(os.getenv('SMTP_PORT', "587"))

# ==============================================================================
# NOTES FOR DEPLOYMENT
# ==============================================================================
# 
# For GCP Cloud Run deployment, environment variables are set via:
#   gcloud run deploy --set-env-vars KEY=VALUE
# 
# For sensitive data like EMAIL_PASSWORD, use Secret Manager:
#   gcloud run deploy --update-secrets EMAIL_PASSWORD=secret-name:latest
#
# For local development, you can:
#   1. Set environment variables in your shell
#   2. Or modify the default values above (not recommended)
#   3. Or use a .env file with python-dotenv (requires installation)
#
