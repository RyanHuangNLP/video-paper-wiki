# TERMINAL-2 r1 — 完整长文分批知识与选择性增量刷新

## Functionality
T2 实现冻结的完整长文分批知识、有界滚动合并、普通记录/视图集成、待处理作业备份识别，以及选择性增量刷新：

- `plan_knowledge_batches` / `export_knowledge_batch` / `import_knowledge_batch` / `knowledge_batch_status` / `export_knowledge_merge_context` / `import_knowledge_merge` / `finalize_knowledge_batches` / `knowledge_batch_backup_blockers` 在 `light_knowledge_batch.py`
- `plan_knowledge_refresh` / `export_knowledge_diff` / `apply_knowledge_refresh` 在 `light_knowledge_refresh.py`
- `light_knowledge.py` 扩展显式 batch/refresh wrapper、coverage/provenance、祖先遍历与普通 record/view；legacy `import_knowledge` 仍只接受现场重算的 one-shot `light-knowledge-context.v1`
- `light_backup.py` 窄扩展：pending batch-job → `LIGHT_BACKUP_INVALID`；未知/篡改 job → `LIGHT_BACKUP_CONFLICT`；已完成且无 pending stage 的 job 作为历史纳入备份

关键语义：贪心分批 ≤48 chunks 且 `sum(len(text))≤80000`、最多 128 批；超限或无 derived evidence 先拒绝且不建 job；滚动合并禁止复活已丢弃 citation、禁止截断；full finalize 发一条普通 knowledge record 并推 HEAD；refresh finalize 只发 candidate 不推 HEAD；全 unknown 终稿写 `INSUFFICIENT_EVIDENCE` 且不推 HEAD；精确重试可复用；跨 workspace（含 restore）不可 resume。

## Files
Eight owned paths only. See `handoff.json` files manifest and `snapshot_sha256`.

## Tests
- Focused: 94 passed, exit 0, `/private/tmp/t2-research-r1-final/focused`
  - `test_light_knowledge_batch.py`: 12
  - `test_light_knowledge_refresh.py`: 6
  - `test_light_knowledge.py`: 37
  - `test_light_backup.py`: 39
- Interpreter: `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 3.13.13
- Modules resolved from this worktree `src/` via PYTHONPATH. Not a root editable import.
- uv 0.12.7 at `/Users/huangzhanpeng/.hermes/bin`; no copied venv, no installs, no Git mutation.

## Unresolved issues
- T3 CLI/Skill/docs 不在本 lane，未编辑。
- `light_backup.py` 的写作修订识别仅在 Architect 明确移交该精确文件后才交给 T3。
- 双 Python / wheel / CI / PR95 / 真实 inbox PDF / 当前模型试验仍属 Architect/T3 集成工作。
- 未做 commit、push、merge、真实 Vault/admin 或 human-gate 关闭。`architect_accepted` 保持 false。

## Status
ready_for_architect; architect_accepted=false; stopped_writing=true.
