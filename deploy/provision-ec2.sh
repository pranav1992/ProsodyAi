#!/bin/bash
# Provisions the single-instance AWS pilot deployment: an EC2 box running
# `docker compose up` for db+backend+frontend, behind a fixed Elastic IP.
#
# Usage:
#   OPENAI_API_KEY=sk-... ./deploy/provision-ec2.sh
#   (or have backend/.env with OPENAI_API_KEY set already — it'll be read from there)
#
# Re-running this script after a successful run refuses to proceed (see
# STATE_FILE check below) — run deploy/destroy-ec2.sh first if you want to
# tear down and recreate.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

REGION="ap-south-1"
INSTANCE_TYPE="t3.medium"
KEY_NAME="prosodyai-pilot"
SG_NAME="prosodyai-pilot-sg"
REPO_URL="https://github.com/pranav1992/ProsodyAi.git"
STATE_FILE="deploy/.state"
SSH_KEY_PATH="$HOME/.ssh/${KEY_NAME}.pem"

if [[ -f "$STATE_FILE" ]]; then
  echo "Error: $STATE_FILE already exists — a pilot deployment looks like it's already provisioned." >&2
  echo "Run deploy/destroy-ec2.sh first if you want to recreate it." >&2
  exit 1
fi

OPENAI_API_KEY="${OPENAI_API_KEY:-}"
if [[ -z "$OPENAI_API_KEY" && -f backend/.env ]]; then
  OPENAI_API_KEY="$(grep '^OPENAI_API_KEY=' backend/.env | head -1 | cut -d= -f2-)"
fi
if [[ -z "$OPENAI_API_KEY" ]]; then
  read -rsp "OPENAI_API_KEY: " OPENAI_API_KEY
  echo
fi
if [[ -z "$OPENAI_API_KEY" ]]; then
  echo "Error: no OPENAI_API_KEY provided." >&2
  exit 1
fi

echo "==> Looking up your current public IP (for the SSH security group rule)..."
MY_IP="$(curl -s https://checkip.amazonaws.com)"
echo "    $MY_IP"

echo "==> Finding the latest Ubuntu 24.04 AMI in $REGION..."
AMI_ID="$(aws ec2 describe-images \
  --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" "Name=state,Values=available" \
  --query "sort_by(Images, &CreationDate)[-1].ImageId" \
  --output text --region "$REGION")"
echo "    $AMI_ID"

VPC_ID="$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text --region "$REGION")"

echo "==> Allocating Elastic IP..."
EIP_JSON="$(aws ec2 allocate-address --domain vpc --region "$REGION" \
  --tag-specifications 'ResourceType=elastic-ip,Tags=[{Key=Name,Value=prosodyai-pilot}]')"
ALLOC_ID="$(echo "$EIP_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["AllocationId"])')"
PUBLIC_IP="$(echo "$EIP_JSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["PublicIp"])')"
echo "    $PUBLIC_IP ($ALLOC_ID)"

echo "==> Creating key pair..."
mkdir -p "$HOME/.ssh"
aws ec2 create-key-pair --key-name "$KEY_NAME" --query "KeyMaterial" --output text --region "$REGION" > "$SSH_KEY_PATH"
chmod 400 "$SSH_KEY_PATH"
echo "    saved to $SSH_KEY_PATH"

echo "==> Creating security group (22 from $MY_IP only, 3000+8000 public, no DB port)..."
SG_ID="$(aws ec2 create-security-group \
  --group-name "$SG_NAME" \
  --description "ProsodyAI pilot: SSH from admin IP, app ports public, DB internal-only" \
  --vpc-id "$VPC_ID" --region "$REGION" --query "GroupId" --output text)"
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 --cidr "${MY_IP}/32" --region "$REGION" >/dev/null
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 3000 --cidr 0.0.0.0/0 --region "$REGION" >/dev/null
aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 8000 --cidr 0.0.0.0/0 --region "$REGION" >/dev/null
aws ec2 create-tags --resources "$SG_ID" --tags Key=Name,Value=prosodyai-pilot --region "$REGION"
echo "    $SG_ID"

echo "==> Generating app secrets..."
JWT_SECRET="$(openssl rand -hex 32)"
POSTGRES_PASSWORD="$(openssl rand -base64 24 | tr -d '=+/')"
ADMIN_PASSWORD="$(openssl rand -base64 12 | tr -d '=+/')"
ADMIN_EMAIL="admin@autoace.ai"

USER_DATA_FILE="$(mktemp)"
trap 'rm -f "$USER_DATA_FILE"' EXIT

cat > "$USER_DATA_FILE" <<USERDATA
#!/bin/bash
set -ex
exec > >(tee -a /var/log/prosodyai-bootstrap.log) 2>&1

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git docker.io docker-compose-v2
systemctl enable --now docker

git clone $REPO_URL /opt/prosodyai
cd /opt/prosodyai

cat > .env <<'ENVEOF'
OPENAI_API_KEY=$OPENAI_API_KEY
CLASSIFICATION_MODEL=gpt-4o-mini
JWT_SECRET=$JWT_SECRET
POSTGRES_USER=autoace
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=autoace
ADMIN_EMAIL=$ADMIN_EMAIL
ADMIN_PASSWORD=$ADMIN_PASSWORD
CORS_ORIGINS=http://$PUBLIC_IP:3000
NEXT_PUBLIC_API_URL=http://$PUBLIC_IP:8000
ENVEOF

docker compose up -d --build

echo "BOOTSTRAP COMPLETE"
USERDATA

echo "==> Launching $INSTANCE_TYPE instance..."
INSTANCE_ID="$(aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":30,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
  --user-data "file://$USER_DATA_FILE" \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=prosodyai-pilot}]' \
  --count 1 --region "$REGION" \
  --query "Instances[0].InstanceId" --output text)"
echo "    $INSTANCE_ID"

echo "==> Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"

echo "==> Associating Elastic IP..."
aws ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID" --region "$REGION" >/dev/null

cat > "$STATE_FILE" <<STATE
REGION=$REGION
INSTANCE_ID=$INSTANCE_ID
SG_ID=$SG_ID
ALLOC_ID=$ALLOC_ID
KEY_NAME=$KEY_NAME
PUBLIC_IP=$PUBLIC_IP
STATE

echo
echo "Done. Docker build + first boot takes several minutes (Whisper/ML deps + Next.js build)."
echo "Watch progress:  ssh -i $SSH_KEY_PATH ubuntu@$PUBLIC_IP 'tail -f /var/log/prosodyai-bootstrap.log'"
echo
echo "Once ready:"
echo "  App:      http://$PUBLIC_IP:3000"
echo "  Login:    $ADMIN_EMAIL / $ADMIN_PASSWORD"
echo "  SSH:      ssh -i $SSH_KEY_PATH ubuntu@$PUBLIC_IP"
echo
echo "Save that password now -- it is not stored anywhere else by this script."
