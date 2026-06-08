from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import sqlite3, os, csv, io, re, random, string
from judge.runner import run_code
from judge.analyzer import analyze_complexity

app = Flask(__name__)
app.secret_key = "cp_exam_secret_2024"
DB = os.path.join(os.path.dirname(__file__), "exam.db")

# ── DB helpers ────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn

def normalize_output(s):
    """Strip each line, normalize list/comma formatting, trim trailing blank lines."""
    if not s:
        return ""
    lines = []
    for line in s.strip().splitlines():
        line = line.strip()
        line = re.sub(r'\s*,\s*', ',', line)
        line = re.sub(r'\[\s*', '[', line)
        line = re.sub(r'\s*\]', ']', line)
        lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)

def get_batch_for_roll(roll):
    """Detect batch from last 3 digits of roll number (001-032 = batch1, 033-062 = batch2)."""
    digits = re.sub(r'\D', '', str(roll))
    if digits:
        n = int(digits[-3:]) if len(digits) >= 3 else int(digits)
        if 1 <= n <= 32:
            return 'batch1'
        elif 33 <= n <= 62:
            return 'batch2'
    return None

def get_exam_active(settings, batch):
    if batch == 'batch1':
        return bool(settings['batch1_active'])
    elif batch == 'batch2':
        return bool(settings['batch2_active'])
    return bool(settings['exam_active'])

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_number TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'student',
            batch TEXT
        );
        CREATE TABLE IF NOT EXISTS problems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            input_format TEXT DEFAULT '',
            output_format TEXT DEFAULT '',
            constraints TEXT DEFAULT '',
            sample_explanation TEXT DEFAULT '',
            time_limit INTEGER DEFAULT 5,
            memory_limit INTEGER DEFAULT 256,
            active INTEGER DEFAULT 1,
            batch TEXT DEFAULT 'both',
            python_template TEXT DEFAULT '',
            java_template TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS testcases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id INTEGER NOT NULL,
            input TEXT NOT NULL,
            expected_output TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('public','private','custom')),
            label TEXT DEFAULT '',
            student_id INTEGER,
            FOREIGN KEY(problem_id) REFERENCES problems(id) ON DELETE CASCADE,
            FOREIGN KEY(student_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            problem_id INTEGER NOT NULL,
            language TEXT NOT NULL,
            code TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            score INTEGER DEFAULT 0,
            time_complexity TEXT DEFAULT '',
            space_complexity TEXT DEFAULT '',
            complexity_notes TEXT DEFAULT '',
            submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES users(id),
            FOREIGN KEY(problem_id) REFERENCES problems(id)
        );
        CREATE TABLE IF NOT EXISTS testcase_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            testcase_id INTEGER NOT NULL,
            passed INTEGER NOT NULL,
            stdout TEXT DEFAULT '',
            stderr TEXT DEFAULT '',
            exec_time REAL DEFAULT 0,
            FOREIGN KEY(submission_id) REFERENCES submissions(id) ON DELETE CASCADE,
            FOREIGN KEY(testcase_id) REFERENCES testcases(id)
        );
        CREATE TABLE IF NOT EXISTS exam_settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            exam_active INTEGER DEFAULT 0,
            batch1_active INTEGER DEFAULT 0,
            batch2_active INTEGER DEFAULT 0,
            exam_name TEXT DEFAULT 'Competitive Programming — End Semester Lab Exam'
        );
        INSERT OR IGNORE INTO exam_settings (id) VALUES (1);
        INSERT OR IGNORE INTO users (roll_number, name, password, role)
            VALUES ('admin', 'Professor', 'admin-password-cp-exam@123', 'admin');
        PRAGMA foreign_keys = ON;
    """)
    conn.commit()

    # Schema migrations — add columns to existing DB if needed
    for sql in [
        "ALTER TABLE users ADD COLUMN batch TEXT",
        "ALTER TABLE problems ADD COLUMN batch TEXT DEFAULT 'both'",
        "ALTER TABLE problems ADD COLUMN python_template TEXT DEFAULT ''",
        "ALTER TABLE problems ADD COLUMN java_template TEXT DEFAULT ''",
        "ALTER TABLE problems ADD COLUMN solution_code TEXT DEFAULT ''",
        "ALTER TABLE problems ADD COLUMN solution_language TEXT DEFAULT 'python'",
        "ALTER TABLE exam_settings ADD COLUMN batch1_active INTEGER DEFAULT 0",
        "ALTER TABLE exam_settings ADD COLUMN batch2_active INTEGER DEFAULT 0",
    ]:
        try:
            conn.execute(sql)
            conn.commit()
        except Exception:
            pass  # Column already exists

    # Auto-assign batch for existing students missing one
    students = conn.execute(
        "SELECT id, roll_number FROM users WHERE role='student' AND batch IS NULL"
    ).fetchall()
    for s in students:
        b = get_batch_for_roll(s['roll_number'])
        if b:
            conn.execute("UPDATE users SET batch=? WHERE id=?", (b, s['id']))
    if students:
        conn.commit()

    # Pre-load students if table is empty
    existing = conn.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0]
    if existing == 0:
        for i in range(1, 63):
            roll  = str(1000 + i)  # 1001 – 1062
            batch = 'batch1' if i <= 32 else 'batch2'
            conn.execute(
                "INSERT OR IGNORE INTO users (roll_number,name,password,role,batch) VALUES (?,?,?,'student',?)",
                (roll, f"Student {i}", roll, batch)
            )
        conn.commit()
        print("  Pre-loaded 62 students (1001 – 1062)")

    conn.close()

# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        roll = request.form["roll_number"].strip()
        pwd  = request.form["password"].strip()
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE roll_number=? AND password=?", (roll, pwd)
        ).fetchone()
        conn.close()
        if user:
            session.update({
                "user_id": user["id"],
                "roll":    user["roll_number"],
                "name":    user["name"],
                "role":    user["role"],
                "batch":   user["batch"],
            })
            return redirect(url_for("admin_dashboard" if user["role"] == "admin" else "student_dashboard"))
        flash("Invalid roll number or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ── Student ───────────────────────────────────────────────────────────────────

@app.route("/student")
def student_dashboard():
    if session.get("role") != "student":
        return redirect(url_for("login"))
    conn        = get_db()
    settings    = conn.execute("SELECT * FROM exam_settings WHERE id=1").fetchone()
    batch       = session.get("batch")
    exam_active = get_exam_active(settings, batch)

    problems = conn.execute(
        "SELECT * FROM problems WHERE active=1 AND (batch='both' OR batch=?) ORDER BY id",
        (batch or 'both',)
    ).fetchall()
    statuses = {}
    for p in problems:
        sub = conn.execute(
            "SELECT status FROM submissions WHERE student_id=? AND problem_id=? ORDER BY submitted_at DESC LIMIT 1",
            (session["user_id"], p["id"])
        ).fetchone()
        statuses[p["id"]] = sub["status"] if sub else None

    # When exam not active, fetch submissions to show instead
    my_submissions = []
    if not exam_active:
        my_submissions = conn.execute("""
            SELECT s.*, p.title FROM submissions s
            JOIN problems p ON s.problem_id=p.id
            WHERE s.student_id=?
            ORDER BY s.submitted_at DESC
        """, (session["user_id"],)).fetchall()

    conn.close()
    return render_template("student/dashboard.html", problems=problems,
                           settings=settings, statuses=statuses,
                           exam_active=exam_active, student_batch=batch,
                           my_submissions=my_submissions)

@app.route("/student/problem/<int:pid>")
def problem_detail(pid):
    if session.get("role") != "student":
        return redirect(url_for("login"))
    conn        = get_db()
    settings    = conn.execute("SELECT * FROM exam_settings WHERE id=1").fetchone()
    batch       = session.get("batch")
    exam_active = get_exam_active(settings, batch)

    if not exam_active:
        conn.close()
        flash("The exam is not active. You can only view your submissions.", "error")
        return redirect(url_for("student_dashboard"))

    problem = conn.execute("SELECT * FROM problems WHERE id=? AND active=1", (pid,)).fetchone()
    if not problem:
        flash("Problem not found.", "error")
        return redirect(url_for("student_dashboard"))

    pub_tcs  = conn.execute("SELECT * FROM testcases WHERE problem_id=? AND type='public'", (pid,)).fetchall()
    cust_tcs = conn.execute(
        "SELECT * FROM testcases WHERE problem_id=? AND type='custom' AND student_id=?",
        (pid, session["user_id"])
    ).fetchall()
    submissions = conn.execute(
        "SELECT * FROM submissions WHERE student_id=? AND problem_id=? ORDER BY submitted_at DESC",
        (session["user_id"], pid)
    ).fetchall()
    last_sub = submissions[0] if submissions else None
    conn.close()

    read_only = not exam_active
    return render_template("student/problem.html", problem=problem,
                           pub_tcs=pub_tcs, cust_tcs=cust_tcs, submissions=submissions,
                           last_sub=last_sub, read_only=read_only, exam_active=exam_active)

@app.route("/student/run", methods=["POST"])
def student_run():
    if session.get("role") != "student":
        return jsonify({"error": "Unauthorized"}), 403
    d      = request.json
    result = run_code(d.get("code",""), d.get("language","python"), d.get("input",""))
    passed = None
    if d.get("expected") and result["stdout"] is not None:
        passed = normalize_output(result["stdout"]) == normalize_output(d["expected"])
    return jsonify({**result, "passed": passed})

@app.route("/student/add_custom_tc", methods=["POST"])
def add_custom_tc():
    if session.get("role") != "student":
        return jsonify({"error": "Unauthorized"}), 403
    d = request.json
    if not d.get("input","").strip():
        return jsonify({"error": "Input cannot be empty"}), 400
    conn = get_db()
    conn.execute(
        "INSERT INTO testcases (problem_id,input,expected_output,type,label,student_id) VALUES (?,?,?,?,?,?)",
        (d["problem_id"], d["input"], d.get("expected_output",""), "custom",
         d.get("label","Custom"), session["user_id"])
    )
    conn.commit()
    tc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return jsonify({"success": True, "id": tc_id})

@app.route("/student/delete_custom_tc/<int:tc_id>", methods=["DELETE"])
def delete_custom_tc(tc_id):
    if session.get("role") != "student":
        return jsonify({"error": "Unauthorized"}), 403
    conn = get_db()
    conn.execute("DELETE FROM testcases WHERE id=? AND student_id=? AND type='custom'",
                 (tc_id, session["user_id"]))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/student/submit", methods=["POST"])
def student_submit():
    if session.get("role") != "student":
        return jsonify({"error": "Unauthorized"}), 403

    conn     = get_db()
    settings = conn.execute("SELECT * FROM exam_settings WHERE id=1").fetchone()
    if not get_exam_active(settings, session.get("batch")):
        conn.close()
        return jsonify({"error": "Exam is not active."}), 403

    d        = request.json
    code     = d.get("code","")
    language = d.get("language","python")
    pid      = d.get("problem_id")

    problem = conn.execute("SELECT * FROM problems WHERE id=?", (pid,)).fetchone()
    pub_tcs = conn.execute("SELECT * FROM testcases WHERE problem_id=? AND type='public'", (pid,)).fetchall()
    prv_tcs = conn.execute("SELECT * FROM testcases WHERE problem_id=? AND type='private'", (pid,)).fetchall()
    all_tcs = list(pub_tcs) + list(prv_tcs)

    results   = []
    passed_ct = 0

    for tc in all_tcs:
        res    = run_code(code, language, tc["input"],
                          time_limit=problem["time_limit"],
                          memory_limit=problem["memory_limit"])
        passed = (res["stdout"] is not None and
                  normalize_output(res["stdout"]) == normalize_output(tc["expected_output"]))
        if passed:
            passed_ct += 1
        results.append({
            "tc_id":     tc["id"],
            "type":      tc["type"],
            "passed":    passed,
            "stdout":    res["stdout"],
            "stderr":    res["stderr"],
            "exec_time": res["exec_time"],
        })

    # Empirical timing: pairs of (input_text, exec_time) for the analyzer
    tc_input_map = {tc["id"]: tc["input"] for tc in all_tcs}
    tc_timings   = [(tc_input_map[r["tc_id"]], r["exec_time"])
                    for r in results if r["exec_time"] > 0]
    complexity = analyze_complexity(code, language, tc_timings=tc_timings)

    total  = len(all_tcs)
    score  = int(passed_ct / total * 100) if total else 0
    status = "Accepted" if passed_ct == total and total > 0 else f"{passed_ct}/{total} Passed"

    conn.execute("""
        INSERT INTO submissions
        (student_id,problem_id,language,code,status,score,time_complexity,space_complexity,complexity_notes)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (session["user_id"], pid, language, code, status, score,
          complexity["time"], complexity["space"], complexity["notes"]))
    conn.commit()
    sub_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for r in results:
        conn.execute("""
            INSERT INTO testcase_results (submission_id,testcase_id,passed,stdout,stderr,exec_time)
            VALUES (?,?,?,?,?,?)
        """, (sub_id, r["tc_id"], int(r["passed"]),
              r["stdout"] or "", r["stderr"] or "", r["exec_time"]))
    conn.commit()
    conn.close()

    return jsonify({
        "submission_id":    sub_id,
        "status":           status,
        "score":            score,
        "time_complexity":  complexity["time"],
        "space_complexity": complexity["space"],
        "complexity_notes": complexity["notes"],
        "public_results":   [r for r in results if r["type"] == "public"],
        "private_results":  [{"passed": r["passed"]} for r in results if r["type"] == "private"],
        "passed":           passed_ct,
        "total":            total,
    })

