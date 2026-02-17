# ============================================================================
# SAP Documentation Monitor - Cloud Run Deployment Script (PowerShell)
# ============================================================================

# Exit on error
$ErrorActionPreference = "Stop"

# ============================================================================
# CONFIGURATION - UPDATE THESE VALUES
# ============================================================================

$PROJECT_ID = "your-gcp-project-id"  # <-- Replace with your GCP Project ID
$REGION = "us-central1"
$SERVICE_NAME = "sap-doc-monitor"
$SCHEDULE = "0 9 * * *"  # Daily at 9 AM (cron format)

# Email Configuration (or use Secret Manager)
$EMAIL_SENDER = "ais.support@asint.net"
$EMAIL_RECEIVER = "learn.sapui5.frontend@gmail.com, daxesh.prajapati@asint.net"
$SMTP_SERVER = "smtp.office365.com"
$SMTP_PORT = "587"
$BASE_DOC_URL = "https://help.sap.com/docs/SAP_APM/2602f93216bb4530ba169c75be619edf/0840fd102be84f3ab8f8662a91f949a3.html"

# ============================================================================
# DEPLOYMENT SCRIPT
# ============================================================================

Write-Host "`nStarting deployment of SAP Documentation Monitor..." -ForegroundColor Green

# Step 1: Verify gcloud is configured
Write-Host "`nStep 1: Verifying gcloud configuration..." -ForegroundColor Yellow
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: gcloud CLI not found. Please install it first." -ForegroundColor Red
    exit 1
}

Write-Host "Current project: $(gcloud config get-value project)"
Write-Host "Setting project to: $PROJECT_ID"
gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION

# Step 2: Enable required APIs
Write-Host "`nStep 2: Enabling required GCP APIs..." -ForegroundColor Yellow
gcloud services enable `
    run.googleapis.com `
    cloudscheduler.googleapis.com `
    cloudbuild.googleapis.com `
    storage.googleapis.com `
    secretmanager.googleapis.com

# Step 3: Create storage bucket for snapshots
Write-Host "`nStep 3: Creating Cloud Storage bucket for snapshots..." -ForegroundColor Yellow
$BUCKET_NAME = "$PROJECT_ID-sap-snapshots"

# Check if bucket exists
$bucketExists = $false
try {
    gsutil ls -b "gs://$BUCKET_NAME" 2>$null
    $bucketExists = $true
    Write-Host "Bucket already exists: gs://$BUCKET_NAME"
} catch {
    Write-Host "Creating new bucket: gs://$BUCKET_NAME"
    gsutil mb -p $PROJECT_ID -l $REGION "gs://$BUCKET_NAME"
}

# Grant access to App Engine default service account
gsutil iam ch "serviceAccount:${PROJECT_ID}@appspot.gserviceaccount.com:objectAdmin" "gs://$BUCKET_NAME"

# Step 4: Create secret for email password
Write-Host "`nStep 4: Creating secret for email password..." -ForegroundColor Yellow
$EMAIL_PASSWORD = Read-Host "Please enter your email password" -AsSecureString
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($EMAIL_PASSWORD)
$PlainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)

# Create or update secret
$secretExists = $false
try {
    gcloud secrets describe email-password --project=$PROJECT_ID 2>$null
    $secretExists = $true
    Write-Host "Secret 'email-password' already exists. Updating..."
    $PlainPassword | gcloud secrets versions add email-password --data-file=-
} catch {
    Write-Host "Creating new secret 'email-password'..."
    $PlainPassword | gcloud secrets create email-password --data-file=- --replication-policy="automatic"
}

# Grant access to secret
gcloud secrets add-iam-policy-binding email-password `
    --member="serviceAccount:${PROJECT_ID}@appspot.gserviceaccount.com" `
    --role="roles/secretmanager.secretAccessor"

# Step 5: Build and push Docker image
Write-Host "`nStep 5: Building and pushing Docker image..." -ForegroundColor Yellow
gcloud builds submit --tag "gcr.io/$PROJECT_ID/$SERVICE_NAME"

