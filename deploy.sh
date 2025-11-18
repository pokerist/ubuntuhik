#!/bin/bash

# HydePark Local Server - Ubuntu Deployment Script
# This script automates the installation and setup process

set -e  # Exit on error

echo "╔════════════════════════════════════════════════════════════╗"
echo "║     HydePark Local Server - Ubuntu Deployment             ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo "[ERROR] Please do not run this script as root"
   echo "Usage: ./deploy.sh"
   exit 1
fi

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "[1/8] Updating system packages..."
sudo apt update

echo "[2/8] Installing Python 3 and pip..."
sudo apt install -y python3 python3-pip python3-venv

echo "[3/8] Installing system dependencies for face-recognition..."
sudo apt install -y build-essential cmake
sudo apt install -y libopenblas-dev liblapack-dev
sudo apt install -y libx11-dev libgtk-3-dev

# Optional: Install dlib dependencies (face-recognition needs this)
echo "[4/8] Installing dlib dependencies..."
sudo apt install -y libboost-all-dev

echo "[5/8] Creating Python virtual environment..."
if [ -d "venv" ]; then
    echo "    Virtual environment already exists, skipping..."
else
    python3 -m venv venv
    echo "    ✓ Virtual environment created"
fi

echo "[6/8] Activating virtual environment and installing Python packages..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "[7/8] Setting up .env file..."
if [ -f ".env" ]; then
    echo "    .env file already exists, skipping..."
else
    cp .env.example .env
    echo "    ✓ .env file created from template"
    echo ""
    echo "    ⚠️  IMPORTANT: Please edit .env file with your actual credentials:"
    echo "       nano .env"
    echo ""
fi

echo "[8/8] Setting up systemd service..."
read -p "Do you want to set up the systemd service for auto-start? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    bash setup_service.sh
else
    echo "    Skipping systemd setup. You can run it later with: bash setup_service.sh"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║              Deployment Complete! ✓                        ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "1. Edit the .env file with your credentials:"
echo "   nano .env"
echo ""
echo "2. Test the application manually:"
echo "   source venv/bin/activate"
echo "   python3 main.py"
echo ""
echo "3. If you didn't set up the systemd service, you can do it now:"
echo "   bash setup_service.sh"
echo ""
echo "4. To check service status (if systemd was set up):"
echo "   sudo systemctl status hydepark-sync"
echo ""
