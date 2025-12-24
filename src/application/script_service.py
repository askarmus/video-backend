import json
import os
from google.genai import types

def analyze_video_full_pipeline(client, video_uri: str):
    """
    Analyzes video to generate a clean script AND identify segments to remove 
    (dead air, static frames, noise), specifically handling running clocks.
    """
    print("🎬 Analyzing video for Clean Segments & Professional Script...")
    
    prompt = """
    You are an expert AI Video Editor and Product Marketer.
    I have a raw recording of a software demo. It contains valuable UI actions mixed with "garbage" content.

    Your Goal: Return a JSON object containing two lists: 
    1. 'cleanup_segments' (parts to delete)
    2. 'script_timeline' (polished narration for the good parts)

    ---
    ### PART 1: IDENTIFY GARBAGE (The Cleanup)
    Identify segments that ruin the viewer experience. These will be cut.
    
    **CRITICAL RULE FOR "DEAD FRAMES":** Your video contains a running CLOCK/TIMER (e.g., 01:10:42). **Ignore the clock numbers changing.** If the user is not clicking, typing, or moving the mouse significantly to interact with a UI element, it is a DEAD FRAME, even if the timer is running.

    Mark segments for removal if:
    1. **No User Interaction:** The user is waiting/idle (even if a clock/loader is moving).
    2. **Background Noise:** Distracting audio (loudspeakers, static) where the narrator is silent.
    3. **Mistakes:** User corrects themselves or clicks the wrong thing.

    Structure for 'cleanup_segments':
    {
        "start_time": "MM:SS",
        "end_time": "MM:SS",
        "reason": "no_interaction" | "background_noise" | "mistake",
        "description": "Brief reason (e.g., 'User waiting, clock ticking only')"
    }

    ---
    ### PART 2: THE NARRATION (The Script)
    Focus ONLY on the moments where the user performs a meaningful UI action (excluding the cleanup segments).
    
    **Narration Rules (STRICTLY FOLLOW):**
    1. Speak as a guide, not as a user thinking aloud.
    2. Each line must explain what is happening AND why it matters.
    3. Use concise, polished language suitable for a website demo.
    4. Avoid vague phrases. No filler words (okay, so, you know, then).
    5. Maintain a smooth, logical flow. Do not repeat ideas.
    6. Assume the viewer has never seen this product before.

    **Coverage Requirements:**
    - Cover the full workflow from start to finish.
    - If the system updates or loads (and it's not being cut), narrate it briefly.
    - Create 8-12 narration points that fully describe the workflow.

    Structure for 'script_timeline':
    {
        "timestamp": "MM:SS",
        "ui_element": "Specific UI element",
        "user_action": "Clear description of action",
        "voiceover_text": "Polished, professional narration",
        "pause_duration": 0.6
    }

    **Timestamp & Duration Rules (CRITICAL):**
    1. **Valid Ranges Only:** Every `timestamp` in `script_timeline` MUST fall within a "kept" segment (not in `cleanup_segments`). 
    2. **Avoid "Garbage" Zones:** If an action you want to narrate falls inside a removed segment, snap the `timestamp` to the beginning of the NEXT valid kept range.
    3. **Continuous Flow:** Ensure the `script_timeline` covers the entire duration of the kept segments without significant gaps.
    4. **Last Frame Safety:** If your narrations exceed the available video duration, the system will automatically freeze the last frame to cover the audio.

    ---
    ### FINAL OUTPUT
    Return strictly JSON with this structure:
    {
      "cleanup_segments": [ ... ],
      "script_timeline": [ ... ]
    }
    """
    
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-001",
            contents=[
                types.Part.from_uri(file_uri=video_uri, mime_type="video/mp4"), 
                prompt
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1, # Keep strict for analysis
                max_output_tokens=8192
            )
        )
        
        return json.loads(response.text)
        
    except Exception as e:
        print(f"Error: {e}")
        return {"cleanup_segments": [], "script_timeline": []}

 
 
def load_script(file_path: str):
    """
    Read script data from a local JSON file
    """
    if not os.path.exists(file_path):
        return None
        
    print(f"📁 Loading script from {file_path}...")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading script file: {e}")
        return None

def save_script(script_data, file_path: str):
    """
    Save script data to a local JSON file
    """
    print(f"💾 Saving script to {file_path}...")
    try:
        # Ensure dir exists
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(script_data, f, indent=2)
            return True
    except Exception as e:
        print(f"Error saving script file: {e}")
        return False
