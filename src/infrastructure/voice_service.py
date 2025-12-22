import os
import json
from google.cloud import texttospeech

def generate_voiceover(script_data, credentials, output_dir="voiceovers"):
    """
    Convert script to AI voice using Google Text-to-Speech
    """
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Initialize TTS client with provided credentials
    tts_client = texttospeech.TextToSpeechClient(credentials=credentials)
    
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name="en-US-Neural2-F",
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
    )
    
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=1.08,
        pitch=2.0
    )
    
    audio_files = []
    
    for i, entry in enumerate(script_data):
        print(f"🎤 Generating voiceover {i+1}/{len(script_data)}...")
        
        synthesis_input = texttospeech.SynthesisInput(text=entry['voiceover_text'])
        
        response = tts_client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        
        timestamp_clean = entry['timestamp'].replace(':', '')
        filename = os.path.join(output_dir, f"narration_{i+1:02d}_{timestamp_clean}.mp3")
        
        with open(filename, "wb") as out:
            out.write(response.audio_content)
        
        audio_files.append({
            "filename": filename,
            "timestamp": entry['timestamp'],
            "duration": entry.get('pause_duration', 1.5),
            "text": entry['voiceover_text']
        })
        
    
    # Save metadata
    metadata_path = os.path.join(output_dir, "metadata.json")
    with open(metadata_path, "w") as f:
        json.dump({
            "total_narrations": len(audio_files),
            "audio_files": audio_files,
            "script": script_data
        }, f, indent=2)
    
    return audio_files
