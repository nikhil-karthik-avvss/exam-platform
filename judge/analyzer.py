import re
import ast

# ─── Public API ───────────────────────────────────────────────────────────────

def analyze_complexity(code: str, language: str) -> dict:
    """
    Analyzes time and space complexity of submitted code.
    Returns: {time, space, notes}
    """
    if language == "python":
        return _analyze_python(code)
    elif language == "java":
        return _analyze_java(code)
    return {"time": "Unknown", "space": "Unknown", "notes": "Language not supported for analysis."}


# ─── Python Analysis ──────────────────────────────────────────────────────────

def _analyze_python(code: str) -> dict:
    notes = []
    time_complexity  = "O(1)"
    space_complexity = "O(1)"

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"time": "Unknown", "space": "Unknown", "notes": "Syntax error — could not analyze."}

    # Count nesting depth of loops
    max_loop_depth   = _get_max_loop_depth(tree)
    has_recursion    = _has_recursion(tree)
    uses_sorting     = _uses_sorting_python(code)
    uses_dfs_bfs     = _uses_dfs_bfs(code)
    allocations      = _count_data_structures_python(tree)
    uses_dp_table    = _uses_dp_table(code)
    uses_binary_search = _uses_binary_search(code)
    uses_set_or_dict = _uses_set_or_dict_python(tree)

    # ── Time Complexity ──
    if has_recursion and uses_dp_table:
        time_complexity = "O(n²) or O(n·m)"
        notes.append("Recursive DP pattern detected — complexity depends on state space.")
    elif has_recursion:
        time_complexity = "O(2ⁿ) or O(n!)"
        notes.append("Recursion without memoization detected — likely exponential time.")
    elif uses_dfs_bfs:
        time_complexity = "O(V + E)"
        notes.append("Graph traversal (DFS/BFS) detected.")
    elif uses_sorting and max_loop_depth >= 1:
        time_complexity = "O(n log n)"
        notes.append("Sorting combined with iteration detected.")
    elif uses_sorting:
        time_complexity = "O(n log n)"
        notes.append("Built-in sort/sorted() detected (Timsort).")
    elif uses_binary_search:
        time_complexity = "O(log n)"
        notes.append("Binary search pattern detected.")
    elif max_loop_depth >= 3:
        time_complexity = "O(n³)"
        notes.append(f"Triple nested loops detected (depth={max_loop_depth}).")
    elif max_loop_depth == 2:
        time_complexity = "O(n²)"
        notes.append("Double nested loops detected.")
    elif max_loop_depth == 1:
        time_complexity = "O(n)"
        notes.append("Single loop detected.")
    else:
        time_complexity = "O(1)"
        notes.append("No loops or recursion detected — constant time.")

    # ── Space Complexity ──
    if uses_dp_table:
        space_complexity = "O(n²) or O(n·m)"
        notes.append("2D DP table detected.")
    elif uses_set_or_dict and max_loop_depth >= 1:
        space_complexity = "O(n)"
        notes.append("Hash map/set used within loops — linear space.")
    elif allocations > 2:
        space_complexity = "O(n)"
        notes.append(f"{allocations} data structure allocations detected.")
    elif allocations > 0:
        space_complexity = "O(n)"
        notes.append("List/dict/set allocation detected.")
    elif has_recursion:
        space_complexity = "O(n)"
        notes.append("Recursive call stack contributes O(n) space.")
    else:
        space_complexity = "O(1)"
        notes.append("No significant auxiliary space detected.")

    return {
        "time":  time_complexity,
        "space": space_complexity,
        "notes": " | ".join(notes) if notes else "No specific patterns detected."
    }


def _get_max_loop_depth(tree) -> int:
    """Find maximum nesting depth of for/while loops."""
    def depth(node, current=0):
        if isinstance(node, (ast.For, ast.While)):
            current += 1
        max_d = current
        for child in ast.iter_child_nodes(node):
            max_d = max(max_d, depth(child, current))
        return max_d
    return depth(tree)


def _has_recursion(tree) -> bool:
    """Detect if any function calls itself."""
    func_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in func_names:
                return True
    return False


def _uses_sorting_python(code: str) -> bool:
    return bool(re.search(r'\b(sorted|\.sort\(|heapq\.)', code))


def _uses_binary_search(code: str) -> bool:
    return bool(re.search(r'\b(bisect|binary_search|lo\s*=|hi\s*=|mid\s*=)', code))


def _uses_dfs_bfs(code: str) -> bool:
    return bool(re.search(r'\b(dfs|bfs|deque|stack\.append|queue\.append|visited)\b', code, re.IGNORECASE))


