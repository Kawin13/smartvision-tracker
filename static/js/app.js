/**
 * VisionTrack AI — Dashboard Controller
 *
 * Handles:
 *  • Live clock in header
 *  • /stats polling (1 s interval) → KPI cards + System Overview
 *  • Animated counter updates
 *  • Camera start / stop / reset
 *  • Video upload with XHR progress
 *  • FPS sparkline (pure Canvas)
 *  • Snapshot download
 *  • Fullscreen toggle
 *  • Toast notifications
 *
 * NO backend logic is modified here.
 * All API endpoints remain identical.
 */

"use strict";

/* ══════════════════════════════════════════════════════════════════════
   1. Clock
   ══════════════════════════════════════════════════════════════════════ */

function _updateClock() {
  const now   = new Date();
  const dateEl = document.getElementById("hdr-date");
  const timeEl = document.getElementById("hdr-time");
  if (dateEl) dateEl.textContent = now.toLocaleDateString(undefined,
    { weekday: "short", year: "numeric", month: "short", day: "numeric" });
  if (timeEl) timeEl.textContent = now.toLocaleTimeString(undefined,
    { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

setInterval(_updateClock, 1000);
_updateClock();

/* ══════════════════════════════════════════════════════════════════════
   2. Animated counter
   ══════════════════════════════════════════════════════════════════════ */

const _prevValues = {};

function _animateValue(id, raw) {
  const el = document.getElementById(id);
  if (!el) return;

  // If the value isn't numeric just set it directly
  const num = parseFloat(raw);
  if (isNaN(num)) { el.textContent = raw ?? "—"; return; }

  const from = parseFloat(_prevValues[id] ?? num);
  _prevValues[id] = num;

  const steps    = 12;
  const duration = 300; // ms
  let   step     = 0;

  const timer = setInterval(() => {
    step++;
    const t   = step / steps;
    const val = from + (num - from) * t;
    // Show integer if source is integer, else 1 decimal
    el.textContent = Number.isInteger(num) ? Math.round(val) : val.toFixed(1);
    if (step >= steps) { el.textContent = Number.isInteger(num) ? num : num.toFixed(1); clearInterval(timer); }
  }, duration / steps);
}

/* ══════════════════════════════════════════════════════════════════════
   3. FPS Sparkline (pure Canvas)
   ══════════════════════════════════════════════════════════════════════ */

const FPS_LEN   = 60;
const fpsHistory = new Array(FPS_LEN).fill(0);
const canvas     = document.getElementById("fps-chart");
const ctx        = canvas ? canvas.getContext("2d") : null;

function _pushFps(v) {
  fpsHistory.push(v);
  if (fpsHistory.length > FPS_LEN) fpsHistory.shift();
  _drawSparkline();
}

function _drawSparkline() {
  if (!ctx || !canvas) return;
  const W = canvas.offsetWidth  || 320;
  const H = canvas.offsetHeight || 90;
  canvas.width  = W;
  canvas.height = H;

  const max  = Math.max(...fpsHistory, 1);
  const step = W / (FPS_LEN - 1);

  ctx.clearRect(0, 0, W, H);

  // Grid
  ctx.strokeStyle = "rgba(22,32,64,.8)";
  ctx.lineWidth   = 1;
  [0.25, 0.5, 0.75].forEach(f => {
    const y = Math.round(H * (1 - f)) + 0.5;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
  });

  // Filled area
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0,   "rgba(59,130,246,.40)");
  grad.addColorStop(0.5, "rgba(6,182,212,.18)");
  grad.addColorStop(1,   "rgba(6,182,212,.00)");
  ctx.fillStyle = grad;

  ctx.beginPath();
  ctx.moveTo(0, H);
  fpsHistory.forEach((v, i) => {
    ctx.lineTo(i * step, H - (v / max) * H * 0.88);
  });
  ctx.lineTo((FPS_LEN - 1) * step, H);
  ctx.closePath();
  ctx.fill();

  // Line
  const lineGrad = ctx.createLinearGradient(0, 0, W, 0);
  lineGrad.addColorStop(0,   "#3b82f6");
  lineGrad.addColorStop(1,   "#06b6d4");
  ctx.strokeStyle = lineGrad;
  ctx.lineWidth   = 2;
  ctx.lineJoin    = "round";
  ctx.beginPath();
  fpsHistory.forEach((v, i) => {
    const x = i * step;
    const y = H - (v / max) * H * 0.88;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Dot at end
  const lastX = (FPS_LEN - 1) * step;
  const lastY = H - (fpsHistory[FPS_LEN - 1] / max) * H * 0.88;
  ctx.beginPath();
  ctx.arc(lastX, lastY, 3, 0, Math.PI * 2);
  ctx.fillStyle = "#06b6d4";
  ctx.fill();
}

/* ══════════════════════════════════════════════════════════════════════
   4. Toast
   ══════════════════════════════════════════════════════════════════════ */

let _toastTimer = null;

function showToast(msg, type = "info") {
  const t = document.getElementById("toast");
  if (!t) return;
  t.textContent = msg;
  t.className   = `toast show${type !== "info" ? " " + type : ""}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove("show"), 3800);
}

/* ══════════════════════════════════════════════════════════════════════
   5. UI helpers
   ══════════════════════════════════════════════════════════════════════ */

function _setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val ?? "—";
}

function _formatSource(src) {
  if (src === null || src === undefined) return "—";
  if (src === "0" || src === 0 || src === 0) return "Webcam";
  const parts = String(src).replace(/\\/g, "/").split("/");
  const name  = parts[parts.length - 1];
  return name.length > 16 ? name.slice(0, 14) + "…" : name;
}

function _formatSourceFull(src) {
  if (src === null || src === undefined) return "—";
  if (src === "0" || src === 0)          return "Webcam";
  const parts = String(src).replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || String(src);
}

function _setButtonsRunning(isRunning) {
  const s = document.getElementById("btn-start-cam");
  const p = document.getElementById("btn-stop");
  if (s) s.disabled = isRunning;
  if (p) p.disabled = !isRunning;
}

/* ══════════════════════════════════════════════════════════════════════
   6. Stats polling
   ══════════════════════════════════════════════════════════════════════ */

let _prevStatus = null;

async function _pollStats() {
  try {
    const res = await fetch("/stats");
    if (!res.ok) return;
    const d   = await res.json();

    const isRunning = d.status === "running";
    const isError   = d.status === "error";

    // ── KPI cards ──────────────────────────────────────────────────────
    _animateValue("stat-fps",     parseFloat(d.fps)     || 0);
    _animateValue("stat-objects", parseInt(d.objects)   || 0);
    _animateValue("stat-tracks",  parseInt(d.tracks)    || 0);
    _setText("stat-source", _formatSource(d.source));

    // ── FPS sparkline ───────────────────────────────────────────────────
    _pushFps(parseFloat(d.fps) || 0);

    // ── Header status pill ──────────────────────────────────────────────
    const pill     = document.getElementById("hdr-status-pill");
    const dot      = document.getElementById("hdr-dot");
    const pillText = document.getElementById("hdr-status-text");

    if (pill && pillText) {
      if (isRunning) {
        pill.className    = "header-status-pill";
        pillText.textContent = "Monitoring Active";
      } else if (isError) {
        pill.className    = "header-status-pill error";
        pillText.textContent = "Error";
      } else {
        pill.className    = "header-status-pill idle";
        pillText.textContent = "Standby";
      }
    }

    // ── Live badge ──────────────────────────────────────────────────────
    const liveBadge = document.getElementById("live-badge");
    if (liveBadge) liveBadge.classList.toggle("active", isRunning);

    // ── Video overlay ───────────────────────────────────────────────────
    const overlay = document.getElementById("video-overlay");
    if (overlay) overlay.classList.toggle("hidden", isRunning);

    // ── Overview banner ─────────────────────────────────────────────────
    const banner   = document.getElementById("overview-banner");
    const bannerTx = document.getElementById("banner-text");
    const ovDot    = document.getElementById("overview-dot");

    if (banner && bannerTx) {
      if (isRunning) {
        banner.className    = "overview-status-banner";
        bannerTx.textContent = "🟢  Monitoring Active";
        if (ovDot) ovDot.className = "overview-status-dot active";
      } else if (isError) {
        banner.className    = "overview-status-banner error";
        bannerTx.textContent = "⚠  " + (d.error || "Error occurred");
        if (ovDot) ovDot.className = "overview-status-dot error";
      } else {
        banner.className    = "overview-status-banner idle";
        bannerTx.textContent = "⏸  System on Standby";
        if (ovDot) ovDot.className = "overview-status-dot";
      }
    }

    // ── Overview rows ───────────────────────────────────────────────────
    _setText("ov-source",  _formatSourceFull(d.source) || "No source");
    _setText("ov-objects", isRunning ? `${d.objects ?? 0} detected` : "—");
    _setText("ov-tracks",  isRunning ? `${d.tracks  ?? 0} active`   : "—");
    _setText("ov-fps",     isRunning ? `${parseFloat(d.fps).toFixed(1)} fps` : "—");
    _setText("ov-updated", new Date().toLocaleTimeString());

    // ── Button state ────────────────────────────────────────────────────
    _setButtonsRunning(isRunning);

    // ── Status-change toast ─────────────────────────────────────────────
    if (d.status !== _prevStatus) {
      if (isError && d.error) showToast("⚠ " + d.error, "error");
      _prevStatus = d.status;
    }

  } catch (_) { /* swallow network blips */ }
}

/* ══════════════════════════════════════════════════════════════════════
   7. Camera / source controls (call existing Flask APIs unchanged)
   ══════════════════════════════════════════════════════════════════════ */

async function startCamera() {
  showToast("Starting camera…");
  try {
    const res  = await fetch("/start_camera", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ index: 0 }),
    });
    const data = await res.json();
    if (data.success) {
      showToast("✓ Camera started", "success");
      _refreshStream();
    } else {
      showToast("✗ " + (data.message || "Camera unavailable"), "error");
    }
  } catch (err) {
    showToast("✗ Network error", "error");
  }
}

async function stopCamera() {
  try {
    const res  = await fetch("/stop_camera", { method: "POST" });
    const data = await res.json();
    showToast(data.success ? "■ Source stopped" : "✗ " + data.message,
              data.success ? "info" : "error");
  } catch {
    showToast("✗ Network error", "error");
  }
}

async function resetSystem() {
  try {
    const res  = await fetch("/reset", { method: "POST" });
    const data = await res.json();
    showToast(data.success ? "↺ System reset" : "✗ " + data.message,
              data.success ? "info" : "error");
    if (data.success) _refreshStream();
  } catch {
    showToast("✗ Network error", "error");
  }
}

/* ══════════════════════════════════════════════════════════════════════
   8. Video upload
   ══════════════════════════════════════════════════════════════════════ */

function uploadVideo(input) {
  const file = input.files[0];
  if (!file) return;

  const wrap  = document.getElementById("upload-bar-wrap");
  const bar   = document.getElementById("upload-bar");
  const label = document.getElementById("upload-label");

  wrap.style.display  = "block";
  bar.style.width     = "0%";
  label.textContent   = "Uploading…";

  const fd  = new FormData();
  fd.append("video", file);
  const xhr = new XMLHttpRequest();

  xhr.upload.addEventListener("progress", e => {
    if (!e.lengthComputable) return;
    const pct = Math.round((e.loaded / e.total) * 100);
    bar.style.width   = pct + "%";
    label.textContent = `Uploading… ${pct}%`;
  });

  xhr.addEventListener("load", () => {
    wrap.style.display = "none";
    try {
      const data = JSON.parse(xhr.responseText);
      if (data.success) {
        showToast("✓ " + (data.message || "Video loaded"), "success");
        _refreshStream();
      } else {
        showToast("✗ " + (data.message || "Upload failed"), "error");
      }
    } catch {
      showToast("✗ Unexpected server response", "error");
    }
    input.value = "";
  });

  xhr.addEventListener("error", () => {
    wrap.style.display = "none";
    showToast("✗ Upload failed (network error)", "error");
    input.value = "";
  });

  xhr.open("POST", "/upload_video");
  xhr.send(fd);
}

/* ══════════════════════════════════════════════════════════════════════
   9. Snapshot
   ══════════════════════════════════════════════════════════════════════ */

function takeSnapshot() {
  const img = document.getElementById("video-stream");
  if (!img || !img.src) { showToast("No stream to capture", "error"); return; }

  const cvs = document.createElement("canvas");
  cvs.width  = img.naturalWidth  || img.width;
  cvs.height = img.naturalHeight || img.height;
  const c = cvs.getContext("2d");
  try {
    c.drawImage(img, 0, 0);
    const a    = document.createElement("a");
    a.download = `visiontrack-snapshot-${Date.now()}.jpg`;
    a.href     = cvs.toDataURL("image/jpeg", 0.92);
    a.click();
    showToast("✓ Snapshot saved", "success");
  } catch {
    showToast("Snapshot blocked by browser (CORS)", "error");
  }
}

/* ══════════════════════════════════════════════════════════════════════
   10. Fullscreen
   ══════════════════════════════════════════════════════════════════════ */

function toggleFullscreen() {
  const wrapper = document.getElementById("video-wrapper");
  if (!wrapper) return;
  if (!document.fullscreenElement) {
    wrapper.requestFullscreen().catch(() => showToast("Fullscreen unavailable", "error"));
  } else {
    document.exitFullscreen();
  }
}

/* ══════════════════════════════════════════════════════════════════════
   11. Stream refresh helper
   ══════════════════════════════════════════════════════════════════════ */

function _refreshStream() {
  const img = document.getElementById("video-stream");
  if (img) img.src = "/video_feed?" + Date.now();
}

/* ══════════════════════════════════════════════════════════════════════
   12. Init
   ══════════════════════════════════════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", () => {
  _drawSparkline();
  _pollStats();
  setInterval(_pollStats, 1000);

  // Auto-retry stream on error
  const streamImg = document.getElementById("video-stream");
  if (streamImg) {
    streamImg.addEventListener("error", () => setTimeout(_refreshStream, 3000));
  }

  // Redraw sparkline on resize
  window.addEventListener("resize", _drawSparkline);
});
