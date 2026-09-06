#!/usr/bin/env python3
"""Fetch public release artifacts with pinned GitHub release SHA-256 digests.

Requires Python >= 3.11, curl, GNU tar, Linux x86_64. No installer scripts or root access.
The destination must be dedicated to this toolchain; extraction is repeatable.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import zipfile


def main():
    if sys.version_info < (3, 11):
        raise SystemExit("bootstrap requires Python >= 3.11")
    if (platform.system(), platform.machine()) != ("Linux", "x86_64"):
        raise SystemExit("pinned binaries support Linux x86_64 only")
    root = Path(__file__).resolve().parents[2]
    tools = Path(os.environ.get("TOOLS", root / ".wasi-tools")).resolve()
    cache = tools / "downloads"
    cache.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(Path(__file__).with_name("toolchain.json").read_text())
    for artifact in manifest["artifacts"]:
        archive = cache / artifact["url"].rsplit("/", 1)[1]
        if not archive.exists():
            partial = archive.with_suffix(archive.suffix + ".partial")
            subprocess.run(["curl", "--fail", "--location", "--retry", "3",
                            "--connect-timeout", "30", "--max-time", "600",
                            "--proto", "=https", "--proto-redir", "=https",
                            "--output", str(partial), artifact["url"]], check=True)
            partial.rename(archive)
        with archive.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != artifact["sha256"]:
            raise SystemExit(f"integrity failure: {archive}; refusing extraction")
        destination = tools / artifact["destination"]
        destination.mkdir(parents=True, exist_ok=True)
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as bundle:
                if bundle.namelist() != ["ninja"]:
                    raise SystemExit("unexpected Ninja archive contents")
                bundle.extract("ninja", destination)
            (destination / "ninja").chmod(0o755)
        else:
            # Only the exact digest-pinned upstream bundles reach extraction.
            subprocess.run(["tar", "--extract", "--gzip", "--file", str(archive),
                            "--directory", str(destination), "--no-same-owner",
                            "--no-same-permissions"], check=True)
        print(f"Verified and extracted {archive.name}: {digest}", flush=True)


if __name__ == "__main__":
    main()
