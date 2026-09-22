# P3-R1：有界研究产物备份与无原根恢复

`research-r1` 只覆盖本文件列出的白名单。它不是全项目保险，也不证明科学结论、官方性、发布资格或外部存储可靠。成功归档只说明这份清单里的字节已被装进私有 classic ZIP。

默认 profile 仍是 `vault-v1`。不带 `--profile` 的命令保持原有行为：v1 恢复必须提供 `--source-root`，不读取 checkout，也不把 `.work` 放进 v1 的 `ROOTS`。

## 覆盖

| 规则 | 保存什么 |
|---|---|
| `vault` | `V/.raw/**` 与 `V/wiki/**` 的完整 v1 集合，含原始证据、operation receipts、registries、已安装历史、阅读页和 `wiki/reading-notes/**`。 |
| `code-evidence` | `C/.work/<batch>/code-evidence-v1/` 下的 request、intent、observation、bundle，以及全部 `objects/*.body`、`configs/*.json`、`handoffs/*.json`。 |
| `flow` | `flow/selection.json`，`experiments/<setting_key>/input.json`，`articles/<article_id>/{context,document}.json`。 |
| `domain` | `domain/annotations/<lineage>/<annotation>.json`，`reviews/<lineage>/<review>.json`，`heads.json`。 |
| `experiments` | `experiments/records/<condition>/<record>.json`，`heads.json`。 |
| `articles` | `articles/records/<article>/<revision>.json`，`render/<article>/<revision>.md`。不保存 `articles/heads.json`。 |
| `draft` | `draft/paper-analysis-draft.v1.json` |
| `review` | `review/paper.md` |
| `plan` | `plan/ingest-plan.v1.json` |

扫描器自动枚举 `C/.work` 下通过 `validate_batch_id` 的批次，只进入上表的固定布局。每个批次的八条规则都会记成 `included` 或 `absent`。空目录可以是 `included` 且 `file_count=0`。存在但不可读、符号链接、硬链接、特殊文件或读取中变化，都不会记成 `absent`。白名单目录里的未知名字会拒绝并报告路径。

同一份 staging 即使已经安装进 Vault，也仍然单独保存，不去重、不裁历史。

上限与 v1 相同：单文件 64 MiB，目录加文件合计 65,534 项，以及 classic ZIP 的总字节上限。Vault 和 checkout 共用这一份剩余预算。checkout 扫描、内层枚举和复核都先按剩余限额停住，再收集和排序；不会把超限文件读完之后才拒绝。另外最多 128 个批次，发现阶段最多检查 4,096 个候选目录项。超限整次失败，不产生部分归档。

成功出口和异常出口都会在 checkout 内容复核之后再核对 Vault。最终复核期间 Vault 发生变化时，返回的是失败，不是复核开始前的旧 manifest。

## 明确不在这份归档里

这些项会出现在 manifest 的 `excluded` 里。成功不能解释成“无需备份”或“已经完整保护”。

可重建（`rebuildable`）：

- `V/.vault-meta/**`：catalog 和索引由恢复后的 operator 重建。
- `C/.work/<batch>/source-catalog/**`
- `C/.work/<batch>/reading/**`（已安装的 `V/wiki/reading/**` 仍随 wiki 保存）
- `C/.work/<batch>/{domain,experiment,article,reading}-publication/**`
- Git checkout 的代码、`.git`、依赖、模型和测试输出。恢复后的代码环境要另外准备。

未覆盖（`out_of_scope`）：

- 轻量工作区的 `papers`、`.light-library`、`.light-knowledge`、`.light-workflow`、写作产物和外部输出。继续用现有 `vpwiki-research backup`。
- `C/.work/research/<session>/{manual-pdf,discovery-v1,preview-v1}/**`
- `C/.work/blobs/**`、`VPWIKI_BLOB_ROOT` 和外部原始 PDF
- 不在白名单中的其他 capture、conversion、publication 输入、临时工作树和自定义文件
- `.work/pdf-migration/**`、迁移 journal、rollback backups、Drive 远端文件

