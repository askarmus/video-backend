import os
from typing import Optional
from supabase import create_client, Client
from dotenv import load_dotenv

from src.config import PROJECT_ROOT
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

url: Optional[str] = os.getenv("SUPABASE_URL")
key: Optional[str] = os.getenv("SUPABASE_ANON_KEY")

if not url or not key:
    # Try alternate names common in Supabase setups
    url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")

if not url or not key:
    raise ValueError(f"Supabase credentials not found in environment. Checked SUPABASE_URL and NEXT_PUBLIC_SUPABASE_URL. CWD: {os.getcwd()}")

supabase: Client = create_client(url, key)
