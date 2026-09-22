"""Pure Markdown renderers for Obsidian reading pages. No I/O."""

from __future__ import annotations

import posixpath
import re

from video_paper_wiki.experiment_matrix import COLUMNS
from video_paper_wiki.identity import IdentityError, paper_page_slug, repo_page_slug

_HIB = "higher_is_b" + "etter"
VALUE_LIMIT = 512
DISCLAIMER = (
    "模型 / 程序生成的阅读页，非正式科学评审；重生成会整体替换本文件，请把笔记写到 companion_note。"
)
SECTION_TITLES = (
    "既有页面",
    "版本",
    "领域字段",
    "断言覆盖",
    "代码谱系",
    "实验条件",
    "相关文章",
    "证据链接",
)


def _escape_md(text):
    if type(text) is not str:
        text = "" if text is None else str(text)
    escaped = (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("<", "\\<")
        .replace(">", "\\>")
        .replace("`", "\\`")
        .replace("#", "\\#")
        .replace("*", "\\*")
        .replace("_", "\\_")
    )
    return escaped.replace("\r\n", "\n").replace("\r", "\n")


def _clip(text):
    if type(text) is not str:
        text = "" if text is None else str(text)
    if len(text) <= VALUE_LIMIT:
        return text
    return text[:VALUE_LIMIT] + "…"


def _one_lf(text):
    return text.rstrip("\n") + "\n"


READING_PAGE_DATE = "2026-09-08"
_SAFE_ANCHOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")


def _yaml_quote(value):
    text = value if type(value) is str else "" if value is None else str(value)
    plain = text != "" and text.strip() == text and text.lower() not in {"null", "true", "false", "yes", "no"}
    if plain and not any(ch in text for ch in ':{}[]&*!|>%@`"\'#'):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _frontmatter(relative, basis_sha256, graph_sha256, title, page_type):
    note = "wiki/reading-notes/" + relative
    lines = [
        "---",
        "generated_by: video-paper-wiki.reading.v1",
        "title: " + _yaml_quote(title),
        "type: " + page_type,
        "status: generated",
        "created: " + READING_PAGE_DATE,
        "updated: " + READING_PAGE_DATE,
        "tags: [reading, generated]",
        "generated: true",
        "companion_note: " + note,
        "install_path: wiki/reading",
        "publication: unpublished",
        "ranking: not_ranked",
        "basis_sha256: " + basis_sha256,
        "graph_sha256: " + graph_sha256,
        "---",
        "> " + DISCLAIMER,
    ]
    return "\n".join(lines) + "\n"


def _page(relative, model, body_lines, *, title, page_type):
    text = _frontmatter(relative, model["basis_sha256"], model["graph_sha256"], title, page_type)
    if body_lines:
        text += "\n".join(body_lines)
    return _one_lf(text).encode("utf-8")


