# 🎯 Real-Time Object Detection & Tracking System

A production-ready, CPU-friendly object detection and tracking dashboard built with **YOLOv8**, **OpenCV**, **SORT/Kalman-Filter tracking**, and **Flask**.

---

## ✨ Features

| Feature | Details |
|---|---|
| Detection | YOLOv8n – 8 COCO classes (person, car, bus, truck, motorcycle, bicycle, dog, cat) |
| Tracking | SORT with Kalman filter – stable IDs across frames |
| Input | Webcam (`cv2.VideoCapture(0)`) **or** uploaded video file |
| Output | Annotated MJPEG stream with bounding boxes, class labels, confidence %, track IDs |
| Dashboard | Modern dark-mode web UI with live FPS chart and stats |
| Deployment | Local Windows / Render / Railway |

---

## 🗂 Project Structure

```
object-tracking-system/
├── app.py               ← Flask app & API routes
├── detector.py          ← YOLOv8 wrapper (thread-safe)
├── tracker.py           ← SORT multi-object tracker (pure Python)
├── video_manager.py     ← Background capture & processing thread
├── config.py            ← All tuneable settings
├── requirements.txt
├── Procfile             ← Render / Railway start command
├── render.yaml          ← Render deployment spec
├── .env.example         ← Environment variable template
├── templates/
│   └── index.html       ← Dashboard HTML
├── static/
│   ├── css/style.css    ← Responsive dark-mode styles
│   └── js/app.js        ← Dashboard controller & FPS chart
├── uploads/             ← Uploaded video files (auto-created)
└── models/              ← Place yolov8n.pt here (auto-downloaded)
```

---

## 🚀 Quick Start — Local (Windows 10/11)

### 1. Clone / extract the project
```
cd object-tracking-system
```

### 2. Create a virtual environment
```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate    # macOS / Linux
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```
> The first run will automatically download `yolov8n.pt` (~6 MB) from Ultralytics.

### 4. Run
```bash
python app.py
```

Open **http://localhost:5000** in your browser.

---

## 🌐 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/` | Dashboard UI |
| `GET`  | `/video_feed` | MJPEG stream |
| `GET`  | `/stats` | Live JSON stats |
| `GET`  | `/system_status` | Full system info |
| `POST` | `/start_camera` | Start webcam `{"index": 0}` |
| `POST` | `/stop_camera` | Stop current source |
| `POST` | `/upload_video` | Upload video file (multipart) |
| `POST` | `/reset` | Reset system & tracker |

---

## ⚙️ Configuration (`config.py` / `.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5000` | Flask port |
| `CONF_THRESH` | `0.40` | Detection confidence threshold |
| `IOU_THRESH` | `0.45` | NMS IoU threshold |
| `INFER_SIZE` | `640` | YOLOv8 inference resolution |
| `FRAME_WIDTH` | `640` | Output frame width |
| `FRAME_HEIGHT` | `480` | Output frame height |
| `JPEG_QUALITY` | `80` | Stream JPEG quality (1-100) |
| `STREAM_FPS` | `30` | Target stream frame rate |
| `MAX_DISAPPEARED` | `30` | Frames before track is dropped |

Copy `.env.example` → `.env` and edit as needed.

---

## ☁️ Deploy on Render (Free Tier)

1. Push the project to a GitHub repo.
2. Go to [render.com](https://render.com) → **New Web Service** → connect repo.
3. Render will detect `render.yaml` automatically.
4. Click **Deploy**.

> **Note:** Webcam is not available on cloud servers. Upload a video file to use the system remotely.

---

## 🚂 Deploy on Railway

1. Push to GitHub.
2. Import the repo in [railway.app](https://railway.app).
3. Railway detects `Procfile` automatically.
4. Set environment variables if needed.

---

## 🛠 Troubleshooting

| Problem | Fix |
|---------|-----|
| Camera not found | Try a different index (`{"index": 1}`). On some systems the webcam is index 1. |
| Slow FPS | Lower `INFER_SIZE` to `320` or `FRAME_WIDTH/HEIGHT` to `480x360`. |
| Model not loading | Ensure internet access on first run so `yolov8n.pt` can be downloaded. |
| Port in use | Change `PORT=5001` in `.env`. |
| Upload fails | Check `MAX_CONTENT_MB` (default 200 MB) and ensure `uploads/` folder exists. |

---

## 📦 Dependencies

```
flask               ← Web framework
opencv-python-headless ← Computer vision (no GUI required)
ultralytics         ← YOLOv8
numpy               ← Numerical arrays
pillow              ← Image utilities
scipy               ← Scientific computing (optional, used by SORT extensions)
gunicorn            ← Production WSGI server
python-dotenv       ← .env file support
```

---

## 🏗 Architecture

```
Browser
  │  (MJPEG stream + REST API)
  ▼
Flask (app.py)
  │
  ├── GET /video_feed ──► VideoManager.generate_frames()
  │                            │
  │              ┌─────────────┘
  │              │  Background thread
  │              ▼
  │         OpenCV VideoCapture
  │              │
  │              ▼
  │         YOLODetector.detect()   (detector.py)
  │              │  YOLOv8n inference
  │              ▼
  │         SORTTracker.update()    (tracker.py)
  │              │  Kalman filter + Hungarian matching
  │              ▼
  │         Draw annotations (video_manager.py)
  │              │
  │              ▼
  │         JPEG encode → stored in memory
  │
  └── GET /stats ──► VideoManager.stats  (JSON)
```

---

## License

MIT – free for personal and commercial use.
