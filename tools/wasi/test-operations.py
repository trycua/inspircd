#!/usr/bin/env python3
"""Bounded operational failure-path checks against the WasmEdge server."""
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
TOOLS = Path(os.environ.get("TOOLS", ROOT / ".wasi-tools")).resolve()
RUNTIME = BUILD / "operations-runtime"
WASM = BUILD / "src/inspircd.wasm"
RUNTIME.mkdir(parents=True, exist_ok=True)
assert WASM.read_bytes()[:8] == b"\0asm\1\0\0\0", "not a WebAssembly module"


def free_port():
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        return reserve.getsockname()[1]


def config(port, localmax=8):
    return f'''<server name="irc.wasi.ops" id="002" description="WASI operations test" network="WASI">
<admin name="WASI test" email="test@example.invalid">
<bind address="127.0.0.1" port="{port}" type="clients">
<connect name="local" allow="127.0.0.1" resolvehostnames="no" timeout="3" pingfreq="60" localmax="{localmax}" globalmax="{localmax}" recvq="4096" hardsendq="2048" softsendq="1024">
<type name="testoper" commands="REHASH">
<oper name="testoper" password="test-password" host="*@127.0.0.1" type="testoper">
<path configdir="/irc" datadir="/irc" logdir="/irc" moduledir="/irc" runtimedir="/irc">
<options nosnoticestack="yes">
'''


class Server:
    def __init__(self, config_text):
        self.port = free_port()
        self.path = RUNTIME / "inspircd.conf"
        self.path.write_text(config_text.replace('port="0"', f'port="{self.port}"'))
        self.log_path = BUILD / "wasmedge-operations.log"
        self.log = self.log_path.open("w")
        self.proc = subprocess.Popen(
            [str(TOOLS / "bin/wasmedge"), "--dir", f"/irc:{RUNTIME}", str(WASM),
             "--nofork", "--config", "/irc/inspircd.conf"],
            stdout=self.log, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 30
        while True:
            assert self.proc.poll() is None, "server exited during startup"
            try:
                self.probe = socket.create_connection(("127.0.0.1", self.port), timeout=0.2)
                self.probe.close()
                return
            except OSError:
                assert time.monotonic() < deadline, "listener startup timed out"
                time.sleep(0.1)

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.log.close()


class Client:
    def __init__(self, port, nick):
        self.nick = nick
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=2)
        self.sock.settimeout(0.25)
        self.buffer = b""
        self.lines = []

    def send(self, line):
        self.sock.sendall((line + "\r\n").encode())

    def wait(self, predicate, label, server):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            for line in self.lines:
                if predicate(line):
                    return line
            assert server.proc.poll() is None, f"server exited while waiting for {label}"
            try:
                data = self.sock.recv(65536)
            except socket.timeout:
                continue
            assert data, f"connection closed while waiting for {label}"
            self.buffer += data
            while b"\r\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\r\n", 1)
                text = line.decode(errors="replace")
                self.lines.append(text)
                if text.startswith("PING "):
                    self.send("PONG " + text[5:])
        raise AssertionError(f"{self.nick}: timeout waiting for {label}")

    def register(self, server):
        self.send(f"NICK {self.nick}")
        self.send(f"USER {self.nick} 0 * :WASI operations test")
        self.wait(lambda line: re.match(rf":\S+ 001 {self.nick} ", line), "registration", server)

    def ping(self, label, server):
        self.send("PING :" + label)
        self.wait(lambda line: " PONG " in line and line.endswith(" :" + label), label, server)

    def close(self):
        self.sock.close()


def require_closed(client, server, label):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        assert server.proc.poll() is None, f"server exited during {label}"
        try:
            if not client.sock.recv(65536):
                return
        except (ConnectionResetError, BrokenPipeError):
            return
        except socket.timeout:
            pass
    raise AssertionError(f"{label}: connection was not refused within deadline")


