# Video Paper Wiki

Video Paper Wiki 是固定版 Claude Obsidian 之上的视频论文领域扩展。日常读论文、检索和当前会话问答走下面的轻量路径：原生 PDF 文本 → 分页 Markdown → 工作区内词法检索 → 当前模型回答/草稿 → 带 PDF 页码引用的 Markdown。Claude Obsidian 仍负责 Vault 事务、capture、lint、chunk 与 BM25；正式入库、67 篇 seed 和审批绑定的 PDF/代码 staging 见后文。

## 轻量 PDF 阅读与问答（正常路径）

普通使用从自然语言 Skill 开始：在当前对话打开 [`.agents/skills/video-paper-read/SKILL.md`](.agents/skills/video-paper-read/SKILL.md)，直接说“读这份本地 PDF / 用这几篇论文回答 / 写一段相关工作”。Skill 会调用本机 CLI、准备可恢复会话，并由**当前对话模型**根据返回的 evidence 写答案或短稿；不要手写内部 JSON。明确的 canonical Vault staging / 目录查询仍走 `video-paper-ingest` 与 `video-paper-query`，不要把真实 Vault 当成默认阅读工作区。

工作区必须放在批准的 `.work/**` 下。只持久化 Markdown、小型来源记录、可重建文本索引和工作流会话，不把 PDF、图片或视频拷进知识目录，也不下载 OCR/版面/embedding 模型。

不要依赖本机 PATH 上的旧 `vpwiki-research` console script。`vpwiki-research` 与 `python -m video_paper_wiki_research` 等价。请用已安装包或指定源码树启动：

```bash
# 已安装环境（推荐）：清空 PYTHONPATH，在源码树外执行
python -I -B -m video_paper_wiki_research --help

# 源码树（开发机）：必须显式指向已验收的 integration/src
export PYTHONPATH=/absolute/path/to/integration/src
python -B -m video_paper_wiki_research --help
```

连续步骤、选论文、状态/重启继续、改 source 后重新 prepare，以及 Bash/zsh 可复制命令见 [轻量 PDF 快速入门](docs/lightweight-pdf-quickstart.md)。整理带引用的知识笔记、比较选定论文、编辑/归档/恢复/替换论文，以及轻量工作区备份/恢复见 [轻量文库快速入门](docs/lightweight-library-quickstart.md)。中文问英文论文、长文分批知识、选择性刷新和提纲/章节修订见 [轻量研究快速入门](docs/lightweight-research-quickstart.md)。把 export 的 stdout JSON 对象保存为 `--context`；知识/比较 JSON 与显式 `--include-output` 必须是 8 MiB 内的常规 UTF-8 文件。备份 ZIP 只收文件、不收空目录，也不拷原 PDF；恢复后重新 `index build` 并 prepare。最小 CLI fallback（内部 JSON 仍由当前会话根据 prepare 结果生成）：

```bash
SESSION_ID=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
python -m video_paper_wiki_research workspace inspect --workspace .work/papers-ws
python -m video_paper_wiki_research workflow prepare --workspace .work/papers-ws --kind qa --query "What method does this paper propose?" --pdf /absolute/path/paper.pdf
python -m video_paper_wiki_research workflow status --workspace .work/papers-ws
python -m video_paper_wiki_research workflow complete --workspace .work/papers-ws --session-id "$SESSION_ID" --document /absolute/path/qa-answer.json --output /absolute/path/outside-ws/qa.md
```

同一 PDF 可再 `prepare` / `pdf add`，已有 notes 和用户改过的 `source.md` 会保留。`--paper-id sha256:<64 hex>` 可重复出现，用来限定问答或写作只看这些论文；未知或格式错误的 ID 会被拒绝，不会悄悄退回全部论文。`workflow status` 只读；重启后用同一个 `session_id` 继续 `complete`。改过 source 后需要重新 `index build` 或再 `workflow prepare`，旧 context 会变成 `INDEX_STALE`。同一已完成会话再用相同 document/output 会复用原文件；换一份 document 或输出路径则是 `LIGHT_SESSION_CONFLICT`，旧 Markdown 保持不动。