@app.route("/student/submission/<int:sub_id>")
def student_submission(sub_id):
    if session.get("role") != "student":
        return redirect(url_for("login"))
    conn = get_db()
    sub  = conn.execute("""
        SELECT s.*, p.title FROM submissions s
        JOIN problems p ON s.problem_id=p.id
        WHERE s.id=? AND s.student_id=?
    """, (sub_id, session["user_id"])).fetchone()
    if not sub:
        flash("Submission not found.", "error")
        return redirect(url_for("student_dashboard"))
    results = conn.execute("""
        SELECT tr.*, tc.type, tc.input, tc.expected_output, tc.label
        FROM testcase_results tr JOIN testcases tc ON tr.testcase_id=tc.id
        WHERE tr.submission_id=?
    """, (sub_id,)).fetchall()
    conn.close()
    return render_template("student/submission.html", sub=sub, results=results)

# ── Admin ─────────────────────────────────────────────────────────────────────

@app.route("/admin")
def admin_dashboard():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    conn      = get_db()
    problems  = conn.execute("SELECT * FROM problems ORDER BY id").fetchall()
    students  = conn.execute("SELECT * FROM users WHERE role='student' ORDER BY roll_number").fetchall()
    settings  = conn.execute("SELECT * FROM exam_settings WHERE id=1").fetchone()
    sub_count = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
    b1_count  = conn.execute("SELECT COUNT(*) FROM users WHERE role='student' AND batch='batch1'").fetchone()[0]
    b2_count  = conn.execute("SELECT COUNT(*) FROM users WHERE role='student' AND batch='batch2'").fetchone()[0]
    conn.close()
    return render_template("admin/dashboard.html", problems=problems, students=students,
                           settings=settings, sub_count=sub_count,
                           b1_count=b1_count, b2_count=b2_count)