`blobs`、`pdf-migration`、`research` 这三个顶层名字即使符合批次语法，也不会被当成批次。已经进入 `V/.raw` 或 `V/wiki` 的数据仍按 v1 保存。

## 命令

```bash
vpwiki backup manifest --profile research-r1 \
  --vault-root "$V" --checkout-root "$C"

vpwiki-admin backup create --profile research-r1 \
  --vault-root "$V" --checkout-root "$C" \
  --manifest "$M" --destination "$A"

vpwiki-admin backup restore --profile research-r1 \
  --archive "$A" --manifest "$M" \
  --expected-manifest-sha256 "$H" \
  --restore-root "$R" --upstream-root "$U" --config "$P"

vpwiki backup verify --profile research-r1 \
  --manifest "$M" --expected-manifest-sha256 "$H" \
  --restore-root "$R" --upstream-root "$U" --config "$RESTORED_CONFIG"
```

`research-r1` 的 manifest 和 create 必须带 `--checkout-root`。profile 与 manifest 的 schema 不一致时直接拒绝，不会降级成 v1。

`vpwiki backup manifest` 打印现有 JSON envelope。只有 `.data` 是可以交给 operator 的 manifest 文档：

```bash
vpwiki backup manifest --profile research-r1 --vault-root "$V" --checkout-root "$C" \
  | python -c 'import json,sys; json.dump(json.load(sys.stdin)["data"], sys.stdout, ensure_ascii=False, separators=(",", ":"))' \
  > "$M"
H=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["manifest_sha256"])' "$M")
```

`$H` 必须是此时单独保存的 `manifest_sha256`。从正在校验的 ZIP 里临时读出一个哈希，不能当作这个独立锚。

create 和 restore 仍是逐次交互确认，没有 `--yes`。非 TTY 或拒绝确认时不写归档、不改恢复根。create 成功只表示归档已经生成，`research_validation` 为 `pending`。

## 恢复到新根

`.raw/**` 和 `wiki/**` 来自 Vault，白名单 `.work/**` 来自 checkout。两者可以是同一目录，也可以分开。恢复写到新的空目录 `R`（模式 `0700`），相对路径不变，所以 `R` 同时有 Vault 数据和研究 `.work`。

恢复不打开原来的 Vault 或 checkout 去补文件。开始前会检查归档、嵌入 manifest、外部 manifest 和成员集合。拒绝路径穿越、绝对路径、重复成员和类型伪造。不使用不受约束的 `extractall`。

目的地和恢复根不能与来源根或归档重叠。原来的路径如果已经不存在，不会因此失败；如果还在，并且和恢复根是同一路径或嵌套，则拒绝。

失败不会返回成功。已经写出的成员只在本次提取还能证明归属时清理；不能证明归属的路径不会被递归删除。

恢复后的代码环境不是归档的一部分。备份命令不会创建 `.git`，也不会放宽 `resolve_checkout_root`。在 `R` 上准备候选版本的做法是本地 Git：

```bash
git init
git fetch /path/to/candidate HEAD
git checkout --detach FETCH_HEAD
```

先确认这个提交的受控路径不覆盖 `.raw`、`wiki`、`.work`，再 checkout。研究读取和最终 `backup verify` 的进程当前目录都是这份恢复根 `R`。在 `R` 之外执行时，研究读取以 `RESTORE_VERIFICATION_FAILED` 拒绝，消息是 `research verify requires the restored checkout`。

`backup verify` 会核对 manifest 自哈希、source anchor、v1 `vault_manifest_sha256`、规则计数和逐项字节，并调用现有的 `status_code_proof`、`build_flow_status`、`status_article_store`、`article_history`、`status_domain_store`、`status_experiment_store`（只对清单里 `included` 的规则）。传给 flow 的 `vault_root` 是字符串，这样生成的 argv 才能通过字符串 schema。

