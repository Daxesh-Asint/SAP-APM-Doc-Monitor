# 🚀 GCP Deployment Summary

## What I've Created for You

I've prepared your SAP Documentation Monitor for Google Cloud Platform deployment with the following files:

### 📄 New Files Created

1. **[QUICKSTART_GCP.md](QUICKSTART_GCP.md)** - Quick 5-minute deployment guide
2. **[GCP_DEPLOYMENT_GUIDE.md](GCP_DEPLOYMENT_GUIDE.md)** - Comprehensive deployment documentation
3. **[Dockerfile](Dockerfile)** - Container configuration with Chrome/Selenium
4. **[.dockerignore](.dockerignore)** - Optimized Docker build
5. **[deploy-to-cloud-run.ps1](deploy-to-cloud-run.ps1)** - Automated deployment script (Windows)
6. **[deploy-to-cloud-run.sh](deploy-to-cloud-run.sh)** - Automated deployment script (Linux/Mac)
7. **[cloud_run_app.py](sap-doc-monitor/cloud_run_app.py)** - HTTP endpoint for Cloud Run
8. **[settings.cloud.py](sap-doc-monitor/config/settings.cloud.py)** - Cloud-ready configuration

## 🎯 Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Google Cloud Platform                      │
│                                                               │
│  ┌──────────────────┐        ┌──────────────────┐          │
│  │  Cloud Scheduler │───────▶│    Cloud Run     │          │
│  │  (Trigger Timer) │        │  (Your Monitor)  │          │
│  └──────────────────┘        └────────┬─────────┘          │
│                                        │                     │
│                              ┌─────────▼─────────┐          │
│                              │ Secret Manager    │          │
│                              │ (Email Password)  │          │
│                              └───────────────────┘          │
│                                        │                     │
│                              ┌─────────▼─────────┐          │
│                              │ Cloud Storage     │          │
│                              │ (Snapshots)       │          │
│                              └───────────────────┘          │
└─────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                              ┌───────────────────┐
                              │  Email to Users   │
                              └───────────────────┘
```

## 🏃 Quick Start (Choose One)

### Option A: Automated Deployment (Recommended)

**For Windows (PowerShell):**
```powershell
# 1. Edit deploy-to-cloud-run.ps1 - set your PROJECT_ID
# 2. Run:
.\deploy-to-cloud-run.ps1
```

**For Linux/Mac (Bash):**
```bash
# 1. Edit deploy-to-cloud-run.sh - set your PROJECT_ID
# 2. Make executable and run:
chmod +x deploy-to-cloud-run.sh
./deploy-to-cloud-run.sh
```

### Option B: Manual Step-by-Step

Follow the detailed guide: [GCP_DEPLOYMENT_GUIDE.md](GCP_DEPLOYMENT_GUIDE.md)

## ⚡ How to Trigger the Automation

### 1. Automatic (Scheduled) - Default
Once deployed, your monitor runs automatically based on the schedule you set (default: daily at 9 AM).

**No action needed!** Cloud Scheduler triggers it automatically.

### 2. Manual Trigger (On-Demand)

**From PowerShell/Terminal:**
```powershell
gcloud scheduler jobs run sap-doc-monitor-job --location=us-central1
```

**From GCP Console:**
1. Visit: https://console.cloud.google.com/cloudscheduler
2. Click **RUN NOW** on your job

**Via HTTP (for testing):**
```powershell
$SERVICE_URL = gcloud run services describe sap-doc-monitor --region=us-central1 --format='value(status.url)'
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" -X POST $SERVICE_URL
```

## 📅 Customize the Schedule

Edit the `SCHEDULE` variable in your deployment script:

```powershell
$SCHEDULE = "0 9 * * *"  # Daily at 9 AM (default)
```

**Common schedules:**
- Every hour: `"0 * * * *"`
- Every 3 hours: `"0 */3 * * *"`
- Every 6 hours: `"0 */6 * * *"`
- Twice daily (9 AM & 6 PM): `"0 9,18 * * *"`
- Weekdays at 9 AM: `"0 9 * * 1-5"`

**Update after deployment:**
```powershell
gcloud scheduler jobs update http sap-doc-monitor-job `
    --location=us-central1 `
    --schedule="0 */3 * * *"
