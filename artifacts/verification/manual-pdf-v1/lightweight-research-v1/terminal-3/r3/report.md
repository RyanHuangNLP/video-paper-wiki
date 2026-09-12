# TERMINAL-3 r3 — 写作项目残余返修

## Functionality
T3 R3 只改冻结的两条写作路径，并写出新的 r3 证据。停写的 R1 快照
`0e005388e60f104da964d534219148819b4f6c24161b6cf3259eb632428771f2`
与 R2 快照
`74343c8f1767e92833715c94ee5acba0cabfb8605c279e45bce8236a149b2d98`
及全部审查记录保持原字节。未改 CLI/Skill/docs/`light_backup`，也不自批验收。

三类残余覆盖四次已复现失败：

1. 首次提纲 HEAD 意图必须在任何 revision 安装前完整落盘，并贯穿 revision/HEAD/cleanup 中断。干净的所有权写入前中断可正常重试；已拥有但不完整的 staging 仅按精确所有权/期望字节恢复。删除已完成 HEAD 或未拥有 revision 不得用新 intent 回补。精确重试复用同一 revision identity。
2. 完整公开调用、history 与 backup 关闭畸形 JSON 形值：list/object 枚举、缺失嵌套字段、surrogate、bool/非有限/溢出 score。现场畸形证据为 `LIGHT_CONTEXT_INVALID`；新模型/wrapper 为 `LIGHT_WRITING_PROJECT_INVALID`；已存状态为 `LIGHT_WRITING_PROJECT_CONFLICT` 且 backup 返回有界诊断、不抛异常、不写、不加锁。保留 `INDEX_STALE` 等既有现场状态。不改 legacy `light_context`/`copy_evidence`。
3. 每个 successor 的 selected target 必须是合法章节模型文档（provisional 或精确 unknown）。初始提纲与非目标保留节仍允许 unwritten。伪造 unwritten/no-op 子 revision 在 history/export/import/retry/backup 一律拒绝。合法 unknown-to-unknown、相同 provisional 与精确重试复用保留；不加广泛 no-op 禁令。

## Files
Two owned paths only. See `handoff.json` files manifest and `snapshot_sha256`
`7e49bf284530199f0cc52d8bd927030290725550428ed991be7d74fb3770638f`.

## Tests
- COMMON 精确源 scoped：49 passed, exit 0, `/private/tmp/t3-research-r3/focused`
  - `test_light_writing_project.py`: 19（保留原 16，新增 3）
  - `test_light_writing.py`: 6
  - `test_light_context.py`: 24
- 未改动的 Root `probes/t3_acceptance.py`：12/12 passed，新报告
  `terminal-3/r3/architect-probes.json`；R1/R2 报告未覆盖。
- Interpreter: `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 3.13.13
- Modules resolved from this worktree `src/` via PYTHONPATH. Not a root editable import.
- uv 0.12.7 at `/Users/huangzhanpeng/.hermes/bin`; no copied venv, no installs, no Git mutation.

## Unresolved issues
- T3 R3 未经 Architect 验收；独立审查与 Architect 审查仍开放。
- CLI/Skill/docs 与 `light_backup` 写作识别不在本 R3 allowlist，未编辑。
- `writing_backup_blockers` 仅供后续集成 owner 调用；不声称备份集成完成。
- 双 Python / wheel / CI / PR95 / 真实 inbox PDF / 当前模型提纲与章节试验仍属 Architect/集成工作。
- 未做 commit、push、merge、真实 Vault/admin 或 human-gate 关闭。`architect_accepted` 保持 false。

## Status
ready_for_architect; architect_accepted=false; stopped_writing=true.
