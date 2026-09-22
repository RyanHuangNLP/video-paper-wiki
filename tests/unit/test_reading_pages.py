from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from tests.unit.test_article_revision import _import_outline, _write_json
from tests.unit.test_domain_proposal import make_world
from tests.unit.test_graph_projection import _three_chain
from tests.unit.test_reading_view import _import_full
from video_paper_wiki.article_revision import render_article_revision
from video_paper_wiki.identity import paper_page_slug, repo_page_slug
from video_paper_wiki.reading.pages import _escape_md
from video_paper_wiki.reading.view import build_reading_views
from video_paper_wiki.secure_io import read_regular_file
from video_paper_wiki.staging import resolve_checkout_root


SECTION_HEADINGS = (
    "既有页面",
    "版本",
    "领域字段",
    "断言覆盖",
    "代码谱系",
    "实验条件",
    "相关文章",
    "证据链接",
)
WIKI = re.compile(r"\[\[([^\]]+)\]\]")
MD_LINK = re.compile(r"\]\(([^)]+)\)")
EXISTING = (
    re.compile(r"^\.\./papers/[^#]+$"),
    re.compile(r"^\.\./code/[^#]+$"),
    re.compile(r"^\.\./concepts/[^/#]+$"),
)


@pytest.fixture
def world(tmp_path, monkeypatch):
    return make_world(tmp_path, monkeypatch)


def _build(world, batch="pg1", **kwargs):
    return build_reading_views(
        vault_root=str(world["vault"]),
        batch_id=batch,
        **kwargs,
    )


def _root(world, batch):
    return world["checkout"] / ".work" / batch / "reading"


def _pages(world, batch):
    root = _root(world, batch)
    out = {}
    for path in root.rglob("*"):
        if path.is_file() and path.suffix == ".md":
            out[path.relative_to(root).as_posix()] = path.read_bytes()
    return out


def _frontmatter_ok(raw):
    assert raw.startswith(b"---\ngenerated_by: video-paper-wiki.reading.v1\n")
    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\n\n")
    assert b"\r" not in raw
    text = raw.decode("utf-8")
    keys = []
    for line in text.splitlines()[1:]:
        if line == "---":
            break
        keys.append(line.split(":", 1)[0])
    assert keys == [
        "generated_by",
        "title",
        "type",
        "status",
        "created",
        "updated",
        "tags",
        "generated",
        "companion_note",
        "install_path",
        "publication",
        "ranking",
        "basis_sha256",
        "graph_sha256",
    ]
    assert "created: 2026-09-08\n" in text
    assert "updated: 2026-09-08\n" in text
    assert "status: generated\n" in text


def _is_existing(target):
    return any(item.match(target) for item in EXISTING)


def _resolve(vault: Path, page_rel: str, target: str):
    page_dir = vault / "wiki" / "reading" / Path(page_rel).parent
    if target.startswith("../") or target.startswith("./"):
        return (page_dir / target)
    if "/" in target or target.endswith(".md") or target.endswith(".json"):
        if target.startswith("../../") or target.startswith("../"):
            return page_dir / target
        return vault / "wiki" / "reading" / target
    return vault / "wiki" / "reading" / (target + ".md")


