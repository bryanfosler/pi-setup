#!/bin/bash
# switch-network.sh
# Manually switch the Pi to a specific WiFi network.
#
# Usage:
#   bash setup/switch-network.sh              # show status + available networks
#   bash setup/switch-network.sh home         # connect to home WiFi
#   bash setup/switch-network.sh iphone       # connect to iPhone hotspot
#   bash setup/switch-network.sh mac          # connect to Mac Internet Sharing

SHORTCUTS=(
  "home:$(nmcli -t -f NAME,TYPE connection show | grep wifi | head -1 | cut -d: -f1)"
  "iphone:iphone-hotspot"
  "mac:mac-sharing"
)

resolve_shortcut() {
  local input="$1"
  for entry in "${SHORTCUTS[@]}"; do
    key="${entry%%:*}"
    val="${entry#*:}"
    if [ "$input" = "$key" ]; then
      echo "$val"
      return
    fi
  done
  echo "$input"  # pass through as-is if not a shortcut
}

print_status() {
  echo "==> Currently active:"
  nmcli -t -f NAME,DEVICE,STATE connection show --active | grep -i wlan || echo "    (no WiFi active)"
  echo ""
  echo "==> All configured WiFi networks (by priority):"
  nmcli -t -f NAME,TYPE,AUTOCONNECT-PRIORITY connection show | grep wifi | \
    awk -F: '{printf "    %-30s priority %s\n", $1, $3}' | sort -t' ' -k3 -rn
  echo ""
  echo "Usage: $0 [home|iphone|mac|<connection-name>]"
}

if [ -z "$1" ]; then
  print_status
  exit 0
fi

TARGET=$(resolve_shortcut "$1")

echo "==> Switching to: $TARGET"
nmcli connection up "$TARGET"
echo ""
echo "==> Now connected:"
nmcli -t -f NAME,DEVICE,STATE connection show --active | grep -i wlan
