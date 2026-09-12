---
title: Video Paper Wiki Development Plan
title_zh: 视频生成论文知识库开发计划
status: ready-for-vpkb-000
version: 0.3.4
fable_verdict: READY_FOR_VPKB-000
fable_reviewed_version: 0.3.3
fable_reviewed_sha256: "3f170c34d14148b762e2f1efcb151bf669f856bd6dadad28a3f1fa15a7e773a2"
date: 2026-08-30
language: zh-CN
---

# 视频生成论文知识库开发计划

> Fable 第二轮已对 v0.3.1 的 739 行、绑定 SHA-256 输入返回 `READY_FOR_VPKB-000`，六项硬修全部 closed、无 blocker。v0.3.2 的“agent-safe 零 egress”和“retrieval-gold 不在 VPKB-000 冻结”两项方案讨论结论继续保留；v0.3.3 再吸收 Fable non-blocker 与本地固定上游复核修正。此状态只表示可以启动 VPKB-000，不表示所有下游子模块可绕过依赖同时进入生产实现。
>
> v0.3.2 相对 v0.3.1 的两项保留改动：
> 1. agent-safe 零 egress。paper/code/parser-model 下载只走 `vpwiki-admin`；agent 环境不安装该入口，PATH 上也不出现。`prepare` 只消费本地已有 blob，不自算审批 SHA、不回落网络。
> 2. VPKB-000 不冻结 `retrieval-gold.v1`。上游 chunk/BM25 schema 不加字段；evidence unit 的扩展层 exact join/mapping 留给 VPKB-001，脚手架不定检索实现。

## 1. 执行摘要

项目将在两个全新目录中开发，现有 `grok-pilot` 仓库保持不变：

- 代码仓库：`/Users/huangzhanpeng/python_code/video-paper-wiki`
- Obsidian Vault：`/Users/huangzhanpeng/Documents/video-paper-vault`

首版定位为个人、本地、证据链优先的视频生成论文知识库：

- Obsidian 负责阅读、链接、Bases 与人工审核。
- agent-safe `vpwiki` CLI 负责离线联网计划、本地捕获准备、PDF 解析、schema 校验、事务 inspect、索引状态/查询与审计，命令树与实现均零 egress；operator-only `vpwiki-admin` 只在用户独立终端中负责 fetch、apply、索引构建与解析模型 bootstrap，且不得安装进 agent 环境或出现在其 PATH。
- Codex repository Skills 负责论文理解、中文结构化草稿、官方代码映射与证据化问答，但不得调用任何 `apply` 或直接写 Vault。
- 原始 PDF、官方代码文件及其哈希是证据；Wiki 页面、索引与回答是派生产物。
- 每次只摄取一篇论文或映射一个仓库；20 篇基线逐篇完成，优先保证可恢复和可审核。
- Codex staging 位于代码仓库中被忽略的 `.work/<batch-id>/`；Vault 始终位于 Codex workspace 可写根之外。
- 中文正文配合英文 frontmatter key、canonical ID、taxonomy slug 和技术术语别名。
- 不调用额外的模型 API，不建设远程 embedding；Codex 只读取经过选择的本地片段。

核心数据流：

```text
明确论文或官方仓库
  -> 离线生成联网计划和审批哈希
  -> 人工批准精确目标与预算
  -> 用户在独立终端用 vpwiki-admin fetch 拉取字节到本地 staging
  -> 捕获不可变原始文件
  -> Docling 本地解析
  -> Codex 输出结构化 provisional 草稿
  -> 确定性校验与人工审核
  -> 用户在独立终端通过 vpwiki-admin 委托 claude-obsidian 原子事务
  -> Paper / Code / Concept Pages + source / claim ledgers
  -> BM25 + SQLite 可重建索引
  -> 带精确证据 locator 的查询和比较
```

## 2. 目标、非目标与成功定义

### 2.1 Corpus-v1 目标

1. 输入本地 PDF 或一个明确的 HTTPS PDF URL，生成可审核的中文 Paper Page。
2. 每个重要、可证伪的事实都能定位到原 PDF 的页码和 Docling block。
3. 对论文明确关联的官方 GitHub 仓库，固定 commit 并以文件、行号和片段哈希建立代码证据。
4. 保留支持证据、反对证据和不确定性，不允许模型静默解决冲突。
5. 在 Obsidian 中完成论文、概念、代码和 claim 浏览；在 CLI/Codex 中完成证据化问答。
6. 用已批准的 20 篇基线验证从摄取到检索的完整链路。

### 2.2 明确延期

- 自动发现论文、自动跟踪引用图、定时论文雷达。
- 多论文并行 worker、daemon、Web UI、多用户、权限系统和云同步。
- 向量数据库、Graph DB、远程 embedding 和远程 OCR。
- 模型权重、训练数据集或大规模视频数据下载。
- VLM 图表理解、MinerU/GROBID 自动降级链。
- 自动生成并发布综述、博客或技术文章。
- 2025-2026 frontier 模型，以及长视频/世界模型独立技术轴；它们将进入独立的 `frontier-v1`，不改变历史基线。

### 2.3 Corpus-v1 成功定义

本计划采用两个交付层级：`engine-mvp` 只证明三篇论文 + 一仓库的机制纵切，`corpus-v1` 才代表 20 篇知识库首版。Corpus-v1 完成时，20 篇论文都有无重复身份的 Paper Page；所有重要事实都有可解析证据或明确的不支持状态；五个代表仓库的能力声明有 commit 级证据，其余仓库只做官方性、commit 与许可证核验；语义检索达到第 11.3 节的 paper top-5、chunk top-8 门槛，回答中的事实句均带来源定位。

## 3. 已审核的候选 20 篇基线

这套集合用于建立历史、架构、数据、加速、控制和评测坐标，不表示当前模型排行榜。

