# CP Exam Platform

**Competitive Programming — End Semester Lab Practical Exam**
**Service name: exam-platform-mtech**

> Offline Mode — No internet is used or required during the exam.

---

## Architecture

```
          ┌─────────────────────────────┐
          │  Ubuntu Machine: 10.6.6.1   │
          │  exam-platform-mtech        │
          │  (Flask server + SQLite DB) │
          │  Desktop icon → start/stop  │
          └──────────────┬──────────────┘
                         │  LAN (no internet)
         ┌───────────────┼────────────────┐
         │               │                │
  Professor (Windows)  10.6.6.2 ...  10.6.6.40
  Browser →            Student PCs (Ubuntu)
  http://10.6.6.1:5000  Browser → http://10.6.6.1:5000
```

- The **server runs permanently on 10.6.6.1** as a systemd service.
- Everyone — professor and students — connects via browser to `http://10.6.6.1:5000`.
- Internet is blocked on student machines via UFW. LAN is unaffected.
- Start/stop is done by **double-clicking the desktop icon on 10.6.6.1**.

---

## One-Time Setup on 10.6.6.1 (needs internet)

```bash
bash setup.sh
```

This will:
1. Install Python 3 and Java (if not already present)
2. Create a Python virtual environment and install Flask
3. Download CodeMirror editor assets for offline use
4. Initialize the SQLite database and pre-load 62 students
5. Register the systemd service `exam-platform-mtech` (auto-starts on boot)
6. Create a desktop launcher icon on the 10.6.6.1 desktop

After setup, disconnect internet. The platform runs fully offline.

---

## Starting and Stopping the Server

**Double-click "CP Exam Platform" on the desktop of 10.6.6.1.**

A dialog will appear:
- If the server is **stopped**: click "Start Server" — browser opens to admin panel automatically
- If the server is **running**: click "Open admin panel" or "Stop the server"

**Terminal alternative:**
```bash
bash start.sh start    # start
bash start.sh stop     # stop
bash start.sh status   # check if running
bash start.sh restart  # restart
```

**The service auto-starts on every boot** — so after rebooting 10.6.6.1, the server is already running. No need to click anything unless you want to stop it.

---

## Accessing the Platform

| Who | URL |
|-----|-----|
| Professor (Windows browser) | http://10.6.6.1:5000 |
| Students (Ubuntu browser) | http://10.6.6.1:5000 |
| Admin panel | http://10.6.6.1:5000/admin |

---

## Login Credentials

| Role | ID | Password |
|------|----|----------|
| Professor | `admin` | `admin123` |
| Students | Roll number | Roll number (default) |

**Pre-loaded students:** 3122237001001 to 3122237001062 (62 students)

---

## Disabling Internet on Student Machines

**Option A — UFW (recommended: blocks internet, LAN to 10.6.6.1 still works):**
```bash
sudo ufw enable
sudo ufw default deny outgoing
sudo ufw allow out to 10.6.6.0/24
```

**Option B — Stop NetworkManager (blocks everything including LAN — use only if server is on same machine):**
```bash
sudo systemctl stop NetworkManager
```

Use Option A. It blocks internet while keeping LAN access to the server alive.

---

## Professor Workflow

1. Run `setup.sh` once on 10.6.6.1 (with internet, before exam day)
2. Login to `http://10.6.6.1:5000` as admin from any machine
3. Create problems, add public and private test cases
4. On exam day: double-click the desktop icon on 10.6.6.1 → Start Server
5. Click **Start Exam** on the dashboard
6. Students open `http://10.6.6.1:5000` and log in
7. After exam: view submissions, complexity analysis, export CSV

---

## Problems — Add / Edit / Delete

| Action | How |
|--------|-----|
| Add | Dashboard → New Problem |
| Edit | Dashboard → Edit |
| Hide from students | Edit → Visibility → Hidden |
| Delete permanently | Dashboard → Delete |

---

## Best Practices Marks (10 marks)

Displayed automatically on every submission. Professor awards marks manually based on:

| Detected Pattern | Complexity |
|---|---|
| No loops or recursion | O(1) |
| Binary search | O(log n) |
| Single loop | O(n) |
| Sorting | O(n log n) |
| Nested loops | O(n²) |
| Triple nested loops | O(n³) |
| Unoptimized recursion | O(2ⁿ) / O(n!) |
| DFS / BFS | O(V + E) |
| DP / memoization | O(n²) or O(n·m) |

---

## Reset for a New Exam Session

```bash
bash reset_exam.sh
```
Clears all submissions and custom test cases. Problems and students are preserved.

---

## Service Management (systemd)

```bash
sudo systemctl start   exam-platform-mtech
sudo systemctl stop    exam-platform-mtech
sudo systemctl restart exam-platform-mtech
sudo systemctl status  exam-platform-mtech
sudo journalctl -u     exam-platform-mtech -f   # live logs
```

---

## Bulk Import Students

```bash
python3 import_students.py students.csv
```

CSV format:
```
3122237001063,Student Name
3122237001064,Another Student,custom_password
```

---

## Files

```
exam-platform/
├── app.py                  Flask application (all routes)
├── judge/
│   ├── runner.py           Code execution engine (Python & Java)
│   └── analyzer.py         Time & Space complexity analyzer
├── templates/              HTML templates (student + admin)
├── static/
│   ├── css/style.css       Stylesheet
│   ├── js/app.js
│   ├── icon.png            Desktop launcher icon
│   └── codemirror/         Offline code editor assets
├── exam.db                 SQLite database (auto-created)
├── launch_gui.sh           Desktop icon launcher (created by setup.sh)
├── setup.sh                One-time setup (run on 10.6.6.1)
├── start.sh                Terminal start/stop/status
├── reset_exam.sh           Clear submissions
├── download_assets.py      Downloads CodeMirror (called by setup.sh)
└── import_students.py      Bulk student import from CSV
```
