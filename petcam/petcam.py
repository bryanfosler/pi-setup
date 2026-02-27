#!/usr/bin/env python3
"""
petcam.py — Motion-triggered AI pet camera with live stream
Watches a USB webcam, detects motion, sends frame to moondream2 for
description, and pushes a notification (with image) to your phone via ntfy.sh.
Also serves a live MJPEG stream at http://bryanfoslerpi5.local:8080/stream
"""

import cv2
import base64
import time
import logging
import requests
import threading
import numpy as np
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

# ─── CONFIG ─────────────────────────────────────────────────────────────────

# ntfy.sh topic — change this to something unique (it's your "channel")
# Subscribe to this topic in the ntfy iOS app
NTFY_TOPIC = "bryan-petcam-302"

# Camera source — either an integer device index (0 = /dev/video0) or a URL.
# GoPro Hero 12 via USB: set GOPRO_MODE = True and plug in via USB.
# Regular webcam: set GOPRO_MODE = False, CAMERA_DEVICE = 0.
GOPRO_MODE = True
GOPRO_IP = "172.23.194.51"   # GoPro's USB IP (found via scan)
CAMERA_DEVICE = "udp://@:8554"  # GoPro streams here when in webcam mode

# Motion sensitivity — number of changed pixels to trigger analysis
# Lower = more sensitive. Start at 5000, tune up if too many false triggers.
MOTION_THRESHOLD = 5000

# Minimum seconds between notifications (prevents spam during sustained motion)
COOLDOWN_SECONDS = 60

# Ollama settings
OLLAMA_URL = "http://localhost:11434"
VISION_MODEL = "moondream"
VISION_PROMPT = (
    "Describe what you see in this image in one or two sentences. "
    "Specifically mention if there is a pet, dog, cat, or person, and what they are doing."
)

# Only notify if the description contains these keywords (case-insensitive).
# Empty list = notify on all motion.
NOTIFY_KEYWORDS = ["dog", "cat", "pet", "animal", "person", "someone"]

# Live stream port — view at http://bryanfoslerpi5.local:8080/stream
STREAM_PORT = 8080

# ─── LOGGING ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── SHARED FRAME STATE ──────────────────────────────────────────────────────

# Latest frame shared between the capture loop and the stream server
_latest_frame = None
_frame_lock = threading.Lock()


def set_latest_frame(frame):
    global _latest_frame
    with _frame_lock:
        _latest_frame = frame.copy()


def get_latest_frame():
    with _frame_lock:
        return _latest_frame.copy() if _latest_frame is not None else None


# ─── MJPEG STREAM SERVER ─────────────────────────────────────────────────────

class StreamHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress per-request HTTP logs

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while True:
                    frame = get_latest_frame()
                    if frame is None:
                        time.sleep(0.1)
                        continue
                    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    jpg = buffer.tobytes()
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                    self.wfile.write(jpg)
                    self.wfile.write(b"\r\n")
                    time.sleep(0.1)  # ~10 fps
            except (BrokenPipeError, ConnectionResetError):
                pass  # client disconnected

        elif path == "/snapshot":
            frame = get_latest_frame()
            if frame is None:
                self.send_response(503)
                self.end_headers()
                return
            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            jpg = buffer.tobytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpg)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(jpg)

        elif path == "/" or path == "/index.html":
            html = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pet Cam</title>
  <style>
    body { margin: 0; background: #111; display: flex; flex-direction: column;
           align-items: center; justify-content: center; min-height: 100vh; }
    img  { max-width: 100%; border-radius: 8px; }
    p    { color: #888; font-family: sans-serif; font-size: 13px; margin-top: 8px; }
  </style>
</head>
<body>
  <img id="cam" alt="Pet cam live feed">
  <p>bryanfoslerpi5 &mdash; live</p>
  <script>
    var img = document.getElementById('cam');
    function refresh() {
      var next = new Image();
      next.onload = function() { img.src = next.src; };
      next.src = '/snapshot?' + Date.now();
    }
    refresh();
    setInterval(refresh, 500);
  </script>
</body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.end_headers()


def start_stream_server():
    server = ThreadingHTTPServer(("0.0.0.0", STREAM_PORT), StreamHandler)
    log.info(f"Live stream → http://bryanfoslerpi5.local:{STREAM_PORT}")
    server.serve_forever()


# ─── CORE FUNCTIONS ──────────────────────────────────────────────────────────

def encode_frame(frame):
    """JPEG-encode a cv2 frame and return as base64 string."""
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buffer.tobytes()).decode("utf-8")


def describe_frame(frame):
    """Send frame to moondream2 via Ollama and return the text description."""
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": VISION_MODEL,
                "prompt": VISION_PROMPT,
                "images": [encode_frame(frame)],
                "stream": False,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("response", "").strip()
    except requests.exceptions.Timeout:
        log.warning("Ollama timed out — model may still be loading")
        return None
    except Exception as e:
        log.error(f"Ollama error: {e}")
        return None


def should_notify(description):
    """Return True if description contains any of the notify keywords."""
    if not NOTIFY_KEYWORDS:
        return True
    lower = description.lower()
    return any(kw in lower for kw in NOTIFY_KEYWORDS)


