"""Run a complete locked Python suite against explicitly frozen source bytes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(source: Path) -> list[dict]:
    files = []
    for dirname in ("src", "tests"):
        for path in (source / dirname).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                files.append({"path": str(path.relative_to(source)), "sha256": sha(path),
                              "size_bytes": path.stat().st_size})
    return sorted(files, key=lambda row: row["path"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--source-check", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    report = args.report.resolve()
    assert not report.exists()
    check = json.loads(args.source_check.read_text())
    for row in check["files"]:
        assert sha(source / row["path"]) == row["sha256"], row["path"]
    before = inventory(source)
    temp = Path(tempfile.mkdtemp(prefix="lrfull.", dir="/private/tmp"))
    env = dict(os.environ, PYTHONPATH=str(source / "src"), PYTHONNOUSERSITE="1",
               PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               UV_OFFLINE="1", UV_PYTHON_DOWNLOADS="never", GIT_OPTIONAL_LOCKS="0",
               UV_CACHE_DIR="/Users/huangzhanpeng/.cache/uv",
               LW2_UV_CACHE="/Users/huangzhanpeng/.cache/uv")
    env["PATH"] = "/Users/huangzhanpeng/.hermes/bin:" + env["PATH"]
    inspect = subprocess.run(
        [str(args.python), "-c",
         "import json,sys; from video_paper_wiki_research import cli,light_query,light_knowledge_batch,light_knowledge_refresh,light_writing_project; print(json.dumps({'python':sys.version,'executable':sys.executable,'modules':{m.__name__:m.__file__ for m in [cli,light_query,light_knowledge_batch,light_knowledge_refresh,light_writing_project]}}))"],
        cwd=source, env=env, capture_output=True, text=True, check=True,
    )
    origin = json.loads(inspect.stdout)
    assert all(Path(value).is_relative_to(source / "src") for value in origin["modules"].values())
    command = [str(args.python), "-m", "pytest", "-c", str(source / "pyproject.toml"),
               "--rootdir", str(source), "-o", "pythonpath=" + str(source / "src"),
               "--basetemp", str(temp / "p"), "-o", "cache_dir=" + str(temp / "cache"),
               "-q", str(source / "tests")]
    started = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(command, cwd=source, env=env, text=True, capture_output=True)
    stdout, stderr = report.with_suffix(".stdout.log"), report.with_suffix(".stderr.log")
    assert not stdout.exists() and not stderr.exists()
    stdout.write_text(result.stdout, encoding="utf-8")
    stderr.write_text(result.stderr, encoding="utf-8")
    unchanged = inventory(source) == before and all(
        sha(source / row["path"]) == row["sha256"] for row in check["files"]
    )
    payload = {
        "schema": "lightweight-research-frozen-full-suite.v1", "started_at_utc": started,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(), "command": command,
        "cwd": str(source), "source_check_sha256": sha(args.source_check),
        "origin": origin, "exit_code": result.returncode, "source_unchanged": unchanged,
        "source_and_tests": before,
        "source_and_tests_snapshot_sha256": hashlib.sha256(
            json.dumps(before, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "stdout": {"path": str(stdout), "sha256": sha(stdout)},
        "stderr": {"path": str(stderr), "sha256": sha(stderr)},
        "summary": result.stdout.splitlines()[-8:], "temporary_root": str(temp),
        "passed": result.returncode == 0 and unchanged,
    }
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("passed", "exit_code", "source_unchanged", "summary", "temporary_root")}, ensure_ascii=False))
    raise SystemExit(0 if payload["passed"] else 1)


if __name__ == "__main__":
    main()
