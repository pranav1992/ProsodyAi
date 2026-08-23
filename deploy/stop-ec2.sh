#!/bin/bash
# Stops the pilot instance to pause compute billing (storage + the Elastic
# IP keep accruing their small charges either way). Reads deploy/.state for
# the instance ID, so there's nothing to look up or copy-paste.
#
# Usage: ./deploy/stop-ec2.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

STATE_FILE="deploy/.state"
if [[ ! -f "$STATE_FILE" ]]; then
  echo "Error: $STATE_FILE not found -- nothing tracked to stop." >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$STATE_FILE"

echo "==> Stopping instance $INSTANCE_ID..."
aws ec2 stop-instances --instance-ids "$INSTANCE_ID" --region "$REGION" >/dev/null
aws ec2 wait instance-stopped --instance-ids "$INSTANCE_ID" --region "$REGION"
echo "Stopped. Elastic IP $PUBLIC_IP stays reserved -- run deploy/start-ec2.sh to resume."
