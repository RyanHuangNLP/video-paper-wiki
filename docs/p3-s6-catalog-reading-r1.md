# P3-§6 catalog／reading 兼容

本文件记录 `work/p3-s6-catalog-reading-r1` 相对 freeze base `c242d98c9ca34fd6a42caa24b46abb97a09ac326` 的兼容范围。组合候选在叠入 P3 五个提交并完成复演接线后另行记入 DONE。

## Catalog

`require_legacy_profile` 的默认拒绝不变，`publication.py` 仍只调用它。Catalog 在收集投影输入之前调用 `authorize_catalog_profile`：

- 快照里没有 assessment heads、display heads、association／decision／snapshot／observation，也没有 `paper-record.v2`／`assessment-event.v2` 时，仍走 legacy guard，投影与 `join_evidence` 保持原路径。
- 存在上述标记时，按现有 source 校验读取真实字节：heads、association、claim 主体和证据必须闭合。失败直接抛出原错误，不捕获后当成成功。
- v2 paper／event 不写入 v1 表。跳过 v2 paper 之后，source ledger 里属于该论文的页面也不再写入 v1 `source_pages`。它们和 heads、association 等路径以 `{path, sha256}` 进入 `builder_files`。字节变化会改变 `catalog_generation`（status 变为 `stale`），或在重新密封后仍无法通过校验时被明确拒绝。
- v2 paper 的 `source_associations` 必须与实际 association 的标识、内容哈希和论文归属一致，只存在引用 ID 不够。有记录归属的 claim，其页面必须是该记录的规范所有者页面，并且该页字节在同一快照里。
- 研究页上的 `^clm-` 锚点只在 v1 论文页上参与证据连接。其它页面保留在检索映射里，`paper_id` 为空。
- 重建只写既有运行产物（`.vault-meta` 下的索引和 catalog）。不改写 `.raw`、`wiki` 或被备份的 `.work`。

`audit_coverage`、`backup_coverage`、reading manifest 的 `not_wired`，以及四类 apply 的 `publication`／`receipt_backed` 语义都不在本票里改写。目录可重建不表示这些产品已经接到正式发布或 receipt。

## Reading

生成页安装根是 `wiki/reading/`。frontmatter 第一行仍是 `generated_by: video-paper-wiki.reading.v1`，并补上 `title`、`type`、`status`、`created`、`updated`、`tags`。`created` 与 `updated` 固定为 `2026-09-08`，这是阅读页纪元，不是墙钟。

链接按安装位置生成：

- 文章索引导出为 `articles/list.md`，避免与 `index.md` 重名。
- 阅读详情导出为 `papers/{slug}-reading.md`，以便与正式页 `wiki/papers/{slug}.md` 并存且 stem 不同。
- 正式论文、代码、概念页和记录 JSON 只在 Vault 里真实存在时才生成相对链接；否则保留身份和“尚未安装／记录文件缺失”说明。
- 文章记录指向 `{revision}.json`，不指向目录。暂存记录只在该文件位于 Vault 内时链接。
- 文章正文不再用空的 `## 正文` 标题。说明行之后原样接上 S1-R1 render 字节；没有正文时写“暂无正文记录。”

`wiki/reading-notes/**` 与没有生成标记的用户文件仍由既有 apply 边界保护。

## 命令

独立 §6 检查使用锁定环境与短临时目录：

```bash
VPKB_S6_TMP="$(mktemp -d /tmp/vp.XXXXXX)"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
uv run --offline --no-sync python -m pytest -q \
  tests/unit/test_source_state.py \
  tests/unit/test_catalog_store.py \
  tests/unit/test_reading_pages.py \
  tests/unit/test_reading_view.py \
  tests/contract/test_catalog_reading_compat.py \
  tests/closure/test_catalog_reading_compat.py \
  --basetemp "$VPKB_S6_TMP/p" \
  -o cache_dir="$VPKB_S6_TMP/cache"
```

组合分支上的富演练命令以冻票 §6.4 为准。本文件不把 §6-only 结果写成组合候选 CI。
