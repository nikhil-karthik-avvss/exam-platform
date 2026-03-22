#!/usr/bin/env python3
"""
Bulk import students from a CSV file.

CSV format (no header row needed, or with header):
    roll_number,name,password

If password column is missing, roll_number is used as password.

Usage:
    python3 import_students.py students.csv
"""

import csv, sqlite3, sys, os

DB = os.path.join(os.path.dirname(__file__), "exam.db")

if len(sys.argv) < 2:
    print("Usage: python3 import_students.py <students.csv>")
    print("\nCSV format:  roll_number,name[,password]")
    print("If password is omitted, roll_number is used as password.")
    sys.exit(1)

csv_file = sys.argv[1]
if not os.path.exists(csv_file):
    print(f"File not found: {csv_file}")
    sys.exit(1)

if not os.path.exists(DB):
    print("exam.db not found. Please run setup.sh first.")
    sys.exit(1)

conn = sqlite3.connect(DB)
added = 0
skipped = 0

with open(csv_file, newline='', encoding='utf-8') as f:
    reader = csv.reader(f)
    for row in reader:
        if not row or not row[0].strip():
            continue
        roll = row[0].strip()
        # Skip header row
        if roll.lower() in ('roll_number', 'roll', 'rollno', 'id'):
            continue
        name = row[1].strip() if len(row) > 1 else roll
        pwd  = row[2].strip() if len(row) > 2 and row[2].strip() else roll
        try:
            conn.execute(
                "INSERT INTO users (roll_number, name, password, role) VALUES (?,?,?,'student')",
                (roll, name, pwd)
            )
            added += 1
            print(f"  Added: {roll} — {name}")
        except sqlite3.IntegrityError:
            skipped += 1
            print(f"  Skip:  {roll} (already exists)")

conn.commit()
conn.close()

print(f"\nDone. Added: {added}, Skipped (duplicate): {skipped}")