def send_notification(frame, description):
    """Push notification to phone via ntfy.sh with image attached."""
    try:
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        image_bytes = buffer.tobytes()

        timestamp = datetime.now().strftime("%I:%M %p")
        requests.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=image_bytes,
            headers={
                "Title": f"Pet cam — {timestamp}",
                "Message": description[:200],
                "Filename": "detection.jpg",
                "Content-Type": "image/jpeg",
                "Priority": "default",
            },
            timeout=10,
        )
        log.info(f"Notification sent: {description[:80]}...")
    except Exception as e:
        log.error(f"ntfy.sh error: {e}")


def detect_motion(prev_frame, curr_frame):
    """Return number of changed pixels between two grayscale frames."""
    diff = cv2.absdiff(prev_frame, curr_frame)
    _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    return cv2.countNonZero(thresh)


# ─── GOPRO USB ───────────────────────────────────────────────────────────────

def gopro_start():
    """Tell the GoPro to start streaming webcam video over USB."""
    url = f"http://{GOPRO_IP}:8080/gopro/webcam/start"
    for attempt in range(5):
        try:
            r = requests.get(url, timeout=5)
            data = r.json()
            if data.get("error", 1) == 0:
                log.info(f"GoPro webcam started (status={data.get('status')})")
                return True
        except Exception as e:
            log.warning(f"GoPro start attempt {attempt+1} failed: {e}")
        time.sleep(2)
    return False


def gopro_keepalive():
    """GoPro stops streaming if it doesn't receive a keepalive every 2.5s."""
    url = f"http://{GOPRO_IP}:8080/gopro/webcam/keepalive"
    while True:
        try:
            requests.get(url, timeout=2)
        except Exception:
            pass
        time.sleep(2)


# ─── MAIN LOOP ────────────────────────────────────────────────────────────────

def main():
    log.info(f"Starting petcam (camera={CAMERA_DEVICE}, threshold={MOTION_THRESHOLD})")
    log.info(f"Notifications → ntfy.sh/{NTFY_TOPIC}")
    log.info(f"Vision model  → {VISION_MODEL} via {OLLAMA_URL}")

    # Start MJPEG stream server in background thread
    stream_thread = threading.Thread(target=start_stream_server, daemon=True)
    stream_thread.start()

    if GOPRO_MODE:
        log.info(f"GoPro mode — starting webcam stream from {GOPRO_IP}...")
        if not gopro_start():
            raise RuntimeError("Could not start GoPro webcam stream. Is it connected via USB?")
        keepalive_thread = threading.Thread(target=gopro_keepalive, daemon=True)
        keepalive_thread.start()
        time.sleep(1)  # brief pause for stream to stabilise
        cap = cv2.VideoCapture(CAMERA_DEVICE + "?fifo_size=5000000&overrun_nonfatal=1", cv2.CAP_FFMPEG)
    else:
        cap = cv2.VideoCapture(CAMERA_DEVICE)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 2560)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1440)

    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera source: {CAMERA_DEVICE}")

    ret, frame = cap.read()
    if not ret:
        raise RuntimeError("Could not read first frame from camera.")

    set_latest_frame(frame)
    prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    prev_gray = cv2.GaussianBlur(prev_gray, (21, 21), 0)

    last_notification = 0
    analysis_in_progress = threading.Event()
    log.info("Watching for motion...")

    def analyze_and_notify(frame, timestamp):
        """Run in a background thread — never blocks the capture loop."""
        description = describe_frame(frame)
        if not description:
            log.info("No description returned, skipping notification")
        else:
            log.info(f"Description: {description}")
            if should_notify(description):
                send_notification(frame, description)
        analysis_in_progress.clear()

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                log.warning("Failed to read frame — retrying...")
                time.sleep(1)
                continue

            # Always update the shared frame for the live stream
            set_latest_frame(frame)

            curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            curr_gray = cv2.GaussianBlur(curr_gray, (21, 21), 0)

            changed_pixels = detect_motion(prev_gray, curr_gray)
            prev_gray = curr_gray

            if changed_pixels < MOTION_THRESHOLD:
                time.sleep(0.05)
                continue

            log.info(f"Motion detected ({changed_pixels} px changed)")

            now = time.time()
            if now - last_notification < COOLDOWN_SECONDS:
                remaining = int(COOLDOWN_SECONDS - (now - last_notification))
                log.info(f"Cooldown active — {remaining}s remaining")
                time.sleep(0.05)
                continue

            if analysis_in_progress.is_set():
                log.info("Analysis already in progress — skipping")
                time.sleep(0.05)
                continue

            last_notification = time.time()
            analysis_in_progress.set()
            log.info("Sending frame to moondream for analysis (background)...")
            t = threading.Thread(target=analyze_and_notify, args=(frame.copy(), now), daemon=True)
            t.start()

            time.sleep(0.05)

    except KeyboardInterrupt:
        log.info("Shutting down petcam.")
    finally:
        cap.release()


if __name__ == "__main__":
    main()
