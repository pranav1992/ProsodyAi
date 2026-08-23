#!/bin/bash
# Starts a previously-stopped pilot instance back up. The Elastic IP
# reattaches automatically and, since docker-compose.yml sets
# `restart: unless-stopped` on every service, the app comes back on its
# own -- no manual SSH step needed afterward.
#
# Usage: ./deploy/start-ec2.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

STATE_FILE="deploy/.state"
if [[ ! -f "$STATE_FILE" ]]; then
  echo "Error: $STATE_FILE not found -- nothing tracked to start." >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$STATE_FILE"

echo "==> Starting instance $INSTANCE_ID..."
aws ec2 start-instances --instance-ids "$INSTANCE_ID" --region "$REGION" >/dev/null
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"
echo "Running. App should be reachable within a minute or two at:"
echo "  http://$PUBLIC_IP:3000"
