import subprocess, tempfile, os, time, resource, signal

def run_code(code: str, language: str, stdin_input: str = "",
             time_limit: int = 5, memory_limit: int = 256) -> dict:
    """
    Executes code in a sandboxed subprocess.
    Returns: {stdout, stderr, exec_time, error}
    """
    try:
        if language == "python":
            return _run_python(code, stdin_input, time_limit, memory_limit)
        elif language == "java":
            return _run_java(code, stdin_input, time_limit, memory_limit)
        else:
            return {"stdout": None, "stderr": "Unsupported language", "exec_time": 0, "error": "unsupported_language"}
    except Exception as e:
        return {"stdout": None, "stderr": str(e), "exec_time": 0, "error": "internal_error"}


def _set_limits(memory_mb):
    """Set memory and CPU limits for child process (Linux only)."""
    try:
        mem_bytes = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))  # no core dumps
    except Exception:
        pass


def _run_python(code, stdin_input, time_limit, memory_limit):
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "solution.py")
        with open(src, "w") as f:
            f.write(code)

        start = time.time()
        try:
            proc = subprocess.run(
                ["python3", "-W", "ignore", src],
                input=stdin_input,
                capture_output=True,
                text=True,
                timeout=time_limit,
                cwd=tmpdir,
                preexec_fn=lambda: _set_limits(memory_limit)
            )
            elapsed = time.time() - start
            return {
                "stdout":    proc.stdout,
                "stderr":    proc.stderr[:2000] if proc.stderr else "",
                "exec_time": round(elapsed, 4),
                "error":     None
            }
        except subprocess.TimeoutExpired:
            return {"stdout": None, "stderr": f"Time Limit Exceeded ({time_limit}s)", "exec_time": time_limit, "error": "tle"}
        except MemoryError:
            return {"stdout": None, "stderr": "Memory Limit Exceeded", "exec_time": 0, "error": "mle"}


def _run_java(code, stdin_input, time_limit, memory_limit):
    with tempfile.TemporaryDirectory() as tmpdir:
        # Detect public class name
        import re
        match = re.search(r'public\s+class\s+(\w+)', code)
        classname = match.group(1) if match else "Main"
        src = os.path.join(tmpdir, f"{classname}.java")
        with open(src, "w") as f:
            f.write(code)

        # Compile
        compile_result = subprocess.run(
            ["javac", src],
            capture_output=True, text=True, timeout=30, cwd=tmpdir
        )
        if compile_result.returncode != 0:
            return {
                "stdout":    None,
                "stderr":    compile_result.stderr[:2000],
                "exec_time": 0,
                "error":     "compile_error"
            }

        # Run
        start = time.time()
        try:
            proc = subprocess.run(
                ["java", f"-Xmx{memory_limit}m", "-cp", tmpdir, classname],
                input=stdin_input,
                capture_output=True,
                text=True,
                timeout=time_limit,
                cwd=tmpdir
            )
            elapsed = time.time() - start
            return {
                "stdout":    proc.stdout,
                "stderr":    proc.stderr[:2000] if proc.stderr else "",
                "exec_time": round(elapsed, 4),
                "error":     None
            }
        except subprocess.TimeoutExpired:
            return {"stdout": None, "stderr": f"Time Limit Exceeded ({time_limit}s)", "exec_time": time_limit, "error": "tle"}
