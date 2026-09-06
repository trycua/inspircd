#!/usr/bin/env python3
"""Run two bounded WASI stress lifecycles to verify restart and input resilience."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
BUILD = Path(os.environ.get("BUILD", ROOT / "build-wasi")).resolve()
ROUNDS = int(os.environ.get("RESILIENCE_ROUNDS", "6"))
assert 1 <= ROUNDS <= 12, "RESILIENCE_ROUNDS must be between 1 and 12"

cycles = []
for cycle in range(1, 3):
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/wasi/test.py")],
        env={**os.environ, "STRESS": "1", "STRESS_ROUNDS": str(ROUNDS)},
        timeout=12 * 60,
    )
    acceptance = json.loads((BUILD / "acceptance.json").read_text())
    stress = json.loads((BUILD / "stress.json").read_text())
    passed = result.returncode == 0 and acceptance["passed"] and stress["passed"]
    cycles.append({
        "cycle": cycle,
        "passed": passed,
        "seconds": round(time.monotonic() - started, 3),
        "stress": stress,
    })
    assert passed, f"resilience cycle {cycle} failed"

module = BUILD / "src/inspircd.wasm"
evidence = {
    "passed": True,
    "mode": "wasm",
    "restart_cycles": len(cycles),
    "stress_rounds_per_cycle": ROUNDS,
    "sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
    "cycles": cycles,
    "scope": "controlled host termination and relaunch, not crash/OOM recovery",
}
(BUILD / "resilience.json").write_text(json.dumps(evidence, indent=2) + "\n")
print(f"PASS: {len(cycles)} clean host-restart cycles with {ROUNDS * 24 * len(cycles)} churn clients")