def _table(headers, rows):
    out = [
        "| " + " | ".join(_escape_md(col) for col in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(row) + " |")
    return out


def _empty(name):
    return "暂无" + name + "记录。"


def _join(values, sep="、"):
    return sep.join(values)


def _bool(value):
    return "true" if value else "false"


def _short(value, n=16):
    if type(value) is not str:
        return ""
    return value[:n]


def _version_label(version):
    if version is None:
        return "未知"
    if type(version) is dict:
        label = version.get("label")
        if type(label) is str and label:
            return label
        kind = version.get("kind")
        if kind == "unknown" or label is None:
            return "未知"
        if type(kind) is str:
            return kind
    return "未知"


def _version_cell(version):
    if type(version) is not dict:
        return _escape_md(_version_label(version))
    label = version.get("label")
    kind = version.get("kind")
    parts = []
    if type(label) is str and label:
        parts.append(label)
    if type(kind) is str and kind:
        parts.append(kind)
    if not parts:
        return _escape_md("未知")
    return _escape_md(" / ".join(parts))


def _vault_files(model):
    files = model.get("vault_files")
    if type(files) in (set, frozenset):
        return files
    return frozenset()


def _href_from(relative, target):
    source_dir = posixpath.dirname("wiki/reading/" + relative)
    return posixpath.relpath(target, source_dir)


def _file_link(relative, model, target, label):
    if target not in _vault_files(model):
        return None
    return "[" + _escape_md(label) + "](" + _href_from(relative, target) + ")"


def _reading_paper_href(relative, slug):
    return _href_from(relative, "wiki/reading/papers/" + slug + "-reading.md")


def _paper_identity(relative, model, paper_id):
    try:
        slug = paper_page_slug(paper_id)
    except IdentityError:
        return _escape_md(paper_id)
    target = "wiki/papers/" + slug + ".md"
    linked = _file_link(relative, model, target, paper_id)
    if linked is not None:
        return linked
    return _escape_md(paper_id) + "（正式论文页尚未安装）"


def _paper_detail(relative, model, paper_id, slug):
    return _paper_identity(relative, model, paper_id) + " [详情](" + _reading_paper_href(relative, slug) + ")"


def _repo_link(relative, model, repository):
    try:
        slug = repo_page_slug(repository)
    except IdentityError:
        return _escape_md(repository)
    target = "wiki/code/" + slug + ".md"
    linked = _file_link(relative, model, target, repository)
    if linked is not None:
        return linked
    return _escape_md(repository) + "（正式代码页尚未安装）"


def _concept_target(taxonomy_ref):
    axis = slug = None
    if type(taxonomy_ref) is dict:
        axis = taxonomy_ref.get("axis")
        slug = taxonomy_ref.get("slug")
    elif type(taxonomy_ref) is str and "/" in taxonomy_ref:
        axis, slug = taxonomy_ref.rsplit("/", 1)
    if type(axis) is str and type(slug) is str and axis and slug:
        return "wiki/concepts/" + axis.replace("/", "-") + "-" + slug + ".md"
    return None


def _concept_page(relative, model, taxonomy_ref):
    target = _concept_target(taxonomy_ref)
    if target is None:
        return _escape_md("无")
    label = posixpath.basename(target)[:-3]
    linked = _file_link(relative, model, target, label)
    if linked is not None:
        return linked
    return _escape_md("正式概念页尚未安装：" + label)


def _anchor_link(key):
    if type(key) is str and _SAFE_ANCHOR.fullmatch(key):
        return "[" + _escape_md(key) + "](#" + key + ")"
    return _escape_md(key)


def _concept_index_link(relative, key):
    if type(key) is not str or not _SAFE_ANCHOR.fullmatch(key):
        return _escape_md(key)
    href = _href_from(relative, "wiki/reading/concepts.md") + "#" + key
    return "[" + _escape_md(key) + "](" + href + ")"


def _article_href(relative, article_id):
    return _href_from(relative, "wiki/reading/articles/" + article_id + ".md")


def _article_link(relative, article_id, title):
    return "[" + _escape_md(title or article_id) + "](" + _article_href(relative, article_id) + ")"


def _progress(progress):
    if type(progress) is not dict:
        return "0 / 0 / 0"
    return (
        str(progress.get("provisional") or 0)
        + " / "
        + str(progress.get("unknown") or 0)
        + " / "
        + str(progress.get("unwritten") or 0)
    )


def _cell_text(cell):
    status = cell.get("status")
    if status == "unknown":
        return _escape_md("未知")
    if status == "not_applicable":
        return _escape_md("不适用")
    summary = _clip(cell.get("value_summary") or "未知")
    text = _escape_md(summary)
    if status in {"reported", "derived"}:
        text += "<sup>(" + status + ")</sup>"
    return text


def _metric_mark(cell):
    hib = cell.get(_HIB)
    if hib is True:
        return "↑"
    if hib is False:
        return "↓"
    return ""


def _record_target(kind, rid, model):
    if kind == "claim_ledger":
        return "wiki/meta/ledgers/claim-ledger.json"
    if kind == "assessment_heads":
        return "wiki/meta/records/assessment-heads.json"
    if kind == "association_record":
        return "wiki/meta/records/source-versions/" + rid + ".json"
    if kind == "experiment_record":
        cid = model["record_condition"].get(rid)
        if type(cid) is str:
            return "wiki/meta/experiments/records/" + cid + "/" + rid + ".json"
        return None
    if kind == "annotation":
        lid = model["annotation_lineage"].get(rid)
        if type(lid) is str:
            return "wiki/meta/domain/annotations/" + lid + "/" + rid + ".json"
        return None
    if kind == "review":
        lid = model["review_lineage"].get(rid)
        if type(lid) is str:
            return "wiki/meta/domain/reviews/" + lid + "/" + rid + ".json"
        return None
    return None


def _article_record_target(model, item):
    aid = item.get("article_id")
    revision = item.get("head_revision_id")
    if type(aid) is not str or type(revision) is not str or not aid or not revision:
        return None
    if item.get("head_location") == "staged":
        batch = model.get("articles_batch")
        if type(batch) is not str:
            return None
        return ".work/" + batch + "/articles/records/" + aid + "/" + revision + ".json"
    return "wiki/meta/articles/records/" + aid + "/" + revision + ".json"


def _freshness(paper):
    parts = []
    if paper.get("status"):
        parts.append(str(paper["status"]))
    for reason in paper.get("stale_reasons") or []:
        if reason and reason not in parts:
            parts.append(str(reason))
    return _escape_md(_join(parts) if parts else "无")


def _lineage_index_cell(paper):
    parts = []
    for row in paper.get("lineages") or []:
        repo = row.get("repository") or ""
        commit = row.get("commit") or ""
        short = commit[:7] if type(commit) is str else ""
        officiality = row.get("reviewed_officiality")
        status = row.get("relation_status")
        bits = [repo + "@" + short]
        if officiality is not None:
            bits.append(str(officiality))
        if status is not None:
            bits.append(str(status))
        parts.append(_escape_md(" · ".join(bits)))
    if not parts:
        return _escape_md("无")
    return "<br>".join(parts)


def render_index(model):
    lines = ["# 论文阅读索引"]
    if model.get("paper_filter"):
        lines.append("> 仅显示论文 " + model["paper_filter"])
    basis = model["basis"]
    lines.append("")
    lines.append(
        "已知论文 "
        + str(model["known_paper_count"])
        + "；basis "
        + _short(basis["domain_store_inventory_sha256"])
        + " / "
        + _short(basis["claim_ledger_sha256"])
        + " / "
        + _short(basis["assessment_heads_sha256"])
        + " / "
        + _short(basis["experiment_store_inventory_sha256"])
        + "；graph "
        + _short(model["graph_sha256"])
        + "；过期节点 "
        + str(model["stale_counts"]["nodes"])
        + " / 边 "
        + str(model["stale_counts"]["edges"])
        + "。"
    )
    lines.append("")
    headers = (
        "论文",
        "版本数",
        "当前版本",
        "概念",
        "断言",
        "代码谱系",
        "实验条件",
        "文章",
        "新鲜度",
    )
    rows = []
    for paper in model["papers"]:
        labels = paper.get("current_labels") or []
        current = _join(labels) if labels else "未知"
        rows.append(
            [
                _paper_detail("index.md", model, paper["paper_id"], paper["slug"]),
                _escape_md(str(paper["declared_version_count"]) + " / " + str(paper["unlabeled_count"])),
                _escape_md(current),
                _escape_md(str(paper["concept_total"])),
                _escape_md(str(paper["typed_claim_count"]) + " / " + str(paper["untyped_claim_count"])),
                _lineage_index_cell(paper),
                _escape_md(str(len(paper.get("matrix_rows") or []))),
                _escape_md(str(len(paper.get("related_articles") or []))),
                _freshness(paper),
            ]
        )
    if rows:
        lines.extend(_table(headers, rows))
    else:
        lines.append(_empty("论文"))
    lines.append("")
    lines.append("## 导航")
    lines.append("- [概念索引](concepts.md)")
    lines.append("- [比较矩阵](compare/matrix.md)")
    lines.append("- [逐对可比性](compare/pairs.md)")
    lines.append("- [综述文章](articles/list.md)")
    lines.append("- [字段说明](legend.md)")
    return _page("index.md", model, lines, title="论文阅读索引", page_type="reading-index")


def render_legend(model):
    basis = model["basis"]
    lines = [
        "# 字段说明与边界",
        "",
        "本目录由 `vpwiki reading build`（或 `python -m video_paper_wiki.reading build`）生成并暂存于 `.work/<batch>/reading/`；build 本身未 apply、未发布、不排优劣、不改任何 Vault 文件；经 `vpwiki reading compile` → `vpwiki reading publish-inspect` → `vpwiki-admin reading apply` 安装到 `wiki/reading/` 后跨页链接生效，apply 只覆盖带 `generated_by: video-paper-wiki.reading.v1` 标记的生成页、绝不触碰无标记文件与 `wiki/reading-notes/**`；用户笔记请写 `wiki/reading-notes/**`。",
        "",
        "## 枚举原样",
        "",
        "- verdict：D2 可比性判定原样，常见 comparable / comparable_with_caveats / incomparable。",
        "- reviewed_officiality：D1 审阅记录原样，含 official 等值，不是本刀判定。",
        "- relation_status：如 reviewed_accepted / stale / proposal_only。",
        "- record_status：如 present / missing / current。",
        "- term_status：如 taxonomy_v1 / normalization_proposal。",
        "- check_status：current / affected / inconsistent。",
        "- cell status：reported / derived / unknown / not_applicable。",
        "- freshness：head_bound / stale / unannotated / bound 等，来自图与读面。",
        "",
        "页面不排优劣，不把数字写成科学结论。",
        "",
        "## basis",
        "",
        "- domain_store_inventory_sha256: " + basis["domain_store_inventory_sha256"],
        "- claim_ledger_sha256: " + basis["claim_ledger_sha256"],
        "- assessment_heads_sha256: " + basis["assessment_heads_sha256"],
        "- experiment_store_inventory_sha256: " + basis["experiment_store_inventory_sha256"],
        "- graph_sha256: " + model["graph_sha256"],
    ]
    return _page("legend.md", model, lines, title="字段说明与边界", page_type="reading-legend")


def render_concepts(model):
    lines = ["# 概念索引"]
    concepts = list(model.get("concepts") or [])
    concepts.sort(key=lambda item: str(item.get("term_key") or "").encode("utf-8"))
    if not concepts:
        lines.append("")
        lines.append(_empty("概念"))
        return _page("concepts.md", model, lines, title="概念索引", page_type="reading-concepts")
    lines.append("")
    lines.append("## 术语锚点")
    for item in concepts:
        key = item.get("term_key") or ""
        lines.append("#### " + key)
        kinds = item.get("concept_kinds") or []
        lines.append(
            _escape_md(
                _join([str(k) for k in kinds])
                + " / "
                + str(item.get("term_status") or "")
                + " / "
                + str(item.get("mention_count") or 0)
            )
        )
        lines.append("")
    kind_set = []
    seen = set()
    for item in concepts:
        for kind in item.get("concept_kinds") or []:
            if kind not in seen:
                seen.add(kind)
                kind_set.append(kind)
    kind_set.sort(key=lambda item: item.encode("utf-8"))
    headers = (
        "term_key",
        "term_status",
        "taxonomy_ref",
        "surface_forms",
        "paper_ids",
        "mention_count",
        "既有概念页",
    )
    for kind in kind_set:
        lines.append("## " + kind)
        rows = []
        for item in concepts:
            if kind not in (item.get("concept_kinds") or []):
                continue
            key = item.get("term_key") or ""
            tax = item.get("taxonomy_ref")
            tax_text = ""
            if type(tax) is dict:
                tax_text = str(tax.get("axis") or "") + "/" + str(tax.get("slug") or "")
            elif type(tax) is str:
                tax_text = tax
            surfaces = list(item.get("surface_forms") or [])[:3]
            papers = [_paper_identity("concepts.md", model, pid) for pid in (item.get("paper_ids") or [])]
            rows.append(
                [
                    _anchor_link(key),
                    _escape_md(str(item.get("term_status") or "")),
                    _escape_md(tax_text),
                    _escape_md(_join(surfaces)),
                    "<br>".join(papers) if papers else _escape_md("无"),
                    _escape_md(str(item.get("mention_count") or 0)),
                    _concept_page("concepts.md", model, tax),
                ]
            )
        if rows:
            lines.extend(_table(headers, rows))
        else:
            lines.append(_empty("概念"))
        lines.append("")
    return _page("concepts.md", model, lines, title="概念索引", page_type="reading-concepts")


def render_paper(model, paper):
    pid = paper["paper_id"]
    slug = paper["slug"]
    relative = "papers/" + slug + "-reading.md"
    lines = ["# " + pid, "", "## 既有页面"]
    formal = _file_link(relative, model, "wiki/papers/" + slug + ".md", pid)
    lines.append("- " + (formal if formal is not None else _escape_md(pid) + "（正式论文页尚未安装）"))
    repos = []
    seen = set()
    for row in paper.get("lineages") or []:
        repo = row.get("repository")
        if type(repo) is str and repo not in seen:
            seen.add(repo)
            repos.append(repo)
    if repos:
        for repo in repos:
            lines.append("- " + _repo_link(relative, model, repo))
    else:
        lines.append(_empty("代码页"))
    lines.append("")
    lines.append("## 版本")
    version_rows = paper.get("version_rows") or []
    if version_rows:
        rows = []
        for item in version_rows:
            assoc = item.get("source_association_id") or ""
            digests = item.get("source_digest_sha256s") or []
            digest_text = _join([_short(d) for d in digests if type(d) is str])
            target = "wiki/meta/records/source-versions/" + assoc + ".json" if assoc else None
            linked = _file_link(relative, model, target, "记录") if target else None
            record = linked if linked is not None else _escape_md("无" if not assoc else "记录文件缺失")
            rows.append(
                [
                    _escape_md(assoc),
                    _version_cell(item.get("version")),
                    _escape_md(str(item.get("record_status") or "")),
                    _escape_md(str(item.get("source_id") or "")),
                    _escape_md(digest_text),
                    record,
                ]
            )
        lines.extend(
            _table(
                (
                    "source_association_id",
                    "version",
                    "record_status",
                    "source_id",
                    "source_digest_sha256s",
                    "记录",
                ),
                rows,
            )
        )
    else:
        lines.append(_empty("版本"))
    lines.append("")
    lines.append("## 领域字段")
    counts = paper.get("concept_kind_counts") or {}
    if counts:
        crow = []
        headers = []
        for kind in sorted(counts, key=lambda item: item.encode("utf-8")):
            headers.append(kind)
            crow.append(_escape_md(str(counts[kind])))
        lines.extend(_table(headers, [crow]))
    else:
        lines.append(_empty("概念计数"))
    coverage = paper.get("capability_coverage") or {}
    if coverage:
        lines.append("")
        cap_rows = []
        for name in sorted(coverage, key=lambda item: item.encode("utf-8")):
            cell = coverage[name] if type(coverage[name]) is dict else {}
            cap_rows.append(
                [
                    _escape_md(name),
                    _escape_md(str(cell.get("present") or 0)),
                    _escape_md(str(cell.get("partial") or 0)),
                    _escape_md(str(cell.get("absent") or 0)),
                    _escape_md(str(cell.get("unverified") or 0)),
                ]
            )
        lines.extend(_table(("capability", "present", "partial", "absent", "unverified"), cap_rows))
    else:
        lines.append(_empty("能力覆盖"))
    concepts = paper.get("concepts") or []
    if concepts:
        lines.append("")
        crows = []
        for item in concepts:
            key = item.get("term_key") or ""
            kinds = item.get("concept_kinds") or []
            tax = item.get("taxonomy_ref")
            tax_text = ""
            if type(tax) is dict:
                tax_text = str(tax.get("axis") or "") + "/" + str(tax.get("slug") or "")
            elif type(tax) is str:
                tax_text = tax
            crows.append(
                [
                    _concept_index_link(relative, key),
                    _escape_md(_join([str(k) for k in kinds])),
                    _escape_md(str(item.get("term_status") or "")),
                    _escape_md(tax_text),
                    _escape_md(str(item.get("mention_count") or 0)),
                ]
            )
        lines.extend(_table(("term_key", "concept_kinds", "term_status", "taxonomy_ref", "mention_count"), crows))
    else:
        lines.append(_empty("概念"))
    lines.append("")
    lines.append("## 断言覆盖")
    lines.append(
        "typed "
        + str(paper["typed_claim_count"])
        + " / untyped "
        + str(paper["untyped_claim_count"])
        + "；uncovered_kinds "
        + str(len(paper.get("uncovered_kinds") or []))
        + "。"
    )
    claim_rows = paper.get("claims") or []
    if claim_rows:
        brows = []
        for item in claim_rows:
            kinds = item.get("claim_kinds") or []
            brows.append(
                [
                    _escape_md(str(item.get("claim_id") or "")),
                    _escape_md(_join([str(k) for k in kinds])),
                    _escape_md("" if item.get("current_assessment") is None else str(item.get("current_assessment"))),
                    _escape_md(str(item.get("ledger_status") or "")),
                    _escape_md(str(item.get("head_bound") or 0)),
                    _escape_md(str(item.get("stale") or 0)),
                    _file_link(relative, model, "wiki/meta/ledgers/claim-ledger.json", "台账") or _escape_md("台账缺失"),
                ]
            )
        lines.extend(
            _table(
                (
                    "claim_id",
                    "claim_kinds",
                    "current_assessment",
                    "ledger_status",
                    "head_bound",
                    "stale",
                    "记录",
                ),
                brows,
            )
        )
    else:
        lines.append(_empty("断言"))
    lines.append("")
    lines.append("## 代码谱系")
    lineages = paper.get("lineages") or []
    if lineages:
        lrows = []
        for item in lineages:
            gaps = item.get("gaps") or []
            freshness = item.get("claim_freshness") or {}
            lrows.append(
                [
                    _escape_md(str(item.get("lineage_id") or "")),
                    _escape_md(str(item.get("repository") or "")),
                    _escape_md(str(item.get("commit") or "")),
                    _escape_md(str(item.get("relation_kind") or "")),
                    _escape_md("" if item.get("reviewed_officiality") is None else str(item.get("reviewed_officiality"))),
                    _escape_md(str(item.get("relation_status") or "")),
                    _escape_md(str(freshness.get("head_bound") or 0) + "/" + str(freshness.get("stale") or 0)),
                    _escape_md(str(item.get("evidence_freshness") or "")),
                    _escape_md(str(len(gaps) if type(gaps) is list else 0)),
                    _escape_md(str(item.get("version_status") or "")),
                ]
            )
        lines.extend(
            _table(
                (
                    "lineage_id",
                    "repository",
                    "commit",
                    "relation_kind",
                    "reviewed_officiality",
                    "relation_status",
                    "claim_freshness",
                    "evidence_freshness",
                    "gaps",
                    "version_status",
                ),
                lrows,
            )
        )
    else:
        lines.append(_empty("代码谱系"))
    conflicts = paper.get("conflicts") or []
    if conflicts:
        lines.append("")
        crows = []
        for item in conflicts:
            crows.append(
                [
                    _escape_md(str(item.get("kind") or "")),
                    _escape_md(_join(item.get("repositories") or [])),
                    _escape_md(_join(item.get("lineage_ids") or [])),
                    _escape_md(str(item.get("detail") or "")),
                ]
            )
        lines.extend(_table(("kind", "repositories", "lineage_ids", "detail"), crows))
    lines.append("")
    lines.append("## 实验条件")
    matrix_rows = paper.get("matrix_rows") or []
    cells = (model.get("matrix") or {}).get("cells") or []
    by_row = {}
    for cell in cells:
        if type(cell) is dict:
            by_row.setdefault(cell.get("row_index"), {})[cell.get("column")] = cell
    if matrix_rows:
        headers = ["setting_key", "version", "row_status", "association_status"] + list(COLUMNS) + ["记录"]
        erows = []
        for row in matrix_rows:
            found = by_row.get(row.get("row_index"), {})
            rec = row.get("record_id") or ""
            cid = row.get("condition_id") or ""
            target = "wiki/meta/experiments/records/" + cid + "/" + rec + ".json" if cid and rec else None
            href = _file_link(relative, model, target, "记录") if target else None
            values = [
                _escape_md(str(row.get("setting_key") or "")),
                _escape_md(_version_label(row.get("version"))),
                _escape_md(str(row.get("row_status") or "")),
                _escape_md(str(row.get("association_status") or "")),
            ]
            for col in COLUMNS:
                values.append(_cell_text(found.get(col) or {"status": "unknown"}))
            values.append(href if href else _escape_md("无" if not target else "记录文件缺失"))
            erows.append(values)
        lines.extend(_table(headers, erows))
    else:
        lines.append(_empty("实验条件"))
    lines.append("")
    lines.append("## 相关文章")
    related = paper.get("related_articles") or []
    if related:
        arows = []
        for item in related:
            aid = item["article_id"]
            arows.append(
                [
                    _article_link(relative, aid, item.get("title") or aid),
                    _escape_md(item.get("head_revision_id") or ""),
                    _escape_md(_bool(item.get("complete"))),
                    _escape_md(str(item.get("check_status") or "")),
                ]
            )
        lines.extend(_table(("文章", "head_revision_id", "complete", "check_status"), arows))
    else:
        lines.append(_empty("相关文章"))
    lines.append("")
    lines.append("## 证据链接")
    sources = paper.get("sources") or []
    if sources:
        for source in sources:
            kind = source["record_kind"]
            rid = source["record_id"]
            target = _record_target(kind, rid, model)
            linked = _file_link(relative, model, target, kind + " / " + rid) if target else None
            lines.append("- " + (linked if linked is not None else _escape_md(kind + " / " + rid + "（记录文件缺失）")))
    else:
        lines.append(_empty("证据链接"))
    return _page(relative, model, lines, title=pid, page_type="reading-paper")


def render_matrix(model):
    matrix = model["matrix"]
    lines = [
        "# 实验条件比较矩阵",
        "> 本页只列条件与指标，不做优劣排序；可比性判定见 pairs.md。",
        "",
    ]
    rows = list(matrix.get("rows") or [])
    cells = matrix.get("cells") or []
    by_row = {}
    for cell in cells:
        if type(cell) is dict:
            by_row.setdefault(cell.get("row_index"), {})[cell.get("column")] = cell
    headers = ["论文", "设置", "版本"] + list(COLUMNS)
    if rows:
        table = []
        for row in rows:
            found = by_row.get(row.get("row_index"), {})
            values = [
                _escape_md(str(row.get("paper_id") or "")),
                _escape_md(str(row.get("setting_key") or "")),
                _escape_md(_version_label(row.get("version"))),
            ]
            for col in COLUMNS:
                values.append(_cell_text(found.get(col) or {"status": "unknown"}))
            table.append(values)
        lines.extend(_table(headers, table))
    else:
        lines.append(_empty("实验条件"))
    lines.append("")
    metric_columns = list(matrix.get("metric_columns") or [])
    metric_cells = list(matrix.get("metric_cells") or [])
    if metric_columns:
        mheaders = ["论文", "设置"] + [item["name"] + " (" + item["unit"] + ")" for item in metric_columns]
        found = {}
        for cell in metric_cells:
            found.setdefault(cell.get("row_index"), {})[(cell.get("name"), cell.get("unit"))] = cell
        mrows = []
        for row in rows:
            values = [
                _escape_md(str(row.get("paper_id") or "")),
                _escape_md(str(row.get("setting_key") or "")),
            ]
            slot = found.get(row.get("row_index"), {})
            for col in metric_columns:
                cell = slot.get((col["name"], col["unit"]))
                if cell is None:
                    values.append("")
                    continue
                mark = _metric_mark(cell)
                values.append(_escape_md(_clip(str(cell.get("value")))) + mark)
            mrows.append(values)
        lines.extend(_table(mheaders, mrows))
    else:
        lines.append(_empty("指标"))
    return _page("compare/matrix.md", model, lines, title="实验条件比较矩阵", page_type="reading-matrix")


def render_pairs(model):
    lines = [
        "# 逐对可比性",
        "> verdict / 差异 / 矛盾候选均为 D2 记录原样，不构成科学结论。",
        "",
    ]
    pairs = list((model.get("matrix") or {}).get("pairwise") or [])
    if not pairs:
        lines.append(_empty("逐对"))
        return _page("compare/pairs.md", model, lines, title="逐对可比性", page_type="reading-pairs")
    headers = (
        "左 (论文 / 设置)",
        "右 (论文 / 设置)",
        "same_paper",
        "verdict",
        "ranking",
        "incomparable_reasons",
        "condition_differences",
        "shared_metrics",
        "contradiction_candidates",
        "scientific_conclusion_contradiction",
    )
    rows = []
    for item in pairs:
        left = item.get("left") or {}
        right = item.get("right") or {}
        diffs = item.get("condition_differences") or []
        keys = []
        for diff in diffs[:3]:
            pointer = diff.get("field_pointer") if type(diff) is dict else ""
            name = str(pointer).rsplit("/", 1)[-1] if pointer else ""
            if name:
                keys.append(name)
        shared = item.get("shared_metrics") or []
        cands = item.get("contradiction_candidates") or []
        reasons = item.get("incomparable_reasons") or []
        rows.append(
            [
                _escape_md(str(left.get("paper_id") or "") + " / " + str(left.get("setting_key") or "")),
                _escape_md(str(right.get("paper_id") or "") + " / " + str(right.get("setting_key") or "")),
                _escape_md(_bool(item.get("same_paper"))),
                _escape_md(str(item.get("verdict") or "")),
                _escape_md(str(item.get("ranking") or "")),
                _escape_md(_join([str(r) for r in reasons])),
                _escape_md(str(len(diffs)) + ((" " + _join(keys)) if keys else "")),
                _escape_md(str(len(shared))),
                _escape_md(str(len(cands))),
                _escape_md(_bool(item.get("scientific_conclusion_contradiction"))),
            ]
        )
    lines.extend(_table(headers, rows))
    return _page("compare/pairs.md", model, lines, title="逐对可比性", page_type="reading-pairs")


def render_articles_index(model):
    lines = [
        "# 综述文章",
        '> 文章均为模型建议草稿、未发布（publication: unpublished）；"位置 staged" 表示尚在 .work 暂存、未进入 Vault。',
    ]
    if model.get("articles_batch") is None:
        lines.append("> 未指定 --articles-batch，仅显示 Vault 中的文章。")
    lines.append("")
    articles = model.get("articles") or []
    if not articles:
        lines.append(_empty("文章"))
        return _page("articles/list.md", model, lines, title="综述文章", page_type="reading-articles")
    headers = (
        "文章",
        "问题",
        "论文",
        "头修订",
        "修订数",
        "位置",
        "kind",
        "进度",
        "complete",
        "check_status",
        "记录",
    )
    rows = []
    for item in articles:
        aid = item["article_id"]
        papers = [_paper_identity("articles/list.md", model, pid) for pid in (item.get("paper_ids") or [])]
        target = _article_record_target(model, item)
        linked = _file_link("articles/list.md", model, target, "记录") if target else None
        record = linked if linked is not None else _escape_md("记录尚未进入 Vault" if item.get("head_location") == "staged" else "记录文件缺失")
        rows.append(
            [
                _article_link("articles/list.md", aid, item.get("title") or aid),
                _escape_md(item.get("question") or ""),
                "<br>".join(papers) if papers else _escape_md("无"),
                _escape_md(item.get("head_revision_id") or ""),
                _escape_md(
                    str(item.get("vault_revision_count") or 0)
                    + " / "
                    + str(item.get("staged_revision_count") or 0)
                ),
                _escape_md(str(item.get("head_location") or "")),
                _escape_md(str(item.get("kind") or "")),
                _escape_md(_progress(item.get("progress"))),
                _escape_md(_bool(item.get("complete"))),
                _escape_md(str(item.get("check_status") or "")),
                record,
            ]
        )
    lines.extend(_table(headers, rows))
    return _page("articles/list.md", model, lines, title="综述文章", page_type="reading-articles")


def render_article(model, article):
    aid = article["article_id"]
    relative = "articles/" + aid + ".md"
    papers = [_paper_identity(relative, model, pid) for pid in (article.get("paper_ids") or [])]
    body = article.get("render_bytes") or b""
    digest = article.get("render_sha256") or ""
    title = article.get("title") or aid
    lines = [
        "# " + _escape_md(title),
        "",
        "## 阅读导航",
        "",
        "- 问题：" + _escape_md(article.get("question") or ""),
        "- 论文：" + (" ".join(papers) if papers else _escape_md("无")),
        "- head_revision_id：" + _escape_md(article.get("head_revision_id") or ""),
        "- head_location：" + _escape_md(str(article.get("head_location") or "")),
        "- check_status：" + _escape_md(str(article.get("check_status") or "")),
        "- 受影响段落：" + _escape_md(_join(article.get("affected_sections") or []) or "无"),
        "- markdown_path：" + _escape_md(article.get("render_path") or ""),
        "- markdown_sha256：" + _escape_md(digest),
        "- complete：" + _escape_md(_bool(article.get("complete"))),
        "",
        "## 修订链",
        "",
    ]
    revisions = article.get("revisions") or []
    if revisions:
        rrows = []
        for item in revisions:
            rrows.append(
                [
                    _escape_md(str(item.get("revision_id") or "")),
                    _escape_md("" if item.get("previous_revision_id") is None else str(item.get("previous_revision_id"))),
                    _escape_md(str(item.get("kind") or "")),
                    _escape_md("" if item.get("target_section_id") is None else str(item.get("target_section_id"))),
                    _escape_md(str(item.get("recorded_at") or "")),
                    _escape_md(str(item.get("recorded_by") or "")),
                    _escape_md(str(item.get("location") or "")),
                    _escape_md(_bool(item.get("superseded"))),
                    _escape_md(_progress(item.get("progress"))),
                ]
            )
        lines.extend(
            _table(
                (
                    "revision_id",
                    "previous_revision_id",
                    "kind",
                    "target_section_id",
                    "recorded_at",
                    "recorded_by",
                    "location",
                    "superseded",
                    "progress",
                ),
                rrows,
            )
        )
    else:
        lines.append(_empty("修订"))
    lines.append("")
    lines.append("正文（S1-R1 render 逐字节，sha256 " + _short(digest) + "）。")
    prefix = _page(relative, model, lines, title=title, page_type="reading-article")
    if body:
        merged = prefix.rstrip(b"\n") + b"\n\n" + body
    else:
        merged = prefix.rstrip(b"\n") + "\n\n暂无正文记录。\n".encode("utf-8")
    return _one_lf(merged.decode("utf-8")).encode("utf-8")


def render_all(model):
    pages = {
        "index.md": render_index(model),
        "legend.md": render_legend(model),
        "concepts.md": render_concepts(model),
        "compare/matrix.md": render_matrix(model),
        "compare/pairs.md": render_pairs(model),
        "articles/list.md": render_articles_index(model),
    }
    for paper in model.get("papers") or []:
        pages["papers/" + paper["slug"] + "-reading.md"] = render_paper(model, paper)
    for article in model.get("articles") or []:
        pages["articles/" + article["article_id"] + ".md"] = render_article(model, article)
    return pages
