"""Disposable fixtures for the pinned manual-PDF capture adapter."""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT / "vendor/claude-obsidian"
PAYLOAD = b"%PDF-1.4\n% vpkb manual capture\n%%EOF\n"
SOURCE_PATH = "inbox/paper.pdf"
OPERATION_ID = "capture-manual-pdf-test"
GENERATED_AT = "2026-09-01T04:00:00Z"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_vault(base: Path, *, reuse: bool = False) -> Path:
    vault = base / "vault"
    for relative in (".obsidian", "wiki", ".raw", "inbox"):
        (vault / relative).mkdir(parents=True, exist_ok=True)
    (vault / SOURCE_PATH).write_bytes(PAYLOAD)
    if reuse:
        captured = vault / ".raw/captured"
        captured.mkdir()
        (captured / f"{sha256(PAYLOAD)}.pdf").write_bytes(PAYLOAD)
    return vault


def snapshot_tree(root: Path) -> dict[str, tuple[str, int, bytes | None]]:
    result: dict[str, tuple[str, int, bytes | None]] = {}
    for path in [root, *sorted(root.rglob("*"))]:
        info = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        kind = "dir" if stat.S_ISDIR(info.st_mode) else "file" if stat.S_ISREG(info.st_mode) else "other"
        result[relative] = (
            kind,
            stat.S_IMODE(info.st_mode),
            path.read_bytes() if kind == "file" else None,
        )
    return result
