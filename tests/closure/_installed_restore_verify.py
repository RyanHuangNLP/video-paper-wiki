"""Run restore verification with writer tripwires in the installed wheel."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from pathlib import Path

from video_paper_wiki import backup_archive, catalog_store, publication, staging, upstream_runtime
from video_paper_wiki.restore_verification import verify_restored_vault


def snapshot(root: Path) -> list[dict]:
    root_info=root.lstat()
    rows = [{"path":"","mode":stat.S_IFMT(root_info.st_mode)|stat.S_IMODE(root_info.st_mode),
             "dev":root_info.st_dev,"ino":root_info.st_ino,"nlink":root_info.st_nlink,
             "size":root_info.st_size,"sha256":None}]
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix().encode()):
        info = path.lstat()
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "mode": stat.S_IFMT(info.st_mode) | stat.S_IMODE(info.st_mode),
                "dev": info.st_dev,
                "ino": info.st_ino,
                "nlink": info.st_nlink,
                "size": info.st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
                if stat.S_ISREG(info.st_mode)
                else None,
            }
        )
    return rows


def main() -> None:
    source, restore, manifest_path, upstream, config_path = map(Path, sys.argv[1:6])
    writers: list[str] = []

    def forbidden(*_args, **_kwargs):
        writers.append("called")
        raise AssertionError("read-only restore verification invoked a writer")

    for owner, name in (
        (catalog_store, "build_current_catalog"),
        (catalog_store, "build_catalog_database"),
        (catalog_store, "_run_builders"),
        (publication, "stage_publication_request"),
        (backup_archive, "create_backup_archive"),
        (backup_archive, "restore_backup_archive"),
    ):
        setattr(owner, name, forbidden)
    for name in ("stage_transaction_inspect_files", "stage_compilation"):
        if hasattr(staging, name):
            setattr(staging, name, forbidden)

    real_run = upstream_runtime.subprocess.run
    children: list[list[str]] = []

    def observe(argv, *args, **kwargs):
        words = [str(value) for value in argv]
        children.append(words)
        joined = " ".join(words)
        if any(
            token in joined
            for token in (
                " transaction apply ",
                " catalog build ",
                " backup create ",
                " backup restore ",
                " --apply",
                " bm25-index.py build",
            )
        ):
            forbidden()
        return real_run(argv, *args, **kwargs)

    upstream_runtime.subprocess.run = observe
    before = snapshot(restore)
    result = verify_restored_vault(
        source_root=source,
        restore_root=restore,
        manifest=json.loads(manifest_path.read_bytes()),
        upstream_root=upstream,
        config=json.loads(config_path.read_bytes()),
    )
    after = snapshot(restore)
    print(
        json.dumps(
            {"result": result, "writers": writers, "children": children, "unchanged": before == after},
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
