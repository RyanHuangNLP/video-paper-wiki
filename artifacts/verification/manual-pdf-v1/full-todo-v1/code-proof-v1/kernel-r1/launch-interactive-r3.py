"""Launch the exact authorized Grok Build packet with an interactive approval path."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path("/Users/huangzhanpeng/python_code/video-paper-wiki")
PACKET = ROOT / "docs/ai/packets/full-todo-v1"
RUN = json.loads((PACKET / "CODE-GIT-KERNEL-dispatch-amendment-r3.json").read_text())
for row in RUN["verified_inputs"]:
    data = Path(row["path"]).read_bytes()
    assert len(data) == row["size_bytes"]
    assert hashlib.sha256(data).hexdigest() == row["sha256"]
source = Path(RUN["source_root"])
for relative in RUN["allowed_source_paths"]:
    assert not os.path.lexists(source / relative), "source no longer pristine"
os.chdir(source)
prompt = Path(RUN["prompt_path"]).read_text()
argv = [RUN["executable"], "--model", "grok-4.6", "--reasoning-effort", "xhigh",
        "--permission-mode", "default", "--no-plan", "--no-subagents",
        "--disable-web-search", "--session-id", RUN["new_session_id"],
        "--max-turns", "40", "--no-alt-screen", "--minimal", prompt]
os.execv(argv[0], argv)