高级用户仍可用 `qa export` / `writing export` 看原始 context，以及 `qa import` / `writing import` 直接安装 Markdown。工作区路径可加可选 `--rewrite` JSON（仅 `--workspace`，不能走 Vault/catalog）。`--workspace` 不必再提供 Vault、retrieval config 或 Docling 参数。成功的轻量 export JSON 含 `workspace_root`。写出的 Markdown 里的来源链接相对**输出文件所在目录**，应能打开 workspace 内的 `source.md` 和 PDF **文件页码**对应的 `page-N` 锚点。旧的 `qa export --vault-root ... --upstream-root ... --config ...` 与 `writing export --paper-id ... --vault-root ...` 仍然可用，且不能与 `--workspace` 混用。`qa import` / `writing import` 按 `context.schema` 选择轻量或旧路径。

限制：只提取 PDF 里已经可以选中的文字。扫描页没有原生文本时会给出明确警告或拒绝空文档，不会改走 OCR。图表、公式、多栏版面的阅读顺序仍需对照原 PDF。词法检索支持中文文本，但不等于跨语言语义匹配。无命中是 `NO_RESULTS` / `INSUFFICIENT_EVIDENCE`，不要编造论文。轻量路径不会自动关闭 receipt / published / human-gate，也不代替正式 Vault 发布。当前模型试用不是人工事实验收。

## 安装与固定上游

主 CLI 支持 Python 3.12/3.13：

```bash
uv sync --locked
uv run --offline --no-sync vpwiki doctor
```

需要把 gitlink 初始化到固定提交 `9f8c1199047eac2c3828496279fbb7ba9540b90b`。`vpwiki` 要求显式 `--upstream-root vendor/claude-obsidian`，不会从 wheel 猜测上游位置。默认主包装不安装独立 `operator/` 包。

## 可复制工作流

