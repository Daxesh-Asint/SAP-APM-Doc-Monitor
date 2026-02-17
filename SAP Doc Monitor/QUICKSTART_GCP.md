# Quick Start: Deploy to Google Cloud Platform

## Prerequisites
- Google Cloud Platform account
- gcloud CLI installed: https://cloud.google.com/sdk/docs/install
- Billing enabled on your GCP project

## 🚀 Quick Deployment (5 Minutes)

### Option 1: Using PowerShell Script (Windows - Easiest)

1. **Open PowerShell** in the project directory

2. **Edit the deployment script** - Open `deploy-to-cloud-run.ps1` and update:
   ```powershell
   $PROJECT_ID = "your-gcp-project-id"  # Your GCP project ID
   $REGION = "us-central1"               # Or your preferred region
   $SCHEDULE = "0 9 * * *"               # Daily at 9 AM (modify as needed)
   ```

3. **Run the script**:
   ```powershell
   .\deploy-to-cloud-run.ps1
   ```

4. **Enter your email password** when prompted (it will be stored securely in Secret Manager)

5. **Done!** Your monitor is now running on GCP

### Option 2: Using Bash Script (Linux/Mac)

1. **Open terminal** in the project directory

2. **Make script executable**:
   ```bash
   chmod +x deploy-to-cloud-run.sh
   ```

3. **Edit the script** - Open `deploy-to-cloud-run.sh` and update configuration

4. **Run the script**:
   ```bash
   ./deploy-to-cloud-run.sh
   ```

### Option 3: Manual Deployment

If you prefer to understand each step, follow the [GCP_DEPLOYMENT_GUIDE.md](GCP_DEPLOYMENT_GUIDE.md)

## 📅 Schedule Options

Modify the `$SCHEDULE` or `SCHEDULE` variable in the deployment script:

| Frequency | Cron Expression |
|-----------|----------------|
| Every hour | `0 * * * *` |
| Every 3 hours | `0 */3 * * *` |
| Every 6 hours | `0 */6 * * *` |
| Daily at 9 AM | `0 9 * * *` |
| Twice daily (9 AM & 6 PM) | `0 9,18 * * *` |
| Every Monday at 8 AM | `0 8 * * 1` |
| Weekdays at 9 AM | `0 9 * * 1-5` |

## 🎯 Triggering the Automation

### Automatic Triggers (via Cloud Scheduler)
Once deployed, the automation runs automatically based on your schedule. No action needed!

### Manual Triggers

**Trigger immediately from command line:**
```powershell
# PowerShell
gcloud scheduler jobs run sap-doc-monitor-job --location=us-central1

# Or trigger Cloud Run directly
$SERVICE_URL = gcloud run services describe sap-doc-monitor --region=us-central1 --format='value(status.url)'
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" -X POST $SERVICE_URL
```

**Trigger from GCP Console:**
1. Go to Cloud Scheduler: https://console.cloud.google.com/cloudscheduler
2. Find your job: `sap-doc-monitor-job`
3. Click **RUN NOW**

## 📊 Monitoring

### View Logs
```powershell
# Real-time logs
gcloud run services logs read sap-doc-monitor --region=us-central1 --limit=50

# Follow logs (live)
gcloud run services logs tail sap-doc-monitor --region=us-central1

# Filter for errors only
gcloud run services logs read sap-doc-monitor --region=us-central1 --log-filter="severity>=ERROR"
```

### View in Console
- **Logs**: https://console.cloud.google.com/run
- **Scheduler**: https://console.cloud.google.com/cloudscheduler
- **Storage (Snapshots)**: https://console.cloud.google.com/storage

## 🔄 Updating the Deployment

### Update Code
```powershell
# After making code changes
gcloud builds submit --tag gcr.io/your-project-id/sap-doc-monitor
gcloud run deploy sap-doc-monitor --image gcr.io/your-project-id/sap-doc-monitor --region=us-central1
```

### Update Schedule
```powershell
gcloud scheduler jobs update http sap-doc-monitor-job `
    --location=us-central1 `
    --schedule="0 */3 * * *"  # Every 3 hours
```

### Update Email Settings
```powershell
gcloud run services update sap-doc-monitor `
    --region=us-central1 `
    --set-env-vars EMAIL_RECEIVER="new-email@example.com"
```

## 💰 Cost Estimate

**Cloud Run + Scheduler** (Recommended):
- Cloud Run: ~$0.10 per run (depending on duration)
- Cloud Scheduler: $0.10 per job per month
- Cloud Storage: ~$0.02 per GB per month
- **Total**: ~$5-15/month for hourly runs

## 🔒 Security Notes

1. **Email passwords** are stored in Secret Manager (encrypted)
2. **No public access** - Cloud Run is private, only Cloud Scheduler can trigger it
3. **Audit logs** automatically track all access

## ❓ Troubleshooting

### "Permission denied" errors
```powershell
# Re-authenticate
gcloud auth login
gcloud config set project your-project-id
```

### "API not enabled" errors
```powershell
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com
```

### Check service status
```powershell
gcloud run services describe sap-doc-monitor --region=us-central1
```

### Test locally before deploying
```powershell
# Build Docker image
docker build -t sap-doc-monitor .

# Run locally
docker run -e EMAIL_SENDER=your-email `
           -e EMAIL_PASSWORD=your-password `
           sap-doc-monitor
```

## 📚 Additional Resources

- [Full Deployment Guide](GCP_DEPLOYMENT_GUIDE.md)
- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud Scheduler Documentation](https://cloud.google.com/scheduler/docs)

## 🆘 Need Help?

Common issues and solutions:

1. **Chrome/Selenium errors**: The Dockerfile includes all Chrome dependencies
2. **Timeout errors**: Increase timeout: `--timeout 900` (15 minutes max)
3. **Memory errors**: Increase memory: `--memory 2Gi` or `--memory 4Gi`
4. **Email not sending**: Check SMTP settings and firewall rules

For more help, see the [GCP_DEPLOYMENT_GUIDE.md](GCP_DEPLOYMENT_GUIDE.md) troubleshooting section.
