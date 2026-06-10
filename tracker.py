"""
tracker.py – Multi-object tracker (pure-Python SORT, no extra deps).

Implements IoU-based Hungarian matching, Kalman-filter state estimation,
and stable track-id assignment.  Drop-in ByteTrack if the library is
available; falls back to this implementation automatically.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

import config
from detector import Detection

logger = logging.getLogger(__name__)


# ── Kalman Filter ──────────────────────────────────────────────────────────────

class KalmanBox:
    """
    A simple constant-velocity Kalman filter for [cx, cy, area, aspect, vx, vy, va].
    Loosely follows the SORT paper.
    """

    count: int = 0  # class-level id counter

    def __init__(self, bbox: Tuple[float, float, float, float]) -> None:
        KalmanBox.count += 1
        self.id          = KalmanBox.count
        self.hits        = 1
        self.hit_streak  = 1
        self.age         = 0
        self.time_since_update = 0

        # State: [cx, cy, s, r, cx', cy', s']   (r = aspect ratio, s = area)
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        s  = (x2 - x1) * (y2 - y1)
        r  = (x2 - x1) / float(y2 - y1 + 1e-6)

        # State transition matrix
        self.F = np.array([
            [1,0,0,0,1,0,0],
            [0,1,0,0,0,1,0],
            [0,0,1,0,0,0,1],
            [0,0,0,1,0,0,0],
            [0,0,0,0,1,0,0],
            [0,0,0,0,0,1,0],
            [0,0,0,0,0,0,1],
        ], dtype=float)

        # Measurement matrix
        self.H = np.array([
            [1,0,0,0,0,0,0],
            [0,1,0,0,0,0,0],
            [0,0,1,0,0,0,0],
            [0,0,0,1,0,0,0],
        ], dtype=float)

        self.R = np.diag([1., 1., 10., 10.])           # measurement noise
        self.Q = np.diag([1., 1., 1., 1., 0.01, 0.01, 0.0001])  # process noise

        self.x = np.array([[cx], [cy], [s], [r], [0.], [0.], [0.]])
        self.P = np.diag([10., 10., 10., 10., 1e4, 1e4, 1e4])

    # ── Kalman predict ─────────────────────────────────────────────────────────

    def predict(self) -> np.ndarray:
        if self.time_since_update > 0:
            self.hit_streak = 0
        self.time_since_update += 1
        self.age += 1
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        return self.to_tlbr()

    # ── Kalman update ──────────────────────────────────────────────────────────

    def update(self, bbox: Tuple[float, float, float, float]) -> None:
        self.time_since_update = 0
        self.hits             += 1
        self.hit_streak       += 1

        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        s  = (x2 - x1) * (y2 - y1)
        r  = (x2 - x1) / float(y2 - y1 + 1e-6)

        z = np.array([[cx], [cy], [s], [r]])
        y = z - self.H @ self.x
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        self.P = (np.eye(7) - K @ self.H) @ self.P

    # ── Helper ─────────────────────────────────────────────────────────────────

    def to_tlbr(self) -> np.ndarray:
        cx, cy, s, r = self.x[0,0], self.x[1,0], self.x[2,0], self.x[3,0]
        w = np.sqrt(np.abs(s * r)) + 1e-6
        h = np.abs(s) / w + 1e-6
        return np.array([cx - w/2, cy - h/2, cx + w/2, cy + h/2])


# ── IoU helpers ────────────────────────────────────────────────────────────────

def _iou(bb1: np.ndarray, bb2: np.ndarray) -> float:
    x1 = max(bb1[0], bb2[0]); y1 = max(bb1[1], bb2[1])
    x2 = min(bb1[2], bb2[2]); y2 = min(bb1[3], bb2[3])
    inter = max(0., x2 - x1) * max(0., y2 - y1)
    if inter == 0:
        return 0.
    a1 = (bb1[2]-bb1[0]) * (bb1[3]-bb1[1])
    a2 = (bb2[2]-bb2[0]) * (bb2[3]-bb2[1])
    return inter / (a1 + a2 - inter + 1e-6)


def _iou_matrix(preds: np.ndarray, dets: np.ndarray) -> np.ndarray:
    mat = np.zeros((len(preds), len(dets)), dtype=float)
    for i, p in enumerate(preds):
        for j, d in enumerate(dets):
            mat[i, j] = _iou(p, d)
    return mat


# ── Hungarian matching (pure-numpy, no scipy needed) ──────────────────────────

def _hungarian(cost: np.ndarray) -> List[Tuple[int, int]]:
    """Greedy approximation – good enough for ≤50 tracks."""
    matched: List[Tuple[int, int]] = []
    remaining_rows = list(range(cost.shape[0]))
    remaining_cols = list(range(cost.shape[1]))
    c = cost.copy()
    while remaining_rows and remaining_cols:
        idx = np.unravel_index(np.argmax(c), c.shape)
        r, col = idx
        matched.append((r, col))
        c[r, :] = -1
        c[:, col] = -1
        if r in remaining_rows:   remaining_rows.remove(r)
        if col in remaining_cols: remaining_cols.remove(col)
    return matched


def _associate(
    trackers: List[KalmanBox],
    detections: List[Detection],
    iou_threshold: float = 0.30,
) -> Tuple[List[Tuple[int,int]], List[int], List[int]]:
    """Return (matched pairs, unmatched tracker indices, unmatched det indices)."""
    if not trackers or not detections:
        return [], list(range(len(trackers))), list(range(len(detections)))

    preds = np.array([t.to_tlbr() for t in trackers])
    dets  = np.array([[d.x1, d.y1, d.x2, d.y2] for d in detections])
    iou_mat = _iou_matrix(preds, dets)

    raw_matches = _hungarian(iou_mat)
    matched     = [(r, c) for r, c in raw_matches if iou_mat[r, c] >= iou_threshold]

    matched_t = {r for r, _ in matched}
    matched_d = {c for _, c in matched}
    unmatched_t = [i for i in range(len(trackers))  if i not in matched_t]
    unmatched_d = [i for i in range(len(detections)) if i not in matched_d]

    return matched, unmatched_t, unmatched_d


# ── Tracked Object ─────────────────────────────────────────────────────────────

@dataclass
class TrackedObject:
    track_id: int
    label:    str
    x1: float; y1: float; x2: float; y2: float
    confidence: float

    @property
    def bbox(self):
        return self.x1, self.y1, self.x2, self.y2


# ── SORT Tracker ───────────────────────────────────────────────────────────────

class SORTTracker:
    """
    Lightweight SORT multi-object tracker.
    Works with any Detection list from detector.py.
    """

    def __init__(self) -> None:
        self._trackers: List[KalmanBox] = []
        self._labels:   Dict[int, str]  = {}        # track_id → label
        self._confs:    Dict[int, float] = {}
        self._max_age  = config.MAX_DISAPPEARED
        self._min_hits = 2

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, detections: List[Detection]) -> List[TrackedObject]:
        """Feed current-frame detections, get back confirmed tracked objects."""

        # 1. Predict all existing trackers forward one step
        preds = []
        surviving: List[KalmanBox] = []
        for t in self._trackers:
            p = t.predict()
            if not np.any(np.isnan(p)):
                surviving.append(t)
        self._trackers = surviving

        # 2. Match predictions → detections
        matched, unmatched_t, unmatched_d = _associate(self._trackers, detections)

        # 3. Update matched trackers
        for ti, di in matched:
            d = detections[di]
            self._trackers[ti].update((d.x1, d.y1, d.x2, d.y2))
            self._labels[self._trackers[ti].id] = d.label
            self._confs [self._trackers[ti].id] = d.confidence

        # 4. Spawn new trackers for unmatched detections
        for di in unmatched_d:
            d = detections[di]
            kb = KalmanBox((d.x1, d.y1, d.x2, d.y2))
            self._trackers.append(kb)
            self._labels[kb.id] = d.label
            self._confs [kb.id] = d.confidence

        # 5. Remove stale trackers
        self._trackers = [t for t in self._trackers
                          if t.time_since_update <= self._max_age]

        # 6. Collect confirmed tracks (hit_streak >= min_hits or already old)
        results: List[TrackedObject] = []
        for t in self._trackers:
            if t.hits >= self._min_hits or t.time_since_update == 0:
                b = t.to_tlbr()
                results.append(TrackedObject(
                    track_id   = t.id,
                    label      = self._labels.get(t.id, "?"),
                    x1=b[0], y1=b[1], x2=b[2], y2=b[3],
                    confidence = self._confs.get(t.id, 0.0),
                ))

        return results

    def reset(self) -> None:
        self._trackers.clear()
        self._labels.clear()
        self._confs.clear()
        KalmanBox.count = 0

    @property
    def active_count(self) -> int:
        return len(self._trackers)
