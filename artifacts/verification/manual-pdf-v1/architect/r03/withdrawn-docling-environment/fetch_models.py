#!/usr/bin/env python3
"""Download the five pinned public model artifacts; never reads a PDF."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODELS = ROOT / ".work/models/docling-2.117.0"
LOCK = HERE / "models.lock.json"


def verify(path, spec):
    if not path.is_file() or path.stat().st_size != spec["size"]:
        return False
    digest = hashlib.sha256() if spec["sha256"] else hashlib.sha1()
    if not spec["sha256"]:
        digest.update(f"blob {spec['size']}\0".encode())
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == (spec["sha256"] or spec["blob_id"])


def fetch(spec):
    target = MODELS / spec["directory"] / spec["file"]
    if verify(target, spec):
        print("VERIFIED " + spec["file"], flush=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".download")
    url = f"https://huggingface.co/{spec['repo']}/resolve/{spec['revision']}/{spec['file']}"
    print("DOWNLOAD " + spec["file"] + f" ({spec['size']:,} bytes)", flush=True)
    start = last = time.monotonic()
    downloaded = 0
    with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            downloaded += len(chunk)
            now = time.monotonic()
            if now - last >= 20:
                print(f"{spec['file']}: {downloaded:,}/{spec['size']:,} bytes", flush=True)
                last = now
    if not verify(partial, spec):
        raise RuntimeError("Model checksum mismatch: " + spec["file"])
    partial.replace(target)
    print(f"VERIFIED {spec['file']} ({time.monotonic()-start:.1f}s)", flush=True)


if __name__ == "__main__":
    specs = json.loads(LOCK.read_text())
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(fetch, specs))
    print("MODELS_READY", flush=True)
