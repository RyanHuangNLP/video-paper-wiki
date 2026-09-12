# Video Paper Wiki

Video Paper Wiki 是固定版 Claude Obsidian 之上的视频论文领域扩展。Claude Obsidian 负责 Vault 事务、capture、lint、chunk 与 BM25；本项目负责 67 篇确定性 seed、审批绑定的 PDF/代码 staging、中文 Paper/Code/Concept 编译、code-evidence manifest 和查询结果整形。

用户类目种子清单：[预训练（12 篇）](docs/seed/pretraining.md)，包含九篇模型论文与三篇训练方法论文，独立记录于固定工程 seed 之外。

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
