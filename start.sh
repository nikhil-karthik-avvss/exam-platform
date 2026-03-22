#!/bin/bash
# ============================================================
#   CP Exam Platform — Start / Stop via terminal
#   Service name: exam-platform-mtech
#   Usage: bash start.sh [start|stop|status|restart]
# ============================================================

BOLD='\033[1m'; CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
SERVICE="exam-platform-mtech"
URL="http://10.6.6.1:5000"

ACTION="${1:-start}"

case "$ACTION" in
  start)
    echo -e "${CYAN}Starting $SERVICE...${NC}"
    sudo systemctl start "$SERVICE"
    sleep 1
    if systemctl is-active --quiet "$SERVICE"; then
        echo -e "${GREEN}Server is running.${NC}"
        echo ""
        echo -e "  Admin panel  : ${BOLD}$URL/admin${NC}"
        echo -e "  Student URL  : ${BOLD}$URL${NC}"
        echo -e "  Admin login  : admin / admin123"
    else
        echo -e "${RED}Server failed to start.${NC}"
        echo "Check logs: sudo journalctl -u $SERVICE -n 30"
    fi
    ;;
  stop)
    echo -e "${CYAN}Stopping $SERVICE...${NC}"
    sudo systemctl stop "$SERVICE"
    echo -e "${GREEN}Stopped.${NC}"
    ;;
  restart)
    sudo systemctl restart "$SERVICE"
    echo -e "${GREEN}Restarted.${NC}"
    ;;
  status)
    systemctl status "$SERVICE"
    ;;
  *)
    echo "Usage: bash start.sh [start|stop|restart|status]"
    ;;
esac
