# Cloud development handoff — 2026-09-13

The user requested a commit of the current local changes before moving development
to cloud. This checkpoint preserves the current workspace, including previously
untracked plans, work packets, verification records, research code and tools.
It is a saved working state, not a new implementation acceptance or CI result.

## Choose the development baseline deliberately

- The main workspace checkpoint is based on
  `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`, on
  `repair/vpkb000-plan-approval-prepare-follow2`.
- The more recent development baseline is the already committed, clean
  `codex/code-proof-v1` at `d440c7aaebb4dcc2c52cab719b0d73347a41493f`,
  currently checked out under `.work/parallel/code-proof-v1/terminal-1/source`.
  Its Git repository is separate from the main workspace repository.
- Start continued product development from the CODE proof branch. The main
  workspace's older source files must not overwrite that newer implementation.
  The checkpoint also preserves coordination and evidence that were maintained
  outside the newer development checkout.

The next-work inventory is
[REMAINING-DEVELOPMENT-2026-09-11-R2.md](packets/full-todo-v1/REMAINING-DEVELOPMENT-2026-09-11-R2.md).
Its recorded CODE I/O attempts are evidence, not accepted implementation.
Check the actual source and recorded outcomes before continuing any old task.

## Local checkpoint validation

The main workspace passed 36 tests covering publication and the research modules:

```sh
VPKB_COMMIT_TEST_TMP="$(mktemp -d /tmp/vp.XXXXXX)"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q \
  tests/unit/test_publication_wave.py tests/upstream/test_publication_wave.py \
  tests/research --basetemp "$VPKB_COMMIT_TEST_TMP/p" \
  -o cache_dir="$VPKB_COMMIT_TEST_TMP/cache"
```

These results apply to this local working snapshot only. They are not a full
regression run, remote CI, or acceptance of the newer development branch.

## Materials that remain local

Existing ignored environments, generated `.work/` data and historical worktrees
remain local. Untracked PDFs, disposable verification virtual environments and
nested test checkouts, macOS `.DS_Store` files and the local Feishu task-store lock
are excluded. Historical evidence retains its original
bytes, paths and claims; local absolute paths will need their corresponding
artifacts or a deliberate mapping when used on another machine.

Saving this checkpoint does not merge a PR, update `main`, close a human gate,
restart a Builder or paused automation, or establish a running cloud environment.
Remote publication and cloud execution should be verified separately from local
commit success.
