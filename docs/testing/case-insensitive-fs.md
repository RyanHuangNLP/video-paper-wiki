# Case-insensitive filesystem and portable apply-write faults

This note covers the seven macOS CI failures against
`integration@13fa8220573454611fd3689e9dfcd0a469d7c6e3`. The consumer already
rejects spelling collisions and rolls back failed writes. The defects were in
**test fixtures**, not production apply code.

## Failures

| ID | Test | Cause |
|---|---|---|
| F1–F5 | article / domain / experiment apply write-fault cases | Injectors resolved the target fd with `os.readlink("/proc/self/fd/N")`. That path does not exist on macOS, so the wrapper fell back to `""` and never raised `ENOSPC`. |
| F6 | `test_apply_rejects_parent_directory_case_collision_before_write` | Consumer correctly refused `PAPERS` vs planned `papers`. The trailing `papers.exists()` call aliases the existing `PAPERS` entry on a case-insensitive volume. |
| F7 | `test_apply_post_commit_collision_keeps_committed_paths_and_repair_store` | Writing `PAPERS/private.txt` beside an installed `papers` directory creates a sibling only on case-sensitive volumes. On a case-insensitive volume it adds a file inside `papers`, so post-verify reports `inventory` instead of a spelling collision. |

## Test semantics

F1–F5 locate the prepared create payload and inject `ENOSPC` at the real
`os.write` for that file. The target fd is identified by `(st_dev, st_ino)` of
the path that `_write_excl` just created. The wrapper does not read
`/proc/self/fd` or `/dev/fd`, and it does not guess “the Nth write in the
process”. Open, `created_files` registration, and rollback stay on the
production path. Each case asserts that the inject hit and that the target file
already existed. Article successor and domain orphan cases write at least one
byte before failing.

F6 keeps the `PAPERS/private.txt` fixture, `READING_COMPILE_TARGET_INVALID`,
`portable_collision`, and the file snapshot. Zero extra directory entries are
proved by comparing real `os.listdir` / walk names before and after apply, not
by a lowercased `exists()`.

F7, inside the after-commit callback, renames the installed directory with a
casefold-distinct transit name:

```text
papers → .vpkb-fs-rename-<hex> → PAPERS
```

That yields a real `PAPERS` directory entry on both case-sensitive and
case-insensitive volumes, with the original contents and no leftover transit
name. The case must keep `READING_APPLY_VERIFY_FAILED`,
`prior_code=READING_COMPILE_TARGET_INVALID`, `reason=portable_collision`,
`next_action=repair_store`, and `committed_paths` containing
`wiki/reading/manifest.json`. `inventory` is not an accepted reason.

Path folding is only a collision detector. Canonical paths, IDs, manifests, and
consumer result spellings are unchanged.

A separate “two same-fold names exist at once” case may skip only when the
actual temporary volume cannot host that pair. Skip must follow a volume probe,
not `sys.platform`. This packet does not add such a case; F1–F7 always run.

## Volume probe and focused replay

Run this on the same temporary volume the tests will use. macOS acceptance
requires a case-insensitive volume.

```bash
set -euo pipefail

for VPKB_FS_PY in 3.12 3.13; do
  uv sync --locked --python "$VPKB_FS_PY"
  VPKB_FS_TMP="$(mktemp -d /tmp/vpmfs.XXXXXX)"
  VPKB_FS_TMP="$(uv run --offline --no-sync python -c \
    'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve())' \
    "$VPKB_FS_TMP")"

  uv run --offline --no-sync python - "$VPKB_FS_TMP" <<'PY'
import os
import sys
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory(dir=sys.argv[1]) as directory:
    root = Path(directory)
    original = root / "CaseProbe"
    alias = root / "caseprobe"
    original.write_bytes(b"probe")
    insensitive = alias.exists() and os.path.samefile(original, alias)
    print(sys.version)
    print("case_insensitive =", insensitive)
    print("directory_entries =", sorted(p.name for p in root.iterdir()))
    if sys.platform == "darwin":
        assert insensitive, "macOS 验收需使用大小写不敏感的测试卷"
PY

  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 UV_PYTHON_DOWNLOADS=never \
    uv run --offline --no-sync python -m pytest -q -ra \
    --basetemp "$VPKB_FS_TMP/p" \
    -o cache_dir="$VPKB_FS_TMP/cache" \
    tests/unit/test_{article,domain,experiment,reading}_apply.py \
    tests/unit/test_{article,domain,experiment,reading}_apply_operator.py \
    tests/unit/test_reading_publication.py
done
```

Linux workstations typically print `case_insensitive = False`. That does not
replace macOS or CI evidence.

## No `/proc/self/fd` regression

This process-local patch makes `readlink("/proc/self/fd/...")` raise `ENOENT`
and forwards every other `readlink`. It checks that F1–F5 no longer need that
path. It is not a case-insensitive filesystem test.

```bash
set -euo pipefail
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 UV_PYTHON_DOWNLOADS=never \
  uv run --offline --no-sync python - <<'PY'
import errno
import os
import sys

import pytest

real_readlink = os.readlink


def readlink(path, *args, **kwargs):
    text = os.fsdecode(os.fspath(path))
    if text == "/proc/self/fd" or text.startswith("/proc/self/fd/"):
        raise OSError(errno.ENOENT, "No such file or directory", path)
    return real_readlink(path, *args, **kwargs)


os.readlink = readlink
sys.exit(
    pytest.main(
        [
            "-q",
            "-ra",
            "tests/unit/test_article_apply.py::test_apply_replace_heads_mismatch_and_faults",
            "tests/unit/test_article_apply.py::test_apply_genesis_write_rollback_removes_articles_dir",
            "tests/unit/test_domain_apply.py::test_apply_write_phase_oserror_unlinks_orphan",
            "tests/unit/test_experiment_apply.py::test_apply_replace_heads_mismatch_and_faults",
            "tests/unit/test_experiment_apply.py::test_apply_genesis_write_rollback_removes_experiments_dir",
        ]
    )
)
PY
```

After the fixture fix the five cases must pass under that patch. Full
`macos-15 × Python 3.12/3.13` evidence remains with draft PR CI.
