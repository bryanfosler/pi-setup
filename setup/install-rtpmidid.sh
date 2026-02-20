#!/bin/bash
# Builds and installs rtpmidid from source on Raspberry Pi (Debian Trixie)
# rtpmidid is not in the Trixie repos — must be built from source.
# Run as: bash install-rtpmidid.sh

set -e

echo "Installing build dependencies..."
sudo apt-get install -y git cmake pkg-config libfmt-dev libasound2-dev libavahi-client-dev

echo "Cloning rtpmidid..."
cd ~
git clone https://github.com/davidmoreno/rtpmidid.git
cd rtpmidid
mkdir -p build && cd build

echo "Building..."
cmake ..
make -j4

echo "Installing binary..."
sudo cp src/rtpmidid /usr/local/bin/

echo "Installing systemd service..."
sudo cp /tmp/rtpmidid.service /etc/systemd/system/ 2>/dev/null || \
sudo tee /etc/systemd/system/rtpmidid.service > /dev/null << 'EOF'
[Unit]
Description=rtpMIDI Daemon
After=network.target avahi-daemon.service

[Service]
ExecStart=/usr/local/bin/rtpmidid --port 5004
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable rtpmidid
sudo systemctl start rtpmidid

echo "Done. rtpmidid is running on UDP ports 5004 and 5005."
sudo ss -ulnp | grep -E '500[45]'
