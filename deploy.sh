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

if [ ! -f "$PROJECT_DIR/.env" ]; then
  if [ -f "$PROJECT_DIR/.env.example" ]; then
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo "Created .env from .env.example"
  else
    echo "Missing .env and .env.example"
    exit 1
  fi
fi

# Ensure dashboard defaults
if ! grep -q '^DASHBOARD_ENABLED=' "$PROJECT_DIR/.env"; then
  echo 'DASHBOARD_ENABLED=True' >> "$PROJECT_DIR/.env"
fi
if ! grep -q '^DASHBOARD_PORT=' "$PROJECT_DIR/.env"; then
  echo 'DASHBOARD_PORT=8080' >> "$PROJECT_DIR/.env"
fi
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

if grep -q '^DASHBOARD_ENABLED=\s*True' "$PROJECT_DIR/.env"; then
  PORT=$(grep -E '^DASHBOARD_PORT=' "$PROJECT_DIR/.env" | cut -d'=' -f2)
  [ -z "$PORT" ] && PORT=8080
  echo "Dashboard: http://$(hostname -I | awk '{print $1}'):$PORT/"
fi
