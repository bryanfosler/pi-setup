#!/bin/bash
# install-ollama.sh
# Installs Ollama, configures it for network access, and pulls a starter model.
# Run once after SSHing into the Pi via ethernet.
#
# Usage: bash setup/install-ollama.sh

set -e

DEFAULT_MODEL="llama3.2:3b"   # ~2GB, fast on Pi 5 8GB — good default
# Other options:
#   llama3.2:1b   ~1.3GB  very fast, less capable
#   mistral:7b    ~4.1GB  more capable, slower (~3-5 tok/s on Pi 5)
#   moondream2    ~1.8GB  vision model (can describe images) — for pet cam later

echo "==> Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

echo ""
echo "==> Configuring Ollama to listen on all network interfaces..."
# By default Ollama only accepts connections from localhost.
# This override lets your Mac (and any device on the LAN) hit the API.
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf > /dev/null <<'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF

sudo systemctl daemon-reload
sudo systemctl restart ollama
sleep 2

echo ""
echo "==> Pulling default model: $DEFAULT_MODEL (may take several minutes on first run)..."
ollama pull $DEFAULT_MODEL

echo ""
echo "========================================"
echo "  Ollama installed successfully"
echo "========================================"
echo ""
echo "  API endpoint:  http://bryanfoslerpi5.local:11434"
echo "  List models:   curl http://bryanfoslerpi5.local:11434/api/tags"
echo ""
echo "  Quick chat test (on the Pi):"
echo "  ollama run $DEFAULT_MODEL"
echo ""
echo "  Service status:"
sudo systemctl status ollama --no-pager -l
