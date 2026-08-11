#!/bin/bash
set -e

sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu

mkdir -p /opt/kawaiiapi
