import re, ast, subprocess, tempfile, os, time, math

# ─── Public API ───────────────────────────────────────────────────────────────

def analyze_complexity(code: str, language: str, tc_timings=None) -> dict:
    """
    Analyse time and space complexity.

    tc_timings: optional list of (input_str, exec_time_seconds) collected while
                judging all test cases.  Used for empirical curve-fitting first.
    Priority order:
      1. Empirical log-log regression on (input_length, exec_time) pairs
      2. Synthetic timing with two array-sized inputs  (Python only)
      3. Improved static AST / regex analysis
    """
    # 1 ── Empirical from actual test-case timings
    if tc_timings and len(tc_timings) >= 3:
        emp = _empirical_from_timings(tc_timings)
        if emp:
            static = _static_analysis(code, language)
            emp["space"] = static["space"]
            space_note = _space_note_only(static["notes"])
            if space_note:
                emp["notes"] += " | " + space_note
            return emp

    # 2 ── Synthetic timing (Python only; Java JVM startup makes it noisy)
    if language == "python":
        syn = _synthetic_timing_python(code)
        if syn:
            static = _analyze_python(code)
            syn["space"] = static["space"]
            space_note = _space_note_only(static["notes"])
            if space_note:
                syn["notes"] += " | " + space_note
            return syn

    # 3 ── Static analysis
    return _static_analysis(code, language)


# ─── Empirical: from actual test-case run timings ────────────────────────────

def _empirical_from_timings(tc_timings) -> dict | None:
    """
    tc_timings: [(input_str, exec_time), ...]
    Uses len(input_str) as a proxy for problem size n.
    Fits log T = alpha * log n + C  via least-squares, then classifies alpha.
    """
    valid = [(len(inp), t) for inp, t in tc_timings if t > 0.0003]
    if len(valid) < 3:
        return None

    sizes = [x[0] for x in valid]
    if max(sizes) < 3 * min(sizes):
        return None          # not enough size spread for reliable regression

    log_s = [math.log(max(s, 1)) for s, _ in valid]
    log_t = [math.log(max(t, 1e-9)) for _, t in valid]
    n = len(log_s)

    sx  = sum(log_s);  sy  = sum(log_t)
    sxx = sum(x*x for x in log_s)
    sxy = sum(x*y for x, y in zip(log_s, log_t))
    denom = n * sxx - sx * sx
    if denom == 0:
        return None

    alpha = (n * sxy - sx * sy) / denom
    time_class, note = _alpha_to_complexity(alpha)
    return {
        "time":  time_class,
        "notes": f"Empirical (α≈{alpha:.2f}, {n} test cases) → {note}",
    }


# ─── Empirical: synthetic timing (Python) ────────────────────────────────────

def _gen_array_input(n: int) -> str:
    """Most common CP format:  first line = n, second line = 1..n space-separated."""
    return f"{n}\n" + " ".join(str(i) for i in range(1, n + 1)) + "\n"


_TLE = "TLE"   # sentinel returned when the process times out

def _run_python_timed(code: str, stdin_text: str, timeout: float):
    """
    Return wall-clock seconds on success.
    Return _TLE  if the process times out.
    Return None  if the process crashes (wrong input format, RecursionError, etc.).
    """
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "sol.py")
        with open(src, "w") as f:
            f.write(code)
        try:
            t0 = time.perf_counter()
            proc = subprocess.run(
                ["python3", "-W", "ignore", src],
                input=stdin_text, capture_output=True, text=True,
                timeout=timeout, cwd=d,
            )
            elapsed = time.perf_counter() - t0
            return elapsed if proc.returncode == 0 else None
        except subprocess.TimeoutExpired:
            return _TLE
        except Exception:
            return None


_STARTUP_CODE = "import sys; sys.stdin.read(); print(0)"

def _measure_startup() -> float:
    """Measure Python subprocess startup overhead with a trivial program."""
    times = []
    for _ in range(2):
        t = _run_python_timed(_STARTUP_CODE, "1\n", timeout=5)
        if isinstance(t, float):
            times.append(t)
    return min(times) if times else 0.065  # conservative fallback


