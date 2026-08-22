#!/bin/bash
# Tears down everything deploy/provision-ec2.sh created. Reads deploy/.state
# for the resource IDs, so it only ever removes what that script made.
#
# Usage: ./deploy/destroy-ec2.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

STATE_FILE="deploy/.state"
if [[ ! -f "$STATE_FILE" ]]; then
  echo "Error: $STATE_FILE not found -- nothing tracked to destroy." >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$STATE_FILE"

read -rp "This will terminate instance $INSTANCE_ID and release its Elastic IP ($PUBLIC_IP). Continue? [y/N] " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  echo "Aborted."
  exit 0
fi

echo "==> Terminating instance $INSTANCE_ID..."
aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" --region "$REGION" >/dev/null
aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID" --region "$REGION"

echo "==> Releasing Elastic IP $ALLOC_ID..."
aws ec2 release-address --allocation-id "$ALLOC_ID" --region "$REGION"

echo "==> Deleting security group $SG_ID..."
aws ec2 delete-security-group --group-id "$SG_ID" --region "$REGION"

echo "==> Deleting key pair $KEY_NAME (AWS-side)..."
aws ec2 delete-key-pair --key-name "$KEY_NAME" --region "$REGION"

echo "==> Local private key at ~/.ssh/${KEY_NAME}.pem was left in place -- remove it yourself if you're done with it."

rm -f "$STATE_FILE"
echo "Done. $STATE_FILE removed."
