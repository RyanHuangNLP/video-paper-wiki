# Terminal 2 — 实时引用校验与论文选择

先读 COMMON、CONTRACT、freeze.json。cwd 为 ROOT/.work/parallel/lightweight-workflow-v2/terminal-2/source；Grok 4.6 / xhigh。预计约 3–5 小时，完成合同 B：用当前源文档与索引验证全部证据，给 Q&A/写作统一的选论文语义，并原子输出 Markdown。

## 精确自有源码范围

- `src/video_paper_wiki_research/light_index.py`
- `src/video_paper_wiki_research/light_context.py`（新增）
- `tests/research/test_light_index.py`
- `tests/research/test_light_context.py`（新增）
- `tests/research/test_light_selection.py`（新增）

不改纯 light_qa/light_writing、CLI、PDF、Skill 或共享测试 helper。T1 依赖的 index 私有函数/返回形状必须保留。新校验 helper 可加在 index/context 内；不能通过减少检查字段、信任传入 hashes 或吞异常返回 OK 来通过测试。

## 已复现输入

只读 `E/import-gap-observation.json` 与 `E/prove_import_gap.py`：基线真实 CLI 对 valid control、伪造 context 文本并重算 hash、导出后改 source、改 source 后重建 index 再导入旧 context，四项均成功。你的实现必须保留第一项成功并关闭后三项；最终新 CLI 回归归 T4，你的 API 定向回归先证明修复。

## 连续里程碑

1. 实现严格当前 index/source snapshot 验证和 validate_live_context；对三项已复现问题建立回归，覆盖所有 evidence（含未被引用的坏 row）。用实际 metadata/Markdown 派生完整 chunk set，防 index 与 context 一起伪造。实现 qa/writing export_context，冻结公开函数后发布 backend milestone，供 T3 继续。
2. 实现 render_document/import_document，保留当前 body/citation 配对及路径展示规则；output 相对路径以当前 cwd 解析，所有链接以 output.parent 计算。拒绝前校验、提交前重验、同目录原子安装、create-only 模式与失败时保留旧输出。
3. 严格 paper selection：None/[] 全选，合法重复 ID 去重，未知/错误格式/空串拒绝，多篇中筛选后再 top-k；QA/写作同规则。多篇 fixture 证明错误 ID 不会悄悄退回全集，选中论文无结果时不会引用未选论文。
4. 对抗与兼容：篡改 title/page/path/offset/chunk_id/hash/text/df/token_count、缺失/额外/重复 chunk、类型错误、未引用坏证据、改 source 保留 anchor、改后重建、无变化重建、删除论文、metadata 编辑、输出 symlink/路径碰撞、校验间发生修改、I/O 异常和旧输出保留。回归现有轻量纯 renderer/API 后冻结 final。

## 必须证明的行为

对正确 context 新输出成功且每个 citation 的 text 等于源文件相应 Unicode slice；坏例必须明确非零/ok=false（API 测 status），没有新 Markdown，已有输出 SHA 不变。相同源内容的 no-op index rebuild 不会凭时间戳让 context 失效。export/search 遇 index 损坏稳定返回 INDEX_STALE，不抛 KeyError。render_document 是只读；import_document overwrite=False 在并发同目标情况下最多一个创建成功。

不要把模型的 score 当源身份；要求有限数值即可。selected_paper_ids 是新增限制字段，保留旧 light-context.v1 缺该字段时的兼容，但必须执行实时源验证。现有纯 renderer 的 fixture 不含真实 workspace，不能因为新 I/O 层而破坏纯测试。

## 验证与交接

跑自己的三个 test 文件与 `tests/research/test_light_qa.py`、`test_light_writing.py`、`test_light_pipeline.py` 相关旧项。直接输出 API smoke 证明从正确源码导入。CLI 最后由 T4 接线；不得把基线 CLI 仍有旧问题误称新 API 失败，亦不得声称尚未接线的 CLI 已修复。交接列出每种拒绝 status、结果产物 SHA、回归和全部输入绑定。
