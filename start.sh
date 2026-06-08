#!/bin/bash
# ============================================================
#   CP Exam Platform — Start / Stop
#   Service: exam-platform-mtech  (systemd, auto-starts on boot)
#
#   Usage: bash start.sh [start|stop|restart|status|logs]
#
#   ⚠  DO NOT use "kill -9" to stop the server.
#      The service has Restart=on-failure, so systemd will
#      bring it back automatically after a kill.
#      Use:  bash start.sh stop
# ============================================================

BOLD='\033[1m'; CYAN='\033[0;36m'; GREEN='\033[0;32m'
RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

SERVICE="exam-platform-mtech"
# Auto-detect the machine's LAN IP
LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
URL="http://${LAN_IP:-localhost}:5000"

ACTION="${1:-start}"

case "$ACTION" in

  start)
    # If already running, just print info and exit
    if systemctl is-active --quiet "$SERVICE"; then
        echo -e "${YELLOW}Server is already running.${NC}"
        echo -e "  Stop first with:  ${BOLD}bash start.sh stop${NC}"
        echo ""
        echo -e "  Admin panel  : ${BOLD}$URL/admin${NC}"
        echo -e "  Student URL  : ${BOLD}$URL${NC}"
        exit 0
    fi

    # Clear any stray process on port 5000 that isn't owned by systemd
    fuser -k 5000/tcp 2>/dev/null
    sleep 0.5

    echo -e "${CYAN}Starting $SERVICE...${NC}"
    # Reset failed state so systemctl start works even after a crash
    sudo systemctl reset-failed "$SERVICE" 2>/dev/null
    sudo systemctl start "$SERVICE"
    sleep 2

    if systemctl is-active --quiet "$SERVICE"; then
        echo -e "${GREEN}✓ Server is running.${NC}"
        echo ""
        echo -e "  Admin panel  : ${BOLD}$URL/admin${NC}"
        echo -e "  Student URL  : ${BOLD}$URL${NC}"
        echo -e "  Admin login  : ${BOLD}admin / admin-password-cp-exam@123${NC}"
        echo ""
        echo -e "${CYAN}The server will restart automatically on reboot.${NC}"
        echo -e "  To stop : ${BOLD}bash start.sh stop${NC}"
        echo -e "  Logs    : ${BOLD}bash start.sh logs${NC}"
    else
        echo -e "${RED}✗ Server failed to start.${NC}"
        echo "  Check logs: sudo journalctl -u $SERVICE -n 30"
        exit 1
    fi
    ;;

  stop)
    echo -e "${CYAN}Stopping $SERVICE...${NC}"
    sudo systemctl stop "$SERVICE"
    # Belt-and-suspenders: also clear port 5000
    fuser -k 5000/tcp 2>/dev/null
    echo -e "${GREEN}✓ Stopped.${NC}"
    echo -e "  To start again: ${BOLD}bash start.sh${NC}"
    ;;

  restart)
    echo -e "${CYAN}Restarting $SERVICE...${NC}"
    sudo systemctl reset-failed "$SERVICE" 2>/dev/null
    sudo systemctl restart "$SERVICE"
    sleep 2
    if systemctl is-active --quiet "$SERVICE"; then
        echo -e "${GREEN}✓ Restarted.${NC}"
    else
        echo -e "${RED}✗ Restart failed.${NC}"
        echo "  sudo journalctl -u $SERVICE -n 30"
        exit 1
    fi
    ;;

  status)
    systemctl status "$SERVICE"
    ;;

  logs)
    sudo journalctl -u "$SERVICE" -n 50 --no-pager
    ;;

  *)
    echo "Usage: bash start.sh [start|stop|restart|status|logs]"
    ;;

esac
