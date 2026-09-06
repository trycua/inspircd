#!/usr/bin/env python3
"""Exercise the actual WasmEdge-hosted InspIRCd with two raw TCP clients."""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
BUILD = Path(os.environ.get("BUILD", ROOT / "build-wasi")).resolve()
RUNTIME = BUILD / "runtime"
RUNTIME.mkdir(parents=True, exist_ok=True)
NATIVE = Path(os.environ["NATIVE_PREFIX"]).resolve() if "NATIVE_PREFIX" in os.environ else None
BINARY = NATIVE / "bin/inspircd" if NATIVE else BUILD / "src/inspircd.wasm"
if not NATIVE:
    assert BINARY.read_bytes()[:8] == b"\0asm\1\0\0\0", "not a WebAssembly module"
config_root = str(RUNTIME) if NATIVE else "/irc"
module_root = str(NATIVE / "modules") if NATIVE else "/irc"
with socket.socket() as reserve:
    reserve.bind(("127.0.0.1", 0))
    port = reserve.getsockname()[1]
(RUNTIME / "inspircd.conf").write_text(f'''<server name="irc.wasi.test" id="001" description="Actual InspIRCd on WasmEdge" network="WASI">
<admin name="WASI test" email="test@example.invalid">
<bind address="127.0.0.1" port="{port}" type="clients">
<connect name="local" allow="127.0.0.1" resolvehostnames="no" timeout="3" pingfreq="60" localmax="128" globalmax="128" recvq="4096" hardsendq="65536" softsendq="8192">
<path configdir="{config_root}" datadir="{config_root}" logdir="{config_root}" moduledir="{module_root}" runtimedir="{config_root}">
<options nosnoticestack="yes">
''')
transcript = []

def record(text):
    transcript.append(text)
    print(text, flush=True)

class Client:
    def __init__(self, nick):
        self.nick = nick
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=2)
        self.sock.settimeout(0.5)
        self.buffer = b""
        self.lines = []

    def send(self, line):
        record(f"{self.nick} >> {line}")
        self.sock.sendall((line + "\r\n").encode())

    def wait(self, predicate, description):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            for line in self.lines:
                if predicate(line):
                    return line
            assert server.poll() is None, f"Server exited: {server.returncode}"
            try:
                data = self.sock.recv(65536)
            except socket.timeout:
                continue
            assert data, f"connection closed while waiting for {description}"
            self.buffer += data
            while b"\r\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\r\n", 1)
                text = line.decode()
                record(f"{self.nick} << {text}")
                self.lines.append(text)
                if text.startswith("PING "):
                    self.send("PONG " + text[5:])
        raise AssertionError(f"{self.nick}: timed out waiting for {description}")

    def numeric(self, number):
        return self.wait(lambda line: re.match(rf":\S+ {number:03} {self.nick} ", line), f"numeric {number}")

clients = []
log = (BUILD / "wasmedge-server.log").open("w")
command = ([str(BINARY), "--nofork", "--runasroot", "--config", str(RUNTIME / "inspircd.conf")]
           if NATIVE else ["sh", str(ROOT / "tools/wasi/run.sh")])
server = subprocess.Popen(command,
                          env={**os.environ, "BUILD": str(BUILD), "RUNTIME": str(RUNTIME)},
                          stdout=log, stderr=subprocess.STDOUT)
