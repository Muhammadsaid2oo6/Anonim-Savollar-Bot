#!/bin/bash

# Exit on any error
set -e

echo "Updating system..."
sudo apt-get update
sudo apt-get upgrade -y

echo "Installing Python and dependencies..."
sudo apt-get install python3.9 python3.9-venv python3-pip git -y

echo "Creating project directory..."
mkdir -p /home/ubuntu/AnonimVaqtiBot
cd /home/ubuntu/AnonimVaqtiBot

echo "Setting up virtual environment..."
python3.9 -m venv venv
source venv/bin/activate

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Setting up systemd service..."
# Create log files and set permissions
sudo touch /var/log/anonimvaqti-bot.log
sudo touch /var/log/anonimvaqti-bot.error.log
sudo chown ubuntu:ubuntu /var/log/anonimvaqti-bot.*

# Copy service file to systemd
sudo cp anonimvaqti-bot.service /etc/systemd/system/
sudo systemctl daemon-reload

# Start and enable the service
sudo systemctl enable anonimvaqti-bot
sudo systemctl start anonimvaqti-bot

echo "Checking service status..."
sudo systemctl status anonimvaqti-bot

echo "Deployment complete! Bot should be running."
echo "To check logs:"
echo "  sudo journalctl -u anonimvaqti-bot -f"
echo "To check service status:"
echo "  sudo systemctl status anonimvaqti-bot" 