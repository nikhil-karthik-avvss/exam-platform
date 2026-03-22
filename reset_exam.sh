#!/bin/bash
# ============================================================
#   CP Exam Platform — Reset Submissions
#   Clears all submissions for a new exam session.
#   Problems, test cases, and students are preserved.
# ============================================================

BOLD='\033[1m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo ""
echo -e "${YELLOW}This will DELETE all student submissions and run results.${NC}"
echo -e "${YELLOW}Problems, test cases, and students are kept.${NC}"
echo ""
read -p "Type YES to confirm: " confirm

if [ "$confirm" != "YES" ]; then
    echo "Cancelled."
    exit 0
fi

source venv/bin/activate
python3 - <<'EOF'
import sqlite3, os
conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), 'exam.db'))
conn.execute('DELETE FROM testcase_results')
conn.execute('DELETE FROM submissions')
conn.execute("DELETE FROM testcases WHERE type='custom'")
conn.execute('UPDATE exam_settings SET exam_active=0')
conn.commit()
conn.close()
print('Done. All submissions cleared, exam stopped.')
EOF

echo -e "${GREEN}Reset complete. Platform ready for a new exam session.${NC}"
echo ""
