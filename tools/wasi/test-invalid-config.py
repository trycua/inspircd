#!/usr/bin/env python3
"""Independent, bounded configuration error-path regression suite."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
build = Path(os.environ.get("BUILD", root / "build-wasi")).resolve()
tools = Path(os.environ.get("TOOLS", root / ".wasi-tools")).resolve()
runtime = build / "negative-runtime"
runtime.mkdir(parents=True, exist_ok=True)
base = '''<server name="irc.wasi.test" id="001" description="Negative test" network="WASI">
<path configdir="/irc" datadir="/irc" logdir="/irc" moduledir="/irc" runtimedir="/irc">
'''
cases = {
    "invalid-id": (base.replace('id="001"', 'id="invalid"'), "not a valid server ID"),
    "syntax": (base + "not-a-tag", "Syntax error"),
    "exec": (base + '<include executable="not-an-executable">', "Executable config includes are unavailable"),
    "missing-include": (base + '<include file="/irc/absent.conf">', "Could not read"),
    "duplicate-class": (base + '<class name="duplicate"><class name="duplicate">', "Duplicate class block"),
    "recursive-include": (base + '<include file="/irc/recursive-include.conf">', "recursive"),
    "privilege-drop": (base + '<security runasuser="nobody">', "WASI cannot drop privileges"),
    "tls-profile": (base + '<bind address="127.0.0.1" port="16667" sslprofile="test">', "WASI does not support TLS profiles"),
    "connection-hook": (base + '<bind address="127.0.0.1" port="16667" hook="test">', "WASI does not support TLS profiles"),
}
results = []
try:
    for name, (config, diagnostic) in cases.items():
        (runtime / f"{name}.conf").write_text(config)
        command = [str(tools / "bin/wasmedge"), "--dir", f"/irc:{runtime}",
                   str(build / "src/inspircd.wasm"), "--nofork", "--config", f"/irc/{name}.conf"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=20)
        log = f"exit={result.returncode}\n" + result.stdout + result.stderr
        (build / f"negative-{name}.log").write_text(log)
        passed = (0 < result.returncode < 128 and diagnostic in log
                  and "execution failed:" not in log and "[error]" not in log)
        results.append({"case": name, "passed": passed, "exit": result.returncode})
        print(f"{'PASS' if passed else 'FAIL'}: {name} (exit {result.returncode})")
        if not passed:
            print(log)
finally:
    (build / "negative-config.json").write_text(json.dumps({
        "sha256": hashlib.sha256((build / "src/inspircd.wasm").read_bytes()).hexdigest(),
        "cases": results, "passed": len(results) == len(cases) and all(r["passed"] for r in results),
    }, indent=2) + "\n")
assert len(results) == len(cases) and all(r["passed"] for r in results), "configuration regression failed"
