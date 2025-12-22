import os
import subprocess
import shutil

class AudioService:
    def __init__(self):
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg not found. Install FFmpeg and add it to PATH.")

    def run_cmd(self, cmd):
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p.returncode != 0:
            raise RuntimeError(f"Command failed:\n{' '.join(cmd)}\n\nSTDERR:\n{p.stderr[:4000]}")
        return p.stdout, p.stderr

    def concat_audio_files(self, audio_files, output_path, temp_dir):
        """
        Concatenates multiple audio files into a single MP3.
        audio_files: list of dicts with {'filename': path}
        """
        audio_list_path = os.path.join(temp_dir, "audio_list.txt")
        
        with open(audio_list_path, "w") as f:
            for a in audio_files:
                # Ensure we use forward slashes for ffmpeg concat filter on Windows
                abs_path = os.path.abspath(a['filename']).replace('\\', '/')
                f.write(f"file '{abs_path}'\n")

        self.run_cmd([
            "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", audio_list_path, "-acodec", "libmp3lame", output_path
        ])
        
        return output_path
