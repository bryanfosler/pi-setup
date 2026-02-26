# Pet Cam — Reference Guide
*bryanfoslerpi5 — updated 02.26.2026*

---

## How It Works

```
USB Webcam
    ↓  reads frames continuously (OpenCV)
    ↓  compares each frame to the previous one
Motion detected (pixel diff > threshold)
    ↓
Frame sent to moondream2 (Ollama vision model)
    ↓  "A dog is lying on the couch near the window..."
Keywords matched? (dog, cat, pet, person...)
    ↓
ntfy.sh push notification → 📱 your phone
    (image attached, description as message)
    ↓
60 second cooldown
```

---

## First-Time Setup

### 1. Set your ntfy topic
Edit `/usr/local/lib/petcam/petcam.py` and change:
```python
NTFY_TOPIC = "bryanpi-petcam"   # ← make this something unique to you
```
Then restart: `sudo systemctl restart petcam`

### 2. Install ntfy on your iPhone
- App Store → search **ntfy**
- Open app → **+** → enter your topic name (must match `NTFY_TOPIC` exactly)

### 3. Test the notification pipeline
```bash
# Send a test notification from the Pi
curl -d "Test from Pi" ntfy.sh/YOUR_TOPIC_NAME

# With an image
curl -T /path/to/image.jpg \
  -H "Title: Test" \
  -H "Message: Hello from Pi" \
  ntfy.sh/YOUR_TOPIC_NAME
```

---

## Configuration

All config is at the top of `/usr/local/lib/petcam/petcam.py`:

```python
NTFY_TOPIC = "bryanpi-petcam"    # your ntfy channel name
CAMERA_DEVICE = 0                 # 0 = /dev/video0, try 1 if camera not found
MOTION_THRESHOLD = 5000           # changed pixels to trigger (lower = more sensitive)
COOLDOWN_SECONDS = 60             # min seconds between notifications
VISION_MODEL = "moondream2"       # Ollama vision model
NOTIFY_KEYWORDS = ["dog", "cat", "pet", "animal", "person", "someone"]
                                  # only notify if description contains these words
                                  # set to [] to notify on all motion
```

After any config change:
```bash
sudo systemctl restart petcam
```

---

## Tuning Motion Sensitivity

| `MOTION_THRESHOLD` | Behavior |
|--------------------|---------|
| `1000` | Very sensitive — triggers on shadows, light changes |
| `5000` | Default — good for pets moving around |
| `15000` | Less sensitive — only large movements |

Watch the logs to see how many pixels are changing in your environment:
```bash
journalctl -u petcam -f
```
You'll see lines like: `Motion detected (8432 px changed)` — use this to calibrate.

---

## Service Management

```bash
# Status and recent logs
sudo systemctl status petcam

# Live log (see motion events and AI descriptions in real time)
journalctl -u petcam -f

# Restart (required after config changes)
sudo systemctl restart petcam

# Stop / Start
sudo systemctl stop petcam
sudo systemctl start petcam

# Disable autostart
sudo systemctl disable petcam
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Could not open camera device 0` | Try `CAMERA_DEVICE = 1` in config; confirm webcam is plugged in |
| No notifications arriving | Test with `curl -d "test" ntfy.sh/YOUR_TOPIC` from Pi |
| Too many false notifications | Raise `MOTION_THRESHOLD` (try 10000–20000) |
| No notifications despite motion | Lower `MOTION_THRESHOLD`; check `NOTIFY_KEYWORDS` isn't filtering too aggressively |
| `Ollama timed out` in logs | moondream2 may still be loading; wait 30s and it should recover |
| Notifications flood during sustained motion | Raise `COOLDOWN_SECONDS` (try 120 or 300) |

---

## Find Your Camera Device

```bash
# List connected video devices
ls /dev/video*

# Get device info
v4l2-ctl --list-devices

# Test camera capture (saves a test frame)
fswebcam -d /dev/video0 -r 640x480 /tmp/test.jpg
# Then scp to Mac to view:
# scp bfosler@bryanfoslerpi5.local:/tmp/test.jpg ~/Desktop/
```

---

## Upgrading to Pi Camera Module Later

If you ever switch to a Pi Camera Module 3:
- Install `picamera2`: `sudo apt install python3-picamera2`
- Replace the `cv2.VideoCapture()` section in `petcam.py` with `Picamera2()`
- Pi Camera has better low-light performance (useful for night pet-watching)
- Cost: ~$25 for Module 3, ~$35 for Module 3 Wide
