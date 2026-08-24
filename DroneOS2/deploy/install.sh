#!/bin/bash
set -e

echo "==============================================="
echo " SwarmOS Raspberry Pi Deployment Installer"
echo "==============================================="

# 1. Update and install base dependencies
echo "Updating APT packages..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv git htop

# 2. Prepare Directory structure
echo "Preparing /opt/SwarmOS directory..."
if [ -d "/opt/SwarmOS" ]; then
    echo "Directory exists. Updating permissions..."
else
    sudo mkdir -p /opt/SwarmOS
fi
sudo chown -R $USER:$USER /opt/SwarmOS

# 3. Copy project files
echo "Deploying files to /opt/SwarmOS..."
# Normally this would be a git clone or rsync. Assuming files are adjacent for this script:
rsync -av --exclude 'venv' --exclude '.git' ../ /opt/SwarmOS/

# 4. Setup Python Virtual Environment
echo "Setting up Python Virtual Environment..."
cd /opt/SwarmOS
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip

# 5. Install Python dependencies
echo "Installing Python dependencies..."
pip install -r deploy/requirements.txt

# 6. Install Systemd Service
echo "Installing systemd service..."
sudo cp /opt/SwarmOS/deploy/droneos.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable droneos.service

echo "==============================================="
echo "Installation complete!"
echo "To start DroneOS immediately, run:"
echo "sudo systemctl start droneos.service"
echo "To view logs, run:"
echo "journalctl -u droneos.service -f"
echo "==============================================="
