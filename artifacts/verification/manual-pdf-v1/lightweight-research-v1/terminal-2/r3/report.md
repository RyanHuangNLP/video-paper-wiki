# TERMINAL-2 r3 — 共享 raw 路径边界修复

## Functionality
本修订只关闭独立审查复现的 raw symlink/`..` 边界缺陷，不改公共 API / schema / 选择、合并、refresh 语义：

1. `light_knowledge._raw_absolute_path` 在 normpath/resolve 之前检查原始分量；任何产品边界上的 raw `..` 立即以 `WORKSPACE_INVALID` 拒绝。
2. 随后检查给定路径与解析后边界：已存在/不存在的 output 父目录，以及指向内部或外部目录的 symlink，均不得越过 `.work`。
3. 普通绝对路径和相对 `.work/ws` 仍可用。
4. 全部 batch/refresh 公共入口、只读 `knowledge_batch_status` 与 `knowledge_batch_backup_blockers` 继承同一拒绝；拒绝路径不创建计划、不改 HEAD/notes、不改 output 哨兵字节。
5. 直接测试 `require_product_workspace`、`require_work_output`，以及未改动的 `import_comparison` 在已有哨兵字节上的 output 拒绝。
6. `knowledge_batch_backup_blockers` 只增加对共享 `require_product_workspace` 的继承，不改分类/备份语义。
7. 保留全部 R2 complete-inventory、refresh seed/ancestry 与 merge/finalization 测试。

`light_backup.py` 与 `light_knowledge_refresh.py` 字节未改。R2/files 七份拷贝保持历史，未回写。

## Files
Eight owned paths in handoff/ready and `files/`. All eight cumulative copies are present relative to BASE, including unchanged `src/video_paper_wiki_research/light_backup.py`.

Changed from stopped R2 snapshot `202c7fffafa4589f9a8db21fbf6f4ecc97a48c38f2f49b241dc319999da88532`:
- `src/video_paper_wiki_research/light_knowledge.py`
- `src/video_paper_wiki_research/light_knowledge_batch.py`
- `tests/research/test_light_knowledge.py`
- `tests/research/test_light_knowledge_batch.py`
- `tests/research/test_light_knowledge_refresh.py`

## Tests
- Focused: 111 passed, exit 0, `/private/tmp/t2-research-r3-final/focused`
  - `test_light_knowledge_batch.py`: 22
  - `test_light_knowledge_refresh.py`: 10
  - `test_light_knowledge.py`: 39
  - `test_light_backup.py`: 40
- Interpreter: `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 3.13.13
- cwd: `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-research-v1/terminal-2/source`
- Modules resolved from this worktree `src/` via PYTHONPATH and `-o pythonpath=ABS_SOURCE/src`. Not a root editable import.
- uv 0.12.7 at `/Users/huangzhanpeng/.hermes/bin`; no copied venv, no installs, no Git mutation.
- R2 的 108 项测试不覆盖 raw symlink/`..` 缺陷；本修订新增 3 项回归，不得把 108 当作本缺陷的覆盖证明。

## Unresolved issues
- T3 CLI/Skill/docs 不在本 lane，未编辑。
- `light_backup.py` 的写作修订识别仅在 Architect 明确移交该精确文件后才交给 T3。
- 双 Python / wheel / CI / PR95 / 真实 inbox PDF / 当前模型试验仍属 Architect/T3 集成工作。
- 未做 commit、push、merge、真实 Vault/admin 或 human-gate 关闭。`architect_accepted` 保持 false。

## Status
ready_for_architect; architect_accepted=false; stopped_writing=true.
