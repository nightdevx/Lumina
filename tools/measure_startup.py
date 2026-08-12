"""Measure cold/warm start of the built exe: launch -> window on screen.

    .venv\\Scripts\\python.exe tools\\measure_startup.py [runs]
"""
import subprocess
import sys
import time
from pathlib import Path

import win32gui
import win32process

EXE = Path(__file__).resolve().parent.parent / "build" / "output" / "dist" / "LUMINA" / "LUMINA.exe"
RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
TIMEOUT = 20.0


def window_of(pid: int):
    found = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, owner = win32process.GetWindowThreadProcessId(hwnd)
        if owner == pid and win32gui.GetWindowText(hwnd) == "LUMINA":
            found.append(hwnd)

    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


if not EXE.exists():
    sys.exit(f"not built: {EXE}")

print(f"exe: {EXE}")
results = []
for run in range(1, RUNS + 1):
    start = time.perf_counter()
    proc = subprocess.Popen([str(EXE)])
    hwnd = None
    while time.perf_counter() - start < TIMEOUT:
        hwnd = window_of(proc.pid)
        if hwnd:
            break
        time.sleep(0.01)
    elapsed = (time.perf_counter() - start) * 1000
    if hwnd is None:
        print(f"  run {run}: NO WINDOW after {TIMEOUT}s (exit={proc.poll()})")
    else:
        results.append(elapsed)
        print(f"  run {run}: window visible after {elapsed:7.0f} ms")
    time.sleep(1.5)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    time.sleep(0.6)

if results:
    print(f"\nfirst (cold): {results[0]:.0f} ms")
    if len(results) > 1:
        warm = results[1:]
        print(f"warm median : {sorted(warm)[len(warm) // 2]:.0f} ms")