def _synthetic_timing_python(code: str) -> dict | None:
    """
    Run with n=300 and n=3000 (10× scale).  Subtract startup overhead so
    only actual computation time is used for the ratio.
    Falls back to None if startup dominates (fast O(1)/O(n)/O(n log n) code)
    or if the code crashes on synthetic input.
    """
    small_n, large_n = 300, 3000
    small_in = _gen_array_input(small_n)
    large_in = _gen_array_input(large_n)

    # Time the small run 3× (median) to reduce startup noise
    t_smalls = []
    for _ in range(3):
        t = _run_python_timed(code, small_in, timeout=4)
        if t is None or t is _TLE:
            return None          # code doesn't accept this input format
        t_smalls.append(t)
    t_smalls.sort()
    t_small = t_smalls[1]       # median

    # Time the large run once (allow generous timeout for O(n²) cases)
    t_large = _run_python_timed(code, large_in, timeout=8)

    startup = _measure_startup()

    if t_large is None:
        # Crash (RecursionError, wrong format, etc.) — result unreliable
        return None
    elif t_large is _TLE:
        # Genuine TLE on large but not small → infer ratio from timeout bound
        comp_small = max(t_small - startup, 0.002)
        if comp_small < 0.01:
            return None   # computation too fast to be meaningful
        ratio = (8.0 - startup) / comp_small
    else:
        # Subtract startup overhead so we compare pure computation times
        comp_small = max(t_small - startup, 0.002)
        comp_large = max(t_large - startup, 0.002)
        ratio = comp_large / comp_small

    # If computation time for small input is negligible (< 5 ms), the algorithm
    # is too fast to classify via timing — fall back to static analysis.
    comp_small_check = max(t_small - startup, 0)
    if comp_small_check < 0.005 or ratio < 1.5:
        return None

    scale = large_n / small_n           # 10×
    alpha = math.log(max(ratio, 0.01)) / math.log(scale)
    time_class, note = _alpha_to_complexity(alpha)

    large_str = "TLE (>8s)" if t_large is _TLE else f"{t_large:.4f}s"
    return {
        "time":  time_class,
        "notes": (f"Synthetic timing: T({small_n})={t_small:.4f}s, "
                  f"T({large_n})={large_str}, startup≈{startup:.3f}s "
                  f"(comp ratio≈{ratio:.1f}×, α≈{alpha:.2f}) → {note}"),
    }


# ─── Classify exponent → Big-O label ─────────────────────────────────────────

def _alpha_to_complexity(alpha: float) -> tuple[str, str]:
    """Map log-log slope to a standard complexity class."""
    if alpha < 0.15:
        return "O(1)",           "Constant — time independent of input size."
    elif alpha < 0.65:
        return "O(log n)",       "Logarithmic — halving strategy (binary search / balanced tree)."
    elif alpha < 1.25:
        return "O(n)",           "Linear — single pass through input."
    elif alpha < 1.65:
        return "O(n log n)",     "Linearithmic — sorting or divide-and-conquer."
    elif alpha < 2.35:
        return "O(n²)",          "Quadratic — nested iteration over input."
    elif alpha < 3.35:
        return "O(n³)",          "Cubic — triple nested loops."
    else:
        return "O(2ⁿ) or worse", "Exponential — likely unoptimised recursion."


# ─── Static analysis dispatcher ──────────────────────────────────────────────

def _static_analysis(code: str, language: str) -> dict:
    if language == "python":
        return _analyze_python(code)
    if language == "java":
        return _analyze_java(code)
    return {"time": "Unknown", "space": "Unknown", "notes": "Language not supported."}


def _space_note_only(notes: str) -> str:
    """Extract the space-related note from a static analysis notes string."""
    for part in notes.split(" | "):
        low = part.lower()
        if any(kw in low for kw in ("space", "stack", "table", "allocat", "dict", "hash", "set")):
            return part
    return ""


# ─── Python static analysis ───────────────────────────────────────────────────

