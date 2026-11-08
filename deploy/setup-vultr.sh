#!/usr/bin/env bash
# One shot setup for a fresh Ubuntu 22.04 or 24.04 Vultr VM (2 vCPU, 4 GB is plenty).
# Run as root:  bash deploy/setup-vultr.sh
set -euo pipefail

APP=/opt/proofbox
DOMAIN="${1:-}"

echo "==> packages"
apt-get update -y
apt-get install -y ca-certificates curl git rsync python3 python3-venv ufw docker.io caddy
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs
systemctl enable --now docker

echo "==> user and folders"
id proofbox >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin proofbox
usermod -aG docker proofbox
mkdir -p "$APP" /var/lib/proofbox
rsync -a --delete --exclude node_modules --exclude .venv --exclude .next ./ "$APP"/ 2>/dev/null || cp -r ./* "$APP"/
chown -R proofbox:proofbox "$APP" /var/lib/proofbox

echo "==> sandbox image (Foundry and solc are baked in; the box has no network at run time)"
docker build -t proofbox-sandbox:latest "$APP/sandbox"

echo "==> backend"
sudo -u proofbox python3 -m venv "$APP/backend/.venv"
sudo -u proofbox "$APP/backend/.venv/bin/pip" install -q -r "$APP/backend/requirements.txt"

echo "==> frontend"
cd "$APP/frontend"
sudo -u proofbox npm ci --no-audit --no-fund || sudo -u proofbox npm install --no-audit --no-fund
sudo -u proofbox npm run build

echo "==> config"
[ -f /etc/proofbox.env ] || { cp "$APP/deploy/proofbox.env.example" /etc/proofbox.env; chmod 600 /etc/proofbox.env; }
cp "$APP"/deploy/proofbox-api.service "$APP"/deploy/proofbox-web.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now proofbox-api proofbox-web

echo "==> firewall: only SSH and web"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

if [ -n "$DOMAIN" ]; then
  sed "s/proofbox.example.com/$DOMAIN/" "$APP/deploy/Caddyfile" > /etc/caddy/Caddyfile
else
  sed 's/proofbox.example.com/:80/' "$APP/deploy/Caddyfile" > /etc/caddy/Caddyfile
fi
systemctl restart caddy

echo
echo "Done. Add your key:  nano /etc/proofbox.env  then  systemctl restart proofbox-api"
echo "Check:  curl -s localhost:8000/api/health"
