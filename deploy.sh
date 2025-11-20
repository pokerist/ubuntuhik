#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found"
  exit 1
fi

if [ ! -d "$PROJECT_DIR/venv" ]; then
  python3 -m venv "$PROJECT_DIR/venv"
fi

. "$PROJECT_DIR/venv/bin/activate"
pip install --upgrade pip
pip install requests schedule python-dotenv urllib3

SERVICE_NAME="hydepark-sync"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root to install systemd service"
  exit 1
fi

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=HydePark Local Sync Service
After=network.target

[Service]
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
systemctl status "$SERVICE_NAME" --no-pager -l || true

echo "Deployed and started $SERVICE_NAME"
