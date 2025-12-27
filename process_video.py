import os
from src.infrastructure.storage_service import download_file, upload_file
from src.application.video_service import VideoService
from urllib.parse import urlparse

def parse_public_uri(uri):
    """
    Parses a public GCS URL to extract bucket and blob name.
    Example: https://storage.googleapis.com/bucket-name/path/to/blob
    Returns (bucket_name, blob_name) or (None, None)
    """
    parsed = urlparse(uri)
    if parsed.netloc != 'storage.googleapis.com':
        return None, None
    
    # Path is like /bucket-name/path/to/blob
    # Split by / and we get ['', 'bucket-name', 'path', 'to', 'blob']
    parts = parsed.path.lstrip('/').split('/', 1)
    if len(parts) < 2:
        return None, None
        
    return parts[0], parts[1]

def run_trim_workflow(video_uri):
    """
    Downloads, trims, and uploads a video.
    """
    print(f"🚀 Starting Video Processing Workflow for: {video_uri}")
    
    bucket_name, blob_name = parse_public_uri(video_uri)
    if not bucket_name:
        print("❌ Invalid Public URI")
        return

    # 1. Download
    local_input = os.path.join("temp", os.path.basename(blob_name))
    download_file(bucket_name, blob_name, local_input)

    # 2. Trim
    local_output = os.path.join("temp", f"trimmed_{os.path.basename(blob_name)}")
    video_service = VideoService()
    video_service.fast_trim(local_input, local_output)

    # 3. Upload
    destination_blob = f"trimmed/{blob_name}"
    public_url = upload_file(bucket_name, local_output, destination_blob)
    
    print(f"✨ Workflow Complete! Processed video at: {public_url}")

if __name__ == "__main__":
    # Example usage
    VIDEO_URI = "https://storage.googleapis.com/evalsy-storage/text.mp4"
    run_trim_workflow(VIDEO_URI)
