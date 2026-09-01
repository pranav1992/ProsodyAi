#!/bin/bash
# Pulls the latest main and rebuilds/restarts the app on the pilot
# instance, then re-applies the nginx config in case it changed. Run this
# from your own machine whenever you want to ship what's on main -- there
# is no automatic/CI deploy (see README's "Redeploying" section for why:
# a GitHub-hosted runner has no fixed IP to allowlist for SSH, and a
# self-hosted runner is unsafe on a public repo, so this stays a manual,
# direct-SSH step rather than pulling in either of those tradeoffs).
#
# Usage: ./deploy/redeploy.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

STATE_FILE="deploy/.state"
if [[ ! -f "$STATE_FILE" ]]; then
  echo "Error: $STATE_FILE not found -- nothing tracked to deploy to." >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$STATE_FILE"

SSH_KEY_PATH="$HOME/.ssh/${KEY_NAME}.pem"

echo "==> Deploying to $PUBLIC_IP..."
ssh -i "$SSH_KEY_PATH" "ubuntu@$PUBLIC_IP" '
  set -e
  cd /opt/prosodyai
  git pull
  sudo docker compose up -d --build
  sudo cp deploy/nginx/prosodyai.conf /etc/nginx/sites-available/prosodyai.conf
  sudo nginx -t
  sudo systemctl reload nginx
'
echo "Done. App should reflect the latest main at:"
echo "  http://$PUBLIC_IP"
