"""
Cloud Storage integration for persistent snapshot storage.
Used when running on GCP Cloud Run (ephemeral containers).
Falls back to local filesystem when GCS is not configured.
"""
import os
import logging

logger = logging.getLogger(__name__)

# Check if google-cloud-storage is available
try:
    from google.cloud import storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False


def _get_bucket_name():
    """Get GCS bucket name from environment variable."""
    return os.getenv('GCS_BUCKET_NAME', '')


def _get_gcs_client():
    """Get GCS client (uses default credentials on Cloud Run)."""
    if not GCS_AVAILABLE:
        return None
    try:
        return storage.Client()
    except Exception as e:
        logger.warning(f"Could not create GCS client: {e}")
        return None


def is_gcs_enabled():
    """Check if GCS storage is configured and available."""
    bucket_name = _get_bucket_name()
    return bool(bucket_name) and GCS_AVAILABLE


def download_snapshot(snapshot_filename, local_path):
    """
    Download a snapshot file from GCS to local path.
    Returns True if file was downloaded, False if it doesn't exist in GCS.
    """
    if not is_gcs_enabled():
        return os.path.exists(local_path)
    
    bucket_name = _get_bucket_name()
    blob_name = f"snapshots/{snapshot_filename}"
    
    try:
        client = _get_gcs_client()
        if not client:
            return os.path.exists(local_path)
        
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        if blob.exists():
            # Ensure local directory exists
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            blob.download_to_filename(local_path)
            logger.info(f"Downloaded snapshot from GCS: {blob_name}")
            return True
        else:
            logger.info(f"No existing snapshot in GCS: {blob_name}")
            return False
            
    except Exception as e:
        logger.warning(f"Error downloading from GCS: {e}")
        return os.path.exists(local_path)


def upload_snapshot(snapshot_filename, local_path):
    """
    Upload a snapshot file from local path to GCS.
    """
    if not is_gcs_enabled():
        return
    
    bucket_name = _get_bucket_name()
    blob_name = f"snapshots/{snapshot_filename}"
    
    try:
        client = _get_gcs_client()
        if not client:
            return
        
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(local_path)
        logger.info(f"Uploaded snapshot to GCS: {blob_name}")
        
    except Exception as e:
        logger.warning(f"Error uploading to GCS: {e}")


def download_all_snapshots(local_dir):
    """
    Download all snapshot files from GCS to local directory.
    """
    if not is_gcs_enabled():
        return
    
    bucket_name = _get_bucket_name()
    
    try:
        client = _get_gcs_client()
        if not client:
            return
        
        bucket = client.bucket(bucket_name)
        blobs = bucket.list_blobs(prefix="snapshots/")
        
        os.makedirs(local_dir, exist_ok=True)
        count = 0
        
        for blob in blobs:
            # Skip the "directory" blob itself
            if blob.name == "snapshots/":
                continue
            
            filename = os.path.basename(blob.name)
            local_path = os.path.join(local_dir, filename)
            blob.download_to_filename(local_path)
            count += 1
        
        logger.info(f"Downloaded {count} snapshots from GCS bucket '{bucket_name}'")
        
    except Exception as e:
        logger.warning(f"Error downloading snapshots from GCS: {e}")


def upload_all_snapshots(local_dir):
    """
    Upload all snapshot files from local directory to GCS.
    Also removes any GCS files that no longer exist locally (sync).
    """
    if not is_gcs_enabled():
        return
    
    bucket_name = _get_bucket_name()
    
    try:
        client = _get_gcs_client()
        if not client:
            return
        
        bucket = client.bucket(bucket_name)
        
        # Collect current local filenames
        local_files = set()
        for filename in os.listdir(local_dir):
            if filename.endswith('.txt'):
                local_files.add(filename)
        
        # Upload all local snapshot files
        count = 0
        for filename in local_files:
            local_path = os.path.join(local_dir, filename)
            blob_name = f"snapshots/{filename}"
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(local_path)
            count += 1
        
        logger.info(f"Uploaded {count} snapshots to GCS bucket '{bucket_name}'")
        
        # Clean up stale GCS files that no longer exist locally
        stale_count = 0
        blobs = bucket.list_blobs(prefix="snapshots/")
        for blob in blobs:
            if blob.name == "snapshots/":
                continue
            gcs_filename = os.path.basename(blob.name)
            if gcs_filename not in local_files:
                blob.delete()
                logger.info(f"Deleted stale snapshot from GCS: {gcs_filename}")
                stale_count += 1
        
        if stale_count > 0:
            logger.info(f"Cleaned up {stale_count} stale snapshots from GCS bucket")
        
    except Exception as e:
        logger.warning(f"Error uploading snapshots to GCS: {e}")