# Step 6: Deploy to Cloud Run
Write-Host "`nStep 6: Deploying to Cloud Run..." -ForegroundColor Yellow
gcloud run deploy $SERVICE_NAME `
    --image "gcr.io/$PROJECT_ID/$SERVICE_NAME" `
    --platform managed `
    --region $REGION `
    --no-allow-unauthenticated `
    --memory 2Gi `
    --cpu 2 `
    --timeout 900 `
    --max-instances 1 `
    --set-env-vars "EMAIL_SENDER=$EMAIL_SENDER" `
    --set-env-vars "EMAIL_RECEIVER=$EMAIL_RECEIVER" `
    --set-env-vars "SMTP_SERVER=$SMTP_SERVER" `
    --set-env-vars "SMTP_PORT=$SMTP_PORT" `
    --set-env-vars "BASE_DOCUMENTATION_URL=$BASE_DOC_URL" `
    --set-env-vars "SNAPSHOTS_DIR=/app/snapshots" `
    --update-secrets "EMAIL_PASSWORD=email-password:latest"

# Get the service URL
$SERVICE_URL = gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)'
Write-Host "Service deployed at: $SERVICE_URL" -ForegroundColor Green

# Step 7: Create service account for scheduler
Write-Host "`nStep 7: Setting up Cloud Scheduler..." -ForegroundColor Yellow
$SA_NAME = "sap-monitor-scheduler"
$SA_EMAIL = "${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Create service account if it doesn't exist
$saExists = $false
try {
    gcloud iam service-accounts describe $SA_EMAIL --project=$PROJECT_ID 2>$null
    $saExists = $true
    Write-Host "Service account already exists: $SA_EMAIL"
} catch {
    gcloud iam service-accounts create $SA_NAME --display-name "SAP Monitor Scheduler"
}

# Grant invoker permission
gcloud run services add-iam-policy-binding $SERVICE_NAME `
    --member="serviceAccount:$SA_EMAIL" `
    --role="roles/run.invoker" `
    --region=$REGION

# Step 8: Create or update scheduler job
$JOB_NAME = "${SERVICE_NAME}-job"
$jobExists = $false
try {
    gcloud scheduler jobs describe $JOB_NAME --location=$REGION 2>$null
    $jobExists = $true
    Write-Host "Updating existing scheduler job..."
    gcloud scheduler jobs update http $JOB_NAME `
        --location=$REGION `
        --schedule="$SCHEDULE" `
        --uri=$SERVICE_URL `
        --http-method=POST `
        --oidc-service-account-email=$SA_EMAIL `
        --oidc-token-audience=$SERVICE_URL
} catch {
    Write-Host "Creating new scheduler job..."
    gcloud scheduler jobs create http $JOB_NAME `
        --location=$REGION `
        --schedule="$SCHEDULE" `
        --uri=$SERVICE_URL `
        --http-method=POST `
        --oidc-service-account-email=$SA_EMAIL `
        --oidc-token-audience=$SERVICE_URL `
        --time-zone="America/New_York"
}

# Step 9: Test deployment
Write-Host "`nStep 9: Testing deployment..." -ForegroundColor Yellow
Write-Host "Triggering a manual run..."
gcloud scheduler jobs run $JOB_NAME --location=$REGION

Write-Host "`n============================================================================" -ForegroundColor Green
Write-Host "Deployment completed successfully!" -ForegroundColor Green
Write-Host "============================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Service URL: $SERVICE_URL"
Write-Host "Scheduler: $JOB_NAME"
Write-Host "Schedule: $SCHEDULE"
Write-Host "Storage Bucket: gs://$BUCKET_NAME"
Write-Host ""
Write-Host "View logs:"
Write-Host "  gcloud run services logs read $SERVICE_NAME --region=$REGION"
Write-Host ""
Write-Host "Trigger manually:"
Write-Host "  gcloud scheduler jobs run $JOB_NAME --location=$REGION"
Write-Host ""
Write-Host "Update schedule:"
Write-Host "  gcloud scheduler jobs update http $JOB_NAME --location=$REGION --schedule=`"NEW_SCHEDULE`""
Write-Host ""
Write-Host "============================================================================" -ForegroundColor Green
