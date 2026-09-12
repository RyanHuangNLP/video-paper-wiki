# Builder development brief — manual-pdf-extraction-v1 (user-direct)

status: IMPLEMENTATION_COMPLETE_PENDING_REVIEW
stopped_writing: true
recorded_at_utc: 2026-09-06T04:20:00Z
role: Builder (Grok Build, grok-4.6 / xhigh)
claim: fixture_vertical_flow_only
acceptance: not_requested
ci: not_run
real_data: not_run
human_approval: not_claimed
canonical_publication: not_claimed

The historical deadline brief `development-brief.md` is preserved unchanged.

## 1. Frozen inputs

| Item | Path | SHA-256 |
| --- | --- | --- |
| contract | `docs/ai/contracts/manual-pdf-extraction-v1.md` | `d09215792fd250f6687c29346a2513c5bdb0e44ca974d14c89fe842ef9d1da5f` |
| packet | `docs/ai/packets/RESEARCH-WIKI-MANUAL-PDF-EXTRACTION.md` | `011aa774238441f2d62fe7a471650bab1df480b2e7b5a5c5405aff1768efc454` |
| baseline | git HEAD | `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f` |

Working tree is uncommitted. No git commit/push/merge was performed.

## 2. Usage

Default package (no Docling, no admin):

```bash
vpwiki-research pdf intake --pdf /path/to/paper.pdf --session s1
vpwiki-research pdf plan --intake .work/research/s1/manual-pdf/intakes/<sha>.json \
  --profile .work/research/s1/manual-pdf/profile/profile.json --batch-id plan-1
vpwiki-research pdf context --intake <intake.json> --profile <profile.json> \
  --run .work/research/s1/manual-pdf/runs/<run-id> \
  --upstream-root vendor/claude-obsidian --session s1
vpwiki-research pdf analyze --context <context.json> --proposal <unsealed.json> \
  --upstream-root vendor/claude-obsidian --session s1
```

Optional external producer (not in the default lock; never imported by the agent CLI):

```bash
vpwiki-parser profile --artifacts-path /path/to/offline-models --session s1
vpwiki-parser export --intake <intake.json> --profile <profile.json> \
  --artifacts-path /path/to/offline-models --session s1 --run-id run-1
```

`pdf plan` does not create an approval-ref. Staged extraction is not capture, not receipt-backed, and not published.

## 3. Tests actually run

Python 3.13.13 from the locked source venv. Command:

```bash
PYTHONPATH=src:operator/parser_executor/src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python -m pytest -q tests/research
```

Result: **28 passed**.

Also: `tests/security/test_cli_isolation.py` + `tests/contract/test_dependency_manifest.py` + `tests/unit/test_commands.py` + `tests/unit/test_staging.py` → 89 passed together with research tests.

These are synthetic-fixture results. They are not a real Docling, real PDF, real Vault, or human acceptance.

## 4. Unfinished

- Real user PDF + pinned offline Docling/models smoke is pending.
- Canonical genesis/admission/publication is the next packet.
- Dual Python 3.12 full suite and Linux/macOS CI were not run.
- Isolated `uv build --offline` could not resolve hatchling in this worktree cache; the installed test uses an isolated prefix copy of the shipped packages plus a pth bridge to locked jsonschema/pypdf.
- `tests/security/test_cli_isolation.py` was updated so the new `vpwiki-research` console script does not fail the no-admin assertion. That file is outside the original packet brace list; the change is only the scripts dict.

## 5. File hashes

See `file-hashes.sha256` in this directory.
