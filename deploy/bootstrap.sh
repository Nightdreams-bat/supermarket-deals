#!/usr/bin/env bash
# One-shot setup on a fresh Ubuntu VM.
# Assumes you copied the project to ~/supermarket-deals (scp) INCLUDING
# config.ini and .keys.json.
# Run as:  bash ~/supermarket-deals/deploy/bootstrap.sh
set -euo pipefail

SRC="$HOME/supermarket-deals"
APP=/opt/supermarket-deals

echo ">> packages + timezone"
sudo apt-get update -y
sudo apt-get install -y python3 git
sudo timedatectl set-timezone Europe/Vienna

echo ">> config check"
for f in config.ini .keys.json; do
  if [ ! -f "$SRC/$f" ]; then
    echo "!! MISSING $SRC/$f  -- copy it from your PC (setup step 5), then re-run"
    exit 1
  fi
done

echo ">> installing app to $APP"
sudo mkdir -p "$APP"
sudo cp -rT "$SRC" "$APP"
sudo rm -rf "$APP/.git" "$APP/data"
sudo chown -R "$USER:$USER" "$APP"

echo ">> systemd units (running as $USER)"
sudo cp "$APP/deploy/supermarket-deals-bot.service"    /etc/systemd/system/
sudo cp "$APP/deploy/supermarket-deals-digest.service" /etc/systemd/system/
sudo cp "$APP/deploy/supermarket-deals-digest.timer"   /etc/systemd/system/
sudo sed -i "/^\[Service\]/a User=$USER" /etc/systemd/system/supermarket-deals-bot.service
sudo sed -i "/^\[Service\]/a User=$USER" /etc/systemd/system/supermarket-deals-digest.service

sudo systemctl daemon-reload
sudo systemctl enable --now supermarket-deals-bot.service
sudo systemctl enable --now supermarket-deals-digest.timer

echo
echo ">> bot status:"
systemctl --no-pager --lines=8 status supermarket-deals-bot.service || true
echo ">> next digest run:"
systemctl list-timers supermarket-deals-digest.timer --no-pager || true
echo
echo "Send the bot /start in Telegram to confirm it answers."
