#!/bin/bash

# HydePark Local Server - Systemd Service Setup Script
# This script creates and enables a systemd service for auto-start

set -e  # Exit on error

echo "╔════════════════════════════════════════════════════════════╗"
echo "║     HydePark - Systemd Service Setup                      ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Get the script directory (absolute path)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
USER=$(whoami)

# Service name
SERVICE_NAME="hydepark-sync"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "[1/5] Creating systemd service file..."

# Create the service file
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=HydePark Local Server - Face Recognition Sync System
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
Environment="PATH=$SCRIPT_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$SCRIPT_DIR/venv/bin/python3 $SCRIPT_DIR/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security settings
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

echo "    ✓ Service file created at: $SERVICE_FILE"

echo "[2/5] Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "[3/5] Enabling service to start on boot..."
sudo systemctl enable "$SERVICE_NAME"

echo "[4/5] Starting the service..."
sudo systemctl start "$SERVICE_NAME"

echo "[5/5] Checking service status..."
sleep 2
sudo systemctl status "$SERVICE_NAME" --no-pager || true

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║           Systemd Service Setup Complete! ✓               ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Service Commands:"
echo "  • Check status:     sudo systemctl status $SERVICE_NAME"
echo "  • View logs:        sudo journalctl -u $SERVICE_NAME -f"
echo "  • Stop service:     sudo systemctl stop $SERVICE_NAME"
echo "  • Start service:    sudo systemctl start $SERVICE_NAME"
echo "  • Restart service:  sudo systemctl restart $SERVICE_NAME"
echo "  • Disable service:  sudo systemctl disable $SERVICE_NAME"
echo ""
echo "Log files location:"
echo "  • View with: sudo journalctl -u $SERVICE_NAME -f"
echo ""
