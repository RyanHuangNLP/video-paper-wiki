# TERMINAL-3 r1 — 写作项目提纲与章节修订历史

## Functionality
T3 R1 只实现冻结的写作项目模块及其有意义测试，不改 legacy `light_writing`，也不做 CLI/Skill/docs/`light_backup` 集成：

- `export_writing_outline` / `import_writing_outline` / `export_writing_section` / `import_writing_section` / `writing_project_history` / `export_writing_project` / `writing_backup_blockers` 在 `light_writing_project.py`
- 提纲导入创建内容寻址 project、不可变 outline revision 和校验后的 `HEAD.json`
- 章节导入只替换目标 section，其余 section 与既有 revision 字节保持不变；相同文档精确重试复用同一 `revision_id`
- 使用已有 `validate_live_context`、citation 检查、非阻塞 workspace lock，以及 `.light-writing/staging` 原子发布
- `writing_backup_blockers` 只读：缺失 `.light-writing` 或安全空 staging 返回 `[]`；非空/未知 staging、缺失或冲突 HEAD、被编辑或不完整 bundle 会阻止备份

关键语义：wrapper/document 超限关闭为 `LIGHT_WRITING_PROJECT_INVALID` 且不截断；结构/ID 错误为 `LIGHT_WRITING_PROJECT_INVALID`；发布、父 revision 或用户编辑冲突为 `LIGHT_WRITING_PROJECT_CONFLICT`；现场 source/index 问题传播既有 `INDEX_STALE` / `SOURCE_INVALID` / `LIGHT_WORKSPACE_MISMATCH`。全未写或全 unknown 不能作为完成稿导出；不完整稿可导出并报告 `progress.complete=false`。迁移后历史可读且标记 `historical`，旧绝对 context 不能 resume。

## Files
Two owned paths only. See `handoff.json` files manifest and `snapshot_sha256`.

## Tests
- Focused + legacy scoped: 42 passed, exit 0, `/private/tmp/t3-research-r1/focused`
  - `test_light_writing_project.py`: 12
  - `test_light_writing.py`: 6
  - `test_light_context.py`: 24
- Interpreter: `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 3.13.13
- Modules resolved from this worktree `src/` via PYTHONPATH. Not a root editable import.
- uv 0.12.7 at `/Users/huangzhanpeng/.hermes/bin`; no copied venv, no installs, no Git mutation.

## Unresolved issues
- T3 CLI/Skill/docs 不在本 R1 allowlist，未编辑。
- `writing_backup_blockers` 仅供后续集成 owner 调用；未改 `light_backup.py`，不声称备份集成完成。
- 双 Python / wheel / CI / PR95 / 真实 inbox PDF / 当前模型提纲与章节试验仍属 Architect/集成工作。
- 未做 commit、push、merge、真实 Vault/admin 或 human-gate 关闭。`architect_accepted` 保持 false。

## Status
ready_for_architect; architect_accepted=false; stopped_writing=true.
