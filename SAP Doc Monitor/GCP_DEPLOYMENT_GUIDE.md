# GCP Deployment Guide - SAP Documentation Monitor

## Overview

This guide explains how to deploy the SAP Documentation Monitor on Google Cloud Platform (GCP) using two approaches:

1. **Cloud Run + Cloud Scheduler** (Recommended - Serverless)
2. **Compute Engine VM** (Alternative - Traditional VM)

## 📋 Prerequisites

- Google Cloud Platform account
- `gcloud` CLI installed and configured
- Docker installed locally (for building images)
- GCP Project with billing enabled

## 🚀 Recommended: Cloud Run + Cloud Scheduler

This approach is **serverless**, **cost-effective**, and **automatically scalable**.

### Architecture

```
Cloud Scheduler (Trigger) → Cloud Run (Container) → Email Notification
                                ↓
                         Cloud Storage (Snapshots)
```

### Step-by-Step Deployment

#### 1. Set Up GCP Environment

```bash
# Set your GCP project ID
export PROJECT_ID="your-project-id"
export REGION="us-central1"  # Choose your preferred region
export SERVICE_NAME="sap-doc-monitor"

# Configure gcloud
gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION

# Enable required APIs
gcloud services enable run.googleapis.com
gcloud services enable cloudscheduler.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable storage.googleapis.com
```

#### 2. Create Cloud Storage Bucket for Snapshots

```bash
# Create bucket for storing snapshots
gsutil mb -p $PROJECT_ID -l $REGION gs://${PROJECT_ID}-sap-snapshots

# Make bucket accessible to Cloud Run
gsutil iam ch serviceAccount:${PROJECT_ID}@appspot.gserviceaccount.com:objectAdmin gs://${PROJECT_ID}-sap-snapshots
```

#### 3. Build and Push Docker Image

```bash
# Navigate to project directory
cd "e:\2) Fair Work\3) SAP Doc Monitor Automation - Copy\SAP Doc Monitor"

# Build and push using Cloud Build
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME

# Alternative: Build locally and push
# docker build -t gcr.io/$PROJECT_ID/$SERVICE_NAME .
# docker push gcr.io/$PROJECT_ID/$SERVICE_NAME
```

#### 4. Deploy to Cloud Run

```bash
# Deploy the service
gcloud run deploy $SERVICE_NAME \
    --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
    --platform managed \
    --region $REGION \
    --no-allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 900 \
    --set-env-vars EMAIL_SENDER="ais.support@asint.net" \
    --set-env-vars EMAIL_PASSWORD="your-password-here" \
    --set-env-vars EMAIL_RECEIVER="learn.sapui5.frontend@gmail.com" \
    --set-env-vars SMTP_SERVER="smtp.office365.com" \
    --set-env-vars SMTP_PORT="587" \
    --set-env-vars BASE_DOCUMENTATION_URL="https://help.sap.com/docs/SAP_APM/..."
```

#### 5. Set Up Cloud Scheduler

```bash
# Create a service account for the scheduler
gcloud iam service-accounts create sap-monitor-scheduler \
    --display-name "SAP Monitor Scheduler"

# Grant permission to invoke Cloud Run
gcloud run services add-iam-policy-binding $SERVICE_NAME \
    --member=serviceAccount:sap-monitor-scheduler@${PROJECT_ID}.iam.gserviceaccount.com \
    --role=roles/run.invoker \
    --region=$REGION

# Get the Cloud Run URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')

# Create scheduler job (runs daily at 9 AM)
gcloud scheduler jobs create http sap-doc-monitor-daily \
    --location=$REGION \
    --schedule="0 9 * * *" \
    --uri=$SERVICE_URL \
    --http-method=POST \
    --oidc-service-account-email=sap-monitor-scheduler@${PROJECT_ID}.iam.gserviceaccount.com \
    --oidc-token-audience=$SERVICE_URL

# Alternative schedules:
# Every 6 hours: --schedule="0 */6 * * *"
# Every hour: --schedule="0 * * * *"
# Twice daily (9 AM and 6 PM): --schedule="0 9,18 * * *"
```

#### 6. Test the Deployment

```bash
# Trigger manually for testing
gcloud scheduler jobs run sap-doc-monitor-daily --location=$REGION

# View logs
gcloud run services logs read $SERVICE_NAME --region=$REGION --limit=50
```

## 🖥️ Alternative: Compute Engine VM

### Step-by-Step Deployment

#### 1. Create VM Instance

```bash
# Create a VM with Ubuntu
gcloud compute instances create sap-doc-monitor-vm \
    --zone=us-central1-a \
    --machine-type=e2-medium \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=30GB \
    --tags=http-server,https-server

# SSH into the VM
gcloud compute ssh sap-doc-monitor-vm --zone=us-central1-a
```

#### 2. Set Up Environment on VM

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install Python and dependencies
sudo apt-get install -y python3 python3-pip wget unzip

# Install Chrome
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb

# Install ChromeDriver
CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d '.' -f 1)
wget https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION -O chrome_version
CHROMEDRIVER_VERSION=$(cat chrome_version)
wget https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip
unzip chromedriver_linux64.zip
sudo mv chromedriver /usr/local/bin/
sudo chmod +x /usr/local/bin/chromedriver
```

#### 3. Deploy Application

```bash
# Clone or upload your code
mkdir -p ~/sap-doc-monitor
cd ~/sap-doc-monitor