def _analyze_python(code: str) -> dict:
    notes = []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"time": "Unknown", "space": "Unknown",
                "notes": "Syntax error — could not parse."}

    max_loop_depth   = _py_max_loop_depth(tree)
    has_recursion    = _py_has_recursion(tree)
    has_memo         = _py_has_memoization(code)
    uses_sorting     = bool(re.search(
        r'\b(sorted\s*\(|\.sort\s*\(|heapq\.|nlargest|nsmallest)', code))
    uses_dfs_bfs     = bool(re.search(
        r'\b(dfs\s*\(|bfs\s*\(|\.popleft\s*\(|deque\s*\()\b', code, re.IGNORECASE))
    uses_bsearch     = _py_is_binary_search(code)
    uses_2d_dp       = _py_uses_2d_dp(code)
    space_allocs     = _py_space_allocs(tree)
    uses_set_dict    = _py_uses_set_or_dict(tree)
    uses_linear_builtin = bool(re.search(
        r'\b(sum|max|min|any|all|map|filter|zip|enumerate|list|set|dict)\s*\(', code))

    # ── Time ──
    if has_recursion and has_memo:
        time_c = "O(n·m) or O(n²)"
        notes.append("Memoised recursion (DP) — complexity depends on state space.")
    elif has_recursion:
        time_c = "O(2ⁿ)"
        notes.append("Recursion without memoisation — exponential.")
    elif uses_dfs_bfs:
        time_c = "O(V + E)"
        notes.append("Graph traversal (DFS/BFS).")
    elif uses_sorting and max_loop_depth >= 1:
        time_c = "O(n log n)"
        notes.append("Sort + iteration.")
    elif uses_sorting:
        time_c = "O(n log n)"
        notes.append("Built-in sort (Timsort).")
    elif uses_bsearch:
        time_c = "O(log n)"
        notes.append("Binary search pattern.")
    elif max_loop_depth >= 3:
        time_c = "O(n³)"
        notes.append(f"Triple-nested loops (depth={max_loop_depth}).")
    elif max_loop_depth == 2:
        time_c = "O(n²)"
        notes.append("Doubly-nested loops.")
    elif max_loop_depth == 1:
        time_c = "O(n)"
        notes.append("Single loop — linear time.")
    elif uses_linear_builtin:
        time_c = "O(n)"
        notes.append("Linear built-in (sum/max/min/map/filter/etc.) over input.")
    else:
        time_c = "O(1)"
        notes.append("No loops or recursion.")

    # ── Space ──
    if uses_2d_dp:
        space_c = "O(n²) or O(n·m)"
        notes.append("2-D DP / memo table detected.")
    elif space_allocs >= 1 or (uses_set_dict and max_loop_depth >= 1):
        space_c = "O(n)"
        notes.append("Linear auxiliary space (list/dict/set allocation).")
    elif has_recursion:
        space_c = "O(n)"
        notes.append("Recursive call stack — O(n) space.")
    else:
        space_c = "O(1)"
        notes.append("No significant auxiliary space.")

    return {"time": time_c, "space": space_c,
            "notes": " | ".join(notes) if notes else "No pattern detected."}


def _py_max_loop_depth(tree) -> int:
    """Max nesting depth of for/while loops; list comprehensions are excluded."""
    def depth(node, cur=0):
        if isinstance(node, (ast.For, ast.While)):
            cur += 1
        m = cur
        for child in ast.iter_child_nodes(node):
            # Don't descend into comprehensions — they compile to inner functions
            if isinstance(child, (ast.ListComp, ast.SetComp,
                                  ast.DictComp, ast.GeneratorExp)):
                continue
            m = max(m, depth(child, cur))
        return m
    return depth(tree)


def _py_has_recursion(tree) -> bool:
    """True if any function defined in the file calls itself."""
    func_names = {n.name for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in func_names:
                return True
            # Handle method calls like self.solve()
            if isinstance(node.func, ast.Attribute) and node.func.attr in func_names:
                return True
    return False


def _py_has_memoization(code: str) -> bool:
    return bool(re.search(
        r'@\s*lru_cache|@\s*cache\b|functools\.cache|functools\.lru_cache'
        r'|\bdp\b|\bmemo\b', code))


def _py_is_binary_search(code: str) -> bool:
    """Require the classical binary-search pattern, not just variable names."""
    if re.search(r'\bbisect\b', code):
        return True
    # Need a while loop AND lo/hi/mid variables together
    if not re.search(r'\bwhile\b', code):
        return False
    has_bounds = bool(re.search(
        r'\b(lo|low|left)\b.{0,40}\b(hi|high|right)\b', code, re.DOTALL))
    has_mid    = bool(re.search(r'\bmid\b\s*=', code))
    return has_bounds and has_mid


def _py_uses_2d_dp(code: str) -> bool:
    return bool(re.search(
        r'\bdp\s*=\s*\[.*\[|\bmemo\s*=\s*\[.*\['
        r'|\[\[.+\]\s*\*\s*\w+\]\s*\*\s*\w+', code))


def _py_space_allocs(tree) -> int:
    """Count explicit list/dict/set assignments (result containers, not temporaries)."""
    count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        val = node.value
        if isinstance(val, (ast.List, ast.Dict, ast.Set)):
            count += 1
        elif isinstance(val, ast.Call) and isinstance(val.func, ast.Name):
            if val.func.id in ("list", "dict", "set", "deque",
                               "defaultdict", "Counter", "array", "bytearray"):
                count += 1
    return count


def _py_uses_set_or_dict(tree) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Dict, ast.Set, ast.DictComp, ast.SetComp)):
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("dict", "set", "defaultdict", "Counter"):
                return True
    return False


