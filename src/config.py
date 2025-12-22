import os
from pathlib import Path

# This points to the /backend folder
# File is at: /backend/src/config.py
# parent: /backend/src
# parent.parent: /backend
BASE_DIR = Path(__file__).resolve().parent.parent

# PROJECT_ROOT for easy reference throughout the app
PROJECT_ROOT = os.getenv("PROJECT_ROOT", str(BASE_DIR))

# Common paths
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
SRC_DIR = os.path.join(PROJECT_ROOT, "src")

# Ensure critical directories exist
os.makedirs(OUTPUT_DIR, exist_ok=True)