```

## 📊 Monitor Your Deployment

### View Logs
```powershell
# Recent logs
gcloud run services logs read sap-doc-monitor --region=us-central1 --limit=50

# Live logs (follow)
gcloud run services logs tail sap-doc-monitor --region=us-central1

# Errors only
gcloud run services logs read sap-doc-monitor --log-filter="severity>=ERROR"
```

### GCP Console
- **Cloud Run**: https://console.cloud.google.com/run
- **Cloud Scheduler**: https://console.cloud.google.com/cloudscheduler
- **Logs**: https://console.cloud.google.com/logs
- **Secrets**: https://console.cloud.google.com/security/secret-manager

## 💰 Expected Costs

**Monthly estimate for different frequencies:**

| Runs Per Day | Monthly Cost |
|--------------|--------------|
| 1 (daily) | $3-5 |
| 4 (every 6 hours) | $5-10 |
| 24 (every hour) | $10-15 |

*Costs include Cloud Run, Scheduler, Storage, and Secret Manager*

## 🔄 Update Your Deployment

### Update Code
```powershell
# Make your code changes, then:
gcloud builds submit --tag gcr.io/your-project-id/sap-doc-monitor
gcloud run deploy sap-doc-monitor --image gcr.io/your-project-id/sap-doc-monitor
```

### Update Configuration
```powershell
# Update email receiver
gcloud run services update sap-doc-monitor `
    --update-env-vars EMAIL_RECEIVER="new-email@example.com"

# Update documentation URL
gcloud run services update sap-doc-monitor `
    --update-env-vars BASE_DOCUMENTATION_URL="https://new-url.com"
```

## 🛠️ Troubleshooting

### Check Deployment Status
```powershell
gcloud run services describe sap-doc-monitor --region=us-central1
gcloud scheduler jobs describe sap-doc-monitor-job --location=us-central1
```

### Test Locally First
```powershell
# Build Docker image
docker build -t sap-doc-monitor .

# Run locally
docker run -e EMAIL_SENDER=your-email `
           -e EMAIL_PASSWORD=your-password `
           -e EMAIL_RECEIVER=receiver@example.com `
           --rm sap-doc-monitor
```

### Common Issues

**"Permission denied"**
```powershell
gcloud auth login
gcloud config set project your-project-id
```

**"API not enabled"**
```powershell
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com
```

**"Timeout"**
- Increase timeout in deployment script: `--timeout 900`
- The script allows up to 15 minutes

**"Out of memory"**
- Increase memory: `--memory 4Gi`
- Default is 2Gi which should be sufficient

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| [QUICKSTART_GCP.md](QUICKSTART_GCP.md) | 5-minute quick start guide |
| [GCP_DEPLOYMENT_GUIDE.md](GCP_DEPLOYMENT_GUIDE.md) | Detailed deployment documentation |
| [deploy-to-cloud-run.ps1](deploy-to-cloud-run.ps1) | Automated deployment (Windows) |
| [deploy-to-cloud-run.sh](deploy-to-cloud-run.sh) | Automated deployment (Linux/Mac) |
| [Dockerfile](Dockerfile) | Container configuration |

## ✅ Next Steps

1. **Review** [QUICKSTART_GCP.md](QUICKSTART_GCP.md)
2. **Edit** deployment script with your GCP project ID
3. **Run** deployment script
4. **Verify** in GCP Console
5. **Monitor** logs to ensure it's working

## 🆘 Need Help?

- Check [GCP_DEPLOYMENT_GUIDE.md](GCP_DEPLOYMENT_GUIDE.md) for detailed troubleshooting
- View logs: `gcloud run services logs read sap-doc-monitor`
- Test manually: `gcloud scheduler jobs run sap-doc-monitor-job`

---

**You're ready to deploy!** Start with [QUICKSTART_GCP.md](QUICKSTART_GCP.md) for the fastest path to deployment.