# ─── Java static analysis ─────────────────────────────────────────────────────

def _analyze_java(code: str) -> dict:
    notes = []

    max_loop_depth  = _java_max_loop_depth(code)
    has_recursion   = _java_has_recursion(code)
    has_memo        = bool(re.search(r'\bdp\b|\bmemo\b', code))
    uses_sorting    = bool(re.search(
        r'Collections\.sort|Arrays\.sort|\.sort\s*\(', code))
    uses_dfs_bfs    = bool(re.search(
        r'\b(dfs|bfs|Stack|Queue|Deque|visited)\b', code, re.IGNORECASE))
    uses_bsearch    = bool(re.search(
        r'Collections\.binarySearch|Arrays\.binarySearch', code))
    allocations     = len(re.findall(
        r'new\s+(ArrayList|HashMap|HashSet|LinkedList|Stack|TreeMap'
        r'|PriorityQueue|int\[|long\[|char\[)', code))
    uses_2d         = bool(re.search(r'int\s*\[\s*\]\s*\[\s*\]|new\s+int\s*\[', code))

    # ── Time ──
    if has_recursion and has_memo:
        time_c = "O(n·m) or O(n²)"
        notes.append("Memoised recursion (DP).")
    elif has_recursion:
        time_c = "O(2ⁿ)"
        notes.append("Recursion without memoisation — exponential.")
    elif uses_dfs_bfs:
        time_c = "O(V + E)"
        notes.append("Graph traversal (DFS/BFS).")
    elif uses_sorting and max_loop_depth >= 1:
        time_c = "O(n log n)"
        notes.append("Sort + iteration.")
    elif uses_sorting:
        time_c = "O(n log n)"
        notes.append("Arrays/Collections sort.")
    elif uses_bsearch:
        time_c = "O(log n)"
        notes.append("Binary search (library).")
    elif max_loop_depth >= 3:
        time_c = "O(n³)"
        notes.append("Triple nested loops.")
    elif max_loop_depth == 2:
        time_c = "O(n²)"
        notes.append("Doubly nested loops.")
    elif max_loop_depth == 1:
        time_c = "O(n)"
        notes.append("Single loop.")
    else:
        time_c = "O(1)"
        notes.append("No loops or recursion.")

    # ── Space ──
    if has_memo and uses_2d:
        space_c = "O(n²) or O(n·m)"
        notes.append("2-D DP / memo array.")
    elif allocations > 0 or (has_memo):
        space_c = "O(n)"
        notes.append("Linear auxiliary data structure.")
    elif has_recursion:
        space_c = "O(n)"
        notes.append("Recursive call stack.")
    else:
        space_c = "O(1)"
        notes.append("No significant auxiliary space.")

    return {"time": time_c, "space": space_c,
            "notes": " | ".join(notes) if notes else "No pattern detected."}


def _java_max_loop_depth(code: str) -> int:
    """Estimate loop nesting depth by tracking brace depth when a for/while is seen."""
    depth = max_depth = 0
    loop_re = re.compile(r'\b(for|while)\b')
    for line in code.splitlines():
        stripped = line.strip()
        if loop_re.search(stripped):
            depth += 1
            max_depth = max(max_depth, depth)
        # Opening braces increase depth, closing braces decrease it
        depth += stripped.count('{') - stripped.count('}')
        depth = max(depth, 0)
    return max_depth


def _java_has_recursion(code: str) -> bool:
    method_names = re.findall(
        r'(?:public|private|protected|static)[\s\w<>\[\]]+\s+(\w+)\s*\(', code)
    for name in method_names:
        if name in ("main",):
            continue
        if len(re.findall(rf'\b{re.escape(name)}\s*\(', code)) >= 2:
            return True
    return False