```bash
# 确定性 seed（当前目录为 67 篇）
uv run --offline --no-sync vpwiki seed validate
uv run --offline --no-sync vpwiki seed status
uv run --offline --no-sync vpwiki seed render --batch-id seed-preview-1

# 上游初始化：先 dry-run，再由用户以返回的 approval SHA 明确执行
python vendor/claude-obsidian/scripts/claude-obsidian.py init /path/to/vault \
  --operation-id vpwiki-init-1 --generated-at 2026-09-02T00:00:00Z
python vendor/claude-obsidian/scripts/claude-obsidian.py init /path/to/vault \
  --operation-id vpwiki-init-1 --generated-at 2026-09-02T00:00:00Z \
  --approved-plan-sha256 <sha256> --apply

# Seed bundle同样先inspect，再用同一approval执行
python vendor/claude-obsidian/scripts/claude-obsidian.py transaction inspect \
  .work/seed-preview-1/transaction-inspect/bundle.json --vault /path/to/vault
python vendor/claude-obsidian/scripts/claude-obsidian.py transaction apply \
  .work/seed-preview-1/transaction-inspect/bundle.json --vault /path/to/vault \
  --approved-plan-sha256 <sha256>

# PDF staging / capture inspect
vpwiki ingest plan --request request.json
vpwiki ingest prepare --plan .work/<batch>/plan/ingest-plan.v1.json --approval-ref approval-ref.json
vpwiki capture inspect --prepared .work/<batch>/prepared/staged-pdf-capture-request.v1.json \
  --operation-id <id> --upstream-root vendor/claude-obsidian --vault-root /path/to/vault

# UTF-8 code staging / capture inspect
vpwiki code-map plan --request code-request.json
# code-request.json 的 input.source_path 必须与下一条命令完全一致，并进入 plan approval hash
vpwiki code-map prepare --plan .work/<batch>/plan/ingest-plan.v1.json \
  --approval-ref approval-ref.json --source-path src/model.py
vpwiki code-map inspect --prepared .work/<batch>/prepared/staged-code-capture-request.v1.json \
  --operation-id <id> --upstream-root vendor/claude-obsidian --vault-root /path/to/vault

# Code evidence: request → observe → status → config/handoff
# Input is JSON. Results are stored under .work/<batch-id>/code-evidence-v1/.
# Repeat the same bound inputs to reuse or resume a valid prefix. Status never
# creates or repairs files. A changed request, acquisition, or config format
# needs a new batch. There is no --root, --profile, --force, or --repair flag.
vpwiki code-evidence request --input request.json --batch-id <batch>
vpwiki code-evidence observe --input observe.json --bundle-dir .work/raw-bundle --batch-id <batch>
vpwiki code-evidence status --batch-id <batch>
vpwiki code-evidence config --path config.json --format json --batch-id <batch>
vpwiki code-evidence handoff --batch-id <batch>

# 对生成的 transaction bundle，写入由交互式 operator 明确委托固定上游
vpwiki-admin transaction apply --bundle .work/<batch>/transaction-inspect/bundle.json \
  --vault-root /path/to/vault --upstream-root vendor/claude-obsidian \
  --approved-plan-sha256 <sha256>

# 唯一 runtime projection writer；vpwiki 提供只读 status/query/audit
vpwiki-admin catalog build --vault-root /path/to/vault --upstream-root vendor/claude-obsidian --config retrieval-config.json
vpwiki index status --vault-root /path/to/vault --upstream-root vendor/claude-obsidian --config retrieval-config.json
vpwiki query --json --text '视频扩散' --vault-root /path/to/vault --upstream-root vendor/claude-obsidian \
  --config retrieval-config.json
vpwiki audit --vault-root /path/to/vault --upstream-root vendor/claude-obsidian --as-of 2026-09-02

# Canonical inputs -> deterministic pages and an upstream generic bundle
vpwiki compile validate --path canonical-compile-input.json
vpwiki compile render --path canonical-compile-input.json --batch-id compile-1
# The result is preview-only staging. It is not a receipt-backed publication.

# Receipt-backed publication is a separate inspection step. It derives receipt
# and head bytes, stages a compact transaction, and never applies it.
vpwiki publication prepare --request publication-input/knowledge-publication-request.v1.json --batch-id <batch>
vpwiki publication inspect --prepared .work/<batch>/publication-input/knowledge-publication-request.v1.json \
  --operation-id <operation-id> --upstream-root vendor/claude-obsidian --vault-root <vault>

# Package already-produced Docling bytes; this command does not run Docling.
vpwiki ingest package --request extraction-publication-context.json --captured-pdf <captured.pdf> \
  --document-json <document.json> --parser-config <parser-config.json> \
  --model-manifest <model-manifest.json> --run-manifest <run.json> --batch-id <batch>

# Combined read-only audit: receipt/managed-state replay plus pinned strict lint.
vpwiki audit --vault-root <vault> --upstream-root vendor/claude-obsidian

# Exact mapping/evaluation are read-only; gold never feeds mapping or ranking
vpwiki evidence join --path exact-join-input.json --vault-root /path/to/vault
vpwiki retrieval validate --config retrieval-config.json --gold retrieval-gold.json --inventory evidence-inventory.json
vpwiki retrieval evaluate --gold retrieval-gold.json --inventory evidence-inventory.json --config retrieval-config.json --mapping evidence-mapping.json --results retrieval-results.json

# Raw-inclusive private archive; only vpwiki-admin mutates archive/restore paths
vpwiki backup manifest --vault-root /path/to/vault
vpwiki-admin backup create --vault-root /path/to/vault --manifest backup-manifest.json --destination backup.zip
vpwiki-admin backup restore --archive backup.zip --source-root /path/to/vault \
  --restore-root /path/to/private-restore --manifest backup-manifest.json \
  --upstream-root vendor/claude-obsidian --config retrieval-config.json
vpwiki backup verify --source-root /path/to/vault --restore-root /path/to/private-restore \
  --manifest backup-manifest.json --upstream-root vendor/claude-obsidian --config retrieval-config.json
```

`vpwiki` 只在 `.work/**` 生成 staging，不 apply、不 recover、不构建索引。写操作直接使用固定上游公开 CLI；可选 `operator/` 包只是透明转发器，对每次副作用命令要求交互式逐次确认且没有 `--yes`。