results = {}
try:
    # Bind failure is isolated to an owned ephemeral loopback socket.
    held_port = free_port()
    holder = socket.socket()
    holder.bind(("127.0.0.1", held_port))
    holder.listen()
    (RUNTIME / "inspircd.conf").write_text(config(held_port))
    failed = subprocess.Popen(
        [str(TOOLS / "bin/wasmedge"), "--dir", f"/irc:{RUNTIME}", str(WASM),
         "--nofork", "--config", "/irc/inspircd.conf"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    time.sleep(1)
    assert failed.poll() is None, "failed bind unexpectedly terminated the process"
    failed.terminate()
    bind_log, _ = failed.communicate(timeout=5)
    holder.close()
    assert "listeners failed to bind" in bind_log and "Address in use" in bind_log and "execution failed:" not in bind_log, bind_log
    results["failed_bind"] = {"passed": True, "process_survived": True}

    # A low per-host connection cap exercises safe admission refusal without exhausting host FDs.
    server = Server(config(0, localmax=2))
    first = Client(server.port, "first")
    second = Client(server.port, "second")
    try:
        first.register(server)
        second.register(server)
        refused = Client(server.port, "refused")
        try:
            require_closed(refused, server, "connection-limit refusal")
        finally:
            refused.close()
        first.ping("after-refusal", server)
        results["connection_refusal"] = {"passed": True, "localmax": 2}
    finally:
        first.close()
        second.close()
        server.close()

    server = Server(config(0, localmax=8))
    sender = Client(server.port, "sender")
    slow = Client(server.port, "slow")
    observer = Client(server.port, "observer")
    try:
        sender.register(server)
        slow.register(server)
        observer.register(server)
        slow.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
        sender.send("JOIN #backpressure")
        sender.wait(lambda line: " 366 sender #backpressure " in line, "sender join", server)
        slow.send("JOIN #backpressure")
        slow.wait(lambda line: " 366 slow #backpressure " in line, "slow join", server)
        observer.send("JOIN #backpressure")
        observer.wait(lambda line: " 366 observer #backpressure " in line, "observer join", server)
        payload = "x" * 420
        for index in range(256):
            marker = f"{index:03d}-{payload}"
            sender.send("PRIVMSG #backpressure :" + marker)
            # Drain the observer on every write; only the deliberately slow peer
            # should accumulate a send queue.
            observer.wait(lambda line, marker=marker: line.endswith(" :" + marker), "observer delivery", server)
        # The peer deliberately does not read while the observer drains every
        # delivery. This bounds the workload without claiming a kernel-buffer
        # dependent sendq disconnect on every host.
        assert server.proc.poll() is None, "server exited during slow-client workload"
        observer.ping("after-backpressure", server)
        sender.ping("sender-after-backpressure", server)
        results["slow_client_liveness"] = {"passed": True, "messages": 256, "payload_bytes": len(payload), "hardsendq": 2048}

        sender.send("OPER testoper test-password")
        sender.wait(lambda line: " 381 sender " in line, "oper login", server)
        broken = "not-a-tag\n"
        server.path.write_text(broken)
        sender.send("REHASH")
        sender.wait(lambda line: " 382 sender " in line, "invalid rehash acknowledgement", server)
        time.sleep(0.5)
        assert server.proc.poll() is None, "server exited after invalid rehash"
        sender.ping("after-invalid-rehash", server)
        server.path.write_text(config(server.port, localmax=8))
        sender.send("REHASH")
        sender.wait(lambda line: " 382 sender " in line, "valid rehash acknowledgement", server)
        time.sleep(0.5)
        assert server.proc.poll() is None, "server exited after valid rehash"
        observer.ping("after-valid-rehash", server)
        results["rehash_preservation"] = {"passed": True, "invalid_then_valid": True}
    finally:
        sender.close()
        slow.close()
        observer.close()
        server.close()
finally:
    (BUILD / "operations.json").write_text(json.dumps({
        "passed": len(results) == 4 and all(item["passed"] for item in results.values()),
        "sha256": hashlib.sha256(WASM.read_bytes()).hexdigest(),
        "limits": {"connection_refusal_localmax": 2, "slow_client_messages": 256, "slow_client_payload_bytes": 430},
        "results": results,
        "scope": "isolated loopback subprocesses; no host-wide FD or memory exhaustion",
    }, indent=2) + "\n")
assert len(results) == 4 and all(item["passed"] for item in results.values()), results
print("PASS: failed bind, connection refusal, slow-client backpressure, invalid/valid rehash preservation")