passed = False
process_evidence = {}
stress_evidence = {}
try:
    record(f"Server host PID: {server.pid}; binary sha256: {hashlib.sha256(BINARY.read_bytes()).hexdigest()}")
    deadline = time.monotonic() + 30
    while True:
        assert server.poll() is None, "server failed during startup; see wasmedge-server.log"
        try:
            alice = Client("alice")
            break
        except OSError:
            assert time.monotonic() < deadline, "listener startup timed out"
            time.sleep(0.2)
    clients.append(alice)
    proc = Path(f"/proc/{server.pid}")
    if proc.exists():
        process_evidence = {
            "executable": str((proc / "exe").resolve()),
            "argv": (proc / "cmdline").read_bytes().decode().rstrip("\0").split("\0"),
        }
        assert Path(process_evidence["executable"]).name == ("inspircd" if NATIVE else "wasmedge"), process_evidence
        record("Process evidence: " + json.dumps(process_evidence))
    bob = Client("bob")
    clients.append(bob)
    for client in clients:
        client.send(f"NICK {client.nick}")
        client.send(f"USER {client.nick} 0 * :WasmEdge {client.nick}")
        for number in (1, 2, 3, 4):
            client.numeric(number)
    alice.send("JOIN #wasm")
    alice.wait(lambda line: line.startswith(":alice!") and " JOIN :#wasm" in line, "Alice JOIN")
    alice.numeric(366)
    bob.send("JOIN #wasm")
    bob.wait(lambda line: line.startswith(":bob!") and " JOIN :#wasm" in line, "Bob JOIN")
    alice.wait(lambda line: line.startswith(":bob!") and " JOIN :#wasm" in line, "peer JOIN")
    names = bob.numeric(353).split(" :", 1)[1].split()
    assert {name.lstrip("~&@%+") for name in names} == {"alice", "bob"}, names
    bob.numeric(366)
    # Also request a fresh membership list from the first client.
    alice.send("NAMES #wasm")
    alice.wait(lambda line: " 353 alice " in line and "bob" in line and "alice" in line.split(" :", 1)[-1], "both members in Alice NAMES")
    alice.send("PRIVMSG #wasm :alice-to-bob-actual-wasm")
    bob.wait(lambda line: line.startswith(":alice!") and line.endswith(" PRIVMSG #wasm :alice-to-bob-actual-wasm"), "Alice to Bob")
    bob.send("PRIVMSG #wasm :bob-to-alice-actual-wasm")
    alice.wait(lambda line: line.startswith(":bob!") and line.endswith(" PRIVMSG #wasm :bob-to-alice-actual-wasm"), "Bob to Alice")
    # Exercise command framing across two TCP writes.
    alice.sock.sendall(b"PRIVMSG #wasm :fragmented-")
    time.sleep(0.1)
    alice.sock.sendall(b"message\r\n")
    bob.wait(lambda line: line.endswith(" PRIVMSG #wasm :fragmented-message"), "fragmented command")
    bob.send("PART #wasm :test complete")
    alice.wait(lambda line: line.startswith(":bob!") and " PART #wasm :test complete" in line, "peer PART")
    if os.environ.get("STRESS") == "1":
        def sample():
            status = (proc / "status").read_text()
            ticks = (proc / "stat").read_text().split()
            return {"rss_kib": int(re.search(r"VmRSS:\s+(\d+)", status)[1]),
                    "fds": len(list((proc / "fd").iterdir())),
                    "cpu_ticks": int(ticks[13]) + int(ticks[14])}

        def ping(client, label):
            client.send("PING :" + label)
            client.wait(lambda line: " PONG " in line and line.endswith(" :" + label), label)

        def closed(client, expected=None):
            deadline = time.monotonic() + 10
            received = b""
            while time.monotonic() < deadline:
                assert server.poll() is None, "server exited during rejection"
                try:
                    data = client.sock.recv(65536)
                    if not data:
                        break
                    received += data
                except ConnectionResetError:
                    break
                except socket.timeout:
                    pass
            else:
                raise AssertionError("connection not closed within resource deadline")
            if expected:
                text = received.decode(errors="replace")
                record(f"{client.nick} << {text.rstrip()}")
                assert expected in text, (expected, text)

        before = sample()
        peaks = [before]
        for round_id in range(3):
            batch = []
            for index in range(24):
                client = Client(f"c{round_id}_{index}")
                clients.append(client)
                batch.append(client)
                client.send(f"NICK {client.nick}")
                client.send(f"USER {client.nick} 0 * :churn test")
                client.numeric(1)
            peaks.append(sample())
            # Close alternating entries to exercise compact-array gap filling.
            for client in batch[::2]:
                client.sock.close()
            for client in batch[1::2]:
                ping(client, f"survivor-{client.nick}")
                client.send("QUIT :churn complete")
                closed(client)
                client.sock.close()
            ping(alice, f"after-churn-{round_id}")

        oversized = Client("oversized")
        clients.append(oversized)
        oversized.sock.sendall(b"X" * 65536)
        closed(oversized, "RecvQ exceeded")
        oversized.sock.close()
        idle = Client("unregistered")
        clients.append(idle)
        closed(idle, "Connection timeout")
        idle.sock.close()
        ping(alice, "after-abuse")
        start_idle = sample()
        time.sleep(4)
        after = sample()
        assert after["fds"] <= before["fds"] + 2, (before, after)
        assert max(s["rss_kib"] for s in peaks + [after]) < 512 * 1024, peaks
        assert after["rss_kib"] - before["rss_kib"] < 64 * 1024, (before, after)
        assert after["cpu_ticks"] - start_idle["cpu_ticks"] < 2 * os.sysconf("SC_CLK_TCK"), (start_idle, after)
        ping(alice, "after-idle")
        stress_evidence = {"passed": True, "rounds": 3, "clients_per_round": 24,
                           "before": before, "after": after, "peaks": peaks,
                           "idle_seconds": 4, "idle_start": start_idle}
        record("PASS: 72-client churn; gap-fill survivors; oversized input rejection; registration timeout; idle CPU/RSS/fd bounds")
    passed = True
    record("PASS: registration 001-004 for both; JOIN and NAMES membership; bidirectional channel PRIVMSG; fragmented command; PART")
finally:
    for client in clients:
        client.sock.close()
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
    log.close()
    (BUILD / "stress.json").write_text(json.dumps(stress_evidence, indent=2) + "\n")
    (BUILD / "irc-transcript.log").write_text("\n".join(transcript) + "\n")
    (BUILD / "acceptance.json").write_text(json.dumps({"passed": passed, "mode": "native" if NATIVE else "wasm", "binary": str(BINARY), "sha256": hashlib.sha256(BINARY.read_bytes()).hexdigest(), "host_pid": server.pid, "process": process_evidence, "port": port, "shutdown": "host terminates launched server after test"}, indent=2) + "\n")
