#!/bin/bash
# install-open-webui.sh
# Installs Open-WebUI via Docker — browser-based chat interface for Ollama.
# Uses Docker because Open-WebUI's pip package requires Python <3.13,
# and Debian Trixie ships Python 3.13.
#
# Run after install-ollama.sh.
# Access after install: http://bryanfoslerpi5.local:3000
#
# Usage: bash setup/install-open-webui.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WEBUI_PORT=3000

echo "==> Checking Ollama is reachable..."
if ! curl -sf http://localhost:11434/api/tags > /dev/null; then
  echo "ERROR: Ollama doesn't appear to be running."
  echo "Run setup/install-ollama.sh first."
  exit 1
fi
echo "    Ollama is up."

echo ""
echo "==> Installing Docker..."
if command -v docker &>/dev/null; then
  echo "    Docker already installed: $(docker --version)"
else
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  echo "    Docker installed."
fi

echo ""
echo "==> Starting Docker service..."
sudo systemctl enable docker
sudo systemctl start docker
sleep 2

echo ""
echo "==> Pulling Open-WebUI image (ARM64)..."
sudo docker pull ghcr.io/open-webui/open-webui:main

echo ""
echo "==> Starting Open-WebUI container..."
# Remove old container if it exists
sudo docker rm -f open-webui 2>/dev/null || true

sudo docker run -d \
  --name open-webui \
  --restart always \
  -p "$WEBUI_PORT:8080" \
  --add-host=host.docker.internal:host-gateway \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  -v open-webui:/app/backend/data \
  ghcr.io/open-webui/open-webui:main

echo ""
echo "==> Installing systemd service (keeps container running across reboots)..."
sudo cp "$REPO_ROOT/systemd/open-webui.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable open-webui

echo ""
echo "========================================"
echo "  Open-WebUI installed successfully"
echo "========================================"
echo ""
echo "  Open in browser: http://bryanfoslerpi5.local:$WEBUI_PORT"
echo "  (First launch: create a local admin account)"
echo ""
echo "  Container status:"
sudo docker ps --filter name=open-webui --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
