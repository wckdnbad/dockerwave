#!/bin/bash
# Runs on the EC2 server to pull latest code and restart services.
# Usage: bash deploy.sh
set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Pulling latest code"
cd "$APP_DIR"
git pull origin master

echo "==> Installing/updating Python dependencies"
cd "$APP_DIR/server"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo "==> Building React frontend"
cd "$APP_DIR/client"
npm install
npm run build

echo "==> Restarting Flask"
sudo systemctl restart dockerwave

echo "==> Reloading nginx"
sudo systemctl reload nginx

echo "==> Deploy complete"