已安装且仍保留 staging 的文章用兼容读取：先按现有合并读取；若合并因 `staged_previous` 失败，则单独校验 staging 链，并要求每个 staging 修订都已在 Vault 历史中且记录字节相同。渲染快照一并核对。staging 不会被删除。未安装文章仍走原来的合并读取。

`valid=true` 只在这些适用检查和既有 Vault 验证都通过时出现。`external_backup_observation` 保持 `false`。

operator restore 在研究读取之前返回。此时 `research_validation=pending`，不能把 `verification.valid` 当成演练已经通过。

## 失败时怎么处理

- 缺 `--checkout-root`、缺 `--expected-manifest-sha256`、v1 缺 `--source-root`、profile 和 schema 不一致：用法或契约错误，不写目的地。
- 自哈希或独立锚不对、成员缺失、多余、重复、穿越、绝对路径、NFC／casefold 冲突、ZIP 元数据伪造：整次拒绝。
- 符号链接、硬链接、特殊文件、来源在确认窗口被替换、非空恢复根、错误模式、根重叠：整次拒绝。
- 写入或持久化结果对不上：不报告成功。
- 合法的未完成研究状态会原样恢复，不会被补成完成，也不会自动发布。

当前产品边界：`status_experiment_store`、`status_article_store` 和 `build_flow_status` 需要 Vault 里的 `wiki/meta/records/assessment-heads.json`（以及 source association 等材料）。`build_current_catalog` 对这个路径以及 source-version association 会以 `SOURCE_PROFILE_REQUIRED` 拒绝，因为现有 catalog 只接受 legacy profile。因此同一棵树不能同时通过 catalog 重建和这些研究读取。字节恢复、receipt 审计和代码证据读取可以在原根移走后完成；`valid=true` 不能在 catalog 拒绝时被标成通过。四类 apply-result 的 `publication=unpublished`、`receipt_backed=false`、`audit_coverage=not_wired`、`backup_coverage=not_wired` 不因本次备份而改变。

FOLLOW2 新确认的阻塞仍是这两项。FOLLOW3 补上的是另一组资源缺口：共享条目额度在读文件之前就检查，父层待处理名字和子树已占用的条目都计入；Vault 最终完整集合枚举先碰到限额再收集，不再 `list(os.scandir(...))` 把一个目录收齐。本轮没有改 `catalog_store.py`、`catalog_collector.py`、`source_state.py` 或 `reading/pages.py`，也没有删除 assessment-heads、过滤恢复数据或跳过检查。最小前置方案见交付记录：catalog 需要能在不丢弃 assessment-heads 和 source-version association 的前提下重建；阅读页生成需要满足 strict lint 的 frontmatter、链接、基名和节约束。这两项落地之前，带四类 apply 产物的完整演练不能诚实标成 `valid=true`。

已安装的 `wiki/reading/**` 生成页还会让 strict lint 失败。这些页的 frontmatter 没有 `title`、`type`、`status`、`created`、`updated`、`tags`，并且含有指向尚未存在页面的链接、重复的 `index` 基名和空节。手写的 claim/source ledger 与 `wiki/reading-notes` 可以单独通过出处和孤立页检查；这不能把生成阅读页算成 lint 通过。`backup verify` 先停在 strict lint，到不了 catalog。两条失败要分开记录。

