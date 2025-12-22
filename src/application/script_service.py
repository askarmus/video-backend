import json
import os
from google.genai import types

def create_ai_voice_script(client, video_uri: str):
    """
    Generate AI voiceover script from video using Gemini
    """
    print("🎬 Creating AI voiceover script...")
    
    prompt = """
        You are a professional product marketing narrator creating a polished SaaS demo voiceover.
        Your job is to guide a first-time viewer through the product clearly and confidently.

        The narration should cover the entire video timeline without missing sections.

        For each important moment (user action OR system state), create a script entry with:

        {
        "timestamp": "MM:SS",
        "ui_element": "Specific UI element or screen state",
        "user_action": "Clear description of the action",
        "voiceover_text": "Polished, professional narration written for a marketing demo",
        "pause_duration": 0.6
        }

        Narration rules:
        1. Speak as a guide, not as a user thinking aloud
        2. Each line must explain what is happening AND why it matters
        3. Use concise, polished language suitable for a website demo
        4. Avoid vague phrases and generic explanations
        5. Maintain a smooth, logical flow from start to finish
        6. Do not repeat the same idea or sentence across steps
        7. Assume the viewer has never seen this product before

        Never reuse or paraphrase the same narration sentence across multiple steps.
        Each step must introduce new information or move the story forward.

        Tone requirements:
        - Professional
        - Confident
        - Clear
        - Marketing-friendly
        - Natural but not casual
        - No filler words such as: okay, so, you know, then

        Coverage requirements:
        - Cover the full workflow from start to finish
        - Do not leave unexplained gaps
        - If the system updates, loads, or confirms an action, narrate it briefly
        - Narration must feel continuous and intentional

        Create 8-12 narration points that fully describe the workflow without long gaps.

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
                temperature=0.2,
                max_output_tokens=2000
            )
        )
        
        return json.loads(response.text)
        
    except Exception as e:
        print(f"Error: {e}")
        return []

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
