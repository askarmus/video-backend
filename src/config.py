import os
from pathlib import Path

# This points to the /backend folder
BASE_DIR = Path(__file__).resolve().parent.parent

# PROJECT_ROOT for easy reference throughout the app
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(BASE_DIR)))

# Common paths using pathlib
OUTPUT_DIR = PROJECT_ROOT / "output"
SRC_DIR = PROJECT_ROOT / "src"
TEMP_DIR = PROJECT_ROOT / "tmp"

# Ensure critical directories exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# GCS / Storage Config
DEFAULT_BUCKET = "evalsy-storage"
VIDEO_BUCKET = DEFAULT_BUCKET

# Intelligent Bucket Detection
raw_uri = os.getenv("VIDEO_URI")
if raw_uri and raw_uri.startswith("gs://"):
    # gs://bucket-name/folder/... -> bucket-name
    VIDEO_BUCKET = raw_uri.replace("gs://", "").split("/")[0]
else:
    VIDEO_BUCKET = os.getenv("VIDEO_BUCKET", DEFAULT_BUCKET)

# Other Global Configs
FFMPEG_LOGLEVEL = os.getenv("FFMPEG_LOGLEVEL", "error")
