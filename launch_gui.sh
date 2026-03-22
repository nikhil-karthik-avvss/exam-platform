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
