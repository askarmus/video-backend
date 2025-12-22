import os
from google.cloud import storage
from .google_client import creds, PROJECT_ID

# Initialize the Storage client with shared credentials
storage_client = storage.Client(credentials=creds, project=PROJECT_ID)

def upload_file(bucket_name, source_file_path, destination_blob_name):
    """
    Uploads a file to the bucket.
    """
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)

        print(f"📤 Uploading {source_file_path} to {bucket_name}/{destination_blob_name}...")
        blob.upload_from_filename(source_file_path)
        print(f"✅ File uploaded successfully.")
        
        return f"gs://{bucket_name}/{destination_blob_name}"
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        return None

def download_file(bucket_name, source_blob_name, destination_file_path):
    """
    Downloads a blob from the bucket.
    """
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(source_blob_name)

        # Create destination directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(destination_file_path)), exist_ok=True)

        print(f"📥 Downloading {bucket_name}/{source_blob_name} to {destination_file_path}...")
        blob.download_to_filename(destination_file_path)
        print(f"✅ File downloaded successfully.")
        
        return destination_file_path
    except Exception as e:
        print(f"❌ Download failed for {bucket_name}/{source_blob_name}: {e}")
        import traceback
        traceback.print_exc()
        return None

def parse_gcs_uri(uri):
    """
    Helper to extract bucket and blob from a gs:// URI
    """
    if not uri.startswith("gs://"):
        return None, None
    
    parts = uri.replace("gs://", "").split("/", 1)
    bucket_name = parts[0]
    blob_name = parts[1] if len(parts) > 1 else ""
    
    return bucket_name, blob_name
