# TERMINAL-2 r2 — 完整长文分批知识与选择性增量刷新（有界修复）

## Functionality
本修订按 FIX-T2-R2.md 八组修复停止态 T2 R1，不改公共 API / CLI / schema：

1. 现场完整 inventory/partition 绑定；自洽子集或仅重哈希计划在 export/import/finalize 拒绝。
2. 零批 refresh 从同论文 base 重算安全 seed；伪造 seed 或截断 inventory 不能作为授权摘要；全 unknown 终态不推 HEAD。
3. 已接受 batch 在复用/合并/finalize 前按自身 partition 重验 citation 所有权。
4. 滚动合并要求连续 step/parent/next-batch 哈希；非零完成作业的 merge_sha256 必须等于 merges/<batch_count-1>.json。
5. 扩展记录绑定最终作业结果；refresh/selection 校验同论文祖先；processing_complete 公共记录不能认证 pending 作业。发布中的私有 candidate 与公共 current/complete 分离，避免 record↔completion 递归校验。
6. completion 必须指向真实记录页；HEAD 后/记录后中断可由精确重试恢复；外来 HEAD 不是本操作。
7. 作业目录与文件集合一并校验；未知空目录/额外文件/symlink/hardlink 保留并拒绝；pending/unknown 继续阻断备份。
8. 畸形输入关闭而不 traceback；legacy one-shot 与搬迁后完成历史仍可读，不跟随旧绝对路径。

`light_backup.py` 字节未改，仍依赖 batch 分类结果做 pending/completed 识别。

## Files
Eight owned paths in handoff/ready. `files/` copies only the seven paths whose bytes changed from stopped R1 snapshot `5abc88dac56fc77f4ecbb9858f1f9c82950266a10558ee4a64842515a26a6181`. Unchanged: `src/video_paper_wiki_research/light_backup.py`.

## Tests
- Focused: 108 passed, exit 0, `/private/tmp/t2-research-r2-final/focused`
  - `test_light_knowledge_batch.py`: 21
  - `test_light_knowledge_refresh.py`: 9
  - `test_light_knowledge.py`: 38
  - `test_light_backup.py`: 40
- Interpreter: `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python` 3.13.13
- Modules resolved from this worktree `src/` via PYTHONPATH. Not a root editable import.
- uv 0.12.7 at `/Users/huangzhanpeng/.hermes/bin`; no copied venv, no installs, no Git mutation.
- R1 的 94 项测试不覆盖五处已复现缺陷；本修订新增回归，不得把 94 当作本缺陷的覆盖证明。

## Unresolved issues
- T3 CLI/Skill/docs 不在本 lane，未编辑。
- `light_backup.py` 的写作修订识别仅在 Architect 明确移交该精确文件后才交给 T3。
- 双 Python / wheel / CI / PR95 / 真实 inbox PDF / 当前模型试验仍属 Architect/T3 集成工作。
- 未做 commit、push、merge、真实 Vault/admin 或 human-gate 关闭。`architect_accepted` 保持 false。

## Status
ready_for_architect; architect_accepted=false; stopped_writing=true.
