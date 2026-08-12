"""Hardware smoke test for the core layer. Not a unit test - it talks to the
real monitors. Reads everything, then writes each monitor its CURRENT value
back (no visible change) and reports latency against the plan's targets.

    .venv\\Scripts\\python.exe tools\\smoke_core.py
"""
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

logging.basicConfig(level=logging.DEBUG, format="%(levelname)-7s %(name)s: %(message)s")

from lumina.core.backend import INTERNAL, MonitorBackend  # noqa: E402
from lumina.core.discovery import enumerate_displays  # noqa: E402

# "write external" floor is the DDC/CI I2C bus itself (~58-63 ms measured), not
# our code. Targets below it would just be noise.
TARGETS = {"enumerate": 1500, "read internal": 15, "read external": 120,
           "write internal": 15, "write external": 80}


def timed(label, fn):
    start = time.perf_counter()
    result = fn()
    elapsed = (time.perf_counter() - start) * 1000
    target = TARGETS.get(label)
    verdict = "" if target is None else ("  OK" if elapsed <= target else f"  SLOW (>{target} ms)")
    print(f"  {label:<18} {elapsed:8.1f} ms{verdict}")
    return result, elapsed


print("=== raw display enumeration ===")
for d in enumerate_displays():
    print(f"  {d.adapter:<14} identity={d.identity}")
    print(f"  {'':<14} name={d.friendly_name!r} edid={'yes' if d.edid else 'no'} primary={d.is_primary}")

print("\n=== backend ===")
backend = MonitorBackend()
monitors, _ = timed("enumerate", backend.refresh)
for m in monitors:
    state = f"{m.brightness}%" if m.controllable else f"NOT CONTROLLABLE ({m.reason})"
    print(f"  [{m.kind:<8}] {m.name:<24} {state}")

print("\n=== per-monitor latency ===")
failures = []
for m in monitors:
    if not m.controllable:
        continue
    print(f"  -- {m.name}")
    kind = "internal" if m.kind == INTERNAL else "external"
    for _ in range(3):
        _, elapsed = timed(f"read {kind}", lambda mm=m: backend._read(mm))
        if elapsed > TARGETS[f"read {kind}"]:
            failures.append((m.name, f"read {kind}", elapsed))
    current = backend._read(m)
    for _ in range(3):
        ok, elapsed = timed(f"write {kind}", lambda mm=m, v=current: backend.set_percent(mm.key, v))
        if not ok:
            failures.append((m.name, "write returned False", elapsed))
        elif elapsed > TARGETS[f"write {kind}"]:
            failures.append((m.name, f"write {kind}", elapsed))

print("\n=== read_all round trip ===")
timed("read_all", backend.read_all)

backend.close()
print("\nRESULT:", "PASS" if not failures else f"{len(failures)} over target")
for name, what, ms in failures:
    print(f"  {name}: {what} took {ms:.1f} ms")
