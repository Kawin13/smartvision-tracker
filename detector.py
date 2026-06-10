"""
detector.py – YOLOv8 wrapper for object detection.

Returns structured Detection objects consumed by the tracker.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

import config

logger = logging.getLogger(__name__)


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class Detection:
    """One detected object in a frame."""
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    class_id: int
    label: str

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return self.x1, self.y1, self.x2, self.y2

    @property
    def tlwh(self) -> tuple[float, float, float, float]:
        """top-left, width, height"""
        return self.x1, self.y1, self.x2 - self.x1, self.y2 - self.y1

    @property
    def cx_cy(self) -> tuple[float, float]:
        return (self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2


# ── Detector ──────────────────────────────────────────────────────────────────

class YOLODetector:
    """Thread-safe YOLOv8 detector."""

    def __init__(self) -> None:
        self._model = None
        self._lock  = threading.Lock()
        self._ready = False
        self._class_names: List[str] = []
        self._target_ids: Optional[set[int]] = None
        self._load()

    # ── Loading ────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            from ultralytics import YOLO  # lazy import so Flask can start first
            logger.info("Loading YOLOv8 model from %s …", config.MODEL_PATH)
            model = YOLO(config.MODEL_PATH)
            model.fuse()          # fuse Conv+BN layers for faster CPU inference
            self._model       = model
            self._class_names = list(model.names.values())
            self._target_ids  = self._resolve_target_ids()
            self._ready       = True
            logger.info("YOLOv8 model loaded. Classes available: %d", len(self._class_names))
        except Exception as exc:
            logger.error("Failed to load YOLO model: %s", exc)
            self._ready = False

    def _resolve_target_ids(self) -> Optional[set[int]]:
        """Return the numeric class ids for config.TARGET_CLASSES, or None to detect all."""
        if not config.TARGET_CLASSES:
            return None
        ids: set[int] = set()
        for cid, name in enumerate(self._class_names):
            if name.lower() in {c.lower() for c in config.TARGET_CLASSES}:
                ids.add(cid)
        logger.info("Filtering to class ids: %s", ids)
        return ids if ids else None

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def ready(self) -> bool:
        return self._ready

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run inference on a BGR frame and return detections.
        Never raises – returns [] on any failure.
        """
        if not self._ready or self._model is None:
            return []

        try:
            with self._lock:
                results = self._model(
                    frame,
                    imgsz=config.INFERENCE_SIZE,
                    conf=config.CONFIDENCE_THRESHOLD,
                    iou=config.IOU_THRESHOLD,
                    verbose=False,
                    device="cpu",
                )
        except Exception as exc:
            logger.warning("Inference error: %s", exc)
            return []

        detections: List[Detection] = []
        for result in results:
            if result.boxes is None:
                continue
            boxes = result.boxes
            for i in range(len(boxes)):
                try:
                    cid  = int(boxes.cls[i].item())
                    if self._target_ids and cid not in self._target_ids:
                        continue
                    conf = float(boxes.conf[i].item())
                    x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                    label = self._class_names[cid] if cid < len(self._class_names) else str(cid)
                    detections.append(Detection(
                        x1=x1, y1=y1, x2=x2, y2=y2,
                        confidence=conf,
                        class_id=cid,
                        label=label,
                    ))
                except Exception:
                    continue

        return detections

    def reload(self) -> bool:
        """Hot-reload the model (useful after file replacement)."""
        self._ready = False
        self._load()
        return self._ready
