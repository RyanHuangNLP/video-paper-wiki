# 人工 PDF 优先的知识库首版

版本：M1 · 2026-09-06 · 用户范围变更的执行补充；保留 R3.2/R3.3 原文。

## 目标与决定

首版先打通 **你提供 PDF → 系统解析并整理知识 → 检索问答 → 大模型生成简单初稿**。用户无需先提供 arXiv 链接或在线预览决定。来源获取由用户完成；在线发现和下载在知识库可用后再扩展。综合写作先使用当前大模型和知识库证据生成初稿，后续通过 Skill 调整结构、风格和流程。

这是用户对首版输入方式与写作复杂度的明确调整，不是 Fable 的推断。原 PRD 中完整研究产品的长期能力保留；本补充决定首个可用版本的开发顺序。原 `RESEARCH-WIKI-W1-PREVIEW` 的网络预览合同仍是未冻结草稿，不进入实现。已完成 CAP 观察保留，不转记为产品测试。

## 首版实际要交付什么

| 用户动作 | 首版结果 | 复用与新增 |
| --- | --- | --- |
| 提供一份本地 PDF | 校验文件、计算唯一摘要、识别重复输入，生成可继续处理的本地状态 | 复用 PDF 校验、local-blob 和 paper identity；补安全本地接收与入口 |
| 整理论文 | 保留完整解析文本及页/块定位，生成论文摘要、方法/训练/实验/局限等知识建议 | 补真实离线解析产物生产者与提案编排；复用已有 artifact、claim、locator 合同 |
| 查看知识库 | Paper/Concept 页面、主题分类、论文之间的基础关联与证据状态 | 复用编译器、canonical records、taxonomy 与事务发布；补用户入口，不另建平行真源 |
| 搜索并提问 | 通过现有 exact/BM25 找到论文与证据，生成带来源定位的回答，缺证据时说明未知 | 复用查询、generation/current-stale 和映射；补有界上下文与大模型回答入口 |
| 输入写作主题/要求 | 用所选或检索到的论文内容生成可编辑 Markdown 初稿，附来源列表和基础引用 | 简单 context → 当前模型 → draft；不先依赖复杂写作 Skill、图检索或完整比较评测 |
| 检查和保留成果 | 能查入库状态、发现过期索引、进行已有的审计及备份/恢复核验 | 复用既有机制；首版入口展示真实状态，不宣称不存在的真实运行验收 |

“知识库能力搭建完成”以这条用户流程可连续运行判断，不能只以新增 schema 数量、PDF 存盘、空 claims 的标题预览或历史 fixture 测试通过判断。

## 首版延后内容

- arXiv/OpenAlex 等在线获取、在线摘要预览、下载重试/缓存/速率控制与版本发现。
- 自动扩展论文、爬取代码仓库、代码官方性审查及多轮研究 agent 编排。
- 多版本展示 head、图/RRF 排名增强、复杂对比 benchmark；当前不支持的第二版本输入继续明确拒绝。
- 专门的长文写作 Skill、复杂结构优化和多轮编辑评审。初稿可以生成，正式受管文章发布仍走既有授权与证据规则。

这些能力均有后续位置，不挡住人工 PDF 知识库首版。用户此前保留的 FABLE-002/008 产品选择不由本补充代选；本次已明确的简单初稿不再依赖复杂比较报告完成。

## 独立代码核查结论

现有底座支持 `input.kind=local-blob`，无外部 ID 时可用 `sha256:<PDF 摘要>` 作为 paper identity；capture/inspect、artifact package、canonical compile、publication、catalog/query、audit、backup/restore 已有实现。无需为了人工输入重写这些底座。

必须补齐的真实缺口是：BlobStore 目前只读；`draft export` 的 pypdf 路径最多读 20 页且输出空 claims；Docling 入口只提供标题预览；`ingest package` 要求四份解析产物已存在，并要求被捕获 PDF 有 receipt。因此“把 PDF 放入 inbox”还不能自然完成有证据的知识整理。

首先实现的工作包应完成安全本地接收、明确的 parser profile、独立离线 Docling 产物生产与既有 package 的交接。接着补齐来源分析/知识建议、状态和发布编排，再接检索问答与简单写作。解析代码可在默认环境用隔离 stub 验证接口，真实模型运行必须单独记录；不能把 stub 当真实论文解析结果。

## 顺序与验收

1. **人工 PDF/解析**：精确输入字节、去重、不可变 profile 与四份解析产物；正常/加密/破损/超限/缺模型/来源变化均有明确结果。
2. **知识整理/发布衔接**：从真实解析块产生有定位的 claim/entity 建议；保留 provisional/unknown，按现有 review/事务/receipt 编译论文与概念页面，支持中断后继续。
3. **检索问答**：复用当前索引和 exact/BM25；索引过期明确返回待重建；回答绑定实际提供的证据和基础引用。
4. **简单写作**：输入主题、要求与论文范围，生成带来源的本地 Markdown 初稿；模型可由当前会话提供，不新增模型服务或预设已验证身份。
5. **贯通验证**：人工提供的 PDF 串通上述流程，并检查已有审计、备份/恢复入口。每步工程测试与真实资料/人工验收分开记录。

这五步是连续的开发顺序，不是重新启动五轮 PRD 讨论。Architect 按接口依赖冻结窄工作包，Builder 实现，Repo Steward 对精确候选独立核验并续交现有 draft PR → integration。任何提交后的 source 或 base 变化重新绑定对应 CI/验收。

## 边界与历史

默认 Python 环境、锁文件与 seed/overlays 的 67 项不因本补充改变。不安装/运行 vpwiki-admin，不自动下载 Docling 模型，不修改真实 Vault；副作用仍由既有 operator/user 路径负责。本地 PDF 不是许可或人工 claim 通过的证明。不会为首版简单写作新设编辑 gate。

仓库观察：基线 `bcff631ce12fe777ab6db7a4dd6531db3bbaea3f`，PR 94 为 OPEN DRAFT，目标 integration `08709894adfb20ec07e976783f0ba436d975b74f`。历史 Tests run `33642835702`/attempt 1 在 merge preview `ee6159ea7d3b36720b862617b3a9a2c99ef3ba73` 四项各 2152 通过；它只证明旧基线，不证明本次新功能。

参考：[范围决定](packets/RESEARCH-WIKI-MANUAL-PDF-SCOPE.md)、[R3.3 原 PRD](video-generation-research-wiki-v1-prd-r3.3.md)、[R3.2 讨论](video-generation-research-wiki-v1-prd-r3.md)、[团队流程](codex-team.md)。