def test_pages_frontmatter_tables_links_and_escape(world):
    _three_chain(world)
    data = _build(world, "pg1")
    pages = _pages(world, "pg1")
    assert "index.md" in pages
    assert "legend.md" in pages
    assert "concepts.md" in pages
    assert "compare/matrix.md" in pages
    assert "compare/pairs.md" in pages
    assert "articles/list.md" in pages
    assert "articles/index.md" not in pages
    stems = [Path(path).stem for path in pages]
    assert len(stems) == len(set(stems))
    paper_pages = sorted(path for path in pages if path.startswith("papers/"))
    assert len(paper_pages) == data["counts"]["papers"] == 2
    for raw in pages.values():
        _frontmatter_ok(raw)
    index = pages["index.md"].decode("utf-8")
    assert index.count("|") >= data["counts"]["papers"]
    rows = [line for line in index.splitlines() if "[详情](papers/" in line]
    assert len(rows) == data["counts"]["papers"]
    for paper in data["pages"]:
        if not paper["path"].startswith("papers/"):
            continue
        slug = paper["path"][len("papers/") : -len("-reading.md")]
        assert "正式论文页尚未安装" in index
        assert "[详情](papers/" + slug + "-reading.md)" in index
        assert "[[../papers/" not in index
    first_slug = paper_pages[0][len("papers/") : -len("-reading.md")]
    paper = pages[paper_pages[0]].decode("utf-8")
    headings = [line[3:] for line in paper.splitlines() if line.startswith("## ")]
    assert headings[:8] == list(SECTION_HEADINGS)
    version_lines = []
    capture = False
    for line in paper.splitlines():
        if line == "## 版本":
            capture = True
            continue
        if capture and line.startswith("## "):
            break
        if capture and line.startswith("| sva-"):
            version_lines.append(line)
    from video_paper_wiki.domain_versions import build_domain_source_version_view
    from video_paper_wiki.identity import paper_page_slug as slug_of

    versions = build_domain_source_version_view(vault_root=str(world["vault"]))
    pid = None
    for node_id in (
        "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    ):
        if slug_of(node_id) == first_slug:
            pid = node_id
            break
    assert pid is not None
    expected_versions = [
        item for item in versions["versions"] if pid in item.get("paper_ids", [])
    ]
    if not expected_versions:
        paper_row = next((item for item in versions["papers"] if item["paper_id"] == pid), None)
        expected_versions = list((paper_row or {}).get("versions") or [])
    assert len(version_lines) == len(expected_versions)
    combined_papers = "".join(pages[path].decode("utf-8") for path in paper_pages)
    assert "official" in combined_papers
    assert "reviewed_accepted" in combined_papers or "reviewed\\_accepted" in combined_papers
    from video_paper_wiki.experiment_matrix import build_experiment_comparison_matrix

    matrix_doc = build_experiment_comparison_matrix(vault_root=str(world["vault"]))
    exp_lines = []
    capture = False
    for line in paper.splitlines():
        if line == "## 实验条件":
            capture = True
            continue
        if capture and line.startswith("## "):
            break
        if capture and line.startswith("| ") and "---" not in line and "meta/experiments/records/" in line:
            exp_lines.append(line)
    expected_rows = [row for row in matrix_doc["rows"] if row["paper_id"] == pid]
    assert len(exp_lines) == len(expected_rows)
    matrix = pages["compare/matrix.md"].decode("utf-8")
    cond_rows = [
        line
        for line in matrix.splitlines()
        if line.startswith("| sha256:") and line.count("|") == 13
    ]
    assert len(cond_rows) == 3
    assert "不适用" in matrix
    assert "未知" in matrix
    if any(col["name"] == "fvd" for col in matrix_doc["metric_columns"]):
        assert "fvd" in matrix
    if any(cell.get("higher_is_better") is False for cell in matrix_doc["metric_cells"]):
        assert "↓" in matrix
    if any(cell.get("higher_is_better") is True for cell in matrix_doc["metric_cells"]):
        assert "↑" in matrix
    if all(cell.get("higher_is_better") is None for cell in matrix_doc["metric_cells"]):
        assert "↑" not in matrix
        assert "↓" not in matrix
    pairs = pages["compare/pairs.md"].decode("utf-8")
    pair_rows = [
        line
        for line in pairs.splitlines()
        if line.startswith("| sha256:")
    ]
    assert len(pair_rows) == len(matrix_doc["pairwise"])
    for banned in ("更优", "更差", "胜出", "排名第"):
        assert banned not in pairs
    concepts = pages["concepts.md"].decode("utf-8")
    from video_paper_wiki.domain_structure import build_domain_structure_view

    structure = build_domain_structure_view(vault_root=str(world["vault"]))
    for item in structure["concepts"]:
        key = item["term_key"]
        assert concepts.count("#### " + key) == 1
        tax = item.get("taxonomy_ref")
        if tax:
            axis = tax["axis"]
            slug = tax["slug"]
            assert "正式概念页尚未安装：" + axis.replace("/", "-") + "-" + slug in concepts
    legend = pages["legend.md"].decode("utf-8")
    for key in (
        "domain_store_inventory_sha256",
        "claim_ledger_sha256",
        "assessment_heads_sha256",
        "experiment_store_inventory_sha256",
    ):
        assert data["basis"][key] in legend
    assert data["graph_sha256"] in legend
    assert "未 apply" in legend
    assert "未发布" in legend
    assert "不排优劣" in legend
    sample = "a|b[c]d`e#f*g_h<i>j\\k"
    expected = (
        sample.replace("\\", "\\\\")
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
    assert _escape_md(sample) == expected
    outline = _import_outline(world, batch="esc")
    rec = outline["record"]
    special = "T|itle[x]"
    rec_title = special
    ctx = world["checkout"] / "ctx-esc.json"
    from tests.unit.test_article_revision import _export

    exported = _export(world)
    _write_json(ctx, {"ok": True, "command": "articles.export", "data": exported})
    from video_paper_wiki.article_revision import import_article_revision

    doc = {
        "schema": "video-paper-wiki.article-document.v1",
        "title": rec_title,
        "sections": rec["sections"],
    }
    path = world["checkout"] / "doc-esc.json"
    _write_json(path, doc)
    imported = import_article_revision(
        vault_root=str(world["vault"]),
        batch_id="esc",
        context=str(ctx),
        document=str(path),
        recorded_by="t",
        recorded_at="2026-09-15T03:00:00Z",
        previous_revision_id=rec["revision_id"],
    )
    rendered = render_article_revision(
        vault_root=str(world["vault"]),
        batch_id="esc",
        article_id=imported["record"]["article_id"],
        revision_id=imported["record"]["revision_id"],
    )
    body = read_regular_file(
        resolve_checkout_root() / rendered["markdown_path"],
        missing_code="READING_RENDER_MISSING",
        unsafe_code="WORK_PATH_UNSAFE",
    )
    first = body.decode("utf-8").splitlines()[0]
    assert first == "# " + _escape_md(rec_title)
    dest = world["vault"] / "wiki" / "reading"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(_root(world, "pg1"), dest)
    total = 0
    skipped = 0
    for rel, raw in pages.items():
        text = raw.decode("utf-8")
        for match in WIKI.finditer(text):
            raw_target = match.group(1)
            target = raw_target.split("|", 1)[0].split("#", 1)[0]
            total += 1
            if _is_existing(target):
                skipped += 1
                continue
            path = _resolve(world["vault"], rel, target)
            candidates = [path, Path(str(path) + ".md")]
            assert any(item.exists() for item in candidates), (rel, target, path)
        if rel.endswith(".md"):
            for match in WIKI.finditer(text):
                raw_target = match.group(1)
                if "#" in raw_target.split("|", 1)[0]:
                    anchor = raw_target.split("|", 1)[0].split("#", 1)[1]
                    if "concepts" in raw_target.split("|", 1)[0] or rel == "concepts.md":
                        assert ("#### " + anchor) in pages["concepts.md"].decode("utf-8")
        for match in MD_LINK.finditer(text):
            href = match.group(1).split("#", 1)[0]
            if not href or href.startswith("wiki/reading-notes/"):
                skipped += 1
                continue
            total += 1
            assert not href.endswith("/"), (rel, href)
            path = _resolve(world["vault"], rel, href)
            assert path.is_file(), (rel, href, path)
    assert total > 0
    assert skipped >= 0
    _import_full(world, "w-pages")
    again = _build(world, "pg2", articles_batch="w-pages")
    art_pages = [row for row in again["pages"] if row["path"].startswith("articles/") and row["path"] != "articles/list.md"]
    assert art_pages
    art = (_root(world, "pg2") / art_pages[0]["path"]).read_text(encoding="utf-8")
    assert "## 正文" not in art
    assert "正文（S1-R1 render 逐字节，sha256 " in art
    assert "\n\n# " in art or "暂无正文记录。" in art
    from video_paper_wiki.domain_relations import build_domain_relation_view
    from video_paper_wiki.identity import IdentityError

    relations = build_domain_relation_view(vault_root=str(world["vault"]))
    if relations["lineages"]:
        repo = relations["lineages"][0]["repository"]
        combined = pages[paper_pages[0]].decode("utf-8") + pages[paper_pages[1]].decode("utf-8")
        try:
            slug = repo_page_slug(repo)
        except IdentityError:
            assert repo in combined
        else:
            assert "正式代码页尚未安装" in combined


def test_formal_paper_page_coexists_with_reading_detail(world):
    _three_chain(world)
    pid = world["association"]["paper_id"]
    slug = paper_page_slug(pid)
    formal = world["vault"] / "wiki" / "papers" / (slug + ".md")
    formal.parent.mkdir(parents=True, exist_ok=True)
    formal.write_text(
        "---\ntitle: Formal\ntype: paper\nstatus: active\ncreated: 2026-09-08\nupdated: 2026-09-08\ntags: [paper]\n---\n\n# Formal\n\n共存正文。\n",
        encoding="utf-8",
    )
    formal.chmod(0o600)
    _build(world, "coexist")
    pages = _pages(world, "coexist")
    reading = "papers/" + slug + "-reading.md"
    assert reading in pages
    text = pages[reading].decode("utf-8")
    assert "../../papers/" + slug + ".md" in text
    assert "正式论文页尚未安装" not in text
    assert Path(reading).stem != formal.stem
