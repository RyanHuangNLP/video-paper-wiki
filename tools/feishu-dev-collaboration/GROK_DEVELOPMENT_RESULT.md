# Grok development result (M1–M5)

Date: 2026-08-30. Project: `tools/feishu-dev-collaboration`.  
No gateway restart, no Feishu messages, no Vault, no git, no production TaskStore mutation.

## Milestone status

| ID | Item | Status |
| --- | --- | --- |
| M1 | Adapter lookup for plain Enum + string; shared send path; token diagnostics | **implemented / tested** (offline). Live Feishu delivery **blocked** until Codex restarts only `codexarch` and `grokdev`. |
| M2 | `/dev-resend <task-id>` and `/dev-resend <task-id> handoff` | **implemented / tested**. Does not rerun CLI, change PRD hash, approve, or increment `handoff_round`. |
| M3 | `owner_alias_open_ids`; caller must be this profile owner; record owner in same-person set; empty/unknown fail closed; peer cannot approve/cancel | **implemented / tested**. Production profiles **not** edited (Codex/user must add aliases if they want cross-app cancel). |
| M4 | Handoff/dedup/role/round tests; peer inbound diagnosis | **tested** offline. Live Bot-to-Bot inbound **blocked** / not closed. |
| M5 | Unittest, dual-profile fake integration, host `Platform` contract, SETUP, this report | **implemented / tested** offline. Live PRD→approve→build→review **not** claimed. |

## Files changed

- `cli_bridge/delivery.py` (new)
- `cli_bridge/plugin.py`, `engine.py`, `models.py`, `constants.py`, `plugin.yaml`
- `tests/helpers.py`, `tests/test_dual_bot.py`
- `tests/test_delivery.py`, `tests/test_resend.py`, `tests/test_owner_alias.py`, `tests/test_integration_dual_profile.py` (new)
- `SETUP_FEISHU.md`, `GROK_SEND_FIX_RESULT.md`, `GROK_DEVELOPMENT_RESULT.md`

## Test command and result

```bash
cd /Users/huangzhanpeng/python_code/video-paper-wiki/tools/feishu-dev-collaboration
/Users/huangzhanpeng/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests -q
```

**74 tests, OK, 2.084s.** Fake clients only; no live Codex/Grok model calls in this run. Host test imported installed `gateway.config.Platform` (plain Enum).

## Production record (must stay)

- Task `d2029758833f4f9b8aaa08a11fea203a` stage `draft`, `approved_hash` null.
- PRD hash `6d38fa8b790675325ae9dd95d46e0101050b809cb6aaff854208feb4a1a3d7e1`.
- Files not modified.

## Config example (do not apply here)

```yaml
# plugins.entries.cli-bridge.settings on grokdev
owner_open_id: ou_<this-app-ryan>
owner_alias_open_ids:
  - ou_<codex-app-ryan>
```

Symmetric on `codexarch`. Default empty = no extra power.

## Remaining operator / Codex steps

1. Review this diff.
2. If no in-flight CLI jobs: restart **only** `codexarch` and `grokdev` gateways. Do not restart `ai.hermes.gateway` (Ryan).
3. Owner in `code_agent开发群`: `/dev-resend d2029758833f4f9b8aaa08a11fea203a` on Codex Bot to deliver the existing PRD. Do not approve unless the user reads the full PRD and sends the exact hash.
4. Optional: add `owner_alias_open_ids` on both new profiles after confirming the two Ryan `open_id`s.
5. Live Bot-to-Bot: after restart, `@` ping test must check Hermes inbound logs on the peer, not only send API success (SETUP §6.3).

## Risks

- Unittest ≠ 飞书真实验收.
- Peer inbound may still fail on mentions/allow_bots/identity after send lookup is fixed.
- Secrets previously appeared in chat; rotate when convenient.
- Generic Hermes model provider stays disabled; coding still uses Codex/Grok CLI policy.
