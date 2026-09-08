#!/usr/bin/env bash
# One-shot setup on a fresh Ubuntu VM. Run as: bash deploy/bootstrap.sh
set -euo pipefail

APP=/opt/supermarket-deals

echo ">> installing packages"
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip git
sudo timedatectl set-timezone Europe/Vienna

echo ">> placing app at $APP"
sudo mkdir -p "$APP"
sudo chown "$USER:$USER" "$APP"
# assumes you cloned the repo into ~/supermarket-deals
rsync -a --delete --exclude '.git' ~/supermarket-deals/ "$APP/"

echo ">> python deps"
pip3 install --user -r "$APP/requirements.txt" || true

echo ">> config check"
for f in config.ini .keys.json; do
  if [ ! -f "$APP/$f" ]; then
    echo "!! MISSING $APP/$f  -- copy it from your PC (see setup step 6), then re-run this script"
    exit 1
  fi
done

echo ">> installing systemd units"
sudo cp "$APP/deploy/supermarket-deals-bot.service"    /etc/systemd/system/
sudo cp "$APP/deploy/supermarket-deals-digest.service" /etc/systemd/system/
sudo cp "$APP/deploy/supermarket-deals-digest.timer"   /etc/systemd/system/
# run services as the current (non-root) user
sudo sed -i "/^\[Service\]/a User=$USER" /etc/systemd/system/supermarket-deals-bot.service
sudo sed -i "/^\[Service\]/a User=$USER" /etc/systemd/system/supermarket-deals-digest.service

sudo systemctl daemon-reload
sudo systemctl enable --now supermarket-deals-bot.service
sudo systemctl enable --now supermarket-deals-digest.timer

echo ">> done. status:"
systemctl --no-pager status supermarket-deals-bot.service | head -12
systemctl list-timers supermarket-deals-digest.timer --no-pager
