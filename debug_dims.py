import cv2
import os

base_dir = r"c:\Users\askar\video_narrator\hello_world"
cursor_path = os.path.join(base_dir, "cursor.png")
project_root = r"c:\Users\askar\video_narrator"
video_path = os.path.join(project_root, "demo.mp4")

print(f"Checking {cursor_path}")
img = cv2.imread(cursor_path)
if img is None:
    print("Failed to load cursor.png")
else:
    print(f"cursor.png shape: {img.shape}")

print(f"Checking {video_path}")
cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    print("Failed to open video")
else:
    ret, frame = cap.read()
    if ret:
        print(f"Video frame shape: {frame.shape}")
    else:
        print("Failed to read video frame")
    cap.release()
