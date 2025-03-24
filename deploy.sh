#!/bin/bash

# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Python and pip
sudo apt-get install python3.9 python3.9-venv python3-pip -y

# Create virtual environment
python3.9 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install PM2 for process management
curl -sL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo npm install pm2 -g

# Create PM2 config
echo '{
  "apps": [{
    "name": "anonimvaqti-bot",
    "script": "bot.py",
    "interpreter": "./venv/bin/python3.9",
    "watch": true,
    "time": true,
    "instances": 1,
    "autorestart": true,
    "max_restarts": 10,
    "error_file": "logs/err.log",
    "out_file": "logs/out.log",
    "log_date_format": "YYYY-MM-DD HH:mm Z"
  }]
}' > ecosystem.config.json

# Create logs directory
mkdir -p logs

# Start the bot with PM2
pm2 start ecosystem.config.json 