#!/bin/bash

# ============================================================================
# SAP Documentation Monitor - Cloud Run Deployment Script
# ============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================================================
# CONFIGURATION - UPDATE THESE VALUES
# ============================================================================

PROJECT_ID="integral-iris-449816-g3"
REGION="us-central1"
SERVICE_NAME="sap-doc-monitor"
SCHEDULE="0 9 * * *"  # Daily at 9 AM (cron format)

# Email Configuration (or use Secret Manager)
EMAIL_SENDER="ais.support@asint.net"
EMAIL_RECEIVER="learn.sapui5.frontend@gmail.com"
SMTP_SERVER="smtp.office365.com"
SMTP_PORT="587"
BASE_DOC_URL="https://help.sap.com/docs/SAP_APM/2602f93216bb4530ba169c75be619edf/0840fd102be84f3ab8f8662a91f949a3.html"

# ============================================================================
# DEPLOYMENT SCRIPT
# ============================================================================

echo -e "${GREEN}Starting deployment of SAP Documentation Monitor...${NC}"

# Step 1: Verify gcloud is configured
echo -e "\n${YELLOW}Step 1: Verifying gcloud configuration...${NC}"
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}ERROR: gcloud CLI not found. Please install it first.${NC}"
    exit 1
fi

echo "Current project: $(gcloud config get-value project)"
echo "Setting project to: $PROJECT_ID"
gcloud config set project $PROJECT_ID
gcloud config set run/region $REGION

# Step 2: Enable required APIs
echo -e "\n${YELLOW}Step 2: Enabling required GCP APIs...${NC}"
gcloud services enable \
    run.googleapis.com \
    cloudscheduler.googleapis.com \
    cloudbuild.googleapis.com \
    storage.googleapis.com \
    secretmanager.googleapis.com

# Step 3: Create storage bucket for snapshots
echo -e "\n${YELLOW}Step 3: Creating Cloud Storage bucket for snapshots...${NC}"
BUCKET_NAME="${PROJECT_ID}-sap-snapshots"
if gsutil ls -b gs://${BUCKET_NAME} 2>/dev/null; then
    echo "Bucket already exists: gs://${BUCKET_NAME}"
else
    gsutil mb -p $PROJECT_ID -l $REGION gs://${BUCKET_NAME}
    echo "Created bucket: gs://${BUCKET_NAME}"
fi

# Grant access to App Engine default service account
gsutil iam ch serviceAccount:${PROJECT_ID}@appspot.gserviceaccount.com:objectAdmin gs://${BUCKET_NAME}

# Step 4: Create secret for email password
echo -e "\n${YELLOW}Step 4: Creating secret for email password...${NC}"
echo "Please enter your email password (input will be hidden):"
read -s EMAIL_PASSWORD

# Create or update secret
if gcloud secrets describe email-password --project=$PROJECT_ID &>/dev/null; then
    echo "Secret 'email-password' already exists. Updating..."
    echo -n "$EMAIL_PASSWORD" | gcloud secrets versions add email-password --data-file=-
else
    echo "Creating new secret 'email-password'..."
    echo -n "$EMAIL_PASSWORD" | gcloud secrets create email-password --data-file=- --replication-policy="automatic"
fi

# Grant access to secret
gcloud secrets add-iam-policy-binding email-password \
    --member="serviceAccount:${PROJECT_ID}@appspot.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

# Step 5: Build and push Docker image
echo -e "\n${YELLOW}Step 5: Building and pushing Docker image...${NC}"
gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE_NAME

# Step 6: Deploy to Cloud Run
echo -e "\n${YELLOW}Step 6: Deploying to Cloud Run...${NC}"
gcloud run deploy $SERVICE_NAME \
    --image gcr.io/$PROJECT_ID/$SERVICE_NAME \
    --platform managed \
    --region $REGION \
    --no-allow-unauthenticated \
    --memory 2Gi \
    --cpu 2 \
    --timeout 900 \
    --max-instances 1 \
    --set-env-vars EMAIL_SENDER="$EMAIL_SENDER" \
    --set-env-vars EMAIL_RECEIVER="$EMAIL_RECEIVER" \
    --set-env-vars SMTP_SERVER="$SMTP_SERVER" \
    --set-env-vars SMTP_PORT="$SMTP_PORT" \
    --set-env-vars BASE_DOCUMENTATION_URL="$BASE_DOC_URL" \
    --set-env-vars SNAPSHOTS_DIR="/app/snapshots" \
    --update-secrets EMAIL_PASSWORD=email-password:latest

# Get the service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')
echo -e "${GREEN}Service deployed at: $SERVICE_URL${NC}"

# Step 7: Create service account for scheduler
echo -e "\n${YELLOW}Step 7: Setting up Cloud Scheduler...${NC}"
SA_NAME="sap-monitor-scheduler"
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Create service account if it doesn't exist
if gcloud iam service-accounts describe $SA_EMAIL --project=$PROJECT_ID &>/dev/null; then
    echo "Service account already exists: $SA_EMAIL"
else
    gcloud iam service-accounts create $SA_NAME \
        --display-name "SAP Monitor Scheduler"
fi

# Grant invoker permission
gcloud run services add-iam-policy-binding $SERVICE_NAME \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/run.invoker" \
    --region=$REGION

# Step 8: Create or update scheduler job
JOB_NAME="${SERVICE_NAME}-job"
if gcloud scheduler jobs describe $JOB_NAME --location=$REGION &>/dev/null; then
    echo "Updating existing scheduler job..."
    gcloud scheduler jobs update http $JOB_NAME \
        --location=$REGION \
        --schedule="$SCHEDULE" \
        --uri=$SERVICE_URL \
        --http-method=POST \
        --oidc-service-account-email=$SA_EMAIL \
        --oidc-token-audience=$SERVICE_URL
else
    echo "Creating new scheduler job..."
    gcloud scheduler jobs create http $JOB_NAME \
        --location=$REGION \
        --schedule="$SCHEDULE" \
        --uri=$SERVICE_URL \
        --http-method=POST \
        --oidc-service-account-email=$SA_EMAIL \
        --oidc-token-audience=$SERVICE_URL \
        --time-zone="America/New_York"
fi

# Step 9: Test deployment
echo -e "\n${YELLOW}Step 9: Testing deployment...${NC}"
echo "Triggering a manual run..."
gcloud scheduler jobs run $JOB_NAME --location=$REGION

echo -e "\n${GREEN}============================================================================${NC}"
echo -e "${GREEN}Deployment completed successfully!${NC}"
echo -e "${GREEN}============================================================================${NC}"
echo ""
echo "Service URL: $SERVICE_URL"
echo "Scheduler: $JOB_NAME"
echo "Schedule: $SCHEDULE"
echo "Storage Bucket: gs://${BUCKET_NAME}"
echo ""
echo "View logs:"
echo "  gcloud run services logs read $SERVICE_NAME --region=$REGION"
echo ""
echo "Trigger manually:"
echo "  gcloud scheduler jobs run $JOB_NAME --location=$REGION"
echo ""
echo "Update schedule:"
echo "  gcloud scheduler jobs update http $JOB_NAME --location=$REGION --schedule=\"NEW_SCHEDULE\""
echo ""
echo -e "${GREEN}============================================================================${NC}"
