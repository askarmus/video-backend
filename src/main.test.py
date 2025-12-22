import os
from src.application.video_service import VideoService

if __name__ == "__main__":
    vs = VideoService()
    
    # Path configuration
    input_video = "output/final_text_144233_3ab7.mp4"
    bg_image = "output/bg_template.png"
    output_video = "output/bg_final_text_144233_3ab7.mp4"
    
    # Ensure inputs exist
    abs_input = os.path.abspath(input_video)
    abs_bg = os.path.abspath(bg_image)
    abs_output = os.path.abspath(output_video)

    if os.path.exists(abs_input) and os.path.exists(abs_bg):
        print(f"🎨 Adding background...")
        print(f"📹 Input: {input_video}")
        print(f"🖼️  BG: {bg_image}")
        print(f"🚀 Output: {output_video}")
        
        vs.add_background(abs_input, abs_bg, abs_output)
        print(f"✅ Success! Saved to {output_video}")
    else:
        if not os.path.exists(abs_input):
            print(f"❌ Error: Input video not found at {abs_input}")
        if not os.path.exists(abs_bg):
            print(f"❌ Error: Background image not found at {abs_bg}")