@app.route("/admin/toggle_exam/<batch>", methods=["POST"])
def toggle_batch_exam(batch):
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    if batch not in ('batch1', 'batch2'):
        return redirect(url_for("admin_dashboard"))
    col  = "batch1_active" if batch == "batch1" else "batch2_active"
    conn = get_db()
    cur  = conn.execute(f"SELECT {col} FROM exam_settings WHERE id=1").fetchone()
    new  = 0 if cur[col] else 1
    conn.execute(f"UPDATE exam_settings SET {col}=? WHERE id=1", (new,))
    conn.commit()
    conn.close()
    label = "Batch 1" if batch == "batch1" else "Batch 2"
    flash(f"{label} exam {'started' if new else 'stopped'}.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/problem/new", methods=["GET","POST"])
def new_problem():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    if request.method == "POST":
        f = request.form
        conn = get_db()
        conn.execute("""
            INSERT INTO problems
            (title,description,input_format,output_format,constraints,sample_explanation,
             time_limit,memory_limit,batch,python_template,java_template,
             solution_code,solution_language)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (f["title"], f["description"], f.get("input_format",""),
              f.get("output_format",""), f.get("constraints",""),
              f.get("sample_explanation",""),
              int(f.get("time_limit",5)), int(f.get("memory_limit",256)),
              f.get("batch","both"),
              f.get("python_template",""), f.get("java_template",""),
              f.get("solution_code",""), f.get("solution_language","python")))
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        flash("Problem created successfully.", "success")
        return redirect(url_for("edit_problem", pid=pid))
    return render_template("admin/problem_form.html", problem=None, pub_tcs=[], priv_tcs=[])

@app.route("/admin/problem/<int:pid>/edit", methods=["GET","POST"])
def edit_problem(pid):
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    conn = get_db()
    if request.method == "POST":
        f = request.form
        conn.execute("""
            UPDATE problems SET title=?,description=?,input_format=?,output_format=?,
            constraints=?,sample_explanation=?,time_limit=?,memory_limit=?,active=?,
            batch=?,python_template=?,java_template=?,
            solution_code=?,solution_language=?
            WHERE id=?
        """, (f["title"], f["description"], f.get("input_format",""),
              f.get("output_format",""), f.get("constraints",""),
              f.get("sample_explanation",""),
              int(f.get("time_limit",5)), int(f.get("memory_limit",256)),
              int(f.get("active",1)),
              f.get("batch","both"),
              f.get("python_template",""), f.get("java_template",""),
              f.get("solution_code",""), f.get("solution_language","python"),
              pid))
        conn.commit()
        flash("Problem updated.", "success")
    problem  = conn.execute("SELECT * FROM problems WHERE id=?", (pid,)).fetchone()
    pub_tcs  = conn.execute("SELECT * FROM testcases WHERE problem_id=? AND type='public'", (pid,)).fetchall()
    priv_tcs = conn.execute("SELECT * FROM testcases WHERE problem_id=? AND type='private'", (pid,)).fetchall()
    conn.close()
    return render_template("admin/problem_form.html", problem=problem,
                           pub_tcs=pub_tcs, priv_tcs=priv_tcs)

@app.route("/admin/problem/<int:pid>/delete", methods=["POST"])
def delete_problem(pid):
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    conn = get_db()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("""
        DELETE FROM testcase_results WHERE submission_id IN
        (SELECT id FROM submissions WHERE problem_id=?)
    """, (pid,))
    conn.execute("DELETE FROM submissions WHERE problem_id=?", (pid,))
    conn.execute("DELETE FROM testcases WHERE problem_id=?", (pid,))
    conn.execute("DELETE FROM problems WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    flash("Problem deleted.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/problem/<int:pid>/run_solution", methods=["POST"])
def run_solution(pid):
    if session.get("role") != "admin":
        return jsonify({"error": "Unauthorized"}), 403
    conn    = get_db()
    problem = conn.execute(
        "SELECT solution_code, solution_language FROM problems WHERE id=?", (pid,)
    ).fetchone()
    conn.close()
    if not problem or not (problem["solution_code"] or "").strip():
        return jsonify({"error": "No reference solution saved for this problem."}), 400
    d      = request.json or {}
    result = run_code(problem["solution_code"], problem["solution_language"],
                      d.get("input", ""))
    if result.get("error"):
        return jsonify({"error": result["stderr"] or "Runtime error in solution."})
    output = (result["stdout"] or "").rstrip("\n")
    return jsonify({"output": output})

@app.route("/admin/problem/<int:pid>/add_tc", methods=["POST"])
def add_testcase(pid):
    if session.get("role") != "admin":
        return jsonify({"error":"Unauthorized"}), 403
    d   = request.json or {}
    inp = d.get("input","").strip()
    if not inp:
        return jsonify({"error":"Input is required"}), 400

    expected = d.get("expected_output","").strip()

    # Auto-generate expected output from reference solution when not provided
    if not expected:
        conn    = get_db()
        problem = conn.execute(
            "SELECT solution_code, solution_language FROM problems WHERE id=?", (pid,)
        ).fetchone()
        conn.close()
        if problem and (problem["solution_code"] or "").strip():
            res = run_code(problem["solution_code"], problem["solution_language"], inp)
            if res["stdout"] is not None:
                expected = res["stdout"].rstrip("\n")

    if not expected:
        return jsonify({"error": "Expected output is required (or save a reference solution first to auto-generate)."}), 400

    conn = get_db()
    conn.execute(
        "INSERT INTO testcases (problem_id,input,expected_output,type,label) VALUES (?,?,?,?,?)",
        (pid, inp, expected, d.get("type","public"), d.get("label",""))
    )
    conn.commit()
    tc_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return jsonify({"success": True, "id": tc_id, "generated": not d.get("expected_output","").strip()})

@app.route("/admin/testcase/<int:tc_id>/delete", methods=["DELETE"])
def delete_testcase(tc_id):
    if session.get("role") != "admin":
        return jsonify({"error":"Unauthorized"}), 403
    conn = get_db()
    conn.execute("DELETE FROM testcases WHERE id=?", (tc_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/admin/students", methods=["GET","POST"])
def manage_students():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    conn = get_db()
    if request.method == "POST":
        roll  = request.form["roll_number"].strip()
        name  = request.form["name"].strip()
        pwd   = request.form.get("password","").strip() or roll
        batch = request.form.get("batch","") or get_batch_for_roll(roll)
        try:
            conn.execute(
                "INSERT INTO users (roll_number,name,password,role,batch) VALUES (?,?,?,'student',?)",
                (roll, name, pwd, batch)
            )
            conn.commit()
            flash(f"Student {name} ({roll}) added.", "success")
        except Exception:
            flash("Roll number already exists.", "error")
    students = conn.execute(
        "SELECT * FROM users WHERE role='student' ORDER BY roll_number"
    ).fetchall()
    conn.close()
    return render_template("admin/students.html", students=students)

@app.route("/admin/student/<int:sid>/delete", methods=["POST"])
def delete_student(sid):
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=? AND role='student'", (sid,))
    conn.commit()
    conn.close()
    flash("Student removed.", "success")
    return redirect(url_for("manage_students"))

@app.route("/admin/student/<int:sid>/reset_password", methods=["POST"])
def reset_password(sid):
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    conn    = get_db()
    student = conn.execute("SELECT roll_number FROM users WHERE id=?", (sid,)).fetchone()
    if student:
        conn.execute("UPDATE users SET password=? WHERE id=?", (student["roll_number"], sid))
        conn.commit()
        flash(f"Password reset to roll number for {student['roll_number']}.", "success")
    conn.close()
    return redirect(url_for("manage_students"))

@app.route("/admin/student/<int:sid>/edit", methods=["POST"])
def edit_student(sid):
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    conn  = get_db()
    name  = request.form.get("name","").strip()
    batch = request.form.get("batch","").strip()
    pwd   = request.form.get("password","").strip()
    if name:
        conn.execute("UPDATE users SET name=? WHERE id=?", (name, sid))
    if batch:
        conn.execute("UPDATE users SET batch=? WHERE id=?", (batch, sid))
    if pwd:
        conn.execute("UPDATE users SET password=? WHERE id=?", (pwd, sid))
    conn.commit()
    conn.close()
    flash("Student updated.", "success")
    return redirect(url_for("manage_students"))

@app.route("/admin/randomize_passwords", methods=["POST"])
def randomize_passwords():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    conn     = get_db()
    students = conn.execute(
        "SELECT id, roll_number, name FROM users WHERE role='student' ORDER BY roll_number"
    ).fetchall()
    new_pwds = []
    for s in students:
        pwd = ''.join(random.choices(string.ascii_uppercase, k=4))
        conn.execute("UPDATE users SET password=? WHERE id=?", (pwd, s["id"]))
        new_pwds.append({"roll_number": s["roll_number"], "name": s["name"], "password": pwd})
    conn.commit()
    conn.close()
    return render_template("admin/passwords.html", passwords=new_pwds)

@app.route("/admin/submissions")
def admin_submissions():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    conn   = get_db()
    pid    = request.args.get("problem_id","")
    sid    = request.args.get("student_id","")
    batch  = request.args.get("batch","")
    query  = """
        SELECT s.*, u.name, u.roll_number, u.batch AS student_batch, p.title
        FROM submissions s
        JOIN users u ON s.student_id=u.id
        JOIN problems p ON s.problem_id=p.id
    """
    params, filters = [], []
    if pid:
        filters.append("s.problem_id=?"); params.append(pid)
    if sid:
        filters.append("s.student_id=?"); params.append(sid)
    if batch:
        filters.append("u.batch=?"); params.append(batch)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY s.submitted_at DESC"
    submissions = conn.execute(query, params).fetchall()
    problems    = conn.execute("SELECT id, title FROM problems ORDER BY id").fetchall()
    students    = conn.execute(
        "SELECT id, name, roll_number FROM users WHERE role='student' ORDER BY roll_number"
    ).fetchall()
    conn.close()
    return render_template("admin/submissions.html", submissions=submissions,
                           problems=problems, students=students,
                           sel_pid=pid, sel_sid=sid, sel_batch=batch)

@app.route("/admin/submission/<int:sub_id>")
def admin_submission_detail(sub_id):
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    conn = get_db()
    sub  = conn.execute("""
        SELECT s.*, u.name, u.roll_number, p.title
        FROM submissions s JOIN users u ON s.student_id=u.id
        JOIN problems p ON s.problem_id=p.id
        WHERE s.id=?
    """, (sub_id,)).fetchone()
    results = conn.execute("""
        SELECT tr.*, tc.type, tc.input, tc.expected_output, tc.label
        FROM testcase_results tr JOIN testcases tc ON tr.testcase_id=tc.id
        WHERE tr.submission_id=?
    """, (sub_id,)).fetchall()
    conn.close()
    return render_template("admin/submission_detail.html", sub=sub, results=results)

@app.route("/admin/batch/<batch>/results")
def batch_results(batch):
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    if batch not in ('batch1', 'batch2'):
        return redirect(url_for("admin_dashboard"))
    conn     = get_db()
    students = conn.execute(
        "SELECT * FROM users WHERE role='student' AND batch=? ORDER BY roll_number", (batch,)
    ).fetchall()
    problems = conn.execute(
        "SELECT * FROM problems WHERE active=1 AND (batch='both' OR batch=?) ORDER BY id", (batch,)
    ).fetchall()
    results = {}
    for s in students:
        results[s['id']] = {}
        for p in problems:
            best = conn.execute("""
                SELECT status, score, time_complexity, space_complexity
                FROM submissions WHERE student_id=? AND problem_id=?
                ORDER BY score DESC, submitted_at DESC LIMIT 1
            """, (s['id'], p['id'])).fetchone()
            results[s['id']][p['id']] = dict(best) if best else None
    conn.close()
    return render_template("admin/batch_results.html",
                           batch=batch, students=students,
                           problems=problems, results=results)

@app.route("/admin/export_csv")
def export_csv():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    from flask import make_response
    conn  = get_db()
    batch = request.args.get("batch","")
    query = """
        SELECT u.roll_number, u.name, u.batch, p.title, s.language, s.status, s.score,
               s.time_complexity, s.space_complexity, s.submitted_at
        FROM submissions s
        JOIN users u ON s.student_id=u.id
        JOIN problems p ON s.problem_id=p.id
    """
    params = []
    if batch:
        query += " WHERE u.batch=?"
        params.append(batch)
    query += " ORDER BY u.roll_number, p.id, s.submitted_at"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    out = io.StringIO()
    w   = csv.writer(out)
    w.writerow(["Roll Number","Name","Batch","Problem","Language","Status","Score (%)",
                "Time Complexity","Space Complexity","Submitted At"])
    for r in rows:
        w.writerow(list(r))
    resp = make_response(out.getvalue())
    resp.headers["Content-Type"] = "text/csv"
    resp.headers["Content-Disposition"] = "attachment; filename=exam_results.csv"
    return resp

@app.route("/admin/server_info")
def server_info():
    if session.get("role") != "admin":
        return jsonify({"error": "Unauthorized"}), 403
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.6.6.1", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "localhost"
    return jsonify({"url": f"http://{ip}:5000", "ip": ip})

if __name__ == "__main__":
    init_db()
    import socket
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "unknown"
    print("\n" + "="*56)
    print("  Competitive Programming Exam Platform")
    print("  OFFLINE MODE — No internet required")
    print("="*56)
    print(f"  Local  : http://localhost:5000")
    print(f"  Network: http://{local_ip}:5000")
    print(f"  Admin  : roll=admin  password=admin-password-cp-exam@123")
    print("="*56 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
