"""
video_manager.py – Manages video capture, runs detection+tracking in a
background thread, and exposes MJPEG frames to Flask.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

import cv2
import numpy as np

import config
from detector import Detection, YOLODetector
from tracker import SORTTracker, TrackedObject

logger = logging.getLogger(__name__)


# ── Drawing helpers ────────────────────────────────────────────────────────────

def _colour_for(label: str) -> tuple[int, int, int]:
    return config.CLASS_COLOURS.get(label.lower(),
           config.CLASS_COLOURS["default"])


def _draw_box(frame: np.ndarray, obj: TrackedObject) -> None:
    x1, y1, x2, y2 = (int(obj.x1), int(obj.y1), int(obj.x2), int(obj.y2))
    colour = _colour_for(obj.label)
    cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 2)

    # Build label text
    label_text = f"ID:{obj.track_id} {obj.label.title()} {obj.confidence*100:.0f}%"
    font       = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.5
    thickness  = 1

    (tw, th), baseline = cv2.getTextSize(label_text, font, font_scale, thickness)
    ty = max(y1 - 4, th + 4)

    # Background pill
    cv2.rectangle(frame, (x1, ty - th - baseline - 2), (x1 + tw + 4, ty + 2),
                  colour, -1)
    # White text on coloured background
    cv2.putText(frame, label_text, (x1 + 2, ty - baseline),
                font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)


def _draw_hud(frame: np.ndarray, fps: float, obj_count: int, track_count: int) -> None:
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 28), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    font  = cv2.FONT_HERSHEY_SIMPLEX
    info  = f"FPS: {fps:.1f}   Objects: {obj_count}   Tracks: {track_count}"
    cv2.putText(frame, info, (8, 18), font, 0.5, (50, 220, 50), 1, cv2.LINE_AA)


# ── VideoManager ──────────────────────────────────────────────────────────────

class VideoManager:
    """
    Background thread that reads frames from a source, runs YOLOv8+SORT,
    annotates the frame, and stores the latest JPEG for streaming.
    """

    def __init__(self, detector: YOLODetector) -> None:
        self._detector        = detector
        self._tracker         = SORTTracker()

        self._lock            = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event      = threading.Event()

        self._cap: Optional[cv2.VideoCapture] = None
        self._source: Optional[str | int]     = None   # path or 0 for webcam

        # Shared state (protected by _lock)
        self._latest_jpeg: Optional[bytes] = None
        self._fps_actual  = 0.0
        self._obj_count   = 0
        self._track_count = 0
        self._status      = "idle"    # idle | running | error
        self._error_msg   = ""

    # ── Public control ─────────────────────────────────────────────────────────

    def start_webcam(self, index: int = 0) -> bool:
        self._stop()
        cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            logger.warning("Webcam index %d not available", index)
            self._set_status("error", f"Webcam {index} not available")
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_BUFFERSIZE,   2)
        self._source = index
        self._start_capture(cap)
        return True

    def start_video(self, path: str) -> bool:
        self._stop()
        if not os.path.isfile(path):
            self._set_status("error", "Video file not found")
            return False
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            self._set_status("error", "Cannot open video file")
            cap.release()
            return False
        self._source = path
        self._start_capture(cap)
        return True

    def stop(self) -> None:
        self._stop()

    def reset(self) -> None:
        self._stop()
        self._tracker.reset()
        with self._lock:
            self._latest_jpeg = None
            self._fps_actual  = 0.0
            self._obj_count   = 0
            self._track_count = 0
        self._set_status("idle")

    # ── Frame generator for Flask ──────────────────────────────────────────────

    def generate_frames(self):
        """Yield MJPEG frames (bytes) forever until the source stops."""
        while True:
            with self._lock:
                jpeg = self._latest_jpeg
            if jpeg is not None:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
            else:
                # Emit a placeholder black frame
                blank = np.zeros((config.FRAME_HEIGHT, config.FRAME_WIDTH, 3),
                                 dtype=np.uint8)
                msg = "No source active" if self._status == "idle" \
                      else self._error_msg or "Starting…"
                cv2.putText(blank, msg, (20, config.FRAME_HEIGHT // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 180),
                            2, cv2.LINE_AA)
                _, buf = cv2.imencode(".jpg", blank,
                                      [cv2.IMWRITE_JPEG_QUALITY, 70])
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n"
                       + buf.tobytes() + b"\r\n")
            time.sleep(1 / config.STREAM_FPS)

    # ── Stats ──────────────────────────────────────────────────────────────────

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "fps":         round(self._fps_actual, 1),
                "objects":     self._obj_count,
                "tracks":      self._track_count,
                "status":      self._status,
                "error":       self._error_msg,
                "source":      str(self._source) if self._source is not None else None,
                "model_ready": self._detector.ready,
            }

    # ── Private ────────────────────────────────────────────────────────────────

    def _start_capture(self, cap: cv2.VideoCapture) -> None:
        self._cap = cap
        self._stop_event.clear()
        self._tracker.reset()
        self._set_status("running")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        if self._cap:
            self._cap.release()
            self._cap = None
        self._source = None

    def _set_status(self, status: str, error: str = "") -> None:
        with self._lock:
            self._status    = status
            self._error_msg = error

    # ── Processing loop ────────────────────────────────────────────────────────

    def _run(self) -> None:
        logger.info("Video processing thread started (source=%s)", self._source)
        fps_timer    = time.time()
        frame_count  = 0
        fps_measured = 0.0

        while not self._stop_event.is_set():
            if self._cap is None:
                break

            ret, frame = self._cap.read()
            if not ret:
                # For video files loop back; for webcam treat as error
                if isinstance(self._source, str):
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    logger.warning("Webcam read failed")
                    self._set_status("error", "Camera stream lost")
                    break

            # Resize for performance
            frame = cv2.resize(frame, (config.FRAME_WIDTH, config.FRAME_HEIGHT))

            # Detect
            detections = self._detector.detect(frame)

            # Track
            tracked = self._tracker.update(detections)

            # Draw
            for obj in tracked:
                _draw_box(frame, obj)

            frame_count += 1
            elapsed = time.time() - fps_timer
            if elapsed >= 1.0:
                fps_measured = frame_count / elapsed
                frame_count  = 0
                fps_timer    = time.time()

            _draw_hud(frame, fps_measured, len(detections), len(tracked))

            # Encode and store
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY]
            _, buf = cv2.imencode(".jpg", frame, encode_params)
            with self._lock:
                self._latest_jpeg = buf.tobytes()
                self._fps_actual  = fps_measured
                self._obj_count   = len(detections)
                self._track_count = len(tracked)

        logger.info("Video processing thread exited")
        if self._cap:
            self._cap.release()
            self._cap = None
