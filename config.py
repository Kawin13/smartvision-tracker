"""
Configuration settings for the Object Detection and Tracking System.
"""

import os

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
MODEL_FOLDER  = os.path.join(BASE_DIR, "models")
MODEL_PATH    = os.path.join(MODEL_FOLDER, "yolov8n.pt")

# ── Flask ──────────────────────────────────────────────────────────────────────
SECRET_KEY        = os.environ.get("SECRET_KEY", "change-me-in-production")
DEBUG             = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
HOST              = os.environ.get("HOST", "0.0.0.0")
PORT              = int(os.environ.get("PORT", 5000))
MAX_CONTENT_MB    = 200                        # max upload size in MB
ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv", "webm"}

# ── Detection ──────────────────────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = float(os.environ.get("CONF_THRESH", 0.40))
IOU_THRESHOLD        = float(os.environ.get("IOU_THRESH",  0.45))
INFERENCE_SIZE       = int(os.environ.get("INFER_SIZE",    640))   # px (width)

# COCO classes we care about (subset for speed)
TARGET_CLASSES = [
    "person", "car", "bus", "truck", "motorcycle",
    "bicycle", "dog", "cat",
]

# ── Video / Streaming ──────────────────────────────────────────────────────────
FRAME_WIDTH   = int(os.environ.get("FRAME_WIDTH",  640))
FRAME_HEIGHT  = int(os.environ.get("FRAME_HEIGHT", 480))
JPEG_QUALITY  = int(os.environ.get("JPEG_QUALITY", 80))   # 1-100
STREAM_FPS    = int(os.environ.get("STREAM_FPS",   30))   # target stream fps

# ── Tracking ───────────────────────────────────────────────────────────────────
MAX_DISAPPEARED = int(os.environ.get("MAX_DISAPPEARED", 30))   # frames before track dropped
MAX_DISTANCE    = float(os.environ.get("MAX_DISTANCE",  150))  # pixel distance for IoU match

# ── Colours (BGR) per class label ──────────────────────────────────────────────
CLASS_COLOURS = {
    "person":     (0,   200, 255),
    "car":        (0,   255, 100),
    "bus":        (255, 165,   0),
    "truck":      (255, 100,   0),
    "motorcycle": (200,   0, 255),
    "bicycle":    (0,   180, 255),
    "dog":        (255, 255,   0),
    "cat":        (100, 255, 200),
    "default":    (200, 200, 200),
}

# ── Ensure required directories exist ─────────────────────────────────────────
for _d in (UPLOAD_FOLDER, MODEL_FOLDER):
    os.makedirs(_d, exist_ok=True)
