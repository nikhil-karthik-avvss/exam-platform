#!/bin/bash
# ============================================================
#   CP Exam Platform — One-Time Setup
#   Run on the server machine (10.6.6.1) WITH internet.
#   Usage: bash setup.sh
# ============================================================

set -e
BOLD='\033[1m'; CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo ""
echo -e "${BOLD}================================================${NC}"
echo -e "${BOLD}  CP Exam Platform — Setup${NC}"
echo -e "${BOLD}  Server: 10.6.6.1  |  exam-platform-mtech${NC}"
echo -e "${BOLD}================================================${NC}"
echo ""

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
CURRENT_USER=$(whoami)

# ── 1. Python 3 ──
echo -e "${CYAN}[1/8] Checking Python 3...${NC}"
if ! command -v python3 &>/dev/null; then
    sudo apt-get update -qq && sudo apt-get install -y python3 python3-pip python3-venv
fi
echo -e "${GREEN}  OK: $(python3 --version)${NC}"

# ── 2. Java ──
echo -e "${CYAN}[2/8] Checking Java...${NC}"
if ! command -v javac &>/dev/null; then
    echo "  Installing OpenJDK 17..."
    sudo apt-get update -qq && sudo apt-get install -y openjdk-17-jdk
fi
echo -e "${GREEN}  OK: $(java -version 2>&1 | head -1)${NC}"

# ── 3. Virtual environment ──
echo -e "${CYAN}[3/8] Creating virtual environment...${NC}"
[ ! -d "venv" ] && python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
echo -e "${GREEN}  OK${NC}"

# ── 4. Flask ──
echo -e "${CYAN}[4/8] Installing Flask...${NC}"
pip install --quiet flask==3.0.3
echo -e "${GREEN}  OK${NC}"

# ── 5. CodeMirror offline assets ──
echo -e "${CYAN}[5/8] Downloading CodeMirror assets (for offline editor)...${NC}"
python3 download_assets.py
echo -e "${GREEN}  OK${NC}"

# ── 6. Database ──
echo -e "${CYAN}[6/8] Initializing database + pre-loading 62 students...${NC}"
python3 -c "from app import app, init_db; app.app_context().push(); init_db()"
echo -e "${GREEN}  OK — 3122237001001 to 3122237001062${NC}"

# ── 7. Register systemd service: exam-platform-mtech ──
echo -e "${CYAN}[7/8] Registering systemd service 'exam-platform-mtech'...${NC}"
PYTHON_BIN="$DIR/venv/bin/python3"

sudo tee /etc/systemd/system/exam-platform-mtech.service > /dev/null <<EOF
[Unit]
Description=CP Exam Platform (exam-platform-mtech)
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$DIR
ExecStart=$PYTHON_BIN $DIR/app.py
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable exam-platform-mtech
echo -e "${GREEN}  OK — starts automatically on boot${NC}"

# ── 8. Desktop icon ──
echo -e "${CYAN}[8/8] Creating desktop launcher...${NC}"

# Find desktop directory
DESKTOP="$HOME/Desktop"
[ ! -d "$DESKTOP" ] && DESKTOP="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
mkdir -p "$DESKTOP"

# Create the GUI launcher script (zenity dialog)
cat > "$DIR/launch_gui.sh" <<'LAUNCHEOF'
#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

SERVICE="exam-platform-mtech"
URL="http://10.6.6.1:5000"

is_running() {
    systemctl is-active --quiet "$SERVICE"
}

if is_running; then
    # Server is already running — offer to open or stop
    ACTION=$(zenity --list \
        --title="CP Exam Platform" \
        --text="The exam server is running.\n\nURL: $URL\nService: $SERVICE" \
        --column="Action" \
        "Open admin panel in browser" \
        "Stop the server" \
        --height=220 --width=360 2>/dev/null)

    case "$ACTION" in
        "Open admin panel in browser")
            xdg-open "$URL/admin" 2>/dev/null || firefox "$URL/admin" &
            ;;
        "Stop the server")
            pkexec systemctl stop "$SERVICE"
            zenity --info --title="CP Exam Platform" \
                --text="Server stopped." --width=280 2>/dev/null
            ;;
    esac
else
    # Server is not running — offer to start
    zenity --question \
        --title="CP Exam Platform" \
        --text="Start the exam server?\n\nService: $SERVICE\nURL: $URL\n\nStudents connect to:\nhttp://10.6.6.1:5000" \
        --ok-label="Start Server" \
        --cancel-label="Cancel" \
        --width=340 2>/dev/null || exit 0

    pkexec systemctl start "$SERVICE"
    sleep 2

    if is_running; then
        zenity --info \
            --title="CP Exam Platform" \
            --text="Server started successfully.\n\nAdmin panel:\n$URL/admin\n\nStudent URL:\n$URL\n\nShare the student URL with all students." \
            --width=320 2>/dev/null &
        xdg-open "$URL/admin" 2>/dev/null || firefox "$URL/admin" &
    else
        zenity --error \
            --title="CP Exam Platform" \
            --text="Server failed to start.\nRun: sudo journalctl -u $SERVICE -n 20" \
            --width=320 2>/dev/null
    fi
fi
LAUNCHEOF

chmod +x "$DIR/launch_gui.sh"

# Write .desktop file
cat > "$DESKTOP/CP Exam Platform.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=CP Exam Platform
Comment=Start / Stop the CP Exam server
Exec=bash "$DIR/launch_gui.sh"
Icon=applications-education
Terminal=false
Categories=Education;
StartupNotify=false
EOF

chmod +x "$DESKTOP/CP Exam Platform.desktop"
gio set "$DESKTOP/CP Exam Platform.desktop" metadata::trusted true 2>/dev/null || true

echo -e "${GREEN}  OK — icon on desktop${NC}"

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo -e "  Server URL    :  http://10.6.6.1:5000"
echo -e "  Admin login   :  admin / admin123"
echo -e "  Start method  :  Double-click 'CP Exam Platform' on desktop"
echo -e "  Service name  :  exam-platform-mtech"
echo ""
echo -e "${YELLOW}  Disconnect internet after setup.${NC}"
echo -e "${YELLOW}  All machines connect via LAN to http://10.6.6.1:5000${NC}"
echo ""
