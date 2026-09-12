"""Diagnostic tests of the returned source, without changing the CODE checkout."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

here = Path(__file__).parent
setup = json.loads((here / "preview-focused-setup-r5.json").read_text())
name = sys.argv[1]
assert name in ("py312", "py313")
python = {"py312": "/private/tmp/l4r5.s54ypl35/locked-312/bin/python", "py313": "/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python"}[name]
source = Path(setup["source"])
scratch = Path(setup["scratch"]) / name
scratch.mkdir()
out_path = here / f"preview-focused-r5-{name}.stdout.log"
err_path = here / f"preview-focused-r5-{name}.stderr.log"
record_path = here / f"preview-focused-r5-{name}.json"
assert not any(path.exists() for path in (out_path, err_path, record_path))
argv = [python, "-B", "-m", "pytest", "-q", "-c", "/dev/null", "--rootdir", str(source), "--basetemp", str(scratch / "p"), "-o", f"cache_dir={scratch / 'cache'}", str(source / "tests/unit/test_code_proof_resources.py")]
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONPATH=str(source / "src"), UV_OFFLINE="1")
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
with out_path.open("xb") as out, err_path.open("xb") as err:
    result = subprocess.run(argv, cwd=source, env=env, stdout=out, stderr=err)
def pin(path):
    data = path.read_bytes()
    return {"path": str(path), "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
record = {"schema": "full-todo.foundation-preview-focused-result.v1", "started_at_utc": started, "completed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "argv": argv, "cwd": str(source), "exit_code": result.returncode, "stdout": pin(out_path), "stderr": pin(err_path), "setup": pin(here / "preview-focused-setup-r5.json"), "purpose": "diagnostic only; assembled R5 source; no candidate acceptance"}
with record_path.open("x") as stream:
    json.dump(record, stream, indent=2)
    stream.write("\n")
print(json.dumps(record))
print(out_path.read_text()[-2000:])
print(err_path.read_text()[-1000:])
raise SystemExit(result.returncode)
