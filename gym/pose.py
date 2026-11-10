"""MediaPipe Pose Landmarker (pretrained). Needs the model file - see README step 4."""
import os
import threading
from .util import ApiError

_lm, _lock = None, threading.Lock()


def detect(image_bytes, model_path):
    """Returns (landmarks, width, height); landmarks = 33 x [x, y, visibility] (normalised) or None if no person found."""
    import cv2
    import numpy as np
    import mediapipe as mp
    from mediapipe.tasks import python as mpp
    from mediapipe.tasks.python import vision
    global _lm
    with _lock:
        if _lm is None:
            if not os.path.exists(model_path):
                raise ApiError(503, "pose_model_missing", "The pose model file is missing on the server. See README step 4 to download it.")
            _lm = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
                base_options=mpp.BaseOptions(model_asset_path=model_path), running_mode=vision.RunningMode.IMAGE, num_poses=1))
        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ApiError(422, "invalid", "That image couldn't be read.", "image")
        h, w = img.shape[:2]
        k = min(1.0, 1280 / max(h, w))
        if k < 1:
            img = cv2.resize(img, (int(w * k), int(h * k)))
            h, w = img.shape[:2]
        res = _lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
    if not res.pose_landmarks:
        return None, w, h
    return [[p.x, p.y, p.visibility] for p in res.pose_landmarks[0]], w, h
