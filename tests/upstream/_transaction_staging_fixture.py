from __future__ import annotations

import os
import stat
from pathlib import Path

from tests.support import make_checkout
from tests.contract.test_transaction_independent import _publication
from tests.upstream import test_vpkb001_transaction_inspect as accepted
from video_paper_wiki.transaction_staging import stage_transaction_inspect_transport


def vault_snapshot(root: Path) -> dict[str, tuple[str, bytes | None, int]]:
    result: dict[str, tuple[str, bytes | None, int]] = {}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        relative = path.relative_to(root).as_posix()
        if stat.S_ISREG(info.st_mode):
            result[relative] = ("file", path.read_bytes(), stat.S_IMODE(info.st_mode))
        elif stat.S_ISDIR(info.st_mode):
            result[relative] = ("dir", None, stat.S_IMODE(info.st_mode))
        else:
            result[relative] = ("other", None, stat.S_IMODE(info.st_mode))
    return result


def prepare(
    tmp_path: Path,
    monkeypatch,
    kind: str,
) -> tuple[dict, dict[str, bytes], dict[str, bytes | None], dict[str, bytes | None], Path, Path, dict]:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    make_checkout(checkout)
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    if kind == "later-generic":
        proposal, supplied, originals, reads = _publication(sequence=2)
        proposal, _raw = accepted.seal(proposal, supplied)
        for path, data in {**reads, **originals}.items():
            if data is None:
                continue
            target = vault / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            os.chmod(target, 0o640)
    elif kind == "ingest":
        proposal, supplied, _raw = accepted.ingest(vault)
    else:
        proposal, supplied, _raw = getattr(accepted, kind)()
    if kind != "later-generic":
        originals = {}
        for path, digest in proposal["expected_hashes"].items():
            originals[path] = None if digest is None else (vault / path).read_bytes()
        reads = {}
        for path, digest in proposal["read_preconditions"].items():
            reads[path] = None if digest is None else (vault / path).read_bytes()
    before = vault_snapshot(vault)
    monkeypatch.chdir(checkout)
    staged = stage_transaction_inspect_transport(
        proposal,
        write_bytes=supplied,
        original_bytes=originals,
        read_bytes=reads,
        batch_id="staged-inspect",
    )
    return proposal, supplied, originals, reads, checkout, vault, {"before": before, "staged": staged}


def transport_paths(checkout: Path) -> tuple[Path, Path]:
    work = checkout / ".work"
    bundle = work / "staged-inspect/transaction-inspect/bundle.json"
    return work, bundle
