import os
from src.infrastructure.storage_service import download_file, upload_file, parse_gcs_uri
from src.application.video_service import VideoService

def run_trim_workflow(video_uri):
    """
    Downloads, trims, and uploads a video.
    """
    print(f"🚀 Starting Video Processing Workflow for: {video_uri}")
    
    bucket_name, blob_name = parse_gcs_uri(video_uri)
    if not bucket_name:
        print("❌ Invalid GCS URI")
        return

    # 1. Download
    local_input = os.path.join("temp", blob_name)
    download_file(bucket_name, blob_name, local_input)

    # 2. Trim
    local_output = os.path.join("temp", f"trimmed_{blob_name}")
    video_service = VideoService()
    video_service.fast_trim(local_input, local_output)

    # 3. Upload
    destination_blob = f"trimmed/{blob_name}"
    upload_file(bucket_name, local_output, destination_blob)
    
    print(f"✨ Workflow Complete! Processed video at: gs://{bucket_name}/{destination_blob}")

if __name__ == "__main__":
    # Example usage
    VIDEO_URI = "gs://evalsy-storage/text.mp4"
    run_trim_workflow(VIDEO_URI)
