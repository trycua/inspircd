# InspIRCd on WASI / WasmEdge

**Experimental, not production-qualified.** This fork runs the real InspIRCd
core and 17 static core command-module groups inside a WASI Preview 1 module.
It is not a replacement IRC implementation, native fallback, or host-side proxy.
Upstream baseline is `3822a6a9548ef9afc5d56cf04e48a75e56adebbe` (unstable v5 master).
Upstream copyrights and GPL v2 licensing in `docs/LICENSE.txt` remain unchanged;
new port code is distributed under that same license. This port is not endorsed
by the InspIRCd project. Do not submit AI-generated upstream pull requests.

## Reproduce without sibling directories

Host prerequisites: Linux x86_64 with glibc >= 2.28, Python >= 3.11, curl, GNU tar,
and coreutils (`timeout`). Use a trusted, dedicated checkout/tool directory.
No root, system installation, service deployment, or credentials are required.

```sh
python3 tools/wasi/bootstrap.py
STRESS=1 sh tools/wasi/verify.sh
```

The bootstrap downloads public release archives into `.wasi-tools/downloads`,
checks each SHA-256 against `toolchain.json` BEFORE extraction, and extracts only
into `.wasi-tools`. Digests originate from GitHub release asset metadata. A bad
cached archive fails closed; remove only that archive and retry after checking
its origin. Re-running bootstrap rechecks and re-extracts all pinned archives.
Do not point `TOOLS` at a shared system prefix. Checksums establish reproducible
artifact integrity, not an independent audit of the upstream binaries.

Pinned tools:

- wasi-sdk 34.0 (Clang 23), standard WebAssembly exception encoding, libunwind.
- **WasmEdge 0.17.2-rc.1 interpreter** (a prerelease; stable-release gate is OPEN).
- CMake 4.4.3 and Ninja 1.13.2.

`TOOLS`, `SDK`, `CMAKE`, `BUILD`, and `JOBS` override their respective paths/settings.
Default build directory is `build-wasi`; default parallelism is two jobs.
Only MinSizeRel is qualified for the application, not arbitrary CMake modes.
Overrides do not establish compatibility. `run.sh` rejects unverified runtime
versions, including 0.17.1; there is no unsafe-runtime bypass switch.

Separate operations:

```sh
sh tools/wasi/build.sh
STRESS=1 python3 tools/wasi/test.py
python3 tools/wasi/test-invalid-config.py
sh tools/wasi/run.sh
```

The positive test writes a loopback-only configuration using an available high
port, and launches/cleans up its own runtime. The port is released before launch;
a port race is a test failure, not a pass. `run.sh` reuses this generated config
for a manually supervised local experiment. Only the runtime directory is
preopened as `/irc`; the checkout, tools, and credentials are not preopened.
This is filesystem scoping, NOT host network isolation.

## Exception safety: runtime defect, not suppressed errors

The old runtime 0.17.1 traps on an invalid server ID instead of rejecting config.
A reduced C++ reproducer with an allocating user exception and temporary strings
also traps under optimization. A same-frame std::runtime_error smoke test passes
and is therefore insufficient. The unchanged application binary and reduced
reproducer pass with 0.17.2-rc.1.

The candidate release includes upstream fixes:

- https://github.com/WasmEdge/WasmEdge/pull/5202 discards exception payloads for
  catch_all/catch_all_ref instead of corrupting the operand stack.
- https://github.com/WasmEdge/WasmEdge/pull/5252 removes stale try_table handlers
  on branches, preventing host out-of-bounds writes and unbounded handler growth.

This is runtime/toolchain compatibility evidence, not proof of which individual
fix explains every symptom. No C++ catch, validation, or destructor is removed.
`check-exceptions.cpp` tests repeated allocating cross-frame throws plus matching,
rethrow, and RAII cleanup at `-O0`, `-Os`, and `-O2`, with a timeout for each run.
Stable 0.17.1 is unsuitable even if happy-path IRC works. AOT/JIT are not qualified.

## Validation and evidence

`verify.sh` builds the module, records tool versions, runs all exception probes,
the casemap alignment regression, the protocol test (with stress when requested),
and independent negative config tests. Every failure exits nonzero. Test processes have bounded deadlines and
are terminated in cleanup. Run tests serially per BUILD directory.

Positive protocol requirements:

1. Actual WebAssembly header; on Linux, actual live `/proc` executable and argv.
2. Two clients each receive 001, 002, 003, and 004 registration numerics.
3. JOIN events and both users in NAMES replies.
4. Exact bidirectional channel PRIVMSG delivery.
5. A message split across TCP writes and a peer PART.

`STRESS=1` additionally requires Linux `/proc` and exercises three batches of 24
registered clients (72 total), alternating abrupt disconnects and clean QUITs,
PING/PONG to survivors after descriptor compaction, a 64 KiB unterminated input
rejection, an unregistered connection timeout, and continued healthy-client
service. The test checks host descriptors return to baseline (allowance two),
RSS stays below 512 MiB and grows by less than 64 MiB, and a four-second idle
window consumes less than two CPU seconds. These are short regression thresholds,
NOT a demonstrated capacity limit, load SLA, sustained soak, or leak proof.

