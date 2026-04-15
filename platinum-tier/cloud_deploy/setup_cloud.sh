#!/usr/bin/env bash
# =============================================================================
# setup_cloud.sh — Oracle Cloud Free VM Setup for AI Employee (Platinum Tier)
#
# Run on a fresh Ubuntu 22.04 / 24.04 VM (Oracle Cloud Always Free):
#   curl -sSL https://raw.githubusercontent.com/<repo>/main/cloud_deploy/setup_cloud.sh | bash
# Or:
#   chmod +x setup_cloud.sh && sudo ./setup_cloud.sh
#
# This script:
#   1. Installs system dependencies (Python 3.12+, git, nginx)
#   2. Clones the platinum-tier repo
#   3. Creates Python venv and installs requirements
#   4. Sets up .env from template
#   5. Installs systemd services for cloud_agent and health_monitor
#   6. Configures nginx reverse proxy for health check (port 80 → 8080)
#   7. Opens firewall port 80 for uptime monitors
#   8. Starts all services
# =============================================================================

set -euo pipefail

# ---- Config — edit these before running ----
REPO_URL="${REPO_URL:-https://github.com/AhmedHKhan18/hackathon-zero.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
APP_DIR="${APP_DIR:-/home/ubuntu/platinum-tier}"
APP_USER="${APP_USER:-ubuntu}"
VAULT_PATH="${VAULT_PATH:-${APP_DIR}/AI_Employee_Vault}"
HEALTH_PORT="${HEALTH_PORT:-8080}"
CLOUD_AGENT_INTERVAL="${CLOUD_AGENT_INTERVAL:-60}"
PYTHON="${PYTHON:-python3}"
# -------------------------------------------

COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${COLOR_GREEN}[INFO]${NC} $*"; }
warn()    { echo -e "${COLOR_YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${COLOR_RED}[ERROR]${NC} $*" >&2; exit 1; }

# ---- 1. System dependencies ----
info "Updating packages..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv python3-dev \
    git curl wget nginx \
    build-essential libssl-dev \
    ufw \
    2>/dev/null

# ---- 2. Clone or update repo ----
if [ -d "${APP_DIR}/.git" ]; then
    info "Repo already cloned — pulling latest..."
    sudo -u "${APP_USER}" git -C "${APP_DIR}" pull --rebase origin "${REPO_BRANCH}"
else
    info "Cloning repo to ${APP_DIR}..."
    sudo -u "${APP_USER}" git clone \
        --branch "${REPO_BRANCH}" \
        "${REPO_URL}" \
        "${APP_DIR}"
fi

# ---- 3. Python venv + requirements ----
info "Setting up Python virtual environment..."
VENV_DIR="${APP_DIR}/venv"
sudo -u "${APP_USER}" ${PYTHON} -m venv "${VENV_DIR}"
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --quiet --upgrade pip
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --quiet \
    anthropic \
    python-dotenv \
    google-auth \
    google-auth-oauthlib \
    google-auth-httplib2 \
    google-api-python-client \
    fastmcp \
    playwright \
    watchdog

# Also install project requirements if they exist
if [ -f "${APP_DIR}/requirements.txt" ]; then
    sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"
fi

# ---- 4. .env setup ----
ENV_FILE="${APP_DIR}/.env"
ENV_EXAMPLE="${APP_DIR}/.env.cloud.example"
if [ ! -f "${ENV_FILE}" ]; then
    if [ -f "${ENV_EXAMPLE}" ]; then
        info "Copying .env.cloud.example → .env (edit with your secrets)"
        cp "${ENV_EXAMPLE}" "${ENV_FILE}"
        chown "${APP_USER}:${APP_USER}" "${ENV_FILE}"
        chmod 600 "${ENV_FILE}"
    else
        warn ".env not found and no .env.cloud.example — create it manually"
    fi
else
    info ".env already exists — skipping"
fi

# ---- 5. Git config for vault sync ----
info "Configuring git for vault sync..."
sudo -u "${APP_USER}" git config --global user.name "AI Employee Cloud Agent"
sudo -u "${APP_USER}" git config --global user.email "cloud-agent@ai-employee.local"
sudo -u "${APP_USER}" git config --global pull.rebase true

# ---- 6. Vault directory structure ----
info "Creating vault directory structure..."
DIRS=(
    "${VAULT_PATH}/Needs_Action/cloud"
    "${VAULT_PATH}/Needs_Action/local"
    "${VAULT_PATH}/Pending_Approval"
    "${VAULT_PATH}/Approved"
    "${VAULT_PATH}/Rejected"
    "${VAULT_PATH}/Plans"
    "${VAULT_PATH}/Done"
    "${VAULT_PATH}/Drafts"
    "${VAULT_PATH}/Updates"
    "${VAULT_PATH}/Signals"
    "${VAULT_PATH}/In_Progress/cloud-agent"
    "${VAULT_PATH}/Logs"
    "${VAULT_PATH}/Briefings"
)
for dir in "${DIRS[@]}"; do
    sudo -u "${APP_USER}" mkdir -p "${dir}"
done

# ---- 7. Systemd services ----
info "Installing systemd services..."
PYTHON_BIN="${VENV_DIR}/bin/python"

# cloud_agent.service
cat > /etc/systemd/system/cloud-agent.service << EOF
[Unit]
Description=AI Employee Cloud Agent (Platinum Tier)
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=${ENV_FILE}
ExecStart=${PYTHON_BIN} cloud_agent.py --vault-path ${VAULT_PATH} --interval ${CLOUD_AGENT_INTERVAL}
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=cloud-agent

[Install]
WantedBy=multi-user.target
EOF

# health-monitor.service
cat > /etc/systemd/system/health-monitor.service << EOF
[Unit]
Description=AI Employee Health Monitor (Platinum Tier)
After=network.target
Wants=cloud-agent.service

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=${ENV_FILE}
ExecStart=${PYTHON_BIN} health_monitor.py --vault-path ${VAULT_PATH} --port ${HEALTH_PORT} --no-watchdog
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=health-monitor

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable cloud-agent.service health-monitor.service

# ---- 8. nginx config for health check ----
info "Configuring nginx health check proxy..."
cat > /etc/nginx/sites-available/ai-employee << 'EOF'
server {
    listen 80;
    server_name _;

    location /health {
        proxy_pass http://127.0.0.1:8080/health;
        proxy_set_header Host $host;
        add_header Cache-Control "no-cache, no-store";
    }

    location / {
        return 200 "AI Employee Cloud Agent - OK\n";
        add_header Content-Type text/plain;
    }
}
EOF

ln -sf /etc/nginx/sites-available/ai-employee /etc/nginx/sites-enabled/ai-employee
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
systemctl enable nginx

# ---- 9. Firewall ----
info "Configuring firewall..."
ufw allow ssh
ufw allow http
ufw allow 8080/tcp
echo "y" | ufw enable || true

# ---- 10. Start services ----
info "Starting services..."
systemctl start health-monitor.service
systemctl start cloud-agent.service

info "======================================================"
info "Setup complete!"
info ""
info "Next steps:"
info "  1. Edit ${ENV_FILE} with your actual secrets"
info "  2. Add SSH deploy key for vault Git sync:"
info "     cat ~/.ssh/id_ed25519.pub  # add to GitHub deploy keys"
info "  3. Check service status:"
info "     sudo systemctl status cloud-agent health-monitor"
info "  4. View logs:"
info "     sudo journalctl -u cloud-agent -f"
info "  5. Add http://<VM-IP>/health to UptimeRobot for monitoring"
info "======================================================"
