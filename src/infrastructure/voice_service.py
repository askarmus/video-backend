import os
import json
import uuid

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
        # Generate unique ID for this segment if not present
        if 'id' not in entry:
            entry['id'] = uuid.uuid4().hex[:8]
            
        print(f"🎤 Generating voiceover {i+1}/{len(script_data)} ({entry['id']})...")
        
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
        
        # Calculate estimating duration based on response byte size for MP3 (approximate)
        # MP3 24khz/48kbps approx. 
        # Better: let pipeline service fill this in accurately.
        
        audio_files.append({
            "id": entry['id'],
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

def estimate_word_timestamps(text, total_duration_seconds):
    """
    Estimates the start and end time for each word based on character length.
    This assumes a relatively constant speaking rate, which is true for AI.
    """
    words = text.split()
    if not words:
        return []

    # Calculate total "weight" (characters) to distribute time proportionally
    total_chars = sum(len(w) for w in words)
    if total_chars == 0:
        return []

    # Calculate time per character
    # We leave a tiny buffer at start/end so words don't feel too rushed
    char_duration = total_duration_seconds / total_chars
    
    spans = []
    current_time = 0.0

    for word in words:
        # Duration of this word is proportional to its length
        word_dur = len(word) * char_duration
        
        spans.append({
            "text": word,
            "startTime": round(current_time, 3),
            "endTime": round(current_time + word_dur, 3)
        })
        current_time += word_dur

    return spans
