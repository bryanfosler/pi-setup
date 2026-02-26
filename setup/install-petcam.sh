#!/bin/bash
# install-petcam.sh
# Installs petcam dependencies, pulls the vision model, and sets up the service.
# Run after install-ollama.sh.
#
# Usage: bash setup/install-petcam.sh

set -e

VENV_DIR="/opt/petcam-venv"
SCRIPT_DIR="/usr/local/lib/petcam"

echo "==> Checking Ollama is reachable..."
if ! curl -sf http://localhost:11434/api/tags > /dev/null; then
  echo "ERROR: Ollama doesn't appear to be running."
  echo "Run setup/install-ollama.sh first."
  exit 1
fi
echo "    Ollama is up."

echo ""
echo "==> Installing system dependencies..."
sudo apt-get install -y python3-venv python3-pip libgl1 libglib2.0-0

echo ""
echo "==> Creating Python virtual environment at $VENV_DIR..."
sudo python3 -m venv $VENV_DIR
sudo $VENV_DIR/bin/pip install --upgrade pip

echo ""
echo "==> Installing Python packages (OpenCV, requests)..."
sudo $VENV_DIR/bin/pip install opencv-python-headless requests numpy

echo ""
echo "==> Pulling moondream2 vision model (~1.8GB, may take a few minutes)..."
ollama pull moondream2

echo ""
echo "==> Installing petcam script..."
sudo mkdir -p $SCRIPT_DIR
sudo cp "$(dirname "$0")/../petcam/petcam.py" $SCRIPT_DIR/petcam.py
sudo chmod +x $SCRIPT_DIR/petcam.py

echo ""
echo "==> Installing systemd service..."
sudo cp "$(dirname "$0")/../systemd/petcam.service" /etc/systemd/system/
sudo sed -i "s|__VENV_DIR__|$VENV_DIR|g" /etc/systemd/system/petcam.service
sudo sed -i "s|__SCRIPT_DIR__|$SCRIPT_DIR|g" /etc/systemd/system/petcam.service
sudo sed -i "s|__USER__|$USER|g" /etc/systemd/system/petcam.service

sudo systemctl daemon-reload
sudo systemctl enable petcam
sudo systemctl start petcam

echo ""
echo "========================================"
echo "  Petcam installed successfully"
echo "========================================"
echo ""
echo "  Before it's useful — two things to do:"
echo ""
echo "  1. Set your ntfy topic:"
echo "     Edit /usr/local/lib/petcam/petcam.py"
echo "     Change NTFY_TOPIC = \"bryanpi-petcam\" to something unique"
echo "     Then: sudo systemctl restart petcam"
echo ""
echo "  2. Subscribe in the ntfy iOS app:"
echo "     App Store: search 'ntfy'"
echo "     Add subscription → topic name must match NTFY_TOPIC above"
echo ""
echo "  Test camera detection:"
echo "     sudo systemctl status petcam"
echo "     journalctl -u petcam -f"
echo ""
echo "  Test ntfy manually:"
echo "     curl -d 'test message' ntfy.sh/YOUR_TOPIC_NAME"
