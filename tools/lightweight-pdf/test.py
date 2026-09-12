#!/usr/bin/env python3
"""Run the existing suite with a writable cache and short temporary paths."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--evidence", type=Path, required=True)
args = parser.parse_args()
evidence = args.evidence.resolve()
evidence.mkdir(parents=True, exist_ok=True)
if (evidence / "full-pytest.log").exists():
    raise SystemExit("Use a new evidence directory to preserve the previous run.")
cache = ROOT / ".work/cache/uv-tests"
cache.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryFile(dir=cache):
    pass
run_root = Path(tempfile.mkdtemp(prefix="vp.test.", dir="/private/tmp"))
try:
    with socket.socket(socket.AF_UNIX) as probe:
        probe.bind(str(run_root / "socket"))
except PermissionError:
    raise SystemExit("Sandbox forbids Unix sockets. Run this command in a local terminal or with approved execution permissions; no tests started.")
env = dict(os.environ)
env.pop("PYTHONPATH", None)
uv = Path.home() / ".hermes/bin/uv"
env.update({"PATH": str(uv.parent) + os.pathsep + env.get("PATH", ""),
    "UV_CACHE_DIR": str(cache), "UV_OFFLINE": "1", "UV_PYTHON_DOWNLOADS": "never",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": "/private/tmp"})
cmd = [str(ROOT / ".venv/bin/python"), "-B", "-m", "pytest", "-q", "--basetemp", str(run_root / "p"), "-o", "cache_dir=" + str(run_root / "cache")]
start = time.monotonic()
with (evidence / "full-pytest.log").open("w") as log:
    child = subprocess.Popen(cmd, cwd=args.source.resolve(), env=env, stdout=log, stderr=subprocess.STDOUT)
    launch = {"pid": child.pid, "argv": cmd, "source": str(args.source.resolve()), "run_root": str(run_root), "uv_cache": str(cache)}
    (evidence / "launch.json").write_text(json.dumps(launch, indent=2) + "\n")
    print(json.dumps(launch), flush=True)
    code = child.wait()
result = {"exit_code": code, "elapsed_seconds": round(time.monotonic() - start, 3)}
(evidence / "test-result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result), flush=True)
print("\n".join((evidence / "full-pytest.log").read_text().splitlines()[-10:]), flush=True)
raise SystemExit(code)
