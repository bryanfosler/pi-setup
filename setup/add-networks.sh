#!/bin/bash
# add-networks.sh
# One-time setup: adds iPhone hotspot and Mac Internet Sharing to the Pi.
# Run this after SSHing in via ethernet at home.
#
# Usage: bash setup/add-networks.sh

set -e

# ─── CREDENTIALS ────────────────────────────────────────────────────────────
IPHONE_SSID="Bryan's iPhone"
IPHONE_PASSWORD="11111111"

# Set these up first in macOS: System Settings > General > Sharing > Internet Sharing
# Turn on "Internet Sharing", share via Wi-Fi, then set a custom network name + password
MAC_SHARING_SSID="FILL_IN_MAC_SSID"
MAC_SHARING_PASSWORD="FILL_IN_MAC_PASSWORD"

# Your home WiFi SSID (to set its priority)
HOME_SSID="FILL_IN_HOME_SSID"
# ────────────────────────────────────────────────────────────────────────────

echo "==> Adding iPhone hotspot..."
nmcli connection add \
  type wifi \
  con-name "iphone-hotspot" \
  ssid "$IPHONE_SSID" \
  wifi-sec.key-mgmt wpa-psk \
  wifi-sec.psk "$IPHONE_PASSWORD" \
  connection.autoconnect yes \
  connection.autoconnect-priority 5
echo "    Done."

echo "==> Adding Mac Internet Sharing..."
nmcli connection add \
  type wifi \
  con-name "mac-sharing" \
  ssid "$MAC_SHARING_SSID" \
  wifi-sec.key-mgmt wpa-psk \
  wifi-sec.psk "$MAC_SHARING_PASSWORD" \
  connection.autoconnect yes \
  connection.autoconnect-priority 3
echo "    Done."

echo "==> Setting home WiFi to highest priority..."
# Find the connection name for your home SSID
HOME_CON=$(nmcli -t -f NAME,TYPE connection show | grep wifi | while IFS=: read name type; do
  SSID=$(nmcli -t -f 802-11-wireless.ssid connection show "$name" 2>/dev/null | cut -d: -f2)
  if [ "$SSID" = "$HOME_SSID" ]; then echo "$name"; fi
done)

if [ -n "$HOME_CON" ]; then
  nmcli connection modify "$HOME_CON" connection.autoconnect-priority 10
  echo "    Set '$HOME_CON' to priority 10."
else
  echo "    WARNING: Could not find home WiFi connection for SSID '$HOME_SSID'."
  echo "    Run 'nmcli connection show' to find it and set priority manually:"
  echo "    sudo nmcli connection modify <name> connection.autoconnect-priority 10"
fi

echo ""
echo "==> Network priorities configured:"
echo "    Home WiFi ($HOME_SSID):     10  (highest — always preferred)"
echo "    iPhone Hotspot:              5"
echo "    Mac Internet Sharing:        3"
echo ""
echo "==> Current connections:"
nmcli connection show | grep wifi
