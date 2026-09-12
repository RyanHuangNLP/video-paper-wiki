from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.light_index import (
    INDEX_FILENAME,
    INDEX_DIRNAME,
    INDEX_STALE,
    NO_RESULTS,
    OK,
    build_index,
    search,
)
from video_paper_wiki_research.light_pdf import extract_pdf
from tests.research.test_light_pipeline import _pdf_with_page_texts

EVIDENCE_FIELDS = (
    "chunk_id",
    "paper_id",
    "title",
    "source_sha256",
    "page",
    "markdown_path",
    "markdown_sha256",
    "text_start",
    "text_end",
    "text_sha256",
    "text",
    "score",
)
SHA_A = "a" * 64
SHA_B = "b" * 64
CHINESE_BODY = "混合线性注意力用于视频生成，在长序列上保持效率。"
HEAD = "HEADTOKEN"
TAIL = "TAILTOKEN"


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_paper(workspace: Path, digest: str, title: str, bodies: list[str]) -> Path:
    directory = workspace / "papers" / digest
    directory.mkdir(parents=True)
    markdown = ""
    pages = []
    for index, body in enumerate(bodies, start=1):
        markdown += f'<a id="page-{index}"></a>\n\n## PDF 第 {index} 页\n\n'
        start = len(markdown)
        markdown += body
        end = len(markdown)
        pages.append(
            {
                "page": index,
                "anchor": f"page-{index}",
                "text_start": start,
                "text_end": end,
                "text_sha256": _sha_text(body),
            }
        )
        markdown += "\n\n"
    md_path = directory / "source.md"
    md_path.write_text(markdown, encoding="utf-8")
    meta = {
        "schema": "video-paper-wiki.light-paper.v1",
        "paper_id": "sha256:" + digest,
        "title": title,
        "source": {"path": f"/absolute/{digest}.pdf", "sha256": digest, "size_bytes": 12},
        "parser": {"engine": "pypdf-native-text", "version": "6.16.2"},
        "page_count": len(bodies),
        "document": {
            "path": f"papers/{digest}/source.md",
            "sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        },
        "pages": pages,
        "warnings": [],
    }
    (directory / "source.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return md_path


def _assert_evidence(item: dict, markdown: str) -> None:
    assert set(EVIDENCE_FIELDS) <= set(item)
    start = item["text_start"]
    end = item["text_end"]
    slice_text = markdown[start:end]
    assert item["text"] == slice_text
    assert item["text_sha256"] == _sha_text(slice_text)
    assert type(item["page"]) is int and item["page"] >= 1
    assert math.isfinite(item["score"]) and item["score"] > 0
    assert item["chunk_id"].startswith("chk-")
    assert item["markdown_path"].startswith("papers/")


def test_ranking_filter_and_stable_order(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_paper(
        workspace,
        SHA_A,
        "Alpha paper",
        ["transformer video uniquealpha uniquealpha uniquealpha sharedterm"],
    )
    _write_paper(
        workspace,
        SHA_B,
        "Beta paper",
        ["transformer video uniquebeta sharedterm"],
    )
    built = build_index(workspace)
    assert built["ok"] is True
    assert built["status"] == OK
    assert built["paper_count"] == 2
    print("INDEX_BYTES", built["size_bytes"])
    ranked = search(workspace, "transformer uniquealpha")
    assert ranked["ok"] is True
    assert ranked["status"] == OK
    assert ranked["index_id"] == built["index_id"]
    assert ranked["query"] == "transformer uniquealpha"
    assert [item["paper_id"] for item in ranked["evidence"]][0] == "sha256:" + SHA_A
    md_a = (workspace / "papers" / SHA_A / "source.md").read_text(encoding="utf-8")
    _assert_evidence(ranked["evidence"][0], md_a)
    filtered = search(workspace, "transformer", paper_ids=["sha256:" + SHA_B])
    assert filtered["ok"] is True
    assert {item["paper_id"] for item in filtered["evidence"]} == {"sha256:" + SHA_B}
    first = search(workspace, "sharedterm")
    second = search(workspace, "sharedterm")
    assert [item["chunk_id"] for item in first["evidence"]] == [item["chunk_id"] for item in second["evidence"]]
    assert [item["score"] for item in first["evidence"]] == [item["score"] for item in second["evidence"]]


def test_long_page_splits_same_page_chunks(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    body = HEAD + " " + ("blocktext " * 450) + " " + TAIL
    assert len(body) > 4000
    md_path = _write_paper(workspace, SHA_A, "Long page", [body])
    markdown = md_path.read_text(encoding="utf-8")
    built = build_index(workspace)
    assert built["chunk_count"] >= 2
    head_hit = search(workspace, HEAD)
    tail_hit = search(workspace, TAIL)
    assert head_hit["ok"] is True and tail_hit["ok"] is True
    head_item = head_hit["evidence"][0]
    tail_item = tail_hit["evidence"][0]
    _assert_evidence(head_item, markdown)
    _assert_evidence(tail_item, markdown)
    assert head_item["page"] == tail_item["page"] == 1
    assert head_item["chunk_id"] != tail_item["chunk_id"]
    assert head_item["text_start"] < tail_item["text_start"]
    assert HEAD in head_item["text"] and TAIL not in head_item["text"]
    assert TAIL in tail_item["text"]


def test_chinese_query_retrieves_chinese_page(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    md_path = _write_paper(workspace, SHA_A, "中文论文", [CHINESE_BODY])
    markdown = md_path.read_text(encoding="utf-8")
    build_index(workspace)
    result = search(workspace, "线性注意力")
    assert result["ok"] is True
    assert result["status"] == OK
    item = result["evidence"][0]
    _assert_evidence(item, markdown)
    assert "线性注意力" in item["text"]
    assert item["page"] == 1


def test_empty_query_and_no_match_are_no_results(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_paper(workspace, SHA_A, "Only paper", ["visible lexical content about diffusion"])
    build_index(workspace)
    missing = search(workspace, "zzzznotpresenttoken")
    assert missing["ok"] is False
    assert missing["status"] == NO_RESULTS
    assert missing["evidence"] == []
    blank = search(workspace, "   ")
    assert blank["ok"] is False
    assert blank["status"] == NO_RESULTS
    assert blank["evidence"] == []


def test_markdown_change_and_paper_set_change_are_stale(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    md_path = _write_paper(workspace, SHA_A, "Fresh paper", ["stable uniquebody token"])
    build_index(workspace)
    ok = search(workspace, "uniquebody")
    assert ok["status"] == OK
    original = md_path.read_text(encoding="utf-8")
    md_path.write_text(original.replace("uniquebody", "mutatedbody"), encoding="utf-8")
    stale = search(workspace, "uniquebody")
    assert stale["ok"] is False
    assert stale["status"] == INDEX_STALE
    assert stale["evidence"] == []
    assert "mutatedbody" not in json.dumps(stale, ensure_ascii=False)
    md_path.write_text(original, encoding="utf-8")
    meta_path = workspace / "papers" / SHA_A / "source.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["document"]["sha256"] = hashlib.sha256(original.encode("utf-8")).hexdigest()
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    build_index(workspace)
    _write_paper(workspace, SHA_B, "Added paper", ["brand new extra paper token"])
    added = search(workspace, "uniquebody")
    assert added["ok"] is False
    assert added["status"] == INDEX_STALE
    assert added["evidence"] == []
    missing_index = search(tmp_path / "empty-ws", "uniquebody")
    assert missing_index["status"] == INDEX_STALE
    assert missing_index["evidence"] == []


def _two_page_workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    workspace = tmp_path / ".work" / "pages"
    workspace.mkdir(parents=True)
    pdf = tmp_path / "two.pdf"
    pdf.write_bytes(
        _pdf_with_page_texts(
            [
                "quasar describes the first PDF page only.",
                "nebula describes the second PDF page only.",
            ]
        )
    )
    extract_pdf(pdf, workspace, title="Two Page Fixture")
    paper = next((workspace / "papers").iterdir())
    return workspace, paper / "source.md", paper / "source.json"


def test_inpage_insert_and_delete_keep_page_assignment(tmp_path: Path) -> None:
    workspace, md_path, meta_path = _two_page_workspace(tmp_path)
    original_id = json.loads(meta_path.read_text(encoding="utf-8"))["paper_id"]
    original_sha = json.loads(meta_path.read_text(encoding="utf-8"))["source"]["sha256"]
    build_index(workspace)
    inserted = md_path.read_text(encoding="utf-8").replace("quasar describes", "quasar INSERT describes")
    md_path.write_text(inserted, encoding="utf-8")
    assert search(workspace, "quasar")["status"] == INDEX_STALE
    assert build_index(workspace)["ok"] is True
    markdown = md_path.read_text(encoding="utf-8")
    quasar = search(workspace, "quasar")
    nebula = search(workspace, "nebula")
    assert quasar["evidence"][0]["page"] == 1
    assert nebula["evidence"][0]["page"] == 2
    assert quasar["evidence"][0]["text"] == markdown[quasar["evidence"][0]["text_start"] : quasar["evidence"][0]["text_end"]]
    deleted = markdown.replace("quasar INSERT describes", "quasar describes")
    md_path.write_text(deleted, encoding="utf-8")
    assert search(workspace, "nebula")["status"] == INDEX_STALE
    assert build_index(workspace)["ok"] is True
    restored = md_path.read_text(encoding="utf-8")
    quasar = search(workspace, "quasar")
    nebula = search(workspace, "nebula")
    assert quasar["evidence"][0]["page"] == 1
    assert nebula["evidence"][0]["page"] == 2
    assert "INSERT" not in quasar["evidence"][0]["text"]
    assert quasar["evidence"][0]["text"] == restored[quasar["evidence"][0]["text_start"] : quasar["evidence"][0]["text_end"]]
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["paper_id"] == original_id
    assert meta["source"]["sha256"] == original_sha


def test_invalid_anchors_fail_without_rewriting_source_or_index(tmp_path: Path) -> None:
    workspace, md_path, meta_path = _two_page_workspace(tmp_path)
    build_index(workspace)
    original_md = md_path.read_text(encoding="utf-8")
    original_meta = meta_path.read_bytes()
    index_path = workspace / INDEX_DIRNAME / INDEX_FILENAME
    original_index = index_path.read_bytes()

    def _fail_edit(mutated: str) -> None:
        md_path.write_text(mutated, encoding="utf-8")
        assert search(workspace, "quasar")["status"] == INDEX_STALE
        try:
            build_index(workspace)
            raise AssertionError("build_index must fail")
        except ResearchError as exc:
            assert exc.code == "SOURCE_INVALID"
            assert "re-extract" in exc.message
        assert meta_path.read_bytes() == original_meta
        assert index_path.read_bytes() == original_index
        md_path.write_text(original_md, encoding="utf-8")

    _fail_edit(original_md.replace('<a id="page-2"></a>', ""))
    _fail_edit(original_md.replace('<a id="page-2"></a>', '<a id="page-1"></a>'))
    swapped = original_md.replace('<a id="page-1"></a>', '<a id="page-TMP"></a>')
    swapped = swapped.replace('<a id="page-2"></a>', '<a id="page-1"></a>')
    swapped = swapped.replace('<a id="page-TMP"></a>', '<a id="page-2"></a>')
    _fail_edit(swapped)


_PAGE_ANCHOR = re.compile(r'<a id="page-(\d+)"></a>')
R06_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "r06-legacy-workspace"


def _pages_from_markdown(markdown: str, page_count: int) -> list[dict]:
    matches = list(_PAGE_ANCHOR.finditer(markdown))
    numbers = [int(item.group(1)) for item in matches]
    assert numbers == list(range(1, page_count + 1))
    pages: list[dict] = []
    for index, match in enumerate(matches):
        page = numbers[index]
        heading = f"\n\n## PDF 第 {page} 页\n\n"
        assert markdown.startswith(heading, match.end())
        start = match.end() + len(heading)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        while end > start and markdown[end - 1] == "\n":
            end -= 1
        text = markdown[start:end]
        pages.append(
            {
                "page": page,
                "anchor": f"page-{page}",
                "text_start": start,
                "text_end": end,
                "text": text,
                "text_sha256": _sha_text(text),
            }
        )
    return pages


def _materialize_r06_legacy(workspace: Path) -> dict:
    provenance = json.loads((R06_FIXTURE_DIR / "provenance.json").read_text(encoding="utf-8"))
    for name, digest in provenance["fixture_files"].items():
        raw = (R06_FIXTURE_DIR / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest
        dest = workspace / provenance["materialize"][name]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    return provenance


def test_r06_legacy_misplaced_offsets_recover_from_current_markdown(tmp_path: Path) -> None:
    workspace = tmp_path / "r06-legacy"
    workspace.mkdir()
    provenance = _materialize_r06_legacy(workspace)
    paper_hex = provenance["original_pdf_sha256"]
    md_path = workspace / "papers" / paper_hex / "source.md"
    meta_path = workspace / "papers" / paper_hex / "source.json"
    index_path = workspace / INDEX_DIRNAME / INDEX_FILENAME
    markdown = md_path.read_text(encoding="utf-8")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    historical_pdf = Path(meta["source"]["path"])
    assert historical_pdf.as_posix().startswith("/private/tmp/vp.r06.fixture.")
    assert meta["document"]["sha256"] == hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    for item in meta["pages"]:
        slice_text = markdown[item["text_start"] : item["text_end"]]
        assert _sha_text(slice_text) == item["text_sha256"]
    expected = _pages_from_markdown(markdown, meta["page_count"])
    stored_ranges = [(item["text_start"], item["text_end"]) for item in meta["pages"]]
    located_ranges = [(item["text_start"], item["text_end"]) for item in expected]
    assert stored_ranges != located_ranges
    assert "quasar" in markdown[meta["pages"][1]["text_start"] : meta["pages"][1]["text_end"]]
    assert "nebula" in expected[1]["text"] and "quasar" in expected[0]["text"]
    md_before = md_path.read_bytes()
    meta_before = meta_path.read_bytes()
    index_before = index_path.read_bytes()

    quasar_before = search(workspace, "quasar")
    nebula_before = search(workspace, "nebula")
    print(
        "R06_BEFORE_REBUILD",
        quasar_before["status"],
        [item.get("page") for item in quasar_before.get("evidence") or []],
        nebula_before["status"],
        [item.get("page") for item in nebula_before.get("evidence") or []],
        flush=True,
    )
    assert md_path.read_bytes() == md_before
    assert meta_path.read_bytes() == meta_before
    assert index_path.read_bytes() == index_before
    assert quasar_before["status"] == INDEX_STALE
    assert nebula_before["status"] == INDEX_STALE
    assert quasar_before["ok"] is False
    assert nebula_before["ok"] is False
    assert quasar_before["evidence"] == []
    assert nebula_before["evidence"] == []

    built = build_index(workspace)
    assert built["ok"] is True
    assert built["status"] == OK
    assert md_path.read_bytes() == md_before
    markdown = md_path.read_text(encoding="utf-8")
    expected = _pages_from_markdown(markdown, 2)
    quasar = search(workspace, "quasar")
    nebula = search(workspace, "nebula")
    print(
        "R06_AFTER_REBUILD",
        quasar["status"],
        [item.get("page") for item in quasar.get("evidence") or []],
        nebula["status"],
        [item.get("page") for item in nebula.get("evidence") or []],
        flush=True,
    )
    for found, page, token in ((quasar, 1, "quasar"), (nebula, 2, "nebula")):
        assert found["ok"] is True
        assert found["status"] == OK
        item = found["evidence"][0]
        loc = expected[page - 1]
        assert item["page"] == page
        assert token in item["text"]
        assert item["text_start"] == loc["text_start"]
        assert item["text_end"] == loc["text_end"]
        assert item["text"] == loc["text"]
        assert item["text"] == markdown[item["text_start"] : item["text_end"]]
        assert item["text_sha256"] == loc["text_sha256"] == _sha_text(item["text"])
        assert "## PDF" not in item["text"]
        assert "<a id=" not in item["text"]
        assert markdown[loc["text_start"] - len(f"\n\n## PDF 第 {page} 页\n\n") : loc["text_start"]].endswith(
            f"## PDF 第 {page} 页\n\n"
        )
    refreshed = json.loads(meta_path.read_text(encoding="utf-8"))
    assert refreshed["paper_id"] == provenance["paper_id"]
    assert refreshed["source"]["sha256"] == paper_hex
    assert refreshed["document"]["sha256"] == hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    assert [(item["text_start"], item["text_end"], item["text_sha256"]) for item in refreshed["pages"]] == [
        (item["text_start"], item["text_end"], item["text_sha256"]) for item in expected
    ]

    index_after = index_path.read_bytes()
    meta_after = meta_path.read_bytes()
    second = build_index(workspace)
    assert second["ok"] is True
    assert second["index_id"] == built["index_id"]
    assert index_path.read_bytes() == index_after
    assert meta_path.read_bytes() == meta_after
    assert md_path.read_bytes() == md_before


def test_invalid_second_paper_does_not_rewrite_first_source_or_index(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_paper(workspace, SHA_A, "Alpha paper", ["alpha unique body token"])
    _write_paper(workspace, SHA_B, "Beta paper", ["beta unique body token"])
    built = build_index(workspace)
    assert built["ok"] is True
    meta_a = workspace / "papers" / SHA_A / "source.json"
    meta_b = workspace / "papers" / SHA_B / "source.json"
    md_b = workspace / "papers" / SHA_B / "source.md"
    index_path = workspace / INDEX_DIRNAME / INDEX_FILENAME
    original_a = meta_a.read_bytes()
    original_b = meta_b.read_bytes()
    original_index = index_path.read_bytes()
    md_b.write_text(md_b.read_text(encoding="utf-8").replace('<a id="page-1"></a>', ""), encoding="utf-8")
    assert search(workspace, "alpha")["status"] == INDEX_STALE
    try:
        build_index(workspace)
        raise AssertionError("build_index must fail when the second paper has invalid anchors")
    except ResearchError as exc:
        assert exc.code == "SOURCE_INVALID"
        assert "re-extract" in exc.message
    assert meta_a.read_bytes() == original_a
    assert meta_b.read_bytes() == original_b
    assert index_path.read_bytes() == original_index


def _load_stored_index(workspace: Path) -> dict:
    path = workspace / INDEX_DIRNAME / INDEX_FILENAME
    return json.loads(path.read_text(encoding="utf-8"))


def _write_stored_index(workspace: Path, payload: dict) -> None:
    path = workspace / INDEX_DIRNAME / INDEX_FILENAME
    path.write_bytes(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n")


def test_forged_or_damaged_index_is_stale_without_keyerror(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_paper(workspace, SHA_A, "Alpha paper", ["visible lexical content about diffusion"])
    built = build_index(workspace)
    assert built["ok"] is True
    first_id = built["index_id"]
    again = build_index(workspace)
    assert again["index_id"] == first_id
    stored = _load_stored_index(workspace)
    stored["chunks"][0]["text"] = "fabricated lexical content about diffusion"
    stored["chunks"][0]["text_sha256"] = _sha_text(stored["chunks"][0]["text"])
    _write_stored_index(workspace, stored)
    forged = search(workspace, "diffusion")
    assert forged["ok"] is False
    assert forged["status"] == INDEX_STALE
    assert forged["evidence"] == []
    stored = _load_stored_index(workspace)
    stored["df"] = {"diffusion": 99}
    _write_stored_index(workspace, stored)
    df_forged = search(workspace, "diffusion")
    assert df_forged["status"] == INDEX_STALE
    stored = _load_stored_index(workspace)
    stored["chunks"] = [1, {"chunk_id": "chk-bad"}]
    _write_stored_index(workspace, stored)
    damaged = search(workspace, "diffusion")
    assert damaged["status"] == INDEX_STALE
    assert damaged["evidence"] == []
    stored["chunks"] = [{"tf": "bad"}]
    _write_stored_index(workspace, stored)
    typed = search(workspace, "diffusion")
    assert typed["status"] == INDEX_STALE
    assert typed["evidence"] == []


def test_selection_filters_before_topk(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    _write_paper(workspace, SHA_A, "Alpha paper", ["sharedterm uniquealpha " * 20])
    _write_paper(workspace, SHA_B, "Beta paper", ["sharedterm uniquebeta"])
    build_index(workspace)
    limited = search(workspace, "sharedterm", top_k=1, paper_ids=["sha256:" + SHA_B])
    assert limited["ok"] is True
    assert len(limited["evidence"]) == 1
    assert limited["evidence"][0]["paper_id"] == "sha256:" + SHA_B
