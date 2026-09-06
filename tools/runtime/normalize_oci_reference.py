#!/usr/bin/env python3
"""Add the OCI reference metadata containerd needs when importing a layout."""

import argparse
import io
import json
import os
import tarfile
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--reference", default="latest")
    args = parser.parse_args()

    with tarfile.open(args.archive) as incoming:
        members = incoming.getmembers()
        index_member = next((member for member in members if member.name == "index.json"), None)
        if index_member is None:
            raise SystemExit("OCI archive does not contain index.json")
        index_stream = incoming.extractfile(index_member)
        if index_stream is None:
            raise SystemExit("OCI index.json is unreadable")
        index = json.load(index_stream)

    manifests = index.get("manifests")
    if not isinstance(manifests, list) or len(manifests) != 1:
        raise SystemExit("OCI archive must have exactly one top-level manifest")
    descriptor = manifests[0]
    annotations = descriptor.setdefault("annotations", {})
    annotations["org.opencontainers.image.ref.name"] = args.reference
    # BuildKit's containerd-private image-name annotation prevents ctr from
    # materializing the OCI ref-name entry during import.
    annotations.pop("io.containerd.image.name", None)
    encoded_index = json.dumps(index, separators=(",", ":")).encode()

    with tempfile.NamedTemporaryFile(dir=args.archive.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with tarfile.open(args.archive) as incoming, tarfile.open(temporary_path, "w") as outgoing:
            for member in incoming:
                content = incoming.extractfile(member) if member.isfile() else None
                if member.name == "index.json":
                    member.size = len(encoded_index)
                    outgoing.addfile(member, io.BytesIO(encoded_index))
                elif content is None:
                    outgoing.addfile(member)
                else:
                    outgoing.addfile(member, content)
        os.replace(temporary_path, args.archive)
    finally:
        temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
