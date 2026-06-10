"""
app.py – Flask application entry point for the Real-Time Object Detection
         and Tracking System.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

from flask import (Flask, Response, jsonify, render_template,
                   request, send_from_directory)

import config
from detector import YOLODetector
from video_manager import VideoManager

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_MB * 1024 * 1024
app.secret_key = config.SECRET_KEY

# ── Global singletons (initialised lazily in a thread so Flask starts fast) ───
_detector: YOLODetector | None    = None
_manager:  VideoManager | None    = None
_init_lock = threading.Lock()


def _ensure_init() -> tuple[YOLODetector, VideoManager]:
    global _detector, _manager
    with _init_lock:
        if _detector is None:
            _detector = YOLODetector()
        if _manager is None:
            _manager = VideoManager(_detector)
    return _detector, _manager


def _allowed_file(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in config.ALLOWED_EXTENSIONS


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    _, manager = _ensure_init()
    return Response(
        manager.generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/stats")
def stats():
    _, manager = _ensure_init()
    return jsonify(manager.stats)


@app.route("/system_status")
def system_status():
    detector, manager = _ensure_init()
    return jsonify({
        "model_ready": detector.ready,
        "model_path":  config.MODEL_PATH,
        **manager.stats,
    })


@app.route("/start_camera", methods=["POST"])
def start_camera():
    _, manager = _ensure_init()
    index = int(request.json.get("index", 0)) if request.is_json else 0
    ok = manager.start_webcam(index)
    return jsonify({"success": ok,
                    "message": "Camera started" if ok else manager.stats["error"]})


@app.route("/stop_camera", methods=["POST"])
def stop_camera():
    _, manager = _ensure_init()
    manager.stop()
    return jsonify({"success": True, "message": "Camera stopped"})


@app.route("/reset", methods=["POST"])
def reset():
    _, manager = _ensure_init()
    manager.reset()
    return jsonify({"success": True, "message": "System reset"})


@app.route("/upload_video", methods=["POST"])
def upload_video():
    _, manager = _ensure_init()

    if "video" not in request.files:
        return jsonify({"success": False, "message": "No file part in request"}), 400

    f = request.files["video"]
    if f.filename == "":
        return jsonify({"success": False, "message": "No file selected"}), 400

    if not _allowed_file(f.filename):
        exts = ", ".join(sorted(config.ALLOWED_EXTENSIONS))
        return jsonify({"success": False,
                        "message": f"Unsupported format. Allowed: {exts}"}), 400

    # Save
    filename  = f"upload_{int(time.time())}_{f.filename}"
    save_path = os.path.join(config.UPLOAD_FOLDER, filename)
    try:
        f.save(save_path)
    except Exception as exc:
        logger.error("Failed to save upload: %s", exc)
        return jsonify({"success": False, "message": "Server error saving file"}), 500

    # Start playback
    ok = manager.start_video(save_path)
    return jsonify({
        "success": ok,
        "message": "Video loaded and playing" if ok else manager.stats["error"],
        "filename": filename,
    })


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(413)
def too_large(_):
    return jsonify({"success": False,
                    "message": f"File too large (max {config.MAX_CONTENT_MB} MB)"}), 413


@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def server_error(exc):
    logger.error("Internal server error: %s", exc)
    return jsonify({"error": "Internal server error"}), 500


# ── Boot ──────────────────────────────────────────────────────────────────────

def _warm_up() -> None:
    """Pre-load model before first request in a background thread."""
    time.sleep(0.5)
    logger.info("Warming up detector …")
    _ensure_init()
    logger.info("Warm-up complete.")


if __name__ == "__main__":
    threading.Thread(target=_warm_up, daemon=True).start()
    logger.info("Starting Flask on %s:%s", config.HOST, config.PORT)
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        threaded=True,
        use_reloader=False,   # reloader breaks background threads
    )
