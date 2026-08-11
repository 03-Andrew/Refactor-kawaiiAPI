set -e

sudo apt update && sudo apt upgrade -y
sudo apt install docker.io docker-compose-v2 git -y
sudo systemctl enable --now docker


mkdir -p /opt/bookingapi
