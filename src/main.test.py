import os
import sys
import uuid

# Add the project root (one level up from 'src') to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.infrastructure.google_client import creds
from src.infrastructure.repositories.supabase_video_repository import SupabaseVideoRepository
from src.application.use_cases.sync_timeline import SyncTimelineUseCase


def test_batch_audio_edit():
    # --- CONFIGURATION ---
    # Replace these with real IDs from your Supabase database for testing
    video_id = "50a470ff-4207-485a-8a26-4d31ea8a775c" 
    user_id = "b438b72f-d935-4fba-b3e8-8b2a5ed941b3"
    
    updates = [
        {
            "id": "ea33ab33",
            "voiceover_text": "This is a test update for the first segment."
        }
    ]

    # --- INITIALIZATION ---
    repo = SupabaseVideoRepository()
    use_case = SyncTimelineUseCase(repo)

    print(f"🚀 Starting local test for execute_batch...")
    print(f"📹 Video ID: {video_id}")
    print(f"👤 User ID: {user_id}")
    print(f"📝 Updates: {len(updates)} segments")

    print(f"🚀 Executing method: execute_batch...")
    
    try:
        # You can place a breakpoint here or inside the use case itself
        # breakpoint() 
        
        result = use_case.execute_batch(
            video_id=video_id,
            user_id=user_id,
            updates=updates,
            creds=creds
        )

        print("\n✨ Success!")
        print(f"Status: {result.get('status')}")
        print(f"New Master Audio: {result.get('processed_audio_url')}")
        print(f"Updated Script Snippet: {result.get('script')[0] if result.get('script') else 'No script'}")

    except Exception as e:
        print(f"\n❌ Execution Failed: {str(e)}")
        import traceback
        traceback.print_exc()



if __name__ == "__main__":
    # Ensure environment variables are loaded if needed (e.g., SUPABASE_URL, etc.)
    # You might need to run this from the backend root directory
    test_batch_audio_edit()