## 人工 PDF 暂存解析（未入库）

用户提供本地 PDF 后，默认包装只做安全接收、parser profile 校验和有定位的 **provisional** 知识提案。这不是 canonical 入库，也不是真实 Docling/模型验收。

```bash
# 1. 校验并暂存 PDF 字节（写入 .work/blobs/<sha256> 与 intake 信封）
vpwiki-research pdf intake --pdf /path/to/paper.pdf --session s1

# 2. 可选：在另行准备的离线 Docling 环境生成 profile 与四份 staged 产物
#    vpwiki-parser 不在默认 lock 中，agent CLI 从不导入或调用它。
vpwiki-parser profile --artifacts-path /path/to/offline-models --session s1
vpwiki-parser export --intake .work/research/s1/manual-pdf/intakes/<sha>.json \
  --profile .work/research/s1/manual-pdf/profile/profile.json \
  --artifacts-path /path/to/offline-models --session s1 --run-id run-1

# 3. 从四份 staged 产物生成带 locator 的分析上下文（CLI 不调用模型）
vpwiki-research pdf context --intake .work/research/s1/manual-pdf/intakes/<sha>.json \
  --profile .work/research/s1/manual-pdf/profile/profile.json \
  --run .work/research/s1/manual-pdf/runs/run-1 \
  --upstream-root vendor/claude-obsidian --session s1

# 4. 把当前会话模型返回的 unsealed JSON 封成 provisional 提案
vpwiki-research pdf analyze --context .work/research/s1/manual-pdf/contexts/<sha>.json \
  --proposal proposal.unsealed.json --upstream-root vendor/claude-obsidian --session s1
```

`pdf plan` 只生成既有 `ingest-plan.v1` 并返回 `awaiting_external_approval_ref`，**不会**创建 approval-ref。真实 capture 需要后续 genesis → capture inspect/apply → 源登记/receipt 工作流；不要对未初始化的 Vault 执行 capture 并假装随后可以 `ingest package`。夹具测试不是真实 PDF/Docling 验收。

当前模型应只根据 `pdf context` 返回的 task prompt 生成 transport draft，且全部 claim 保持 `provisional`。

## 领域命令

- `ingest inspect --path ... [--schema ...]`、`review inspect ...` 校验已有 closed JSON。
- `draft export/validate` 与 `review export` 生成和检查审阅材料。
- Python API `compile_paper_page`、`compile_code_page`、`compile_concept_page` 生成确定性中文页面。
- `compile validate/render` 从 canonical records、claim evidence、assessment heads、inspected code manifest 和固定 taxonomy 生成页面及上游 generic transaction bundle。
- `evidence join` 只做 exact anchor/locator/chunk/index 绑定；`retrieval validate/evaluate` 验证独立 gold，gold 不参与映射或排序。
- `backup manifest/verify` 只建立 raw-inclusive 完整集与验证隔离恢复树；私有 ZIP 的 create/restore 只由交互式 operator 执行，外部锚和真实隔离恢复观察仍是人工 gate。
- `query` 以 config 和已验证 SQLite catalog 固定 BM25 candidate depth 与 `mapping_sha256`，生成 Paper top-10/top-5 和 evidence top-8；不接受 caller mapping 或 gold。
- `audit` 原样保留上游 strict lint 的 `version`、`engine_version`、`summary` 和 findings，并返回 strict exit 状态。

外部 PDF、人工 claim/assessment 与视觉验收都是运行时输入，不由 seed 或测试 fixture 伪造。approval-ref 只绑定输入，不等于执行授权。

## 测试

准备固定、detached、clean 的上游 checkout 后：

```bash
VPKB_TEST_TMP="$(mktemp -d /tmp/vp.XXXXXX)"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --offline --no-sync python -m pytest -q \
  --basetemp "$VPKB_TEST_TMP/p" -o cache_dir="$VPKB_TEST_TMP/cache"
```

测试使用 disposable Vault；不要对真实 Vault 运行 fixture。目录和 overlays 保持 67 项，PR 交付与人工 gate 状态以 `docs/ai/task-index.yaml` 为准。
