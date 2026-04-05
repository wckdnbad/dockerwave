#!/bin/bash
# Run once on a fresh Ubuntu 22.04 EC2 instance to install all dependencies.
# Usage: bash provision.sh
set -e

echo "==> Updating system packages"
sudo apt-get update && sudo apt-get upgrade -y

echo "==> Installing system dependencies"
sudo apt-get install -y \
    python3 python3-pip python3-venv \
    nginx \
    redis-server \
    git \
    curl \
    ca-certificates \
    gnupg

echo "==> Installing Node.js 20"
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

echo "==> Installing Docker"
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io

echo "==> Adding ubuntu user to docker group (allows Flask to use Docker without sudo)"
sudo usermod -aG docker ubuntu

echo "==> Enabling services on boot"
sudo systemctl enable redis-server
sudo systemctl enable docker
sudo systemctl enable nginx

echo "==> Done. Log out and back in for docker group to take effect."
