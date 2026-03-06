#!/usr/bin/env zsh
# deploy.sh — sync openclaw/ workspace to Pi5 and register new skills
#
# Usage:
#   ./openclaw/deploy.sh              # full sync
#   ./openclaw/deploy.sh --dry-run    # preview what would change
#   ./openclaw/deploy.sh --skill task-builder   # sync one skill only
#
# Requires: ssh key auth to bfosler@bryanfoslerpi5.local

set -euo pipefail

PI_HOST="bfosler@bryanfoslerpi5.local"
PI_WORKSPACE="~/.openclaw/workspace"
LOCAL_OPENCLAW="$(cd "$(dirname "$0")" && pwd)"

DRY_RUN=0
SKILL_ONLY=""

for arg in "$@"; do
  case "$arg" in
    --dry-run)   DRY_RUN=1 ;;
    --skill)     shift; SKILL_ONLY="$1" ;;
    --skill=*)   SKILL_ONLY="${arg#--skill=}" ;;
  esac
done

RSYNC_FLAGS=(-avz --exclude="__pycache__" --exclude="*.pyc" --exclude=".DS_Store")
# NOTE: --delete intentionally omitted. Deploy is additive-only.
# Skills on the Pi that aren't in this repo will not be touched.
[[ $DRY_RUN -eq 1 ]] && RSYNC_FLAGS+=(--dry-run)

echo "==> Deploying to $PI_HOST:$PI_WORKSPACE"
[[ $DRY_RUN -eq 1 ]] && echo "    (DRY RUN — no changes will be made)"
echo ""

if [[ -n "$SKILL_ONLY" ]]; then
  # Single skill sync
  LOCAL_SKILL="$LOCAL_OPENCLAW/skills/$SKILL_ONLY"
  if [[ ! -d "$LOCAL_SKILL" ]]; then
    echo "Error: skill '$SKILL_ONLY' not found at $LOCAL_SKILL" >&2
    exit 1
  fi
  echo "==> Syncing skill: $SKILL_ONLY"
  rsync "${RSYNC_FLAGS[@]}" \
    "$LOCAL_SKILL/" \
    "$PI_HOST:$PI_WORKSPACE/skills/$SKILL_ONLY/"
else
  # Full sync: lib/ + skills/ + scripts/
  echo "==> Syncing lib/"
  rsync "${RSYNC_FLAGS[@]}" \
    "$LOCAL_OPENCLAW/lib/" \
    "$PI_HOST:$PI_WORKSPACE/lib/"

  echo ""
  echo "==> Syncing skills/"
  rsync "${RSYNC_FLAGS[@]}" \
    "$LOCAL_OPENCLAW/skills/" \
    "$PI_HOST:$PI_WORKSPACE/skills/"

  echo ""
  echo "==> Syncing scripts/"
  rsync "${RSYNC_FLAGS[@]}" \
    "$LOCAL_OPENCLAW/scripts/" \
    "$PI_HOST:$PI_WORKSPACE/scripts/"
fi

if [[ $DRY_RUN -eq 0 ]]; then
  echo ""
  echo "==> Making scripts executable on Pi"
  ssh "$PI_HOST" "find $PI_WORKSPACE/skills -name '*.py' -exec chmod +x {} \; && \
                  find $PI_WORKSPACE/scripts -name '*.py' -exec chmod +x {} \;"

  echo ""
  echo "==> Restarting OpenClaw gateway to pick up new skills"
  ssh "$PI_HOST" "systemctl --user restart openclaw-gateway && sleep 2 && \
                  systemctl --user is-active openclaw-gateway && echo 'Gateway: active'"

  echo ""
  echo "Done. Skills deployed:"
  ssh "$PI_HOST" "ls $PI_WORKSPACE/skills/"
fi