| # | 技术轴 | 论文 | arXiv | 官方资源初态 |
|---:|---|---|---|---|
| 1 | 视频扩散基础 | Video Diffusion Models | `2204.03458` | [项目页](https://video-diffusion.github.io/)，未列官方代码 |
| 2 | 迁移式 T2V | Make-A-Video | `2209.14792` | [项目页](https://makeavideo.studio/)，未列官方代码 |
| 3 | 开源 T2V | ModelScope Text-to-Video Technical Report | `2308.06571` | [官方模型页](https://modelscope.cn/models/damo/text-to-video-synthesis/summary) |
| 4 | LVDM / I2V | Stable Video Diffusion | `2311.15127` | [官方仓库](https://github.com/Stability-AI/generative-models) |
| 5 | I2V | DynamiCrafter | `2310.12190` | [官方仓库](https://github.com/Doubiiu/DynamiCrafter) |
| 6 | 离散 tokenizer | Phenaki | `2210.02399` | [项目页](https://phenaki.video/)，未列官方代码 |
| 7 | 3D tokenizer / masked generation | MAGVIT | `2212.05199` | [官方归档仓库](https://github.com/google-research/magvit) |
| 8 | 自回归多模态 | VideoPoet | `2312.14125` | [项目页](https://sites.research.google/videopoet/)，未列官方代码 |
| 9 | Video DiT | Latte | `2401.03048` | [官方仓库](https://github.com/Vchitect/Latte) |
| 10 | Space-Time UNet | Lumiere | `2401.12945` | [项目页](https://lumiere-video.github.io/)，未列官方代码 |
| 11 | DiT / 3D VAE | CogVideoX | `2408.06072` | [官方仓库](https://github.com/THUDM/CogVideo) |
| 12 | 多模态 DiT / 3D VAE | HunyuanVideo | `2412.03603` | [官方仓库](https://github.com/Tencent-Hunyuan/HunyuanVideo) |
| 13 | Flow matching / DiT | Pyramidal Flow Matching | `2410.05954` | [官方仓库](https://github.com/jy0205/Pyramid-Flow) |
| 14 | 数据 / 字幕 | InternVid | `2307.06942` | [官方数据与代码目录](https://github.com/OpenGVLab/InternVideo/tree/main/Data/InternVid) |
| 15 | 数据 / 字幕 / 过滤 | Panda-70M | `2402.19479` | [官方仓库](https://github.com/snap-research/Panda-70M) |
| 16 | 蒸馏 / 加速 | T2V-Turbo | `2405.18750` | [官方仓库](https://github.com/Ji4chenLi/t2v-turbo) |
| 17 | 组合控制 | VideoComposer | `2306.02018` | [官方仓库](https://github.com/ali-vilab/VideoComposer) |
| 18 | 运动控制 | MotionCtrl | `2312.03641` | [官方仓库](https://github.com/TencentARC/MotionCtrl) |
| 19 | 评测 / FVD | Towards Accurate Generative Models of Video | `1812.01717` | [官方 FVD 实现](https://github.com/google-research/google-research/tree/master/frechet_video_distance) |
| 20 | 多维评测 | VBench | `2311.17982` | [官方仓库](https://github.com/Vchitect/VBench) |

基线约束：

- arXiv 摘要页统一为 `https://arxiv.org/abs/<id>`，PDF 统一从明确版本取得并记录最终字节哈希。
- 默认联网策略不抓取 `modelscope.cn` 或独立项目页。ModelScope 与表中项目页只记录为 `unverified_candidate`，不作为 claim 证据；其标题、URL 和“未列代码”等描述必须由已捕获 PDF 或已批准 GitHub 来源重新证明。
- GitHub 官方关系必须由已捕获论文中的 URL 与固定 commit 的仓库身份共同支持；未读取代码前，不声明是否包含训练、推理、数据处理、评测或 checkpoint。
- HunyuanVideo 的 taxonomy 固定为 `multimodal_dit / dual_to_single_stream / MMDiT-style`；不写成“与 SD3 MM-DiT 完全相同”。
- `video-generation-core-20.v1.yaml` 固化标题、arXiv ID、技术轴、官方资源候选和审核状态。
- `HUMAN-GATE-BASELINE-001` 保留以下二选一产品决定；其他章节只能引用此表，不得另行维护名单：

| Gate 结果 | 第 3 篇种子论文 | 五个完整代码映射仓库 |
|---|---|---|
| `keep-modelscope` | 保留 ModelScopeT2V | SVD、CogVideoX、Panda-70M、T2V-Turbo、VBench |
| `replace-with-open-sora` | 用 [Open-Sora 2412.20404](https://arxiv.org/abs/2412.20404) 替换 ModelScopeT2V | SVD、Open-Sora、Panda-70M、T2V-Turbo、VBench |

选择 Open-Sora 时必须固定官方 `v1.2.0` 对应的完整 commit SHA，不得使用当前 `main`、1.3 或 2.0 内容。该 gate 不阻塞 VPKB-000 至 VPKB-003；未关闭时禁止启动 VPKB-004/005。

Gate 不能靠聊天记录关闭。用户必须通过一次 `generic` 事务发布 create-only `video-paper-wiki.gate-decision.v1` event，并原子更新 `wiki/meta/registries/gate-heads.json`。事件固定 gate ID、唯一前驱、`actor_kind=human`、所选枚举值、精确 baseline manifest SHA-256、由该选择导出的五库 ID、审批者、UTC 时间和理由；event ID 由不含自身 ID 的 JCS 内容计算。只有 head event、manifest hash 和派生名单三者一致时状态才是 `closed`。VPKB-004 开始后该选择 held-fixed；如需改变，必须创建 superseding human event、使受影响 packet/记录回到待审并由用户批准迁移，不能静默改 manifest。

## 4. 系统架构

### 4.1 运行环境与固定依赖

- Python `3.12`，使用 `uv` 和提交到仓库的 `uv.lock`。
- Docling 固定为 `2.117.0`，`enable_remote_services=false`，仅使用本地解析和本地 OCR。
- Docling 模型包通过独立联网计划下载；记录精确文件、大小和 SHA-256，不允许测试临时下载模型。
- `claude-obsidian` 作为 Git submodule 固定到 `v2.1.1`、commit `9f8c1199047eac2c3828496279fbb7ba9540b90b`，禁止自动跟踪 `main`。
- 固定上游的 BM25 index schema 与 tokenizer contract；该版本已使用 NFKC 与 CJK 1/2/3 字符 n-gram，禁止在扩展层并行维护另一套 jieba/n-gram 索引。
- 不要求 Docker、Ollama、Neo4j 或独立向量服务。

`claude-obsidian` 负责 Vault 初始化、capture、source ledger、claim ledger、BM25、lint、锁、事务、备份和回滚。本项目只实现视频论文领域扩展，不重新实现这些基础能力。

### 4.2 代码仓库布局

```text
video-paper-wiki/
  .agents/skills/                 Codex repository Skills
  data/baselines/                 固定论文基线 manifest
  docs/                           架构、开发与操作文档
  schemas/                        领域 JSON Schema
  src/video_paper_wiki/           CLI、适配器、解析、编译和审计
  taxonomy/                       版本化 canonical taxonomy
  tests/                          unit / contract / integration / golden
  vendor/claude-obsidian/         固定 commit 的 submodule
  artifacts/verification/         工作包验收证据
  .work/<batch-id>/                被 Git 忽略的 Codex staging；可清理、非权威
  .work/cache/                     被 Git 忽略的代码/下载缓存
```

### 4.3 Vault 布局与数据所有权

```text
video-paper-vault/
  inbox/                          人工放入的待处理文件
  .raw/captured/                  上游 capture 管理的原始 PDF/代码文件
  .raw/derived/<pdf-sha256>/docling/<pipeline-fingerprint>/
                                   不可变 Docling JSON、配置和 run manifest
  wiki/papers/                    编译器管理的 Paper Pages
  wiki/code/                      编译器管理的 Code Pages
  wiki/concepts/                  固定 taxonomy 的 Concept Pages
  wiki/meta/ledgers/              上游 source / claim ledgers
  wiki/meta/records/papers/       canonical Paper records
  wiki/meta/records/repos/        canonical Repository records
  wiki/meta/reviews/              create-only assessment events
  wiki/meta/gates/                create-only human gate-decision events
  wiki/meta/operations/           create-only vpwiki operation receipts
  wiki/meta/registries/operation-head.json
                                   当前 receipt 链头
  wiki/meta/registries/gate-heads.json
                                   human gate 的当前事件头
  wiki/notes/                     人工笔记，编译器禁止覆盖
  .vault-meta/catalog.sqlite      可重建结构化投影
```

字段所有权固定如下：

| 真源 | 唯一负责的数据 |
|---|---|
| `.raw/captured/**` + source ledger | 原始来源字节、来源身份、authority 与来源关系 |
| immutable Docling artifact + run manifest | 解析器版本、配置、模型和 locator provenance |
| claim ledger | claim text、evidence、页面 location 与 supersedes；assessment 字段只是 review head 的物化投影 |
| `wiki/meta/reviews/**` | assessment event 链和 effective assessment 的唯一真源 |
| `wiki/meta/gates/**` + gate-heads | 人工产品 gate 的选择、manifest binding 和唯一当前 head |
| canonical paper/repo records | 页面专属 metadata、aliases、taxonomy、active extraction、章节/能力到 claim ID 的有序引用，以及 paper ref 的 `core` 标记 |
| taxonomy v1 | canonical concept slug、中文 label、aliases 与父子关系 |
| operation receipt chain | vpwiki 管理路径的合法 before/after hash 历史和当前链头 |
| 上游 transaction engine/runtime result | engine 提供原子执行和恢复；runtime result 可丢失、只作按 operation ID 的诊断佐证，不是业务真源 |

Markdown/frontmatter、Concept Pages、上游 chunks/BM25、扩展 SQLite、缓存和工作队列全部是投影。`catalog.sqlite` 的业务事实只来自 canonical records、ledgers、review heads、taxonomy 和 immutable manifests，禁止以 Markdown 或 chunk 文本补造 paper、claim、locator 或 assessment 事实；检索扩展表可以读取同一 index generation 中经 schema/hash 校验的上游 chunk records，但只用于把 chunk identity 精确绑定到 canonical claim/evidence identity。

投影重建的稳定性分层定义：vpwiki 管理的 Markdown/Concept 内容在相同真源下必须字节稳定；`catalog.sqlite` 以版本化 canonical row export 而不是物理 SQLite 文件字节判定稳定；固定上游 chunk/BM25 JSON 去除明确列入 allowlist 的 `created_at/updated_at` 后，其 canonical payload 必须稳定。VPKB-000 冻结 volatile-field allowlist、canonical comparator 和 projection-generation fingerprint，不得把任意时间字段排除在外；检索 join/gold 的业务规则仍按 v0.3.2 决定留给 VPKB-001。`.work/**` 可随时删除。`.vault-meta/**` 是上游/扩展 runtime，不进入 content transaction 或 OUT_OF_BAND managed-prefix audit；只允许用户显式运行原子 builder，Skill 发现 stale index 时只能报告。

### 4.4 上游适配边界

- 使用上游公开 CLI 完成 init/adopt、capture、transaction inspect/apply、lint 和 BM25。
- 论文知识发布使用上游 `operation_type=ingest`；`generic` 仅用于后续 wiki-only 维护，不注册自定义 operation type。
- 上游账本没有 patch API：适配器读取完整账本、在内存合并、以 expected SHA 写入完整新版本；最终状态由上游 validator 检查。
- 上游 capture CLI 只接受 Vault `inbox/` 或 legacy `.raw/` 中的源文件，创建 `.raw/captured/**`，返回 payload SHA-256 `source_identity` 和 `stored_path`；它不写 source ledger，也不返回 `src-*` source ID。VPKB-001 必须以 contract fixture 固定这一行为。
- 上游未公开 source-ID 生成 CLI，因此唯一获准的内部导入是固定版本的 `claude_obsidian.ledgers.stable_source_id`。适配器以受控 module path 加载固定 submodule，并使用 `stable_source_id("file", stored_path, source_identity)`；必须同时验证 submodule HEAD、tracked-clean、目标源码 SHA、`__version__ == 2.1.1`、`module.__file__` 位于 vendor root 和输出 fixture，任一不匹配即 fail closed。
- 原始 PDF 有两条明确且不可混淆的捕获路径：
  - `manual-inbox`：用户先把 no-follow regular、PDF media magic 且文件名以小写 `.pdf` 结尾的文件放入 Vault `inbox/`，由 `vpwiki capture inspect` 固定 payload、候选 `stored_path` 和 sibling snapshot，再在独立终端运行 `vpwiki-admin capture apply`；admin wrapper 复核审批哈希后调用上游 capture CLI，并消费其 `source_identity/stored_path` 返回。不满足 canonical `.pdf` 命名时要求用户先更名，不允许以 `.bin` 进入受支持的 vpwiki PDF 路径。
  - `staged-capture`（URL/外部本地文件默认）：用户先在独立终端用 `vpwiki-admin fetch` 把经批准的字节拉到本地，或直接提供本地文件。`vpwiki ingest prepare` 只对已有本地 blob 做 media magic、大小和 SHA 校验，放入 `.work/<batch>/` 并生成无目标路径的 capture request；`prepare` 零 egress。随后 agent-safe `vpwiki capture inspect --prepared <path>` 枚举 sibling，并物化最终公开 `operation_type=capture` bundle、`capture-inspection.v1` 与 approval hash：无 sibling 时 bundle 使用 bundle-relative `content_file` 且唯一 create 目标为 `<sha256>.pdf`；唯一 byte-matching legacy sibling 时生成 no-write reuse 计划。`vpwiki ingest inspect` 只检查捕获完成后的最终知识发布 bundle，不能替代 capture inspect。用户最后通过 `vpwiki-admin capture apply` 执行与审批完全一致的 changed bundle，或对已存在路径返回 `already_captured`。
- 固定上游 v2.1.1 已支持从 Vault 外的 bundle-relative regular `content_file` 读取并以声明 SHA create raw target。VPKB-001 必须用固定源码行为的 contract fixture 重新证明；fixture、版本或源码 digest 不匹配时返回 `UPSTREAM_CONTRACT_MISMATCH`、保证 Vault 零写并阻塞本包，禁止把 apply 失败静默降级为另一条路径。`manual-inbox` 只作为用户显式选择或恢复路径，不能替代 staged fixture 通过。
- 两条 vpwiki PDF 路径共享同一 digest-sibling 规则：以 no-follow 方式枚举并验证 `.raw/captured/<sha256>.*`；不存在 sibling 时唯一目标都是 `<sha256>.pdf`，恰有一个 byte-matching legacy sibling 时复用其真实 `stored_path`，存在不匹配、多个 sibling、symlink 或特殊文件时 fail closed。`capture-inspection.v1` 把 route、payload hash、选定 `stored_path`、完整 sibling path/hash/mode snapshot 和上游 plan hash 纳入 approval material；apply 前任一变化都要求重新 inspect。无 sibling时 manual/staged 并发指向同一个 create-only `.pdf`，由上游 writer lock 使至多一个 changed transaction 成功，失败方重新 inspect 后只能复用同一路径，不得另建不同后缀。该物理唯一性承诺只覆盖 `vpwiki/vpwiki-admin` 管理的 PDF capture；绕过入口产生的额外 sibling 必须由 ingest prospective validation/audit 阻止进入 `verified`。
- staged capture 不伪造 capture CLI result：其 `source_identity` 就是已验证 payload SHA，`stored_path` 是已验证 sibling 或 deterministic target。捕获成功后 ingest 对 raw path 加 `read_precondition`，再计算 `stable_source_id("file", stored_path, source_identity)`。Docling 从捕获后的文件只读解析；最终 ingest 事务发布 derived artifact、records、页面和账本。
- GitHub code evidence 不复用 PDF media route。`vpwiki-admin fetch` 只把审批计划内、固定 repo/full commit/path 的字节写入 agent 可读 staging；`vpwiki code-map prepare` 零 egress，只接受 bounded no-follow regular UTF-8 text，生成 `code-evidence-manifest.v1` proposal，二进制或不能稳定按行解析的文件不进入 MVP locator。`vpwiki capture inspect` 完成 manifest 的 stored-path/source-ID/operation 绑定并物化 capture bundle：无 sibling 时目标固定为 `<sha256>.bin`，唯一 byte-matching sibling 时复用，错误/多个/symlink/special sibling 时 fail closed；同摘要并发、approval snapshot 和 `stable_source_id` 规则与 PDF 相同。Manifest 固定 logical origin（repo、commit、path）、payload/stored-path/source identity、media/encoding/newline canonicalization 和 capture operation；一份 raw bytes 可由多个 logical origin 引用，但 locator 仍分别保留 repo/commit/path。VPKB-000 冻结该 manifest/line canonicalization 的引擎边界，VPKB-001 fixture 通过前不得实现生产 code-map。
- capture 成功但 ingest 未发生时只形成未编目的 raw artifact，不构成部分知识发布；audit 报告它，重试保持幂等。
- Assessment event 与 claim ledger 当前投影使用一次上游 `generic` 事务原子更新；该事务只能写 `wiki/**`，不能修改 `.raw`。`vpwiki` 必须先验证完整 prospective records/ledgers/review/receipt 状态，再委托上游 inspect/apply；不能假设上游理解扩展 schema。
- 每个 vpwiki knowledge-publication `ingest/generic` 事务同时 create `wiki/meta/operations/<12-digit-sequence>-<operation-id>.json` 并更新 `wiki/meta/registries/operation-head.json`。Receipt 只记录 apply 前可知且无自指的数据：前一 receipt path/hash、严格递增 sequence、上游 operation ID、业务 `writes` 的 before/after hash+mode，以及 `claimed_inputs` 的 path/hash+mode。`intent_sha256` 对 `{sequence, previous, operation_id, writes, claimed_inputs}` 的 JCS 计算，明确排除 receipt/head 自身；真实 bundle/approval hash 只留在 `.work` 和可丢失的 runtime result，不能写入 receipt 形成 hash 循环。
- Genesis 规则固定：VPKB-001 的上游 setup 完成后，第一条 `generic` receipt 以 `sequence=1`、`previous=null` 发布，head 使用 `mode=create`、expected hash=`null`，并通过 `claimed_inputs` 接管 pristine setup 创建的 ledger；后续 head 才使用 `replace` 与 expected hash。无 head/receipt 时，audit 只有在完全无 vpwiki managed state 才视为空；若仅有精确的 pristine setup allowlist，则返回可恢复的 `RECEIPT_BOOTSTRAP_REQUIRED`，其他 managed artifact 一律拒绝。两个并发 genesis 因同一 create/lock 只能一个成功。
- Ingest 的 `claimed_inputs` 把已捕获且经 raw `read_precondition` 验证的 source 纳入链状态；此前它只是允许存在的 orphan。一旦被任一 receipt claim，在 corpus-v1 范围内就持续属于 audit managed set，不因当前 ledger 不再引用而退出；首版不支持 source retirement。业务 writes、claimed inputs、receipt 和 head 都在同一 prospective validator 中检查。
- 若 runtime completed result 尚存，audit 按 operation ID 比较 `changed_paths` 与“business writes + receipt/head + 按 operation type 固定且经 fixture 锁定的 engine-expanded paths”集合；不能把它直接等同于排除 receipt/head 的 writes。Runtime result 缺失不改变 receipt 真源。
- Managed scope 固定为 receipt 链 ever-claimed 的 `.raw/captured/**`、全部 `.raw/derived/**`、`wiki/papers/**`、`wiki/code/**`、`wiki/concepts/**`、`wiki/meta/{ledgers,records,reviews,gates}/**` 与 `wiki/meta/registries/gate-heads.json`。Audit 从 genesis 重放唯一链头、验证所有 operation 文件恰好属于该链且无额外 receipt，再枚举这些前缀，检测新增、删除、回退到旧合法 hash 或任意漂移；`operation-head.json` 作为链自身的 head 单独验证，`inbox/**`、尚未 claim 的 raw、`wiki/notes/**`、`.vault-meta/**` 和 Obsidian 配置按各自规则单列而不冒充 managed content。
- Apply 固定最后写 operation head。Audit 发现上游 writer lock 时返回 `AUDIT_RACE`；否则读取 head/receipt、完成枚举后再次读取 writer lock 与 head，任一变化也返回 `AUDIT_RACE` 并要求重试，不能误报 `OUT_OF_BAND_WRITE`。
- 上游 create-only 语义只防止合法事务覆盖已有 raw，并不防用户删除、磁盘损坏或整座 Vault 连同 receipt 链一起回滚。系统承诺是“逻辑不可覆盖 + 缺失/漂移可检测”；corpus-v1 发布前还必须由用户建立包含 `.raw` 的外部备份或上游 `--include-raw` checkpoint，保存外部锚 hash，并通过一次只读验证加隔离目录 restore drill。若选择上游 checkpoint，必须逐个覆盖所有产生 raw 的 capture/ingest operation，并核对 claimed-raw 全集；单个最终 checkpoint 不自动备份早期 operation 的 raw。没有这项证据不得宣称长期物理耐久。
- 所有非写 evidence 输入使用 `read_preconditions`；完整 ledger、record、page、review、receipt/head 目标使用 expected hashes。遵守上游上限：单文件 64 MiB、每事务新内容 128 MiB、备份 128 MiB、最多 1024 writes。

## 5. 领域契约

### 5.1 Canonical ID

Paper ID 一经建立不可改变，优先级为：

```text
arxiv:<versionless-id>
  -> doi:<normalized-lowercase-doi>
  -> openalex:<W...>
  -> sha256:<pdf-sha256>
```

后来发现 DOI 或 OpenAlex ID 时只增加 alias，不重命名页面或 ID。相同 canonical ID 对应不同 PDF SHA 时返回 `IDENTITY_CONFLICT`，禁止自动覆盖或 supersede。

### 5.2 新增 schema

所有 schema 必须版本化并设置 `additionalProperties: false`：

- `video-paper-wiki.ingest-plan.v1`：输入、hash、页数/字节限制、精确联网目标、parser 配置、审批哈希。
- `video-paper-wiki.capture-inspection.v1`：capture route、payload hash、选定 stored path、完整 sibling snapshot、上游 plan hash、would-change 与审批哈希；只作为 `.work` 中的 inspect/apply 绑定，不是业务真源。
- `video-paper-wiki.code-evidence-manifest.v1`：固定 repo/full commit/path 的 logical origin、payload/stored-path/source identity、media/encoding/newline canonicalization、capture operation 与审批绑定。
- `video-paper-wiki.prepared.v1`：PDF hash、媒体类型、页数、Docling/core 版本、配置/model-manifest hash、pipeline fingerprint、产物和元数据候选。
- `video-paper-wiki.paper-analysis-draft.v1`：固定中文章节、逐条 claim、taxonomy 与 PDF locator。
- `video-paper-wiki.paper-code-alignment.v1`：官方性证据、repo/commit、能力矩阵、代码 locator。
- `video-paper-wiki.paper-record.v1`：论文 metadata、source refs、active extraction、taxonomy 与有序 section→claim refs；每个 ref 显式包含 `core: boolean` 和 `lifecycle=active|retired`。
- `video-paper-wiki.repo-record.v1`：paper refs、canonical repo/commit、officiality/license 与有序 capability→claim refs；每个 ref 同样保留 `active|retired` lifecycle。
- `video-paper-wiki.assessment-event.v1`：system/human assessment transition、父事件和绑定的 claim/evidence fingerprint。
- `video-paper-wiki.gate-decision.v1`：human-only 产品 gate 单链、所选枚举、baseline manifest hash 与派生值。
- `video-paper-wiki.operation-receipt.v1`：前驱/sequence、operation/intent 身份、业务 writes 的 before/after hash，以及只读既有文件的 `claimed_inputs` snapshot。
- `video-paper-wiki.retrieval-config.v1`：BM25 candidate depth、chunk/paper tie-break、per-paper cap、projection generation、query/gold lifecycle-assessment eligibility 和 runtime canonical comparator 版本；与精确 join 一起在 VPKB-001 冻结，不列入 VPKB-000 共享契约。
- `video-paper-wiki.retrieval-gold.v1`：版本化 query variants、must/supporting paper IDs、graded relevance 与 evidence units。Schema/evaluator boundary 在 VPKB-001 冻结，VPKB-005 只填充并版本化 corpus gold，**不列入 VPKB-000 共享契约**。
- `video-paper-wiki.run-manifest.v1`：工具版本、输入输出 hash、开始/结束时间和确定性错误码。

不复制上游 source/claim ledger，也不建立另一套可变数据库。Canonical records 只保存页面专属 metadata 和有序 ID 引用，不复制 claim text、evidence 或 assessment。Audit 由 owner record 可推导的 `stable_subject_id` 与 claim ledger 的 canonical text 重构完整 identity material。

每个持久化 claim 恰有一个 primary owner，由一个 paper/repo record 的 active 或 retired section/capability claim ref 唯一给出；无 owner 或多 owner均 fail closed。新文本 supersede 旧 claim 时，把旧 ref 原位改为 `retired`、新增 active ref，禁止删除旧 owner。`stable_subject_id` grammar 固定为：

```text
paper:<canonical-paper-id>
repo:github:<casefold-owner>/<casefold-repo>
concept:<taxonomy-version>:<canonical-slug>
```

Commit 永远属于 evidence，不属于 repo subject。MVP 不持久化多论文综合 claim 或 concept-owned claim；Concept Page 只反向聚合 paper/repo claims，跨论文比较仅在 query-time 标为 `inference`。

### 5.3 证据 locator

PDF locator：

```text
source_id
+ page=<1-based-page>
+ ref=<Docling-self_ref>
+ optional bbox/charspan
+ artifact_path=<vault-relative-immutable-path>
+ artifact_sha256=<Docling-JSON-hash>
+ text_sha256=<normalized-excerpt-hash>
```

代码 locator：

```text
source_id
+ repository=<owner/repo>
+ commit=<full-immutable-sha>
+ path=<portable-path>
+ lines=<start-end>
+ optional symbol
+ snippet_sha256=<normalized-snippet-hash>
```

`inspect` 必须离线证明 locator 指向已捕获的现存 artifact、页码/ref 或 commit/path/line 一致、规范化内容 hash 相同；验证代码 locator 时以 `.raw/captured/**` 文件为准，不回访 GitHub。

Docling JSON 是 PDF 的派生解析证据，不算第二个独立来源。代码文件和论文可以是独立来源，但必须分别进入 source ledger。

解析升级采用 append-only 策略：

- `pipeline-fingerprint` 覆盖 Docling、docling-core、vpwiki canonicalizer/schema 版本、解析配置和模型清单 SHA-256。
- 确定性 `document.json`、解析配置和模型清单写入 `.../docling/<pipeline-fingerprint>/`；含时间戳的运行记录单独 create 于 `.../runs/<run-id>.json`。
- 同一 fingerprint 重跑若得到不同 canonical `document.json` hash，返回 `NONDETERMINISTIC_EXTRACTION`，差异只留在 `.work` 并拒绝发布；升级或配置变化只创建新的 sibling artifact，合法事务绝不覆盖被 locator/review 引用的旧 artifact，缺失由 audit 报告。
- 新解析生成独立的 locator-migration proposal，不自动修改 claim。
- 任何 claim evidence fingerprint 变化都追加 system `<current> -> provisional` invalidation，包括 `provisional -> provisional`；只新增 active extraction 且 claim evidence 未变时不追加 event，也不改变状态。
- MVP 不做历史解析垃圾回收或批量自动迁移。

### 5.4 Claim 状态

- Codex 生成的 claim 一律从 `provisional` 开始。
- 只有用户明确提交 human assessment event 后才能成为 `accepted`。
- 无支持证据使用 `unsupported`。
- 支持和反对证据并存时使用 `contested`，不得静默选边。
- 失效结论使用 `deprecated` 并保留 supersedes 链。
- 高风险结论继续遵守上游的独立来源要求。

Claim ID 与来源和解析器位置解耦，使用以下 UTF-8 输入的 SHA-256 前 20 位并添加上游要求的 `clm-` 前缀：

```text
claim_id = "clm-" + SHA256(
  "video-paper-wiki.claim.v1\0"
  + stable_subject_id
  + "\0"
  + collapse_whitespace(NFKC(canonical claim text))
).hexdigest()[:20]
```

source ID、page、Docling ref、artifact/text hash 和代码行号全部属于 evidence，不参与 claim 身份。`canonical claim text` 就是最终持久化的可证伪 claim 文本，只执行 UTF-8、NFKC 与连续空白折叠；大小写、标点和措辞均保留，不做翻译或语义改写。只做 exact canonical dedup，不做语义合并；audit 使用 owner record subject + claim ledger text 重算 identity。80-bit 截断 ID 已存在但 identity material 不同则返回 `CLAIM_ID_COLLISION`，绝不合并。证据变化保持 claim ID；事实文本或 subject 改变时创建新 claim，通过 `supersedes` 连接旧记录，旧 claim 仍由 retired ref 持有。

Assessment event 保存为 `wiki/meta/reviews/<claim_id>/<event_id>.json`，每个文件 create-only。记录至少包含 `claim_id`、`previous_event_id`、`actor_kind=system|human`、`transition_kind=genesis|human_assessment|evidence_invalidation`、`from_assessment`、`to_assessment`、`claim_text_sha256`、`evidence_fingerprint`、`decided_by`、`decided_at` 和 `reason`；event ID 为 `ase-` 加不含自身 ID 的 RFC 8785 JCS canonical JSON SHA-256 前 20 位。`evidence_fingerprint` 对 evidence identity fields（关系、source ID、canonical locator 与内容 hash）排序后做 JCS SHA-256，展示顺序变化不能触发 invalidation；精确字段集和 fixture 在 VPKB-000 冻结。

Review 状态规则：

1. Ingest 新 claim 时在同一事务创建 system genesis `null -> provisional` event；因此持久化 claim 不允许无链头。
2. 新 event 的 `previous_event_id` 必须等于唯一当前 head，`from_assessment` 必须等于前一事件的 `to_assessment`，claim/evidence fingerprints 必须匹配 prospective claim ledger。
3. 允许的 transition matrix 只有：system `genesis: null -> provisional`；system `evidence_invalidation: <任一当前状态> -> provisional`；human `human_assessment: <任一当前状态> -> accepted|contested|unsupported|deprecated`。除 evidence invalidation 的 `provisional -> provisional` 外，禁止 no-op；任何转入 accepted 都必须是 human。
4. Evidence fingerprint 变化时必须在同一、经用户批准的 generic migration transaction 中追加 system invalidation 并更新 ledger；禁止在同一事务紧接 human assessment，之后必须由独立人工操作重新定案。Evidence 未变化时禁止伪造 invalidation。
5. Fork、cycle、dangling/cross-claim parent、ID/content mismatch 或 ledger assessment/reviewed_at 与 head 不一致一律 fail closed。
6. `wiki/meta/reviews/**` 是 assessment 的唯一真源；claim ledger 的 assessment/reviewed_at 是供上游验证和查询使用的当前投影。`assessment = head.to_assessment`；head 为 human 时 `reviewed_at` 取该 event 的 UTC 日期，head 为 system genesis/invalidation 时为 `null`。不能由 wall clock 重算。
7. Replacement claim 始终先以 system genesis 从 `provisional` 开始。当 `core=true` claim 被 supersede 时，replacement 的第一次 non-provisional human review 必须在同一次 `review apply` 中使所有被其直接替代的 retired core claim 的有效 assessment 成为 human `deprecated`；旧 claim 已经 deprecated 时不得追加 no-op event。否则 prospective validator 拒绝该 review；此规则不把 retired ref 重新变为 active，也不允许绕过 replacement 自身的人工定案。

## 6. 页面与 taxonomy

### 6.1 Paper Page

路径固定为 `wiki/papers/arxiv-<id>.md`，回退 ID 同样转换为 portable ASCII 文件名。

英文 frontmatter keys：

```text
type, paper_id, title, title_zh, authors, published_at,
arxiv_id, doi, aliases, source_ids, claim_ids, topics,
code_urls, active_extraction_path, active_extraction_sha256,
created_at, updated_at
```

`active_extraction_*` 只指向当前推荐阅读/编译使用的 Docling artifact；历史解析由各 claim locator 和 immutable run manifest 保存。摄取状态不得写入 frontmatter，统一从不可变产物、canonical receipt/assessment 链和可用的上游 runtime result 推导。

上述 frontmatter 全部从 canonical paper record、source ledger 和 claim ledger生成，排序、去重、只读。页面正文不保存不可重建的自由叙事：各固定章节按 paper record 的 active refs 渲染 ledger 中的 claim text、assessment 和 locator；retired refs 仍在“证据状态/历史”中渲染原 anchor，保证 owner 与 locator 可解析。“一句话结论”只引用 1–3 个 active core claim。`created_at/updated_at` 来自 canonical record，内容未变化的 rebuild 不更新时间。

中文正文至少包含：

```text
## 一句话结论
## 研究问题
## 方法
## 表示与架构
## 训练与数据
## 实验与结果
## 局限
## 代码与资源
## 证据状态
## 关联
```

每个重要事实以 Obsidian block ID `^clm-...` 结束，且必须与 claim ledger 双向一致。

### 6.2 Code Page

Code Page 只在官方性证据成立且 commit 已固定后生成，记录：

- 论文与仓库的官方关联证据。
- commit、license、仓库归档状态。
- `training`、`inference`、`data`、`evaluation`、`checkpoints` 能力矩阵。
- 每个能力判断的文件、符号、行号和片段哈希。
- 未核验、缺失、冲突和第三方实现状态。

每项能力状态只能是 `present`、`absent`、`partial`、`unverified`。`absent` 必须记录被检查的 commit/tree 范围和检索模式；checkpoint 必须区分“README 中存在链接”和“artifact 已经取得并验证”。任何活跃仓库都固定到论文时代的 full commit SHA，禁止把后续 CogVideoX、T2V-Turbo v2、VBench 2.0、Panda 管线或其他新版内容归因于原论文。

能力矩阵只显示 active refs；被新 claim supersede 的 retired refs 仍在 Code Page 的“证据历史”区渲染原 block anchor，保证旧 claim 的 owner、review chain 和 locator 可审计。

不得执行下载仓库中的脚本或安装其依赖。代码检查只读取获准的 tree 和源文件，并将实际用于 locator 的文件捕获到 `.raw/captured/**`；离线 audit 不依赖 GitHub 可用性。

五个完整代码映射仓库严格由第 3 节 `HUMAN-GATE-BASELINE-001` 表决定。其余 GitHub 候选只核验 officiality、固定 commit 和 license，所有未逐文件验证的能力标为 `unverified`。

### 6.3 Taxonomy v1

英文 canonical slug 配中文 label 和 aliases。顶层轴固定为：

```text
task/conditioning
formulation/objective
representation/tokenizer
backbone
spatial-temporal-modeling
data/captioning/filtering
training/parallelism/optimization
inference/distillation/acceleration
control
evaluation/dataset/benchmark
```

未知术语进入 review queue，不得静默创建新的 canonical term。

## 7. CLI 与状态机

### 7.1 Agent-safe 与 operator-only CLI

Codex/Skill 可调用的 `vpwiki` 根命令不注册任何 Vault mutation、index build、fetch 或其它网络出口子命令。agent 环境只安装这一入口：

```text
vpwiki doctor
vpwiki init plan|inspect
vpwiki seed validate|status
vpwiki ingest plan|prepare|inspect
vpwiki capture inspect
vpwiki draft export|validate
vpwiki review export|inspect
vpwiki code-map plan|prepare|inspect
vpwiki index status
vpwiki query --json
vpwiki audit
```

只有用户在独立交互终端中运行的 `vpwiki-admin` 才包含 mutation 与 egress。该二进制不得安装进 Codex/agent 的 venv，也不得出现在 agent PATH 或 workspace 可执行目录；批准文件与凭据同样放在 agent 不可见区：

```text
vpwiki-admin fetch
vpwiki-admin init apply
vpwiki-admin capture apply
vpwiki-admin ingest apply
vpwiki-admin review apply
vpwiki-admin code-map apply
vpwiki-admin index build
vpwiki-admin parser-model resolve|fetch
```

统一行为：

- stdout 只输出 JSON；诊断输出 stderr。退出码：`0` 成功，`2` 可预期拒绝，`75` 上游锁或内容冲突，`1` 非预期错误。
- `plan` 只读且不联网，只生成计划与审批哈希，不自己执行下载。
- `prepare` 零 egress：只校验并暂存 agent 已能读到的本地 blob（来自先前 `vpwiki-admin fetch` 或用户放入的 inbox 文件），写入被忽略的 `.work/<batch-id>/`，不能直接发布 Vault。它消费已有 `approval_ref` 与本地字节，不自算审批 SHA，不回落网络。本地无对应 blob 时必须以明确失败码退出且零网络调用；本地已有对应 blob 时应当成功。
- `vpwiki-admin fetch` 是 paper-source / code-evidence 的唯一下载入口，只把经批准的字节写入 staging，不能直接发布 Vault。
- 所有权威 `.raw/**` 与 `wiki/**` 内容写入都必须绑定 `inspect -> approval hash -> apply`；`manual-inbox` 也先由 `vpwiki capture inspect` 固定输入 hash，再由 admin wrapper 复核后调用上游 capture。
- 所有有副作用或网络出口的 admin 命令——`fetch`、`... apply`、`index build`、`parser-model resolve|fetch`——都必须检测交互 TTY 并要求显式确认，不提供 `--yes`、环境变量跳过或 Skill 可调用的别名。Apply 展示 operation、全部目标路径、before/after hash 与审批 hash，并只接受与 inspect 完全一致的 bundle；fetch 展示 exact host/URL/预算；index build 展示替换目标；parser-model 展示 exact origin/hosts/files/预算。TTY 检测是 VPKB-001 的验收项，不阻塞 VPKB-000；VPKB-000 必须先把 admin 入口从 agent 环境拿掉。自动测试直接调用隔离 fixture 中的内部 function，不放宽生产入口。
- TTY 检测与显式确认只是降低 operator 误操作的 UX 层，不是对抗本机 Agent 或 PTY 包装的安全边界；强制边界是 admin 二进制/批准材料不在 agent 环境、Vault 位于 Codex workspace 可写根之外，以及 receipt/managed-prefix audit 对越权写的检测。
- `.vault-meta/**` index 由 `vpwiki-admin index build` 从真源在临时 sibling 中构建、fsync 后原子替换；它不是 content transaction，也不进入 operation receipt。Skill 只能报告 `stale_index` 及用户命令。
- Codex Skill 只能输出供用户复制到独立终端的精确 admin 命令与 approval hash；本机 owner 主动授予额外文件权限、执行 admin 命令或回滚整座 Vault 不属于本边界可阻止的威胁。
- 重复输入且真源无内容变化时返回 `already_ingested`，不生成新事务或更新时间戳。

### 7.2 分离的生命周期

论文 ingest 生命周期与 claim assessment 生命周期不得混成一个线性状态：

```text
ingest:
  absent -> planned -> prepared -> capture_inspected -> captured
         -> parsed -> drafted -> ingest_inspected
         -> applied_provisional -> verified

claim assessment:
  <current head> -> review_prepared -> review_inspected
                 -> assessment_event_applied -> verified

derived index:
  stale -> user_built -> verified
```

`manual-inbox` 与 `staged-capture` 在 `capture_inspected` 之前走不同准备分支，之后汇合；provisional ingest 不等待人工 review。状态从 immutable artifact、canonical record、assessment/receipt 链及可用的上游 runtime result 推导，不维护可变 job database，也不写入 Paper Page frontmatter。任一步失败停留在最近可证明状态；apply 后 audit 失败保持对应 `*_applied`，修复必须创建新 operation/event，禁止改写历史。

## 8. 联网、安全与隐私边界

### 8.1 联网审批

联网计划分成互不混用的三类：

- `paper-source`：只允许 `arxiv.org` / arXiv 下载端点和 `api.openalex.org`。
- `code-evidence`：只允许 `api.github.com`、`github.com`、`raw.githubusercontent.com`、`codeload.github.com`。
- `parser-model`：operator-only Docling 模型 bootstrap，固定 Hugging Face repo ID、full commit、精确文件路径、预期大小和 SHA-256；其权限绝不继承给 paper/code ingest。

`modelscope.cn`、`video-diffusion.github.io`、`makeavideo.studio`、`phenaki.video`、`sites.research.google`、`lumiere-video.github.io` 等独立项目页不在 MVP 默认白名单内：只保存 URL 为 `unverified_candidate`，不抓取、不引用为 claim 证据。新增域名必须经过未来独立产品/安全 gate，不能由一次普通论文摄取临时扩权。

每个 paper/code 计划绑定精确 URL、exact host、HTTP 方法、允许的重定向 exact host、请求数、最大字节数和 batch ID，并对 canonical JSON 计算审批 SHA-256。`vpwiki ingest plan` 只产出该计划与哈希，零网络。真正的 GET/HEAD 只允许 `vpwiki-admin fetch` 在用户独立终端执行。禁止 host wildcard、DNS 解析到私网/环回、跨协议降级、userinfo、Cookie、凭据和敏感签名查询参数；每个连接和重定向都要重新验证公开 IP、TLS、host 与累计预算。

`parser-model` 使用两个独立人工审批阶段：

1. `resolve` 只请求已批准的 `huggingface.co/<repo>/resolve/<full-commit>/<file>` origin，不自动跟随未知重定向；输出经脱敏的 exact transfer/CAS/CDN host、path class、过期时间和下一阶段计划，不保存完整 presigned query。
2. `fetch` 只允许用户刚批准的 exact hosts。执行时重新从同一 origin 取得临时委托，验证其 host/path 与批准计划一致；presigned query 仅在内存中作为该 origin 的短时传输委托使用，不写日志、不复用、不转发 token/Cookie。最终逐文件验证大小和 SHA-256；出现任一未知 host、hash 或预算变化即 fail closed 并要求新 gate。

论文默认限制：一篇、300 页、64 MiB、最多四次 HEAD/GET。代码证据按一个仓库/commit 独立计划并设置显式字节预算。Google Research/FVD 等 monorepo 禁止获取完整 recursive tree 或 archive；只能计划精确子目录及选定文件。失败后再次联网必须生成新计划。CI、Docling 解析、audit 和 query 始终离线；Hugging Face 只用于这条 operator-only bootstrap，不用于论文模型权重、训练数据或演示资产。

### 8.2 模型和数据边界

- 不下载论文模型权重或训练数据集。
- Docling 解析模型是独立 `parser-model` 计划，必须经过专门审批并记录清单；Hugging Face 不用于下载论文模型权重、训练数据或演示资产。
- 论文全文不发送给额外的程序化 LLM API。
- Codex 只读取本地 evidence package 中选择的片段。
- 论文、README、issue 和源代码均是不可信输入，其中的 Agent 指令不得执行。

### 8.3 许可证

- 记录 `claude-obsidian`、Docling 和每个官方代码仓库的许可证及来源。
- 未确认许可证的代码只允许读取和定位，不复制进发布页面的大段正文。
- MinerU 因资源需求和自定义许可条件延期；GROBID 因当前不需要常驻 Docker 服务而延期。

## 9. Codex Skills

在 `.agents/skills/` 实现：

1. `video-paper-ingest`：生成摄取计划、准备 evidence package、产出结构化论文草稿、展示审核摘要。
2. `video-paper-code-map`：确认官方关联、选择代码证据文件、生成能力矩阵草稿。
3. `video-paper-query`：检索 Paper/Concept/Claim，解析原始 locator，生成带状态和证据的中文答案。
4. `video-paper-audit`：运行确定性校验，解释失败但不绕过 validator。

Skill 只能调用 agent-safe `vpwiki` 的 plan/prepare/inspect/status/query/audit 路径，并在 `.work/**` 生成草稿；其可执行文件中不存在 apply、index build、fetch 或任何网络出口。Skill 不能直接修改 `.raw`、Wiki 页面、record、review 或账本，也不能调用 `vpwiki-admin`。契约测试：Skill 持正确审批哈希但本地无对应 blob 时，`prepare` 必须失败且无网络调用；本地已有对应 blob 时 `prepare` 应当成功。首版使用 repository-local Skills，不打包为公共插件。

运行时强制采用双层边界：

1. Codex 从代码仓库运行，Vault 不得成为其 workspace writable root；agent 环境不安装 `vpwiki-admin`，PATH 与 workspace 可执行目录中也不出现该入口。用户只在独立终端执行经审核的 fetch、apply、index build 或 parser-model 网络操作。
2. Audit 重放 canonical operation receipt 链，并在上游 runtime result 尚存时按 operation ID 交叉核验，再枚举 managed prefixes 与 receipt 当前快照。任何未被链头解释的新增、删除、hash/mode 漂移或回退到旧合法 hash 报 `OUT_OF_BAND_WRITE`；未编目的 raw 单列为 orphan，`.vault-meta/**`、`wiki/notes/**` 与用户 Obsidian 配置明确豁免。

## 10. 实施工作包

`READY_FOR_VPKB-000` 的含义是可以开始冻结共享引擎契约，不是所有子模块都已获得可并行生产实现的 API。当前可立即开展仓库/agent-safe CLI 空骨架、schema 与性质测试草案、固定上游源码 fixture；任何持久化或消费业务状态的生产实现必须等待 VPKB-000 冻结对应 schema/interface，依赖上游 transaction/capture/BM25/runtime result 或精确 retrieval join 的实现还必须等待 VPKB-001。VPKB-004/005 继续受 human baseline gate 阻塞。

| 子模块 | 当前可立即开展 | 生产实现/集成最早门槛 |
|---|---|---|
| 工程、配置、双 CLI | 目录与无副作用 `vpwiki` 骨架、admin 隔离安装骨架、JSON envelope fixture | VPKB-000 内完成并冻结 |
| Schema、identity、taxonomy、transaction facade | 引擎 schema/fixture 草案与纯 validator 性质测试 | VPKB-000 冻结后供下游消费；retrieval config/gold schema 依 v0.3.2 留给 001，gold corpus 留给 005 |
| 联网计划与 parser-model 审批 | 零 egress plan/预算/host-policy 测试 | VPKB-000 冻结 envelope；真实 admin fetch/TTY 在 VPKB-001 |
| Capture、上游 transaction、ledger adapter | 固定上游源码 contract fixture | VPKB-001 `adapter-contract` 通过后 |
| Receipt、audit、admin apply、原子 index builder | 失败轨迹与状态机测试草案 | VPKB-001 `integrity-runtime`，且依赖 `adapter-contract` |
| Docling adapter | 固定 JSON fixture 与 standalone canonicalizer 测试 | standalone 可在 VPKB-000 后；权威发布依赖 VPKB-001，端到端验收在 VPKB-002 |
| Canonical compiler、Paper/Code/Concept Pages、review apply | 模板快照与纯投影测试草案 | VPKB-001 完整通过后，在 VPKB-002 纵切验收 |
| BM25、SQLite catalog、evidence join/query/evaluator | ranking 与 join 性质测试草案，不冻结 gold | builder/join/config 在 VPKB-001；完整查询与 generation 集成在 VPKB-002；corpus gold 在 VPKB-005 |
| 仓库 code-map | 四态能力/locator validator 草案 | SVD 纵切在 VPKB-002；五库生产批次依赖 human gate 并在 VPKB-004 |
| 四个 repository Skills | SKILL 结构与只读调用契约草案 | VPKB-002 引擎稳定后，在 VPKB-003 实现和验收 |
| 20 篇语料与黄金评测 | manifest/gold 需求草案 | `HUMAN-GATE-BASELINE-001` + VPKB-004；完整导入/评测在 VPKB-005 |

### VPKB-000：工程基础

- 创建独立仓库、Python 3.12/uv 环境、配置、离线 CI 和两个 CLI entry point 的空骨架：agent 环境只安装 `vpwiki`；`vpwiki-admin` 用单独包装安装，不进入 agent venv/PATH。
- 在实现命令前冻结第 5.2 节引擎最小 schema（ingest-plan、capture-inspection、code-evidence manifest、prepared、draft、records、assessment、gate、receipt、run-manifest；可含 alignment 骨架），以及 canonical JSON/JCS、canonical claim text、stable subject、taxonomy v1、CLI stdout/error JSON envelope 与 fixtures。**不冻结** `retrieval-config.v1`/`retrieval-gold.v1`。上游 BM25 index schema 本包即钉死：不加字段、不维护第二套 tokenizer。这些共享引擎契约只有本包可写。
- 冻结一套非持久化 transaction facade，统一表示 operation ID/type、规范化路径、writes、expected hashes、read preconditions、claimed inputs、approval hash 与 runtime result；CLI、receipt 和 audit 不得各自解释上游 contract。
- 冻结投影层的 `catalog.sqlite` 基础 DDL/PK/FK/排序、projection-generation/stale digest 与 runtime volatile-field comparator；candidate depth、精确 evidence join、query/gold eligibility 和 evaluator 规则留给 VPKB-001/005，不在本包提前定实现。
- 钉死零 egress 契约：`vpwiki` 命令树与实现均无 fetch/HTTP；`prepare` 只消费本地 blob。缺 blob 的失败码进入 envelope 命名空间，但 TTY 检测与真实联网验收留给 VPKB-001。
- 冻结 code-evidence 从 staging 到 `.raw/captured` 的 manifest、无 sibling 时固定 `.bin` target、digest-sibling/source-ID/concurrency 与 UTF-8 line canonicalization；在该契约及 VPKB-001 fixture 通过前，SVD code-map 只能保留测试骨架。
- 固定 Docling 和 `claude-obsidian`，建立依赖、source digest 与 license 清单。
- 建立 `docs/ai/task-index.yaml`、工作包模板和 verification 目录。

### VPKB-001：Vault 与上游事务适配

本包内部按两个有序 verification slice 交付：`adapter-contract` 先锁定 staged/manual/code-evidence capture、Vault 外 `content_file`、ingest/generic、operation-result、ledger merge 与 BM25 上游行为；`integrity-runtime` 依赖前者，再完成 prospective validation、receipt/audit、原子 index builder、精确 evidence join 与 CLI 边界。它们只是中途验收证据，不是新工作包、gate 或生命周期状态；只有整个 VPKB-001 通过后才能启动 VPKB-002。

- 初始化独立 Vault，接通 staged/manual capture、ingest/generic transaction、账本、lint、锁和恢复。
- 锁定 capture 不写 ledger/不返回 source ID、Vault 外 bundle-relative `content_file`、PDF 双路同目标并发与 legacy sibling 复用、code-evidence 无 sibling 时固定 `.bin` target/manifest/同摘要并发、`stable_source_id` 隔离导入、generic/capture/ingest、operation-result、上限与 ledger merge 的 contract fixtures。
- 实现 prospective extension validation、genesis/后续 canonical operation receipt 链、managed-prefix/race audit，以及按 operation ID 的可选 runtime-result 交叉核验；证明并发 genesis、bootstrap recovery、新增、删除、漂移和回退到旧合法 hash 的行为符合契约。
- 锁定上游 BM25 index/chunk schema、NFKC 与 CJK 1/2/3-gram tokenizer；用 `全文检索` 等中文 fixture 验证 build/query 一致性。禁止往上游 chunk/BM25 增加扩展字段；在 `catalog.sqlite` 实现 generation-bound 的 `chunk identity -> evidence_unit_ids` 精确 join，inventory 从全部 canonical claims/locators 计算且不得读取 gold，builder 不得修改上游文件。
- 实现 user-only、原子替换的 BM25/SQLite builder、精确 join、retrieval config 及 stale detection；冻结 `retrieval-gold.v1` schema/evaluator boundary，但不读取或填充 corpus gold；固定 overlap chunk、多 anchor、多 locator、lifecycle/assessment eligibility、candidate depth 与 tie-break。验证 Skill 可执行入口没有 apply/build/fetch，全部 admin side-effect/egress 命令必须 TTY 且不支持 `--yes`。

### VPKB-002：三篇论文 + 一仓库的引擎纵切

- 选择不受 baseline gate 影响的 Video Diffusion Models、Stable Video Diffusion、VBench，以及 SVD 官方仓库；先摄取关联论文，再映射仓库。
- 跑通本地 PDF 与一个明确 HTTPS URL 的 plan、prepare、capture、Docling、draft、provisional ingest、human assessment、receipt、index、query 和 audit。
- 实现 canonical records→Paper/Code/Concept Pages/BM25/SQLite 的确定性编译、解析器无关 claim identity、system genesis、evidence invalidation 和不可变多版本 Docling artifact。
- 删除全部 Markdown/Concept/BM25/SQLite 投影后从真源重建，按第 4.3 节分别验证内容字节、canonical row export 与去 volatile runtime payload 稳定；用旧 locator 解析和同 fingerprint 非确定性 fixture 验证升级路径。
- 本包通过即形成 `engine-data-chain` gate，但尚未完成 Skills/视觉人工检查，也不代表 `engine-mvp` 或 20 篇语料完成。

### VPKB-003：Codex Skills 与引擎 MVP gate

- 实现四个 repository Skills。
- 让中文模板、Skills 和 evidence package 消费并复验 VPKB-002 已实现的 Concept compiler/output 与 VPKB-000 已冻结的 taxonomy/schema；本包不得重新实现另一套 Concept compiler，也不得重新定义或“补完” schema。
- 验证 fresh-context Codex 无 Vault 写权限、Skill 无 apply/build/fetch 命令，伪造非事务修改能被 audit 捕获，stale index 只能提示用户。
- 重跑 VPKB-002 三篇/一库纵切并由人工检查 Obsidian 排版；通过后标记 `engine-mvp` 完成。

### VPKB-004：官方代码映射

- 前置条件：`HUMAN-GATE-BASELINE-001` 已关闭。本包先用已验收的 ingest engine 逐篇补齐 gate 表中五库关联论文的 provisional ingest；只有关联 paper record 已存在后才能为该库建 Code Page，不得创建孤立代码记录。
- 从已捕获论文明确列出的 GitHub URL 开始，固定 paper-era full commit，取得精确 tree/文件但不执行代码。
- 严格按第 3 节 gate 表只对五库完成 license、`present/absent/partial/unverified` 能力矩阵和代码 locator。

### VPKB-005：20 篇基线与检索验收

- 按 gate 后的唯一 manifest 导入剩余论文，使总数达到 20；每篇保持 6–12 条 `lifecycle=active && core=true` claim，retired core 不占该数量区间。
- 每篇剩余论文完成后，再对其 GitHub 候选做浅层 officiality、paper-era full commit 和 license 核验；非五库能力统一保持 `unverified`。
- active 与 retired 的每条 core claim 都必须经人工结束为 `accepted`、`contested`、`unsupported` 或 `deprecated`，其中被 supersede 的 retired core 必须为 human `deprecated`；非 core claim 可保留 `provisional`，但不得进入“一句话结论”或 corpus-v1 核心统计。
- 构建 Paper、Code、Concept、Claim 投影与 Obsidian Bases，运行版本化分层黄金查询，保存 candidate recall、paper ranking、evidence recall、结构化查询完整度和失败分析。
- 建立包含 `.raw` 的外部备份/checkpoint、记录外部锚 hash，并在隔离目录完成 restore drill；然后再次执行 projection rebuild、locator audit 和离线 query。
- 所有第 11 节门槛通过并完成必需人工 gate 后，才标记 `corpus-v1` 完成。

`engine-mvp` 与 `corpus-v1` 是两个独立完成条件：前者证明机制在三篇/一库纵切可行，后者证明 20 篇质量和检索门槛达标，不得互相代替。每个工作包只能修改自己的 `allowed_paths`，记录依赖、回滚步骤和 `artifacts/verification/<packet-id>/`。真实联网、license、安全边界、备份恢复和 Obsidian 视觉结果需要人工 gate，Agent 不得自批。

Task index 必须显式编码依赖链 `VPKB-000 -> 001 -> 002 -> 003 -> 004 -> 005`；VPKB-004/005 还共同依赖已持久化关闭的 `HUMAN-GATE-BASELINE-001`。不得靠“剩余论文”或聊天上下文推断依赖。

## 11. 测试与验收

### 11.1 自动测试

- Canonical paper ID、alias、stable-subject grammar、重复摄取、identity conflict、exact claim dedup 和截断 ID collision。
- Schema、taxonomy、canonical paper/repo record、frontmatter、wikilink、primary owner 与 claim anchor 双向一致性。
- 删除 Markdown/Concept/BM25/SQLite 后从真源重建：vpwiki 管理的 Markdown/Concept 内容字节稳定，SQLite 的版本化 canonical row export 稳定，固定上游 chunk/BM25 仅在移除 VPKB-000 精确冻结的 `created_at/updated_at` allowlist 后 canonical payload 稳定；SQLite 业务表测试明确禁止读取 Markdown，allowlist 外任一字段漂移都必须失败。
- Paper/code HTTPS exact-host、请求/字节预算、重定向只存在于 `vpwiki-admin fetch`；agent-safe `plan`/`prepare` 为“零授权零网络”。契约：持正确哈希、本地无 blob 时 `prepare` 失败且无网络调用；本地已有 blob 时 `prepare` 成功。parser-model 两阶段审批、临时签名委托脱敏、未知 host/hash fail closed。
- Docling page/self-ref/bbox/charspan、artifact path/hash 与规范化文本哈希；两个 pipeline fingerprint 并存，旧 locator 继续解析，同 fingerprint 不同输出拒绝发布。
- Claim ID 在 evidence locator 或 Docling 版本变化时稳定，在 subject/text 变化时生成新 ID；evidence 替换触发 system invalidation。
- Assessment event 的 system genesis、human-only accepted、create-only 单链、唯一 head、fingerprint 与 claim ledger 物化 assessment/reviewed_at 一致性；core replacement 第一次人工定案必须在同一次 `review apply` 把其直接 supersede 的 retired core claim 定案为 human `deprecated`，已 deprecated 的旧 claim 不得追加 no-op。
- 上游 commit/源码 pin、capture 无 ledger/source ID、Vault 外 bundle-relative `content_file`、source-ID fixture、完整 ledger merge、expected SHA 和 transaction 上限；固定上游外部内容 fixture 失败必须以 `UPSTREAM_CONTRACT_MISMATCH` 零写阻塞，不能静默切换捕获路径。
- PDF capture 覆盖 manual/staged 同摘要无 sibling 时同指向 `<sha>.pdf` 的 barrier 并发、唯一 matching legacy sibling 复用、错误/多 sibling 与 symlink/special 拒绝，以及 inspect 后 sibling snapshot 漂移必须重新审批；并发结果至多一个 changed transaction，禁止产生双后缀身份。
- Code-evidence capture 覆盖无 sibling 时固定 `.bin` target、同摘要多 logical origin 复用同一 raw/source identity、manifest 逐 origin 保留 repo/commit/path、barrier 并发、legacy sibling 与 inspect 漂移；非 UTF-8、二进制、换行/行号无法稳定重放或 manifest/源码 hash 不匹配时 fail closed。
- Operation receipt genesis/后续 head、predecessor/sequence/operation ID/intent hash、writes/claimed-inputs、可选 runtime-result 交叉核验，以及 managed path 新增、删除、漂移、回退到旧合法 hash 的检测；并发 genesis、orphan raw、audit race 和 `.vault-meta` 豁免分别测试。
- 固定上游 CJK tokenizer/index schema，中文 build/query 回归；BM25/SQLite 原子 builder 的 stale、失败保留旧索引和成功替换测试。扩展 join rebuild 必须保持上游 chunk/BM25 文件 SHA 不变，canonical mapping export 稳定；canonical Page anchor 唯一、overlap chunk 合法复制、多 anchor 排序去重并集、未知/不 eligible evidence unit、`chunk_id/body_hash` 或 generation 不匹配均有 fail-closed fixture，并证明 builder/evaluator 不读取 gold 来生成映射。
- 事务幂等、stale hash、锁冲突、回滚、中断恢复和零部分发布；备份隔离恢复后 audit/locator/query 保持通过。
- `vpwiki` 命令树中不存在 Vault mutation、index build、fetch 或任何 egress；agent fixture 的 PATH/venv 解析不到 `vpwiki-admin`。任一 `vpwiki-admin` side-effect/egress 命令在无 TTY、无显式确认或 bundle/hash/host-plan 不匹配时拒绝，且不存在 `--yes` bypass。TTY 断言属于 VPKB-001。
- 官方仓库、paper-era full commit、license、四态能力、absence search scope、代码路径/行号/snippet hash 与 checkpoint link/artifact 区分。
- 完整离线链路：`plan -> admin fetch -> prepare -> draft -> inspect -> admin apply -> admin index build -> query -> audit`。无 fetch 的 fixture 链路在已有本地 blob 时从 `prepare` 起跑。
- 普通 CI 使用固定 Docling JSON；真实 `docling_local` 测试不得临时联网下载模型。

建议的发布前命令：

```text
pytest -q
pytest -q -m integration
pytest -q -m docling_local
vpwiki doctor --vault <fixture-vault>
vpwiki audit --vault <fixture-vault> --as-of <fixed-date>
python vendor/claude-obsidian/scripts/claude-obsidian.py lint \
  --vault <fixture-vault> --as-of <fixed-date>
```

### 11.2 20 篇基线验收

- 20 个 Paper Pages 全部存在，无重复 ID。
- 每篇按 `lifecycle=active && core=true` 计数有 6–12 条 claim；active 与 retired 的所有 core claim 都必须能解析到 PDF/官方代码证据或明确标为 `unsupported`，且最终 assessment 不得是 `provisional`。被 supersede 的 retired core claim 必须为 human `deprecated`；非 core claim 可以 provisional。
- 未经人工 review，不存在自动生成的 `accepted` claim。
- 所有 GitHub 官方仓库候选完成 officiality、commit 和 license 核验；第 3 节 gate 所选五个代表仓库完成逐文件能力矩阵，其余能力必须为 `unverified`。
- 所有 `^clm-*` 与 claim ledger 双向一致。
- 所有 claim 都有 system genesis，所有 accepted claim 的链头来自 human assessment event；被引用的历史 Docling artifact 当前存在且 hash 匹配，缺失会被 audit 拒绝。
- Obsidian 中 Paper、Code、Claim 三个 Base 可浏览，中文排版正常且无死链。
- 相同真源重复重建必须满足第 4.3 节的分层稳定性；vpwiki 内容投影不得因 run ID 或 wall clock 改变，只有独立 run manifest 与固定上游 runtime payload 中被精确 allowlist 的时间字段可变化。
- 包含 `.raw` 的外部 backup/checkpoint 有锚 hash 和隔离 restore drill 证据；恢复后全量 locator、receipt 与离线查询通过。

### 11.3 黄金检索与结构化查询

语义比较题限制为 2–3 篇 must-hit 论文，避免用半个语料库掩盖排序质量：

1. 比较 Video Diffusion Models、Lumiere、Latte 的空间与时间建模。
2. 比较 Phenaki、MAGVIT、VideoPoet 的离散表示与生成器类型。
3. 比较 CogVideoX、HunyuanVideo、Pyramidal Flow 的连续 latent、DiT 与 flow/diffusion 设计。
4. 比较 Make-A-Video、Video Diffusion Models、Stable Video Diffusion 对图像、无标注视频和配对数据的使用。
5. 比较 InternVid、Panda-70M、CogVideoX 的字幕、切片与过滤管线。
6. 比较 Stable Video Diffusion、DynamiCrafter、Pyramid Flow 的图像条件注入方式。
7. 比较 Video Diffusion Models、Pyramidal Flow、T2V-Turbo 的训练目标与少步采样。
8. 比较 VideoComposer、MotionCtrl 的控制信号、粒度与组合性。
9. 比较 FVD、VBench，并列出 VBench 可定位而单个 FVD 分数不能定位的至少三类失败。

每道比较题都维护两个 query variant 并分轨报告，禁止混合平均：

- `named_title`：保留论文标题，只作为路由与去重 smoke test。
- `topic_only`：移除标题/arXiv ID，使用中文技术描述、固定英文术语 alias 和人工改写，作为真正的主题语义检索 gate。

另设两类测试：

- 为 20 篇论文各建 `exact_title_or_id` 与 `alias_or_semantic` 两个单论文查找 variant，二者分别报告。
- “将全部 20 篇按代码开放状态分类”只查询 SQLite/canonical records，不计入 BM25 语义检索。

`retrieval-gold.v1` 每条固定 `gold_id`、`corpus_version`、`query_version`、`variant_kind`、中文 query、`must_paper_ids`、`supporting_paper_ids`、graded relevance（must=`2`、supporting=`1`），以及 `required_evidence_units[{evidence_unit_id,paper_id,claim_id,locator_fingerprint}]`。`locator_fingerprint` 是 evidence relation、source ID、canonical locator 与内容 hash 的 JCS SHA-256；`evidence_unit_id` 是 `paper_id/claim_id/locator_fingerprint` canonical identity 的内容哈希，因此一个 claim 的 N 个 locator 产生 N 个 unit。上游 chunk/BM25 schema 不加字段。VPKB-001 的扩展 builder 从全部 paper-owned canonical claim/locator 对计算 inventory，禁止读取 gold；它先在 primary-owner Paper Page 的 canonical Markdown 验证每个 `^<claim_id>` source anchor 恰好出现一次，再把同 generation、经 schema/hash 验证的 upstream `chunk_id/body_hash/raw_text` 与 eligible unit 写入扩展 SQLite mapping。

固定 chunk overlap 导致同一合法 source anchor 出现在多个相邻 chunk 时，这些副本都映射同一组 unit；一个 chunk 含多个合法 anchor 时取各 claim units 的按 ID 排序去重并集。同一 unit 在多个 overlap chunk 命中只计一次。Source anchor 缺失、在 canonical Page 内重复、跨 primary owner/Page 出现，或未出现在任何 validated chunk 时 fail closed。Inventory 为审计保留 active/retired 的全部 unit 及 assessment；默认 query eligibility 为 `lifecycle=active && assessment!=deprecated`，provisional/contested/unsupported 必须回传状态；gold eligibility 只含 `lifecycle=active && core=true && assessment in {accepted,contested}` 且 locator 当前可解析的 unit。Retired/deprecated 仅由显式 historical mode 返回，不进入 corpus gold 或默认答案；lifecycle/assessment/head 变化使旧 generation stale。命中只按当前 `retrieval-config.v1` 与 exact mapping，不做模糊文本匹配；gold 只能引用可重算、eligible 且已映射的 unit。Join、config 与 gold schema/evaluator boundary 在 VPKB-001 落地，VPKB-005 只填充版本化 gold corpus；VPKB-000 不冻结 `retrieval-gold.v1`。九道比较题每题 must-hit 保持 2–3 篇、每个 must paper 至少一个 required unit、每 paper 最多两个 required units、总数不超过八个；gold validator 必须先证明这些结构约束与 top-8/per-paper cap 相容。Gold 修改必须升版本并保存变更理由。

首版没有 reranker，排序算法固定且可复现：BM25 先按 `retrieval-config.v1` 冻结的 candidate depth 返回 chunks；每篇 paper 的得分取其最高 chunk score，按配置中冻结的 score normalization 与 `score desc, paper_id asc` 去重排序，paper top-10 与 top-5 只是同一列表的两个 cutoff。Evidence top-8 只取 paper top-5 内的 chunks：先为每篇返回其最高分 chunk，再按 `score desc, paper_id asc, chunk_id asc` 填满，且每篇最多两个 chunk。生产 query 与 evaluator 必须消费同一份已校验 config、mapping generation 和 tie-break 版本；算法、配置与索引构建均不得读取 gold label。

验收门槛：

| 轨道 | 返回范围 | 指标 | corpus-v1 门槛 |
|---|---:|---|---:|
| 单论文 `exact_title_or_id` | paper top-3 | Hit@3、MRR@3 | 分轨 `Hit@3 = 1.00`、`MRR@3 >= 0.90` |
| 单论文 `alias_or_semantic` | paper top-3 | Hit@3、MRR@3 | 分轨 `Hit@3 = 1.00`、`MRR@3 >= 0.90` |
| 比较题 `named_title` smoke | paper top-10/top-5 | Must Recall@10、Complete@5 | `1.00`、`>= 0.80` |
| 比较题 `topic_only` 候选 | paper top-10 | Must Recall@10 | `1.00` |
| 比较题 `topic_only` 排序 | paper top-5 | Must Recall@5、nDCG@5、Complete@5 | `>= 0.90`、`>= 0.80`、`>= 0.80` |
| `topic_only` 证据定位 | chunk top-8 | Evidence Recall@8、EvidenceComplete@8 | 二者均 `>= 0.80` |
| 全量代码状态 | 20 条结构化记录 | precision、recall | 均为 `1.00` |

所有表内聚合均为同一 variant track 内的 per-query macro，禁止 micro 汇总。Must Recall@K 的 denominator 只含 `must_paper_ids`；supporting IDs 只参与 graded nDCG，nDCG 逐题计算后再 macro。Evidence Recall@8 的 denominator 是该题全部 required evidence unit IDs；`EvidenceComplete@8` 是逐题二值指标，仅当每个 must paper 至少命中一个 exact required unit 时为 1。`Complete@5` 同样逐题二值，仅当全部 must IDs 都在 top-5 时为 1；九题 macro `>= 0.80` 等价于至少 8/9 题完整，不要求每一道都通过。每个事实句必须带可解析 locator；跨论文综合只在 query-time 生成并显式标记为 `inference`。

## 12. 已知风险与固定应对

| 风险 | 固定应对 |
|---|---|
| 上游内部 source-ID API 漂移 | 精确 commit pin、单一适配器、contract fixture、版本不匹配 fail closed |
| 权威字段散落导致页面无法重建 | canonical paper/repo records 只保存页面专属 metadata 与有序 ID refs；投影删除重建测试为 engine gate |
| Review 状态成为双重真源 | assessment event 链唯一权威，claim ledger 仅为 head 的严格物化投影；genesis/invalidation/human transition 同事务校验 |
| 中文查询召回不稳定 | 锁定上游 CJK 1/2/3-gram tokenizer/index schema，运行中文 contract 与 gold retrieval；不维护第二套 tokenizer |
| Docling 输出结构变化 | 完整 pipeline fingerprint、旧 artifact 逻辑不可覆盖且缺失可审计、locator migration proposal、替换 evidence 后重新人工审核 |
| Raw 被误删或整 Vault 回退 | receipt 检测局部缺失/漂移；corpus-v1 要求含 raw 的外部锚、隔离 restore drill；不声称本地链能自证整库回滚 |
| Hugging Face 使用 CDN/CAS/临时签名 URL | operator-only 两阶段 exact-host 审批、临时委托不落盘、公开 IP/TLS/预算复核、最终大小/hash 校验 |
| LLM 摘要幻觉 | claim 默认 provisional；locator 强校验；人工 accepted gate |
| PDF 与正式版本身份冲突 | canonical ID + aliases；不同字节返回 IDENTITY_CONFLICT |
| README 宣称与实际代码不符 | 能力只由固定 commit 的文件/行号证据支持 |
| 多 Agent 并发覆盖 | 单一上游事务、expected SHA、锁、完整 ledger merge |
| Prompt injection | 全部外部内容按不可信数据处理；Skill 无 apply 权限，Vault 位于 workspace writable root 外 |
| 非事务直接修改 Vault | canonical receipt 链 + managed-prefix 枚举；新增/删除/漂移/回退旧 hash 均报 `OUT_OF_BAND_WRITE` |
| 20 篇人工审核量较大 | 每篇保持 6–12 条 active core claim，active/retired core 均须人工定案且 superseded retired core 必须 deprecated；非 core 可 provisional，单篇事务且不放宽 core 证据标准 |

## 13. 审查处置、内部共识与 Fable 第二轮复审

下表记录 Fable 第一轮问题如何进入当前契约；Fable 已按第 13.2 节对 v0.3.1 完成绑定复审并关闭六项硬修。v0.3.2 的两项并发方案修改和 v0.3.3 的 follow-up 只收紧契约，不把尚未发生的实现验证写成已通过。

| 审查问题 | 最终契约处置 |
|---|---|
| 白名单与项目页冲突 | 已选择最小策略：非默认项目页为 `unverified_candidate`，不抓取、不作证据 |
| 中文 BM25 未说明 | 已补固定上游 CJK 1/2/3-gram contract；不引入第二套 tokenizer |
| Claim ID 与 Docling locator 耦合 | 已改为 `stable_subject_id + normalized claim text`，完全排除 evidence 字段 |
| Docling 升级策略缺失 | 已定义包含 canonicalizer/schema 的 fingerprint、create-only artifact、非确定性拒绝和显式 locator migration；物理耐久由外部 backup gate 保证 |
| Review decision 无权威位置/状态不闭合 | 已改为 `wiki/meta/reviews/<claim>/<event>.json` assessment-event 单链；system genesis/invalidation 与 human-only accepted 完整闭合 |
| 页面 metadata 没有真源 | 已新增最小 canonical paper/repo records；Markdown、SQLite、BM25 只作可删投影 |
| Skill 禁写仅靠约定 | `vpwiki` 零 mutation/egress，admin 二进制与批准材料不进 agent 环境；TTY + 确认只是 UX，强制层是 workspace 写边界与 receipt audit |
| 上游 capture 读取 `.work` 的能力未知 | 固定 v2.1.1 源码与自带测试已证明 transaction 接受 Vault 外 bundle-relative `content_file`；VPKB-001 重放 fixture，不匹配则零写阻塞且不静默 fallback |
| completed result 无法证明最新合法状态 | 已新增 create-only operation receipt predecessor 链、唯一 head、managed-prefix 枚举；runtime result 只按 operation ID 交叉核验，不作为真源 |
| parser-model 单域名策略不可执行 | 已改为 operator-only resolve/fetch 两阶段 exact-host 审批与临时签名委托规则 |
| frontmatter 状态重复 | 已删除 `ingest_status`，状态只从不可变产物、canonical receipt/assessment 链和可用 runtime result 推导 |
| 检索门槛过宽/中文题过于依赖标题 | 已固定同一 BM25 paper ranking 的 top-10/top-5 cutoff，拆出 named smoke 与 topic-only gate，并版本化 graded gold/evidence units；`retrieval-gold.v1` 不进入 VPKB-000 冻结面 |
| 全仓库能力核验过重 | 已收窄到 gate 所选五个代表仓库，固定四态能力；其余保持 `unverified` |
| agent-safe 仍可能自己下载 | 已把 paper/code/parser-model egress 全部移出 `vpwiki`；`prepare` 只消费本地 blob；`vpwiki-admin` 不进 agent 环境/PATH |
| BM25 schema 与 evidence unit 字段冲突 | 已钉死上游 chunk/BM25 schema 不加字段；unit 命中改为 VPKB-001 扩展 SQLite exact mapping，inventory 不读取 gold |

### 13.1 内部交叉复审共识

三方内部复审形成以下共识：

- MVP/数据契约：先冻结 record、identity、taxonomy、assessment 和 receipt，再做 CLI；以三篇论文 + SVD 仓库的可删投影重建作为 `engine-mvp`，不能用“能生成 Markdown”代替可恢复性。
- 事务/安全：上游 transaction 仍是原子写入执行器，但扩展必须先验证完整 prospective state，并用自己的 receipt/assessment 链补齐领域审计；`.vault-meta` 索引属于用户重建的 runtime。
- 语料/检索：九道比较题的 must-hit 均为 2–3 篇；标题题只测路由，topic-only 中文改写才测主题召回；代码核验名单只能来自一个 human gate 表。

### 13.2 Fable 第二轮关闭标准与结果

Fable 第二轮复审必须绑定外部提供的当前文件版本、行数与 SHA-256；输入不一致时停止并返回 `REVIEW_INPUT_MISMATCH`。复审不能只复述方案，必须完成：

1. 对第一轮六项硬修逐项给出 `closed`、`partial` 或 `open`，并区分 `blocker` 与 `non-blocker`。
2. 对 operation receipt、assessment-event、manual/staged capture、agent/admin CLI、retrieval gold 和 baseline gate 分别构造最小失败轨迹。
3. 只有当前文本允许两种互斥实现都通过验收、存在计划内不可检测的越权/漂移、原子性或证据真源不可验证时，才能判为 blocker；每个 blocker 都必须附最小计划修改和最小验收测试。
4. 最终结论只能是 `READY_FOR_VPKB-000` 或 `NOT_READY_FOR_VPKB-000`；后者必须至少有一个符合上述定义的 blocker。

实际复审绑定输入为 v0.3.1、739 行、SHA-256 `9eebaf85ae7831043e59843da65693d78c5880028e82a9e03850b537cb2555b8`。Fable 对六项硬修全部判定 `closed`，对六个子系统给出确定的最小失败轨迹，未发现符合上述定义的 blocker，最终结论为 `READY_FOR_VPKB-000`。

五项 non-blocker 在 v0.3.3 中按固定上游源码与本地交叉复核作如下处置：

| # | 处置 | 当前契约 |
|---:|---|---|
| 1 | 接受并服从 v0.3.2 冻结边界 | evidence unit 由 VPKB-001 扩展 SQLite exact mapping 维护，不写固定上游 schema；builder 为全部 claims 计算 inventory，禁止读取 gold；VPKB-000 仍不冻结 gold |
| 2 | 接受验证要求，拒绝静默降级 | 固定上游已证明 Vault 外 `content_file` 可用；fixture 不匹配返回 `UPSTREAM_CONTRACT_MISMATCH` 并阻塞 VPKB-001，manual-inbox 仅是显式用户路径或恢复路径 |
| 3 | 接受 | TTY/确认是 UX guard；admin 隔离安装、workspace 写边界与 receipt audit 才是强制层 |
| 4 | 接受并定义原子边界 | replacement core claim 第一次人工定案与直接 retired core predecessors 的 human `deprecated` 在同一次 `review apply` 完成 |
| 5 | 接受为内部切片 | VPKB-001 内部依次验收 `adapter-contract`、`integrity-runtime`，不新增工作包、gate 或生命周期状态 |

本地复核另关闭了四项实施歧义：manual/staged PDF capture 共享 `.pdf` 目标、审批 sibling snapshot 和并发验收；code evidence 有独立 manifest/无 sibling `.bin` 目标；投影稳定性使用内容/row export/去精确 volatile 字段三层 comparator；canonical Page anchor 唯一而 chunk overlap 副本合法，避免误拒固定上游 chunker。`ready-for-vpkb-000` 只授权启动契约冻结包；各生产子模块仍须按第 10 节依赖 gate 开工。

### 13.3 Fable 终审(第三轮 delta 确认)

绑定输入为 v0.3.3、800 行、SHA-256 `3f170c34d14148b762e2f1efcb151bf669f856bd6dadad28a3f1fa15a7e773a2`。本轮只审 v0.3.1 至 v0.3.3 的 delta:v0.3.2 两项边界(agent-safe 零 egress、gold 不进 VPKB-000 冻结面)、v0.3.3 五项 non-blocker 处置与四项本地歧义关闭均未重开第一轮六项硬修;六个子系统的最小失败轨迹在当前文本下均有确定性拒绝路径;未发现符合第 13.2 节定义的新 blocker。结论维持 `READY_FOR_VPKB-000`。

本轮新增一项 non-blocker:`gate-decision` 事务尚无专属 CLI 命令面(第 7.1 节命令树中既无 `vpwiki gate inspect` / `vpwiki-admin gate apply`,也未声明复用 `review` 路径),而第 7.1 节要求所有权威 `wiki/**` 写入绑定 `inspect -> approval hash -> apply`。Gate 有效性判据是数据层三者一致,不受 CLI 表面影响,且该 gate 在 VPKB-004 前无需关闭,故不构成 blocker;最小修改是在 VPKB-004 开工前把 gate-decision 显式挂到某个 inspect/apply 命令面。

### 13.4 剩余人工产品 gate

唯一未关闭的产品决定是 `HUMAN-GATE-BASELINE-001`。若优先保持最初历史基线，选择 `keep-modelscope`；若优先补齐“完整开放训练管线”技术轴，选择 `replace-with-open-sora`，并严格固定 v1.2.0 的 paper-era commit。两者都不改变底层架构，但在 VPKB-004 开始前必须由用户通过第 3 节定义的 gate-decision event 关闭并绑定唯一 manifest。

## 14. 主要参考

> 本节版本与链接是实施用 pin；其可达性、源码 digest、安装兼容性和许可证结论须在 VPKB-000 验收后才视为已验证。

- [claude-obsidian v2.1.1](https://github.com/AgriciDaniel/claude-obsidian/tree/v2.1.1)
- [claude-obsidian transaction contract](https://github.com/AgriciDaniel/claude-obsidian/blob/9f8c1199047eac2c3828496279fbb7ba9540b90b/skills/wiki/references/operation-transactions.md)
- [claude-obsidian external `content_file` implementation](https://github.com/AgriciDaniel/claude-obsidian/blob/9f8c1199047eac2c3828496279fbb7ba9540b90b/claude_obsidian/transaction.py#L2658-L2749) and [create-only/hash contract test](https://github.com/AgriciDaniel/claude-obsidian/blob/9f8c1199047eac2c3828496279fbb7ba9540b90b/tests/test_transaction.py#L1720-L1745)
- [claude-obsidian operation result schema](https://github.com/AgriciDaniel/claude-obsidian/blob/9f8c1199047eac2c3828496279fbb7ba9540b90b/claude_obsidian/transaction.py#L3745-L3766)
- [claude-obsidian generic transaction scope](https://github.com/AgriciDaniel/claude-obsidian/blob/9f8c1199047eac2c3828496279fbb7ba9540b90b/claude_obsidian/transaction.py#L3140-L3233)
- [claude-obsidian CJK BM25 tokenizer](https://github.com/AgriciDaniel/claude-obsidian/blob/9f8c1199047eac2c3828496279fbb7ba9540b90b/scripts/bm25-index.py#L290-L362)
- [claude-obsidian capture contract implementation](https://github.com/AgriciDaniel/claude-obsidian/blob/9f8c1199047eac2c3828496279fbb7ba9540b90b/claude_obsidian/cli.py#L372-L427)
- [claude-obsidian capture path limits](https://github.com/AgriciDaniel/claude-obsidian/blob/9f8c1199047eac2c3828496279fbb7ba9540b90b/claude_obsidian/capture.py#L585-L635) and [digest sibling reuse](https://github.com/AgriciDaniel/claude-obsidian/blob/9f8c1199047eac2c3828496279fbb7ba9540b90b/claude_obsidian/capture.py#L892-L905)
- [claude-obsidian stable source identity](https://github.com/AgriciDaniel/claude-obsidian/blob/9f8c1199047eac2c3828496279fbb7ba9540b90b/claude_obsidian/ledgers.py#L395-L414)
- [claude-obsidian raw-inclusive checkpoint guidance](https://github.com/AgriciDaniel/claude-obsidian/blob/9f8c1199047eac2c3828496279fbb7ba9540b90b/docs/compound-vault-guide.md#L169-L175)
- [Docling releases](https://github.com/docling-project/docling/releases)
- [Docling installation](https://docling-project.github.io/docling/getting_started/installation/)
- [Docling document model](https://docling-project.github.io/docling/reference/docling_document/)
- [OpenAlex API](https://help.openalex.org/api/)
- [Hugging Face firewall endpoints](https://huggingface.co/docs/hub/main/en/models-downloading#downloading-behind-a-proxy-or-firewall) and [Xet download flow](https://huggingface.co/docs/huggingface_hub/en/guides/download#faster-downloads)
- [Codex Skills](https://learn.chatgpt.com/docs/build-skills)
- [Open-Sora paper](https://arxiv.org/abs/2412.20404) and [official repository](https://github.com/hpcaitech/Open-Sora)

## 15. 默认假设

- 单用户、单 Vault、本地优先，不启用云同步。
- 主机为 Apple Silicon macOS，Python 3.12 环境可通过 `uv` 安装。
- Obsidian、`uv`、Docling 和其模型包在后续工作包中按审批安装，不由本计划文档创建步骤自动安装。
- Fable 已对绑定的 v0.3.1 返回 `READY_FOR_VPKB-000`，并按第 13.3 节对 v0.3.3 完成 delta 终审确认；v0.3.2 的零 egress/gold-freeze 边界和 v0.3.3 的 follow-up 修正均已保留，因此当前只允许启动 VPKB-000。后续模块必须等待第 10 节对应 contract/adapter gate，不能把 verdict 当作全模块并行实施许可。`HUMAN-GATE-BASELINE-001` 不阻塞 VPKB-000 至 003，但仍阻塞 VPKB-004/005。
- 当前只创建计划文档，不初始化代码仓库、Vault、依赖或 Git submodule。
