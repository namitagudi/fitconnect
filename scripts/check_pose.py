"""Quick check that MediaPipe works on your machine:  python scripts/check_pose.py my_photo.jpg"""
import os
import sys
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mpp
from mediapipe.tasks.python import vision

NAMES = {11: "L shoulder", 12: "R shoulder", 13: "L elbow", 14: "R elbow", 15: "L wrist", 16: "R wrist", 23: "L hip", 24: "R hip", 25: "L knee", 26: "R knee", 27: "L ankle", 28: "R ankle"}
model = os.environ.get("POSE_MODEL_PATH", "models/pose_landmarker_full.task")
if not os.path.exists(model):
    sys.exit(f"Model file not found: {model}. Download it first (README step 4).")
if len(sys.argv) < 2:
    sys.exit("Usage: python scripts/check_pose.py my_photo.jpg")
img = cv2.imread(sys.argv[1])
if img is None:
    sys.exit("Could not read that image.")
with vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(base_options=mpp.BaseOptions(model_asset_path=model), num_poses=1)) as lm:
    res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
if not res.pose_landmarks:
    sys.exit("No person detected. Try a clearer full-body photo.")
print("Person detected. Joint visibility (0-1; the app needs >= 0.6):")
for i, n in NAMES.items():
    p = res.pose_landmarks[0][i]
    print(f"  {n:12s} {p.visibility:.2f} {'OK' if p.visibility >= .6 else 'LOW'}")
