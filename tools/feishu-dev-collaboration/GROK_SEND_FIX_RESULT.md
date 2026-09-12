# Grok send-fix result

Date: 2026-08-30. Scope: `tools/feishu-dev-collaboration` only.

## Root cause

Hermes `gateway.config.Platform` is a plain `Enum`, not `str, Enum`.  
`Route.platform` is a string (`"feishu"`). Production `GatewayRunner.adapters` is keyed by `Platform.FEISHU`.  
`gateway.adapters["feishu"]` raised `KeyError` inside `_send`, which swallowed the exception and stored `delivery failed: gateway send unsuccessful`.  
The old acceptance test used `class Platform(str, Enum)` and therefore missed this.

## What changed

- `cli_bridge/delivery.py`: resolve adapters by platform identity; match only the requested platform; no first-adapter fallback.
- `cli_bridge/plugin.py`: async completion and peer handoff share `_send_with_status`. Failure tokens only: `missing_adapter`, `ambiguous_adapter`, `send_exception`, `send_unsuccessful`. No credentials, message bodies, or raw exception text.
- Tests: plain `Enum` completion + handoff; unknown platform cannot use another adapter; installed `gateway.config.Platform` host contract.

## Tests

```bash
cd /Users/huangzhanpeng/python_code/video-paper-wiki/tools/feishu-dev-collaboration
/Users/huangzhanpeng/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests -q
```

Result: **74 tests OK** (2.084s). This is not live Feishu delivery.

## Production task (untouched)

- `d2029758833f4f9b8aaa08a11fea203a` still `draft`, unapproved.
- PRD SHA-256 still `6d38fa8b790675325ae9dd95d46e0101050b809cb6aaff854208feb4a1a3d7e1`.
- `state.json` sha256 `161ea3ec930e4502122feaa0ae7f9adec0972aa6ff9a45e05e8dd7e9584888da`.

Safe recovery (not executed): owner `/dev-resend <task-id>` after Codex restarts the two new gateways. Do not rerun draft, do not approve, do not edit state.json.

## Not done here

- No gateway restart, no Feishu send, no live proof that PRD now arrives in the group.
- Bot-to-Bot inbound silence is a separate issue (see SETUP_FEISHU.md §6.3).
