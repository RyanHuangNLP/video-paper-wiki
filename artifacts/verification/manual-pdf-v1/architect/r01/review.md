# 终端 1–3 报告审阅

日期：2026-09-06。结论：三份候选可以继续用于终端 4 集成，但整体尚未验收；以下功能问题必须处理后，才能宣称 PDF 问答/写作主链路可用。

本轮读取三份完成报告、现有构建/安装证据，检查相关源码及差异，并核对候选哈希。未执行新的 pytest、构建、Grok、真实 PDF 解析、Git 写入或远程操作。本结论不是完整源码审计、CI 验收或提交授权。

原报告和配套小型证据共 30 个文件原字节归档。42 项已有源码/产物哈希与报告记录一致。来源见 [sources.json](../../sources.json)，本轮观察及源码哈希见 [source-observation.json](source-observation.json)。这证明当前观察对象与记录一致，不将旧测试重标为新的集成测试。

## 需要终端 4 优先处理

### R1 / 高：上下文缺少模型可以阅读的证据内容

静态源码确认：主仓库 `src/video_paper_wiki_research/qa.py:119` 的 `_bind_ranked_evidence` 只输出 paper/claim/unit/chunk 标识、locator、标题等元数据；`export_qa_context` 原样导出这些字段，没有加入 claim 正文或来源摘录。`writing.py` 复用同一个构造函数。

结果是模型虽拿到可引用的身份，却没有回答论文方法、实验和局限所需的内容。现有测试使用预写的模型回答，不能证明模型仅靠导出的上下文能够生成有依据的回答。

要求：在导出上下文中提供与 locator/来源摘要相绑定的实际证据文本，并保持提案与原文区别。用具体问题验证导出文件确实包含回答依据，不让测试答案从上下文之外取得知识。

### R2 / 高：引用字段分别存在，不等于它们属于同一条证据

静态源码确认：`qa.py:358` 的 `_match_citation` 在省略 `evidence_unit_id` 时，分别检查 `paper_id` 属于论文集合、`locator_fingerprint` 属于全局指纹集合、`chunk_id` 属于全局 chunk 集合。缺少三者共同归属检查。

具体触发：上下文中有论文 A 和 B，只提供 `paper_id=A` 与 B 的合法 fingerprint，省略 unit ID，可通过当前分支并返回这个错误组合。该问题涉及结构关联本身，与科学事实正确性审查无关。

要求：所有同时提供的引用字段必须匹配同一条已提供证据；维持原有合法的论文级引用语义时也不能接受拼接字段。补两个论文之间交叉配对的最小回归。终端 2 报告的“现有 15 项测试通过、未发现问题”保留为当时结论，不作为无缺陷证明。

### R3 / 高：PDF locator 的浮点兼容缺口尚未解决

终端 3 报告明确说明：测试选用无 bbox 浮点的代码 locator，PDF bbox locator 不能完成当前 catalog 往返。源码中 `evidence_join.py` 的 inventory/mapping 哈希直接调用 integer-only `canonicalize`；`jcs.py` 对 float 明确拒绝。

终端 2 对 `.raw/derived/<digest>/docling/<digest>/document.json` 的解析修复只解决发布侧原始文档 JSON，未覆盖上述 evidence inventory / mapping 编码问题。

要求：终端 4 以实际 PDF locator、非整数坐标贯通发布到索引再到 QA；使用局部且一致的编码方式保存定位和身份，不能通过把 PDF 换成代码 locator、丢掉定位信息或全局放宽账本 JCS 来声称成功。

### R4 / 集成验收缺口：当前检索测试并未执行真实 BM25 全链路

`tests/research/test_qa.py:178` 除 BM25 查询外，还替换了 upstream 验证和 current catalog material collector。因此报告中的“仅隔离 BM25 子进程”不完全准确。现有测试能够证明部分模块行为，不能证明 PDF 发布产物被真实索引并检索。

要求：最后的贯通测试使用同一次发布产生的数据、实际 pinned upstream 和索引，不植入另一份现成 catalog。现有单元测试可保留，不需重复重写；新增检查应覆盖它们尚未证明的连接处。

## 各终端结论与问题裁定

### 终端 1

- 提取候选可以纳入集成。报告的 28 项及扩展 89 项结果属于该候选，本轮未重跑。
- 真实 root/parser wheel 均存在且摘要匹配，安装日志显示 research 模块、schema、prompt 来自安装目录。原先“只有目录拷贝”的缺口已有补充证据。
- 当前 wheel 探测通过 `.pth` 复用共享环境的运行依赖，入口检查为 missing-args 的 USAGE 响应；可证明构建和基本安装布局，不能称为完整独立运行环境或集成功能验收。终端 4 对最终源码再验收；旧安装探测脚本运行时应指定新的输出目录，保留归档证据。
- `tests/security/test_cli_isolation.py` 属于新 research 入口的合理配套修改，允许终端 4 纳入集成范围。实际差异将精确 scripts 字典断言改为单项断言；集成时保留明确的脚本集合检查即可，不需要再开一轮架构工作包。
- 本轮不启动 Steward、不批准单独 commit；继续按用户指定的终端 4 集成流程。

### 终端 2

- source admission / publication 适配与仅针对 derived Docling document 的有限浮点解析属于本次衔接范围，允许纳入集成；严格账本/receipt 解析保持。
- `pages_included=false` 是报告明确列出的限制：provisional 草案只准备 records/events/ledger，正式 paper/concept 页面仍依赖既有 assessment 规则。不能把这一结果写成“论文页面已发布、索引已贯通”，也不能自行升级为人工 accepted。终端 4 应明确哪些步骤可演示、哪些等待真实操作/人工输入。
- capture 绑定使用实际读取的事务前后状态；历史示意代码不能代替这份证据。package/paper 的准备、apply 与读取顺序在集成中核对。
- 15 项 QA/writing 复查通过属于测试覆盖范围内结论；R1/R2/R3/R4 仍未被它覆盖。

### 终端 3

- 独立模块入口、导出上下文/导入模型文档的基本方案符合本轮方向；代码仍须修复 R1/R2 并完成 PDF 集成验收。
- 其完成报告六个源码/测试文件哈希与当前文件相符。
- SVD 验收草案可作为辅助材料，已原字节归档。用户后来指定真实验收论文为 Downloads 下的 SANA-Video 2.0，不能用 SVD 草案替代 SANA 实测，也不能把 pypdf 抽字说成 Docling 解析。

## 给终端 4 的交接

按 R1、R2、R3 和 R4 处理功能与覆盖缺口，不重做三套已有模块。对当前集成候选记录实际源码目录与文件哈希、可运行命令、测试及 wheel 结果和未完成事项。保留 provisional、operator 和人工环节的真实状态。

交接写入统一绝对目录下新的 `terminal-4/rNN/report.md` 及 `evidence/`。未创建的目录/报告不代表完成。历史来源文件、原报告、旧测试和旧审查结论不覆盖。

本次没有向其他终端发送消息或启动它们。用户可以将本文件路径直接交给终端 4。