def _uses_dp_table(code: str) -> bool:
    return bool(re.search(r'\bdp\b|\bmemo\b|\bcache\b|lru_cache|@cache', code))


def _uses_set_or_dict_python(tree) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Dict, ast.Set, ast.DictComp, ast.SetComp)):
            return True
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in ("dict","set","defaultdict","Counter"):
                return True
    return False


def _count_data_structures_python(tree) -> int:
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
            count += 1
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in ("list","dict","set","deque","defaultdict","Counter","array","heapify"):
                count += 1
    return count


# ─── Java Analysis ────────────────────────────────────────────────────────────

def _analyze_java(code: str) -> dict:
    notes = []

    max_loop_depth   = _get_java_loop_depth(code)
    has_recursion    = _java_has_recursion(code)
    uses_sorting     = bool(re.search(r'Collections\.sort|Arrays\.sort|\.sort\(', code))
    uses_dfs_bfs     = bool(re.search(r'\b(dfs|bfs|Stack|Queue|Deque|visited)\b', code, re.IGNORECASE))
    uses_dp          = bool(re.search(r'\bdp\b|\bmemo\b', code))
    uses_binary_search = bool(re.search(r'Collections\.binarySearch|Arrays\.binarySearch|\blo\b.*\bhi\b|\bmid\b', code))
    allocations      = len(re.findall(r'new\s+(ArrayList|HashMap|HashSet|LinkedList|Stack|TreeMap|PriorityQueue|int\[|long\[|char\[)', code))

    # ── Time Complexity ──
    if has_recursion and uses_dp:
        time_complexity = "O(n²) or O(n·m)"
        notes.append("Recursive DP pattern detected.")
    elif has_recursion:
        time_complexity = "O(2ⁿ) or O(n!)"
        notes.append("Recursion without memoization — possibly exponential.")
    elif uses_dfs_bfs:
        time_complexity = "O(V + E)"
        notes.append("Graph traversal (DFS/BFS) detected.")
    elif uses_sorting and max_loop_depth >= 1:
        time_complexity = "O(n log n)"
        notes.append("Sorting with iteration detected.")
    elif uses_sorting:
        time_complexity = "O(n log n)"
        notes.append("Collections/Arrays sort detected.")
    elif uses_binary_search:
        time_complexity = "O(log n)"
        notes.append("Binary search pattern detected.")
    elif max_loop_depth >= 3:
        time_complexity = "O(n³)"
        notes.append(f"Triple nested loops detected.")
    elif max_loop_depth == 2:
        time_complexity = "O(n²)"
        notes.append("Double nested loops detected.")
    elif max_loop_depth == 1:
        time_complexity = "O(n)"
        notes.append("Single loop detected.")
    else:
        time_complexity = "O(1)"
        notes.append("No loops or recursion detected.")

    # ── Space Complexity ──
    if uses_dp:
        space_complexity = "O(n²) or O(n·m)"
        notes.append("DP table allocation detected.")
    elif allocations > 2:
        space_complexity = "O(n)"
        notes.append(f"{allocations} data structure allocations detected.")
    elif allocations > 0:
        space_complexity = "O(n)"
        notes.append("Auxiliary data structure allocation detected.")
    elif has_recursion:
        space_complexity = "O(n)"
        notes.append("Recursive call stack — O(n) space.")
    else:
        space_complexity = "O(1)"
        notes.append("No significant auxiliary space detected.")

    return {
        "time":  time_complexity,
        "space": space_complexity,
        "notes": " | ".join(notes) if notes else "No specific patterns detected."
    }


def _get_java_loop_depth(code: str) -> int:
    """Estimate max loop nesting depth from Java code."""
    depth = 0
    max_depth = 0
    loop_pattern = re.compile(r'\b(for|while)\b')
    lines = code.split('\n')
    for line in lines:
        stripped = line.strip()
        if loop_pattern.search(stripped):
            depth += 1
            max_depth = max(max_depth, depth)
        depth -= stripped.count('}')
        depth = max(depth, 0)
    return max_depth


def _java_has_recursion(code: str) -> bool:
    """Detect method calling itself in Java."""
    method_names = re.findall(r'(?:public|private|protected|static)[\s\w<>\[\]]+\s+(\w+)\s*\(', code)
    for name in method_names:
        pattern = rf'\b{re.escape(name)}\s*\('
        # Count occurrences — declaration + at least one call = recursion
        if len(re.findall(pattern, code)) >= 2:
            return True
    return False
