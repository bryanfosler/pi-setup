#!/bin/bash
# setup-hotspot.sh
# Configures the Pi as a WiFi hotspot (access point).
# When enabled, other devices connect TO the Pi's network instead of
# the Pi connecting to theirs.
#
# Use case: No home WiFi, no iPhone, no ethernet — Pi creates its own
# network and Mac connects to it for SSH, MIDI, Ollama, everything.
#
# Pi IP on hotspot: 192.168.100.1
# Connected devices get IPs: 192.168.100.x (via dnsmasq, managed by NetworkManager)
#
# Usage:
#   bash setup/setup-hotspot.sh            # create the hotspot profile (one-time)
#   bash setup/switch-network.sh hotspot   # enable hotspot
#   bash setup/switch-network.sh home      # disable hotspot, back to WiFi
#
# Run from the root of the cloned pi-setup repo:
#   bash setup/setup-hotspot.sh

set -e

# ─── CREDENTIALS ────────────────────────────────────────────────────────────
HOTSPOT_SSID="BryanPi5"
HOTSPOT_PASSWORD="FILL_IN_HOTSPOT_PASSWORD"    # min 8 chars — change this!
HOTSPOT_IP="192.168.100.1/24"
# ────────────────────────────────────────────────────────────────────────────

if [ "$HOTSPOT_PASSWORD" = "FILL_IN_HOTSPOT_PASSWORD" ]; then
  echo "ERROR: Set HOTSPOT_PASSWORD in this script before running."
  echo "       Edit setup/setup-hotspot.sh and replace FILL_IN_HOTSPOT_PASSWORD"
  exit 1
fi

echo "==> Checking for existing hotspot profile..."
if nmcli connection show "pi-hotspot" &>/dev/null; then
  echo "    Profile 'pi-hotspot' already exists — deleting and recreating..."
  nmcli connection delete "pi-hotspot"
fi

echo "==> Creating WiFi hotspot profile..."
nmcli connection add \
  type wifi \
  ifname wlan0 \
  mode ap \
  con-name "pi-hotspot" \
  ssid "$HOTSPOT_SSID" \
  wifi-sec.key-mgmt wpa-psk \
  wifi-sec.psk "$HOTSPOT_PASSWORD" \
  ipv4.method shared \
  ipv4.addresses "$HOTSPOT_IP" \
  ipv6.method disabled \
  connection.autoconnect no

echo "    Profile created: SSID='$HOTSPOT_SSID', IP=$HOTSPOT_IP"

echo ""
echo "==> Hotspot setup complete!"
echo ""
echo "    To enable the hotspot:"
echo "    bash setup/switch-network.sh hotspot"
echo ""
echo "    While hotspot is active:"
echo "    - Pi is at 192.168.100.1"
echo "    - Mac SSH: ssh bfosler@192.168.100.1"
echo "    - Services work at 192.168.100.1 (Ollama:11434, Open-WebUI:3000, etc.)"
echo "    - Pi has no internet access (no uplink) — local only"
echo ""
echo "    To go back to normal WiFi:"
echo "    bash setup/switch-network.sh home   (or iphone)"
echo ""
