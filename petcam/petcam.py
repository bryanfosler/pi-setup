#!/usr/bin/env python3
"""
petcam.py — Motion-triggered AI pet camera
Watches a USB webcam, detects motion, sends frame to moondream2 for
description, and pushes a notification (with image) to your phone via ntfy.sh
"""

import cv2
import base64
import time
import logging
import requests
import numpy as np
from datetime import datetime

# ─── CONFIG ─────────────────────────────────────────────────────────────────

# ntfy.sh topic — change this to something unique (it's your "channel")
# Subscribe to this topic in the ntfy iOS app
NTFY_TOPIC = "bryanpi-petcam"

# Camera — 0 = first USB camera (/dev/video0). Try 1 if 0 doesn't work.
CAMERA_DEVICE = 0

# Motion sensitivity — number of changed pixels to trigger analysis
# Lower = more sensitive. Start at 5000, tune up if too many false triggers.
MOTION_THRESHOLD = 5000

# Minimum seconds between notifications (prevents spam during sustained motion)
COOLDOWN_SECONDS = 60

# Ollama settings
OLLAMA_URL = "http://localhost:11434"
VISION_MODEL = "moondream2"
VISION_PROMPT = (
    "Describe what you see in this image in one or two sentences. "
    "Specifically mention if there is a pet, dog, cat, or person, and what they are doing."
)

# Only notify if the description contains these keywords (case-insensitive).
# Empty list = notify on all motion.
NOTIFY_KEYWORDS = ["dog", "cat", "pet", "animal", "person", "someone"]

# ─── LOGGING ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

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


# ─── MAIN LOOP ────────────────────────────────────────────────────────────────

def main():
    log.info(f"Starting petcam (camera={CAMERA_DEVICE}, threshold={MOTION_THRESHOLD})")
    log.info(f"Notifications → ntfy.sh/{NTFY_TOPIC}")
    log.info(f"Vision model  → {VISION_MODEL} via {OLLAMA_URL}")

    cap = cv2.VideoCapture(CAMERA_DEVICE)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera device {CAMERA_DEVICE}. "
                           "Check it's plugged in and try CAMERA_DEVICE = 1.")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    ret, frame = cap.read()
    if not ret:
        raise RuntimeError("Could not read first frame from camera.")

    prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    prev_gray = cv2.GaussianBlur(prev_gray, (21, 21), 0)

    last_notification = 0
    log.info("Watching for motion...")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                log.warning("Failed to read frame — retrying...")
                time.sleep(1)
                continue

            curr_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            curr_gray = cv2.GaussianBlur(curr_gray, (21, 21), 0)

            changed_pixels = detect_motion(prev_gray, curr_gray)
            prev_gray = curr_gray

            if changed_pixels < MOTION_THRESHOLD:
                time.sleep(0.1)
                continue

            log.info(f"Motion detected ({changed_pixels} px changed)")

            now = time.time()
            if now - last_notification < COOLDOWN_SECONDS:
                remaining = int(COOLDOWN_SECONDS - (now - last_notification))
                log.info(f"Cooldown active — {remaining}s remaining")
                time.sleep(0.5)
                continue

            log.info("Sending frame to moondream2 for analysis...")
            description = describe_frame(frame)

            if not description:
                log.info("No description returned, skipping notification")
                continue

            log.info(f"Description: {description}")

            if should_notify(description):
                send_notification(frame, description)
                last_notification = time.time()
            else:
                log.info("Description didn't match notify keywords — skipping")

            time.sleep(0.1)

    except KeyboardInterrupt:
        log.info("Shutting down petcam.")
    finally:
        cap.release()


if __name__ == "__main__":
    main()
