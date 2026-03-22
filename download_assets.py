#!/usr/bin/env python3
"""
Downloads CodeMirror assets for offline use.
Run this ONCE on a machine with internet before the exam.
"""
import urllib.request, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
CM   = os.path.join(BASE, "static", "codemirror")
CDN  = "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16"

FILES = {
    "codemirror.min.js"          : f"{CDN}/codemirror.min.js",
    "codemirror.min.css"         : f"{CDN}/codemirror.min.css",
    "mode/python/python.min.js"  : f"{CDN}/mode/python/python.min.js",
    "mode/clike/clike.min.js"    : f"{CDN}/mode/clike/clike.min.js",
    "theme/dracula.min.css"      : f"{CDN}/theme/dracula.min.css",
}

os.makedirs(os.path.join(CM, "mode", "python"), exist_ok=True)
os.makedirs(os.path.join(CM, "mode", "clike"),  exist_ok=True)
os.makedirs(os.path.join(CM, "theme"),           exist_ok=True)

print("Downloading CodeMirror assets...")
for dest, url in FILES.items():
    path = os.path.join(CM, dest)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        print(f"  [skip] {dest} (already exists)")
        continue
    try:
        print(f"  [get]  {dest} ...", end=" ", flush=True)
        urllib.request.urlretrieve(url, path)
        print("OK")
    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)

print("\nAll CodeMirror assets downloaded. Platform is ready for offline use.")