本轮 closure 演练用生产入口准备了代码证据、flow、未安装文章的三次修订、真正未安装的领域标注、审阅和实验记录、四类 apply 产物，以及真实的 draft、review、plan。覆盖集合、字节和模式的期望来自文件系统观察，不调用待测 scanner。manifest 来自 CLI 的 `.data`。create 和 restore 走 operator 的 PTY 确认。原 Vault、checkout 和采集 bundle 移走之后，恢复出的覆盖文件集合、字节和模式与这份独立期望以及 manifest 一致；receipt 审计为 `receipt_backed`；代码、flow、文章 status/history、领域和实验状态与备份前一致；已安装仍保留的文章 staging 按 `retained_installed_staging` 读出，未安装文章按 `merged` 读出。这些消费者核对发生在 operator 返回之后、最终成功断言之前。operator restore 退出码为 2，`SOURCE_PROFILE_REQUIRED`。独立 catalog 调用是同一个代码。最终 `backup verify` 退出码为 2，代码 `RESTORE_VERIFICATION_FAILED`，消息是 `strict lint rejected restored Vault`。本次 lint 计数：`dead_links` 18、`duplicate_basenames` 1、`empty_sections` 1、`missing_frontmatter` 9、`stale_index_entries` 3，其余类别为 0。验证前后覆盖文件没有变化。`valid` 不是 `true`。`missing_frontmatter` 非零是这条历史失败的记录，单独放在失败场景里，不再当作成功演练的前置条件。演练日志写在测试临时目录的 `p3-r1-drill.json`。

FOLLOW4 把两件失败分开记录。

本票的工作目录缺陷：隔离安装富演练的最终 `vpwiki backup verify` 曾经把当前目录设成归档所在的 `outside`。冻票要求最终 verify 从已准备好对应代码版本的恢复 checkout 根执行。当前目录是 `outside` 时，研究读取报 `research verify requires the restored checkout`。Vault 语义检查先跑 strict lint，所以这条工作目录失败会被 lint 挡住；lint 通过之后，演练仍会停在错误的当前目录上。修正后的安装演练把最终 verify 的当前目录改成恢复根。消费者 CLI 退出非 0 时，演练失败，并把该次输出写入 `installed-drill.json`。

§6 的 catalog／reading 前置仍在。本轮没有改 `catalog_store.py`、`catalog_collector.py`、`source_state.py` 或 `reading/pages.py`，也没有删除 assessment-heads、过滤恢复数据或跳过 lint。修正工作目录之后，隔离安装富演练的实测命令和结果如下（候选 `b38817fd1b84b0882d9f2bc1e5c12e0b0f5ae87f`，日志 `/tmp/p3-follow4/closure/test_installed_cli_replays_the0/installed-drill.json`）：

```text
# 当前目录是归档所在目录，不是恢复根
vpwiki-admin backup create --profile research-r1 ...
# 退出 0
vpwiki-admin backup restore --profile research-r1 ... --restore-root "$R" ...
# 退出 2，SOURCE_PROFILE_REQUIRED，source-aware publication/catalog is required

# 在 "$R" 上 checkout 候选版本之后，当前目录改为 "$R"
vpwiki code-evidence status --batch-id d1
vpwiki flow status --vault-root "$R" --batch-id d1
vpwiki domain status --vault-root "$R"
vpwiki experiments status --vault-root "$R"
vpwiki articles status --vault-root "$R"
# 五条退出码都是 0

vpwiki backup verify --profile research-r1 \
  --manifest "$M" --expected-manifest-sha256 "$H" \
  --restore-root "$R" --upstream-root "$U" --config "$P"
# 当前目录是 "$R"
# 退出 2，RESTORE_VERIFICATION_FAILED，strict lint rejected restored Vault
# valid 不是 true
```

这次安装演练的 manifest SHA-256 是 `5388bc0098da32d1541e6b8f1862d01145214568a97678c6ea9077b7cd1b2362`，archive SHA-256 是 `8ae05fc748ec1f0031dafd49099a9c786f15e7368996d2610cee88675658c1db`。restore 退出 0、verify 退出 0、最终 `valid=true` 的硬断言因此失败。失败停在 catalog 拒绝和 strict lint：verify 的代码是 `RESTORE_VERIFICATION_FAILED`，消息是 `strict lint rejected restored Vault`。
