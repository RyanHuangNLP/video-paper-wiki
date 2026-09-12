# Terminal 2 r3 final repair

Architect 对 r2 的结论是 CHANGES_REQUIRED。本 revision 只修审查复现的三项合同 B 缺口，不扩大产品范围。r1/r2 交接与审查目录保持只读。

## 修复

1. `import_document` 在写出 `.light-out.tmp` 之后、`replace`/`link` 之前再次 `validate_live_context`。失败只清理自有临时文件，保留已有输出或让新目标不存在。overwrite=True 与 create-only 均有分阶注入回归。
2. `validate_live_context` 先检查 kind/query/requirements/paper_ids/index_id/evidence/prompt 的存在与类型；`kind=[]` 不再 TypeError。共享 freshness helper 在缺/错类型 hash 时返回 False，validate/import/search 均为 `INDEX_STALE`，无原始异常。evidence 为 null/0/false/""/缺省/空列表，或缺 query，均为 `LIGHT_CONTEXT_INVALID`。
3. 公开 `light_index.search`：`None`/`[]` 表示全部；空白/非法/未知 ID 返回 `LIGHT_SELECTION_INVALID` 且 evidence 为空；去重后先筛选再 top-k。直接调用 search 的测试已覆盖“未筛选 top-k 之外的选中论文”。

## 测试

- 原 6 文件定向+兼容 + 新增回归：**55 passed**。
- 审查 probe 副本回放：empty 选择 OK；blank/unknown 为 LIGHT_SELECTION_INVALID；kind 列表为 LIGHT_CONTEXT_INVALID；缺 markdown_sha256 为 INDEX_STALE 且无输出；分阶后改 source 为 INDEX_STALE 且旧输出保留。
- 测试日志绑定的五文件 hash 与运行前后一致。

## Agent 3/4 必须重新接收

相对 r2 变化的文件：
- `src/video_paper_wiki_research/light_index.py`
- `src/video_paper_wiki_research/light_context.py`
- `tests/research/test_light_index.py`
- `tests/research/test_light_context.py`
- `tests/research/test_light_selection.py`

T3/T4 已基于 r2 的工作只是历史输入，不是对 r2 的批准。请从本 r3 `files/` 按 hash 重收后复验。`light_index.py` 与 `light_context.py` 都变了。

## 未跑 / 未声称

全量 2246、Python 3.12、wheel、CLI、真实 Vault。本文件不是 Architect 验收。

## 路径

- 源码：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-2/source`
- r3：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-2/handoffs/r3`
- 保留的 r2：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-2/handoffs/r2`
