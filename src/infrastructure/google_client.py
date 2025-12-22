import os
import json
from dotenv import load_dotenv
from google import genai
from google.oauth2 import service_account

from src.config import PROJECT_ROOT
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

# 1. Get Path
KEY_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "key.json")
if not os.path.isabs(KEY_PATH):
    KEY_PATH = os.path.join(PROJECT_ROOT, KEY_PATH)

if not os.path.exists(KEY_PATH):
    raise FileNotFoundError(f"Missing key file at: {KEY_PATH}")

# 2. Load Project ID and Credentials
with open(KEY_PATH) as f:
    key_data = json.load(f)
    PROJECT_ID = key_data["project_id"]

creds = service_account.Credentials.from_service_account_file(
    KEY_PATH,
    scopes=['https://www.googleapis.com/auth/cloud-platform']
)

# 3. Initialize Shared Gemini Client
client = genai.Client(
    vertexai=True, 
    project=PROJECT_ID, 
    location='us-central1',
    credentials=creds
)
