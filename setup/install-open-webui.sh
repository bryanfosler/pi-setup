#!/bin/bash
# install-open-webui.sh
# Installs Open-WebUI — a browser-based chat interface for Ollama.
# Run after install-ollama.sh.
#
# Access after install: http://bryanfoslerpi5.local:3000
#
# Usage: bash setup/install-open-webui.sh

set -e

WEBUI_PORT=3000
VENV_DIR="/opt/open-webui-venv"
DATA_DIR="/home/$USER/.open-webui"

echo "==> Checking Ollama is reachable..."
if ! curl -sf http://localhost:11434/api/tags > /dev/null; then
  echo "ERROR: Ollama doesn't appear to be running."
  echo "Run setup/install-ollama.sh first."
  exit 1
fi
echo "    Ollama is up."

echo ""
echo "==> Installing Python dependencies..."
sudo apt-get install -y python3-venv python3-pip ffmpeg libsm6 libxext6

echo ""
echo "==> Creating virtual environment at $VENV_DIR..."
sudo python3 -m venv $VENV_DIR
sudo $VENV_DIR/bin/pip install --upgrade pip

echo ""
echo "==> Installing Open-WebUI (this will take 5-10 minutes)..."
sudo $VENV_DIR/bin/pip install open-webui

echo ""
echo "==> Creating data directory..."
mkdir -p $DATA_DIR

echo ""
echo "==> Installing systemd service..."
sudo cp "$(dirname "$0")/../systemd/open-webui.service" /etc/systemd/system/
# Inject current user and paths into the service file
sudo sed -i "s|__USER__|$USER|g" /etc/systemd/system/open-webui.service
sudo sed -i "s|__VENV_DIR__|$VENV_DIR|g" /etc/systemd/system/open-webui.service
sudo sed -i "s|__DATA_DIR__|$DATA_DIR|g" /etc/systemd/system/open-webui.service
sudo sed -i "s|__PORT__|$WEBUI_PORT|g" /etc/systemd/system/open-webui.service

sudo systemctl daemon-reload
sudo systemctl enable open-webui
sudo systemctl start open-webui

echo ""
echo "========================================"
echo "  Open-WebUI installed successfully"
echo "========================================"
echo ""
echo "  Open in browser: http://bryanfoslerpi5.local:$WEBUI_PORT"
echo "  (First time: create an admin account — local only, not sent anywhere)"
echo ""
echo "  Service status:"
sudo systemctl status open-webui --no-pager -l
