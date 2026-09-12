# TERMINAL-3 r2 — 写作项目有界返修

## Functionality
T3 R2 只改冻结的两条写作路径，并写出新的 r2 证据。停写的 R1 快照
`0e005388e60f104da964d534219148819b4f6c24161b6cf3259eb632428771f2`
与全部审查记录保持原字节。未改 CLI/Skill/docs/`light_backup`，也不自批验收。

四节修复覆盖五组已复现缺陷：

1. 普通多行 Markdown 与修订 instructions：正文/instructions 允许 LF/CR/tab，保留精确正文字节、非空 provisional、标题/目标单行、长度与引用规则；拒绝 surrogate 与非文本控制字符。
2. 精确中断重试与缺失 HEAD 权限：先计算期望子 revision 与父 ancestry/原 wrapper，只允许该 owned retry bundle；删除已有 HEAD 后不得由 section import 重建。初始无 HEAD 仅在已校验的 owned pending publication 下为 pending。发布文件系统失败关闭为 conflict。
3. 原始路径边与托管新父目录：在 lexical normalization 前拒绝 `..`；本地 writing guard 保护全部托管根（含尚不存在的 `.light-index/new-parent`）；拒绝路径不创建目录、不改 output/state。
4. 完整确定性与语义历史回放：从已校验 context/document 重算 draft/identity/manifest；只允许 named target 改变；子 revision 引用对照原始 evidence。history、live export/import/retry 与 backup 共用同一回放。有效迁移历史仍为 historical 且可纳入；现场复用仍为 workspace mismatch。

## Files
Two owned paths only. See `handoff.json` files manifest and `snapshot_sha256`
`74343c8f1767e92833715c94ee5acba0cabfb8605c279e45bce8236a149b2d98`.

## Tests
- COMMON 精确源 scoped：46 passed, exit 0, `/private/tmp/t3-research-r2/focused`
  - `test_light_writing_project.py`: 16
  - `test_light_writing.py`: 6
  - `test_light_context.py`: 24
- 未改动的 Root `probes/t3_acceptance.py`：12/12 passed，新报告
  `terminal-3/r2/architect-probes.json`；R1 报告
  `terminal-3/architect-probes-r1.json` 未覆盖。
- Interpreter: `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 3.13.13
- Modules resolved from this worktree `src/` via PYTHONPATH. Not a root editable import.
- uv 0.12.7 at `/Users/huangzhanpeng/.hermes/bin`; no copied venv, no installs, no Git mutation.

## Unresolved issues
- T3 R2 未经 Architect 验收；独立审查与 Architect 审查仍开放。
- CLI/Skill/docs 与 `light_backup` 写作识别不在本 R2 allowlist，未编辑。
- `writing_backup_blockers` 仅供后续集成 owner 调用；不声称备份集成完成。
- 双 Python / wheel / CI / PR95 / 真实 inbox PDF / 当前模型提纲与章节试验仍属 Architect/集成工作。
- 未做 commit、push、merge、真实 Vault/admin 或 human-gate 关闭。`architect_accepted` 保持 false。

## Status
ready_for_architect; architect_accepted=false; stopped_writing=true.
