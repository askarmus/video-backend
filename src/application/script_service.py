import json
import os
from typing import Dict, Any
from google.genai import types

def get_default_project_template() -> Dict[str, Any]:
    """
    Returns the baseline 'Master Envelope' for a video project.
    """
    return {
        "intro": {
            "enabled": False,
            "text": "",
            "font_size": 48,
            "duration": 2,
            "color": "#ffffff",
            "align": "center"
        },
        "outro": {
            "enabled": False,
            "text": "Welcome message...",
            "font_size": 48,
            "duration": 2,
            "color": "#ffffff",
            "align": "center"
        },
        "music": {
            "enabled": False,
            "url": "/audi_clip/bg_audio1_clip.mp3",
            "volume": 0.3
        },
        "background": "",
        "script": [],
        "cleanup_segments": [],
        "metadata": {
            "version": "1.0",
            "generated_at": ""
        }
    }

 

def analyze_video_full_pipeline(client, video_uri: str, mode: str = "MARKETING"):
    """
    Enhanced analysis that aligns narration with UI labels but groups them into 
    cohesive 'Trupeer-style' segments (Macro-Segmentation).
    """
    print(f"🎬 [Gemini] Analyzing video with Trupeer-style aggregation in '{mode}' mode...")

    style_guardrails = """
        **CRITICAL STYLE RULES:**
        1. **NO STUTTERING:** Never write repeated words like "the the the" or "um". 
        2. **PERFECT GRAMMAR:** Sentences must be grammatically correct standard English.
        * *Wrong:* "Once it is uploaded the file..."
        * *Right:* "Once the file is uploaded..."
        * *Wrong:* "Why doesn't guy doesn't match..."
        * *Right:* "Why the candidate does not match..."
        3. **PROFESSIONAL FLOW:** Speak like a polished narrator, not an improv speaker.
        4. **PROFESSIONAL TERMINOLOGY:** * REPLACE casual words like "guy", "dude", or "fella" with "Candidate" or "User".
        """
    
    # --- 1. PERSONA CONFIGURATION (Kept exactly as you had it) ---
    if mode.upper() == "ONBOARDING":
        persona_instruction = """
        **ROLE:** Technical Trainer.
        **GOAL:** Teach a user strictly *how* to perform a task.
        **TONE:** Patient, Clear, Instructional.
        **KEY INSTRUCTION:** Guide the user through the workflow smoothly.
        """
    elif mode.upper() == "SALES":
        persona_instruction = """
        **ROLE:** Senior Sales Engineer.
        **GOAL:** Persuade a buyer by highlighting the *solution*.
        **TONE:** Professional, Confident, Value-Driven.
        **KEY INSTRUCTION:** Focus on the "Why" behind the features.
        """
    else: # Marketing / Default
        persona_instruction = """
        **ROLE:** Product Marketing Expert.
        **GOAL:** Generate excitement.
        **TONE:** High-Energy, Punchy.
        **KEY INSTRUCTION:** Focus on outcomes and speed.
        """

    # --- 2. THE UPDATED PROMPT (Modified for Trupeer-style flow) ---
    prompt = f"""
    {style_guardrails}
    {persona_instruction}
    
    **CORE OBJECTIVE: MACRO-SEGMENTATION (TRUPEER STYLE)**
    You are creating a video voiceover. The current problem is that scripts are too "choppy" (e.g., narrating every single click).
    
    **YOUR NEW RULE: AGGREGATE ACTIONS.**
    Instead of describing every UI interaction individually, group them into logical "Chapters."
    
    **1. SEGMENTATION STRATEGY:**
    * **BAD (Micro):** "Click Settings. [Pause]. Click Profile. [Pause]. Click Edit."
    * **GOOD (Macro):** "To update your details, simply navigate to the Profile section in Settings."
    * **TIMING TARGET:** specific segments should aim for **10-20 seconds** of narration, covering multiple visual clicks.

    **2. TEXT ALIGNMENT STRATEGY:**
    * Even though you are grouping actions, you must still reference the **Primary UI Text** that anchors the section.
    * If the user clicks "Save", "Confirm", and "Exit", just reference the main action: "Save your changes."

    **OUTPUT STRUCTURE (STRICT JSON):**
    {{
      "cleanup_segments": [
        {{ 
            "start_time": "MM:SS", 
            "end_time": "MM:SS", 
            "reason": "long_pause|mistake|loading", 
            "description": "Brief reason"
        }}
      ],
      "script_timeline": [
        {{
            "timestamp": "MM:SS",
            "ui_element": "Description of the MAIN UI component for this block",
            "detected_text_categories": {{
                "interactive": ["Key_Button_Names_Only"],
                "informational": ["Section_Headers_Only"],
                "navigation": ["Menu_Items"],
                "headers": ["Page_Titles"],
                "messages": ["Status_Alerts"],
                "data": ["Key_Values"]
            }},
            "primary_text_reference": "The ONE most important text label visible in this sequence",
            "user_action": "The high-level goal achieved in this sequence",
            "voiceover_text": "A cohesive, 2-3 sentence paragraph narrating this entire sequence. Focus on value.",
            "text_match_score": 0.0, 
            "pause_duration": 0.5
        }}
      ]
    }}
    
    **QUALITY CHECK:**
    * If your `voiceover_text` is shorter than 10 words, you are segmenting too aggressively. MERGE it with the next action.
    * Ensure `timestamp` represents the start of the *sequence*, not just a random click.
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
                temperature=0.3, # Slightly higher for more natural sentence flow
            )
        )
        return json.loads(response.text)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return {"script_timeline": [], "cleanup_segments": []}

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