# Install Python dependencies
pip3 install -r requirements.txt

# Set up systemd service
sudo nano /etc/systemd/system/sap-monitor.service
```

Add this content:

```ini
[Unit]
Description=SAP Documentation Monitor
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/sap-doc-monitor/sap-doc-monitor
ExecStart=/usr/bin/python3 scheduler.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable sap-monitor
sudo systemctl start sap-monitor

# Check status
sudo systemctl status sap-monitor

# View logs
sudo journalctl -u sap-monitor -f
```

## 💰 Cost Comparison

### Cloud Run + Scheduler
- **Cost**: ~$5-15/month (depending on frequency)
- **Pros**: Serverless, auto-scaling, no maintenance
- **Cons**: Cold starts (first request might be slower)

### Compute Engine VM
- **Cost**: ~$15-30/month (e2-medium running 24/7)
- **Pros**: Always ready, predictable performance
- **Cons**: Requires maintenance, always paying even when idle

## 🔧 Configuration Management

### Using Environment Variables (Cloud Run)

Modify your `config/settings.py` to read from environment variables:

```python
import os

BASE_DOCUMENTATION_URL = os.getenv('BASE_DOCUMENTATION_URL', 'default-url')
EMAIL_SENDER = os.getenv('EMAIL_SENDER', 'default@example.com')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
EMAIL_RECEIVER = os.getenv('EMAIL_RECEIVER', 'receiver@example.com')
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.office365.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
```

### Using Secret Manager (Recommended for Passwords)

```bash
# Enable Secret Manager API
gcloud services enable secretmanager.googleapis.com

# Create secret for email password
echo -n "your-password" | gcloud secrets create email-password --data-file=-

# Grant Cloud Run access to secrets
gcloud secrets add-iam-policy-binding email-password \
    --member=serviceAccount:${PROJECT_ID}@appspot.gserviceaccount.com \
    --role=roles/secretmanager.secretAccessor

# Update Cloud Run to use secrets
gcloud run deploy $SERVICE_NAME \
    --update-secrets EMAIL_PASSWORD=email-password:latest
```

## 📊 Monitoring and Logging

### View Logs

```bash
# Cloud Run logs
gcloud run services logs read $SERVICE_NAME --region=$REGION

# Scheduler logs
gcloud logging read "resource.type=cloud_scheduler_job"

# Filter for errors
gcloud run services logs read $SERVICE_NAME --region=$REGION --log-filter="severity>=ERROR"
```

### Set Up Alerts

```bash
# Create alert for failures
gcloud alpha monitoring policies create \
    --notification-channels=CHANNEL_ID \
    --display-name="SAP Monitor Failures" \
    --condition-display-name="Error Rate" \
    --condition-threshold-value=1 \
    --condition-threshold-duration=60s
```

## 🧪 Testing

### Manual Trigger

```bash
# Trigger Cloud Run directly
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
     -X POST $SERVICE_URL

# Trigger via Scheduler
gcloud scheduler jobs run sap-doc-monitor-daily --location=$REGION
```

### Local Testing with Docker

```bash
# Build locally
docker build -t sap-doc-monitor .

# Run locally
docker run -e EMAIL_SENDER=your-email \
           -e EMAIL_PASSWORD=your-password \
           sap-doc-monitor
```

## 🔒 Security Best Practices

1. **Never commit credentials** - Use Secret Manager
2. **Use least privilege IAM** - Grant minimal permissions
3. **Enable VPC Service Controls** - For enhanced security
4. **Use Private IPs** - If accessing internal resources
5. **Enable audit logging** - Track all access

## 📝 Maintenance

### Update Deployment

```bash
# Rebuild and deploy
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME
gcloud run deploy $SERVICE_NAME --image gcr.io/$PROJECT_ID/$SERVICE_NAME

# Or use continuous deployment from GitHub
```

### Modify Schedule

```bash
# Update scheduler
gcloud scheduler jobs update http sap-doc-monitor-daily \
    --location=$REGION \
    --schedule="0 */3 * * *"  # Every 3 hours
```

## 🆘 Troubleshooting

### Common Issues

1. **Chrome/ChromeDriver errors**: Ensure Dockerfile has correct dependencies
2. **Timeout errors**: Increase timeout in Cloud Run to 900s
3. **Memory errors**: Increase memory allocation to 2Gi or more
4. **Email not sending**: Check SMTP settings and firewall rules

### Debug Commands

```bash
# Check service status
gcloud run services describe $SERVICE_NAME --region=$REGION

# View recent logs
gcloud run services logs read $SERVICE_NAME --limit=100

# Test scheduler
gcloud scheduler jobs run sap-doc-monitor-daily --location=$REGION

# SSH into VM (Compute Engine)
gcloud compute ssh sap-doc-monitor-vm --zone=us-central1-a
```

## 📚 Additional Resources

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [Cloud Scheduler Documentation](https://cloud.google.com/scheduler/docs)
- [Secret Manager Documentation](https://cloud.google.com/secret-manager/docs)

