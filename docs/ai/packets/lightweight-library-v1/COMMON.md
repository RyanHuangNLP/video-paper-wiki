# Common lane protocol

ROOT=/Users/huangzhanpeng/python_code/video-paper-wiki
BASE=3368c6435db166a285b4b0e2df00f5d6a7491956
EVIDENCE=ROOT/artifacts/verification/manual-pdf-v1/lightweight-library-v1

Read the current root AGENTS.md/task-index/codex-team plus this README/CONTRACT/freeze and the assigned TERMINAL. Worktree AGENTS contains historical previous-packet paths; this new Architect packet, authorized by the latest user, owns the explicit current path handoff. Never infer permission to edit a different lane or the root's old product checkout.

Model/runtime: existing Luna/xhigh controller, one Cursor Builder, pinned cursor-grok-4.6-xhigh-fast via run_cursor.py; preserve Smart Auto. New task -> new chat/run, no latest/continue guessing. Use standard require_escalated for necessary host credentials; preserve denial without evasion. No force/yolo/trust/no-sandbox changes. Do not echo tokens or inspect unrelated account/config files.

Build in your assigned source only. Do not make Git mutations, commit, switch branches, fetch/push/merge, change global config, spawn workers, install dependencies or copy environments. The local pinned upstream submodule must remain detached/clean at 9f8c1199047eac2c3828496279fbb7ba9540b90b. Only your explicit allowlist may differ from BASE; other source is read-only.

Tests use the existing read-only ROOT/.venv/bin/python (3.13.13) with PYTHONPATH set to your exact source/src so the dirty root editable install is never accidentally tested. The existing uv executable is /Users/huangzhanpeng/.hermes/bin/uv (0.12.7); prepend its directory to PATH when a test invokes uv. Set PYTHONDONTWRITEBYTECODE=1, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, UV_OFFLINE=1, UV_PYTHON_DOWNLOADS=never and GIT_OPTIONAL_LOCKS=0. Put short disposable basetemp/cache under a real /private/tmp temporary root (resolve mktemp path). Record python version, module __file__, exact commands, exit codes and final test summary. No copied stale venv, no wrapper executing another source's tests. Scope tests first; full suites only on integrated stopped source after relevant fixes. Architect also has an existing locked Python 3.12.14 environment at /private/tmp/l4r5.s54ypl35/locked-312/bin/python for final dual-version acceptance; never relocate or modify it.

All new durable generated data for product trials is inside a .work subtree. Original PDFs are read-only inputs. Existing inbox/, tools/, plans, hidden configuration, historical source and evidence are preserved. No pretend five-paper corpus. Three verified local PDF inputs are in ROOT/inbox/; T3 may use them after integration for real extraction and current-model trials with Architect.

Each attempt has a fresh controller/run-id. Use root run_cursor.py --lane N --controller-id NAME --prompt-file absoluteUTF8. Controller polls at bounded ~30 seconds, sends concrete run/model/chat/exit/handoff status promptly through collaboration.send_message. Final model self-report is not code acceptance. No app task creation or cross-task coordination tools are needed.

At packet completion Builder writes a fresh immutable revision folder EVIDENCE/terminal-N/rN/ with:
- files/ containing exact copies of every changed owned file (no unrelated file)
- checks.json with actual local command/result evidence and source module provenance
- report.md with functionality, files, unresolved issues and tests
- handoff.json and ready.json with identical bytes: packet/lane/base/contract_sha256, owner, status=ready_for_architect, architect_accepted=false, stopped_writing=true, files manifest and snapshot_sha256. The files array has exactly {path, sha256, size_bytes} rows sorted by UTF-8 path; snapshot_sha256 hashes the canonical JSON array without LF. It covers changed owned paths only; T3 identifies exact imported snapshots separately in inputs.
Write source/evidence hashes from actual bytes. Include an inputs array for any accepted imported lane snapshots. New revisions never overwrite prior reports. Don't claim a commit or remote CI that did not happen.
Then stop source writes. The controller checks complete allowed set, source vs files hashes and ready bytes, confirms process exit/log finalization and reports to Astra. Fixes require explicit next revision instruction. Unresolved contract gaps are reported before changing an interface; independent assigned work can continue.

Only after all owner writers stop and Astra reviews can a reassigned existing controller mutate the delivery Git worktree. Commit/push/update the existing draft PR95 only on explicit Architect handoff; no merge/main/human gate closure.
