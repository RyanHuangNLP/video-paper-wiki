import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.preview_fixture import NOW, observation, write_json
from video_paper_wiki_research.cli import main
from video_paper_wiki_research.paper_preview import request_paper


@pytest.mark.parametrize("attack,expected", [
    ("duplicate-json", "ARTIFACT_INVALID"), ("deep-json", "ARTIFACT_INVALID"),
    ("invalid-unicode", "ARTIFACT_INVALID"), ("oversize", "RESPONSE_TOO_LARGE"),
    ("symlink", "WORK_PATH_UNSAFE"), ("parent-symlink", "WORK_PATH_UNSAFE"),
    ("hardlink", "WORK_PATH_UNSAFE"), ("fifo", "WORK_PATH_UNSAFE"),
])
def test_external_bridge_refusals_are_bounded(checkout, capsys, attack, expected):
    result = request_paper(arxiv="2408.06072v2", session="preview", now=NOW)
    source = checkout / "input.json"
    if attack == "duplicate-json":
        source.write_bytes(b'{"request":1,"request":2}')
    elif attack == "deep-json":
        source.write_bytes(b'[' * 2000 + b'0' + b']' * 2000)
    elif attack == "invalid-unicode":
        source.write_bytes(b'"\\ud800"')
    elif attack == "oversize":
        source.write_bytes(b' ' * 1048577)
    elif attack == "fifo":
        os.mkfifo(source)
    else:
        real = checkout / "real"
        real.mkdir()
        original = real / "input.json"
        original.write_bytes(b'{}')
        if attack == "symlink":
            source.symlink_to(original)
        elif attack == "parent-symlink":
            link = checkout / "linked"
            link.symlink_to(real, target_is_directory=True)
            source = link / "input.json"
        else:
            os.link(original, source)
    assert main(["paper", "observe", "--session", "preview", "--request", result["request"]["path"],
                 "--observation", str(source)]) == 2
    raw = capsys.readouterr().out
    assert len(raw) < 4096
    assert json.loads(raw)["error"]["code"] == expected
    root = checkout / ".work/research/preview/preview-v1"
    assert not list((root / "observations").iterdir())


def test_subprocess_entrypoints_are_offline_and_preserve_vault_catalog(checkout):
    root = Path(__file__).parents[2]
    hook = checkout / "hook"
    hook.mkdir()
    (hook / "sitecustomize.py").write_text(
        "import socket,subprocess,os\n"
        "def blocked(*a,**k): raise AssertionError('unexpected network or operator process')\n"
        "socket.socket=blocked\nsocket.create_connection=blocked\nsocket.getaddrinfo=blocked\n"
        "subprocess.Popen=blocked\nos.system=blocked\n", encoding="utf-8")
    sentinel_dir = checkout / "bin"
    sentinel_dir.mkdir()
    sentinel = sentinel_dir / "vpwiki-admin"
    sentinel.write_text("#!/bin/sh\nprintf invoked > operator-was-invoked\nexit 99\n")
    sentinel.chmod(0o755)
    vault = checkout / "disposable-vault"
    vault.mkdir()
    (vault / "paper.md").write_text("Disposable Vault sentinel\n")
    (vault / "catalog.json").write_text('{"entries":[]}\n')
    protected = list(vault.rglob("*")) + list((root / "docs/seed").rglob("*"))
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in protected if p.is_file()}
    env = {**os.environ, "PYTHONPATH": str(hook) + os.pathsep + str(root / "src"),
           "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
           "PATH": str(sentinel_dir) + os.pathsep + os.environ.get("PATH", "")}

    def call(*args):
        result = subprocess.run([sys.executable, "-m", "video_paper_wiki_research", "paper", *args,
                                 "--session", "preview"], cwd=checkout, env=env, text=True,
                                capture_output=True, timeout=20)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)["data"]

    requested = call("request", "--arxiv", "2408.06072v2", "--now", NOW)
    request = json.loads(Path(requested["request"]["path"]).read_bytes())
    bridge = write_json(checkout / "bridge.json", observation(request))
    observed = call("observe", "--request", requested["request"]["path"], "--observation", str(bridge))
    context = call("preview", "context", "--metadata", observed["metadata"]["path"])
    proposal = context["expected_proposal"]
    proposal["generated_at"] = NOW
    proposal_path = write_json(checkout / "proposal.json", proposal)
    preview = call("preview", "validate", "--metadata", observed["metadata"]["path"], "--proposal", str(proposal_path))
    call("preview", "render", "--preview", preview["preview"]["path"])
    call("decide", "--preview", preview["preview"]["path"], "--action", "later", "--event-id", "fixture-event",
         "--user-text", "Synthetic fixture choice", "--source", "fixture", "--recorded-at", NOW)
    call("list")
    engine = subprocess.run([sys.executable, "-c", "from video_paper_wiki.cli import main; raise SystemExit(main(['--help']))"], cwd=checkout,
                            env=env, capture_output=True, text=True, timeout=20)
    assert engine.returncode == 0
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items())
    assert not (checkout / "operator-was-invoked").exists()
    assert not list((checkout / ".work").rglob("*.pdf"))
