#!/usr/bin/env python3
"""Hash-check an entire GHCR OCI graph using anonymous pull authorization."""

import argparse
import hashlib
import json
import re
import urllib.request


def verify(image, digest):
    if not re.fullmatch(r"ghcr\.io/[a-z0-9._/-]+", image):
        raise ValueError("expected a GHCR repository without a tag")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("expected an immutable SHA-256 digest")
    repository = image.removeprefix("ghcr.io/")
    # Request an anonymous pull token directly from the known registry endpoint.
    # It stays in memory and is never part of evidence or error messages.
    url = f"https://ghcr.io/token?service=ghcr.io&scope=repository:{repository}:pull"
    with urllib.request.urlopen(url, timeout=60) as response:
        token = json.load(response)["token"]
    verified = {}

    def visit(expected, kind, size=None):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected):
            raise ValueError("unsupported descriptor digest")
        if expected in verified:
            if size is not None and verified[expected]["size"] != size:
                raise ValueError("conflicting descriptor size")
            return
        request = urllib.request.Request(
            f"https://ghcr.io/v2/{repository}/{kind}/{expected}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json",
            },
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        if "sha256:" + hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"digest mismatch: {expected}")
        if size is not None and len(data) != size:
            raise ValueError(f"size mismatch: {expected}")
        verified[expected] = {"kind": kind, "size": len(data)}
        if kind == "manifests":
            manifest = json.loads(data)
            if "manifests" in manifest:
                for child in manifest["manifests"]:
                    visit(child["digest"], "manifests", child["size"])
            else:
                for blob in [manifest["config"], *manifest["layers"]]:
                    visit(blob["digest"], "blobs", blob["size"])

    visit(digest, "manifests")
    return {"image": f"{image}@{digest}", "anonymous_pull": True, "verified": verified}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("digest")
    args = parser.parse_args()
    print(json.dumps(verify(args.image, args.digest), indent=2, sort_keys=True))
