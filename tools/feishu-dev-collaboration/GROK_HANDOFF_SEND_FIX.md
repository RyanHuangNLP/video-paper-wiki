# Grok CLI implementation handoff: Feishu async delivery fix

Date: 2026-08-30. User explicitly delegates the next repair to Grok CLI.
Codex owns architecture and review; Grok implements and self-tests.

## Scope and authority

Implement a small, production-compatible fix in this directory's `cli_bridge` and tests. Document results in `GROK_SEND_FIX_RESULT.md`. Do not merely propose a fix: make the changes and run tests.

You may read the installed Hermes source at `/Users/huangzhanpeng/.hermes/hermes-agent` to verify contracts; use its venv Python for tests. Do not edit Hermes upstream, profiles, credentials, or launchd files. Do not restart/stop any gateway. Do not send Feishu messages, call model APIs, invoke Codex, create business tasks, approve PRDs, modify task-data, or implement subtract/add. Do not access Vault or unrelated projects. No git commit/push/merge, dependency upgrades, broad permission changes, or subagents. Use apply_patch for edits. Preserve existing files and changes.

The default Ryan gateway must remain untouched. Both new profile plugin directories are symlinks to this code, so a later restart must be done by Codex after review, not by you.

## Verified deployment state

- New profiles: codexarch (Codex architecture) and grokdev (Grok implementation).
- Both gateways are running and WebSocket-connected; human @bot /dev-status succeeds in both directions.
- Group is named `code_agent开发群` (not codex_agent); only Ryan and these two bots. Credentials now authenticate successfully. No credential values are needed for this repair.
- Both profiles have role-specific CLI policies enabled. Gateway generic provider is disabled (`model.provider: auto`, `providers.auto.enabled: false`, empty fallback chain), intentionally. Do not re-enable it.
- Real owner's open_id differs per app; existing profile bindings account for that. TaskStore is shared.
- 61 tests passed before this repair (`python -m unittest discover -s tests -q`). Those passes missed the production enum mismatch.

## Failure and concrete reproduction

Human /dev-prd created task `d2029758833f4f9b8aaa08a11fea203a`. Codex CLI successfully generated the PRD and stored stage=draft, not drafting. Its last_error is `delivery failed: gateway send unsuccessful`.

Record: `task-data/tasks/d2029758833f4f9b8aaa08a11fea203a/state.json`.
PRD: `task-data/tasks/d2029758833f4f9b8aaa08a11fea203a/prd.v1.txt`.
PRD SHA-256: `6d38fa8b790675325ae9dd95d46e0101050b809cb6aaff854208feb4a1a3d7e1`.
This task must remain unapproved and its files unchanged.

`cli_bridge/route.py` normalizes Route.platform to a string via `.value`. `cli_bridge/plugin.py::_send` indexes `gateway.adapters[route.platform]`. Production Hermes defines `class Platform(Enum)` (NOT `class Platform(str, Enum)`) in `gateway/config.py`; GatewayRunner.adapters is keyed by that enum. Therefore `{Platform.FEISHU: object()}['feishu']` raises KeyError before adapter.send is reached. _send catches the exception and returns False, obscuring the reason. The old acceptance test creates `class Platform(str, Enum)` and therefore fails to reproduce the real interface.

Installed adapter signature is correct and should be preserved:
`FeishuAdapter.send(self, chat_id: str, content: str, reply_to=None, metadata=None) -> SendResult`.
Do NOT rename content to text. The underlying issue is adapter lookup, not argument names.

## Required implementation and acceptance

1. Resolve the adapter deterministically by normalized platform identity, supporting production plain Enum keys and existing string-keyed test adapters. Match only the requested platform; never fall back to the first adapter or silently cross platforms. Preserve the testable plugin's ability to import without Hermes installed (avoid unnecessary hard coupling).
2. Use the shared corrected send path for async PRD/build/review completion and peer handoffs. Preserve role checks, owner/peer/group checks, mention formatting, max-hop limits, and human-only approval.
3. Add bounded, useful diagnostics for missing adapter / send exceptions / failed SendResult, without logging message contents, tokens, credentials, or complete potentially sensitive exception strings.
4. Add regression tests using a real plain Enum shaped like Hermes Platform. Show both async completion delivery and peer handoff work with it; retain string-key support; assert unknown platforms cannot send to another adapter. Include failure handling assertions and no unauthorized state transitions. If feasible, add/run a separate integration check importing actual installed `gateway.config.Platform` (not a replacement str Enum).
5. Run full tests using `/Users/huangzhanpeng/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests -q` from this directory. A mocked pass is not proof of live Feishu delivery; report exactly what was tested.
6. Verify real pending task state/PRD hashes unchanged. Record changed files, root cause, test counts/results, and any residual risks in GROK_SEND_FIX_RESULT.md.

## Remaining work: audit/report, not authorized to execute

- Codex must review changes, then restart ONLY new profile gateways if approved and no jobs active.
- Existing generated PRD should be delivered without rerunning its generation and without automatic approval. Identify a safe recovery method; do not execute it or clear errors by hand.
- Earlier Bot-to-Bot /dev-status probes were sent successfully but no peer replies were observed. This is not solved merely by fixing async delivery. A future live test must distinguish Feishu event delivery, mentions, sender identity, and routing. Report any clear additional problem without expanding this patch unnecessarily.
- Shared tasks belong to Codex app-scoped owner IDs; review whether later Grok-side authorization/cancellation assumes the same human open_id across apps. Report findings; do not loosen authorization to work around a mismatch.
- Full Codex→human approval→Grok→Codex workflow has NOT passed live Feishu acceptance. The ready_for_pr records with owner local-owner were earlier local test runs, not proof of the live workflow.

Return a concise summary, exact test commands/results, and the remaining operator steps. Do not claim any gateway restart, message delivery, or end-to-end pass that you did not perform.