Negative cases require a normal nonzero exit and specific diagnostic, never a
runtime trap: invalid server ID, malformed syntax, executable include, missing
include, duplicate oper class, recursive include, guest privilege dropping, TLS profiles,
and connection hooks. Unsupported security settings fail explicitly rather than
being silently ignored. No listener is needed.

Generated evidence (all ignored; never commit binaries, tools, or transient logs):

- `build-wasi/src/inspircd.wasm` and its SHA-256 in `acceptance.json`.
- `build.log`, `tool-versions.log`, `exception-check.log`.
- `wasmedge-server.log`, `irc-transcript.log`, `acceptance.json`, `stress.json`.
- `negative-*.log`, `negative-config.json`.

The guest PID is wasi-libc's emulated 42, not the host PID. Use `/proc` evidence.
The optional `NATIVE_PREFIX` test mode runs an installed native server instead;
never use that mode as WebAssembly acceptance evidence.

`.github/workflows/ci-wasi.yml` is fork-scoped, read-only, and time-bounded. It
bootstraps WASI tools from scratch, runs stress and negative checks, and also
builds/tests native poll and epoll variants on Ubuntu. Existing upstream
workflows are preserved, including the broader irctest suite. A checked-in
workflow is not evidence of a successful run: verify terminal results at the
published commit before promoting anything.

## Native alignment regression

A local native Debug build using the unprivileged Zig 0.16.0 C++ toolchain
(Clang 21.1.0) found a misaligned uint64_t load in the inherited MurmurHash code
at startup. The fix uses memcpy for both 32-bit and 64-bit loads, preserving
native byte order and the existing mixing operations rather than disabling the
runtime safety check. `check-casemap.cpp` compares aligned and unaligned inputs
for 129 lengths at 16 offsets. The original source fails the native check; the
fixed source passes native 64-bit and Wasm 32-bit checks. Native CI runs this
regression with UBSan. Full sanitizer/fuzz coverage remains a separate gate.

## Supported experimental scope

- Single foreground server, inbound IPv4 loopback TCP, static core IRC commands.
- Seventeen groups: channel, clients, info, list, lusers, message, mode, oper,
  serialize_rfc, stats, stub, user, wallops, who, whois, whowas, xline.
- Static factories enter the normal ModuleManager lifecycle; absent modules fail.
- WasmEdge v2 socket ABI adapters convert family/address/port/error values;
  wasi-libc provides poll/read/write/recv/shutdown/close.
- Sparse descriptor maps scale by active count rather than descriptor magnitude.
  The port caps registered handlers at 1024 and closes new accepted sockets when
  full. The cap includes listeners and has not been saturation-qualified.
- WebAssembly linear memory is capped at 256 MiB, including a 4 MiB stack.
  This does NOT bound host runtime RSS, CPU, socket buffers, files, or log storage;
  out-of-memory graceful recovery has not been qualified.
- Native branches remain native. WASI omits process/signal/identity operations;
  RESTART and executable config includes fail explicitly. Rehash reads config
  synchronously (only ConfigReaderThread is included), so it can stall the loop.

Unsupported: dynamic modules/reload, DNS lookup, TLS inside the guest, server
linking, databases, optional/background-worker modules, outbound connect, UDP,
Unix sockets, socket-option changes, fork/exec, privilege dropping, process
signals, meaningful guest process IDs, and native CPU/resource statistics.
Unsupported adapter calls return errors. Poll errors use EIO without SO_ERROR.
IPv6 conversion exists but is unqualified; no IPv6 deployment claim is made.

## Production gates (all required for a production claim)

1. **Publication/reproducibility:** reviewed source-only commit, verified fork SHA,
   clean-checkout bootstrap, successful fork CI at that exact SHA, retained
   evidence. Reconfirm license/provenance and integrity pins for tool upgrades.
2. **Runtime:** supported stable WasmEdge containing both exception fixes; full
   probes/config regressions repeated on every supported runtime/architecture.
   Current RC is a development dependency, not a production recommendation.
3. **Native compatibility:** terminal native poll/epoll results and applicable
   upstream irctest suite. Add sanitizer-backed adapter/descriptor tests.
4. **Error paths:** unavailable modules/options, failed binds, descriptor
   saturation/reuse, OOM/resource exhaustion, invalid rehash preserving live
   configuration, valid rehash, and recovery after each fault.
5. **Capacity/security:** sustained realistic concurrency/traffic and reconnect
   soak; slow readers/writers, sendq/flood controls, malformed/fuzzed IRC input,
   latency/CPU/RSS/FD measurements and declared workload envelope. The short
   churn test does not satisfy this gate.
6. **Operational security:** reviewed host isolation, dedicated unprivileged
   user/container, explicit network policy, host CPU/memory/PID/FD/log quotas,
   read-only binaries, protected configuration, restart policy/backoff, logging,
   monitoring, backups and rollback/recovery drills. WASI alone is not sufficient.
7. **Transport/privacy:** for any non-loopback usage require an existing maintained
   TLS terminator such as HAProxy or stunnel on the host. Keep plaintext backend
   private; manage certificates/renewal outside the guest. No custom cryptography.
   Proxying collapses client IPs unless a separately supported, tested forwarding
   protocol exists (none is qualified here); ban/rate-limit/oper access policy
   must account for that. A TLS terminator is a proposal, not a deployed service.

Until these gates pass, use only isolated local development/testing. Do not
expose the test server to the Internet or assume upstream production support.
