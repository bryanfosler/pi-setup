#!/bin/bash
# install-bt-midi.sh
# Sets up the Pi as a BLE MIDI peripheral ("Pi BT MIDI").
# Mac/iOS sees the Pi in Audio MIDI Setup → Bluetooth after this runs.
#
# Run from the root of the cloned pi-setup repo:
#   bash setup/install-bt-midi.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y \
  bluez \
  python3-dbus \
  python3-gi \
  gir1.2-glib-2.0 \
  python3-pip \
  python3-venv
echo "    Done."

echo "==> Installing python-rtmidi..."
# Use a venv to avoid conflicts with system packages
python3 -m venv /opt/bt-midi-venv --system-site-packages
/opt/bt-midi-venv/bin/pip install --quiet python-rtmidi
echo "    Done."

echo "==> Installing bt-midi-peripheral.py..."
sudo mkdir -p /usr/local/lib/bt-midi
sudo cp "$REPO_ROOT/bt-midi/bt-midi-peripheral.py" /usr/local/lib/bt-midi/bt-midi-peripheral.py
sudo chmod +x /usr/local/lib/bt-midi/bt-midi-peripheral.py
echo "    Installed to /usr/local/lib/bt-midi/bt-midi-peripheral.py"

echo "==> Installing systemd service..."
sudo cp "$REPO_ROOT/systemd/bt-midi.service" /etc/systemd/system/bt-midi.service
sudo systemctl daemon-reload
sudo systemctl enable bt-midi.service
echo "    bt-midi.service enabled"

echo ""
echo "==> Ensuring bluetooth is powered on..."
sudo systemctl enable bluetooth
sudo systemctl start bluetooth
# Give bluez a moment to initialize
sleep 2
sudo bluetoothctl power on || true

echo ""
echo "==> Starting bt-midi service..."
sudo systemctl start bt-midi.service
sleep 2
sudo systemctl status bt-midi.service --no-pager

echo ""
echo "==> BLE MIDI peripheral setup complete!"
echo ""
echo "    On your Mac:"
echo "    1. Open Audio MIDI Setup (Spotlight → 'Audio MIDI Setup')"
echo "    2. Window → Show MIDI Studio"
echo "    3. Double-click 'Bluetooth' in the toolbar"
echo "    4. You should see 'Pi BT MIDI' — click Connect"
echo ""
echo "    To check the service:"
echo "    journalctl -u bt-midi -f"
echo ""
