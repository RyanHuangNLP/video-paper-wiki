"""One-off Terminal 1 self-check for R06 live-anchor interval recovery. Not a product test."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import traceback
from pathlib import Path

SRC = Path("/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r06-v1/terminal-1/src")
sys.path.insert(0, str(SRC))

from video_paper_wiki_research.contracts import ResearchError  # noqa: E402
from video_paper_wiki_research.light_index import (  # noqa: E402
    INDEX_DIRNAME,
    INDEX_FILENAME,
    INDEX_STALE,
    OK,
    _locate_pages,
    build_index,
    search,
)

FIX = Path(
    "/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/"
    "lightweight-r06-parallel-v1/legacy-workspace"
)
PAPER = "670c70b59a0fa748f4a3c123458d4928e8813f6358ae1f4403f0a01cbaa3e3bb"
SHA_A = "a" * 64
SHA_B = "b" * 64
OUT = Path(
    "/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/"
    "lightweight-r06-parallel-v1/terminal-1/evidence/legacy-fixed.json"
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_text(text: str) -> str:
    return _sha(text.encode("utf-8"))


def _materialize(dest: Path) -> Path:
    dest.mkdir(parents=True)
    paper = dest / "papers" / PAPER
    paper.mkdir(parents=True)
    shutil.copyfile(FIX / "source.md", paper / "source.md")
    shutil.copyfile(FIX / "source.json", paper / "source.json")
    (dest / INDEX_DIRNAME).mkdir()
    shutil.copyfile(FIX / "index.v1.json", dest / INDEX_DIRNAME / INDEX_FILENAME)
    return dest


def _assert(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def _hit_page(result: dict, word: str, page: int, markdown: str) -> dict:
    _assert(result["ok"] is True, f"{word} not ok: {result}")
    _assert(result["status"] == OK, f"{word} status {result['status']}")
    item = result["evidence"][0]
    _assert(item["page"] == page, f"{word} page {item['page']} != {page}")
    _assert(word in item["text"], f"{word} missing from text {item['text']!r}")
    slice_text = markdown[item["text_start"] : item["text_end"]]
    _assert(item["text"] == slice_text, f"{word} text != markdown slice")
    _assert(item["text_sha256"] == _sha_text(slice_text), f"{word} slice hash mismatch")
    _assert("## PDF" not in item["text"], f"{word} includes heading")
    _assert("<a id=" not in item["text"], f"{word} includes anchor")
    return item


def _write_paper(workspace: Path, digest: str, title: str, bodies: list[str]) -> tuple[Path, Path]:
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
            "sha256": _sha_text(markdown),
        },
        "pages": pages,
        "warnings": [],
    }
    meta_path = directory / "source.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return md_path, meta_path


def main() -> dict:
    record: dict = {"ok": False, "checks": []}
    ws = Path("/private/tmp/vp.r06.t1.fixed/workspace")
    shutil.rmtree(ws.parent, ignore_errors=True)
    _materialize(ws)
    paper = ws / "papers" / PAPER
    md_path = paper / "source.md"
    meta_path = paper / "source.json"
    index_path = ws / INDEX_DIRNAME / INDEX_FILENAME
    markdown = md_path.read_text(encoding="utf-8")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    located = _locate_pages(markdown, page_count=meta["page_count"])
    src_before = meta_path.read_bytes()
    idx_before = index_path.read_bytes()
    md_before = md_path.read_bytes()

    stale_q = search(ws, "quasar")
    stale_n = search(ws, "nebula")
    _assert(stale_q["status"] == INDEX_STALE, f"expected INDEX_STALE quasar, got {stale_q}")
    _assert(stale_n["status"] == INDEX_STALE, f"expected INDEX_STALE nebula, got {stale_n}")
    _assert(stale_q["evidence"] == [] and stale_n["evidence"] == [], "stale search leaked evidence")
    _assert(meta_path.read_bytes() == src_before, "search rewrote source.json")
    _assert(index_path.read_bytes() == idx_before, "search rewrote index")
    _assert(md_path.read_bytes() == md_before, "search rewrote markdown")
    record["checks"].append("unedited_legacy_search_index_stale")
    record["before_rebuild"] = {"quasar": stale_q, "nebula": stale_n}

    built = build_index(ws)
    _assert(built["ok"] is True and built["status"] == OK, f"build failed {built}")
    edited_md = md_path.read_text(encoding="utf-8")
    _assert(edited_md == markdown, "build_index edited markdown")
    final_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    _assert(final_meta["source"]["sha256"] == PAPER, "source sha changed")
    _assert(final_meta["paper_id"] == "sha256:" + PAPER, "paper_id changed")
    _assert(final_meta["document"]["sha256"] == _sha_text(markdown), "document sha drifted")
    located_after = _locate_pages(edited_md, page_count=final_meta["page_count"])
    stored = final_meta["pages"]
    _assert(len(stored) == 2, "page count")
    _assert([p["page"] for p in stored] == [1, 2], "complete ordered page set")
    for stored_page, live in zip(stored, located_after):
        _assert(stored_page["page"] == live["page"], "page number")
        _assert(stored_page["text_start"] == live["text_start"], "text_start")
        _assert(stored_page["text_end"] == live["text_end"], "text_end")
        _assert(stored_page["text_sha256"] == live["text_sha256"], "text_sha256")
        _assert(stored_page["anchor"] == live["anchor"], "anchor")
        body = edited_md[stored_page["text_start"] : stored_page["text_end"]]
        _assert(body == live["text"], "body != live text")
        _assert(_sha_text(body) == stored_page["text_sha256"], "body hash")
    _assert("quasar" in edited_md[stored[0]["text_start"] : stored[0]["text_end"]], "quasar not page 1 body")
    _assert("nebula" in edited_md[stored[1]["text_start"] : stored[1]["text_end"]], "nebula not page 2 body")
    quasar = search(ws, "quasar")
    nebula = search(ws, "nebula")
    q_item = _hit_page(quasar, "quasar", 1, edited_md)
    n_item = _hit_page(nebula, "nebula", 2, edited_md)
    record["checks"].append("rebuild_restores_quasar_page_1_nebula_page_2")
    record["build"] = {k: v for k, v in built.items()}
    record["after_rebuild"] = {
        "quasar_page": q_item["page"],
        "nebula_page": n_item["page"],
        "stored_pages": stored,
        "located_pages": [{k: v for k, v in item.items() if k != "text"} for item in located_after],
    }

    first_index_id = built["index_id"]
    src_fixed = meta_path.read_bytes()
    idx_fixed = index_path.read_bytes()
    rebuilt = build_index(ws)
    _assert(rebuilt["ok"] is True, "second build failed")
    _assert(rebuilt["index_id"] == first_index_id, "second build index_id changed")
    _assert(meta_path.read_bytes() == src_fixed, "stable rebuild rewrote source.json")
    _assert(index_path.read_bytes() == idx_fixed, "stable rebuild rewrote index bytes")
    _assert(search(ws, "quasar")["evidence"][0]["page"] == 1, "stable quasar")
    _assert(search(ws, "nebula")["evidence"][0]["page"] == 2, "stable nebula")
    record["checks"].append("stable_rebuild")
    record["second_build_index_id"] = rebuilt["index_id"]

    inserted = edited_md.replace("quasar describes", "quasar INSERT describes")
    md_path.write_text(inserted, encoding="utf-8")
    _assert(search(ws, "quasar")["status"] == INDEX_STALE, "insert not stale")
    _assert(build_index(ws)["ok"] is True, "insert rebuild failed")
    inserted_md = md_path.read_text(encoding="utf-8")
    _hit_page(search(ws, "quasar"), "quasar", 1, inserted_md)
    _hit_page(search(ws, "nebula"), "nebula", 2, inserted_md)
    deleted = inserted_md.replace("quasar INSERT describes", "quasar describes")
    md_path.write_text(deleted, encoding="utf-8")
    _assert(search(ws, "nebula")["status"] == INDEX_STALE, "delete not stale")
    _assert(build_index(ws)["ok"] is True, "delete rebuild failed")
    restored = md_path.read_text(encoding="utf-8")
    _hit_page(search(ws, "quasar"), "quasar", 1, restored)
    _hit_page(search(ws, "nebula"), "nebula", 2, restored)
    _assert("INSERT" not in search(ws, "quasar")["evidence"][0]["text"], "insert leaked")
    record["checks"].append("in_page_insert_delete")

    good_md = md_path.read_text(encoding="utf-8")
    good_meta = meta_path.read_bytes()
    good_index = index_path.read_bytes()

    def _fail_edit(mutated: str, label: str) -> None:
        md_path.write_text(mutated, encoding="utf-8")
        _assert(search(ws, "quasar")["status"] == INDEX_STALE, f"{label} search not stale")
        try:
            build_index(ws)
            raise AssertionError(f"{label}: build_index must fail")
        except ResearchError as exc:
            _assert(exc.code == "SOURCE_INVALID", f"{label} code {exc.code}")
            _assert("re-extract" in exc.message, f"{label} message {exc.message}")
        _assert(meta_path.read_bytes() == good_meta, f"{label} rewrote source.json")
        _assert(index_path.read_bytes() == good_index, f"{label} rewrote index")
        md_path.write_text(good_md, encoding="utf-8")

    _fail_edit(good_md.replace('<a id="page-2"></a>', ""), "missing")
    _fail_edit(good_md.replace('<a id="page-2"></a>', '<a id="page-1"></a>'), "duplicate")
    swapped = good_md.replace('<a id="page-1"></a>', '<a id="page-TMP"></a>')
    swapped = swapped.replace('<a id="page-2"></a>', '<a id="page-1"></a>')
    swapped = swapped.replace('<a id="page-TMP"></a>', '<a id="page-2"></a>')
    _fail_edit(swapped, "out_of_order")
    record["checks"].append("invalid_anchors_no_rewrite")

    multi = Path("/private/tmp/vp.r06.t1.multi/workspace")
    shutil.rmtree(multi.parent, ignore_errors=True)
    multi.mkdir(parents=True)
    _write_paper(multi, SHA_A, "Alpha", ["alpha unique token on page one"])
    md_b, meta_b = _write_paper(multi, SHA_B, "Beta", ["beta unique token on page one"])
    build_index(multi)
    meta_a_bytes = (multi / "papers" / SHA_A / "source.json").read_bytes()
    md_a_bytes = (multi / "papers" / SHA_A / "source.md").read_bytes()
    index_bytes = (multi / INDEX_DIRNAME / INDEX_FILENAME).read_bytes()
    meta_b_bytes = meta_b.read_bytes()
    md_b.write_text(md_b.read_text(encoding="utf-8").replace('<a id="page-1"></a>', ""), encoding="utf-8")
    _assert(search(multi, "alpha")["status"] == INDEX_STALE, "later-invalid search not stale")
    try:
        build_index(multi)
        raise AssertionError("later invalid paper must fail build")
    except ResearchError as exc:
        _assert(exc.code == "SOURCE_INVALID", f"later invalid code {exc.code}")
    _assert((multi / "papers" / SHA_A / "source.json").read_bytes() == meta_a_bytes, "rewrote earlier source.json")
    _assert((multi / "papers" / SHA_A / "source.md").read_bytes() == md_a_bytes, "rewrote earlier markdown")
    _assert((multi / INDEX_DIRNAME / INDEX_FILENAME).read_bytes() == index_bytes, "rewrote index after later invalid")
    _assert(meta_b.read_bytes() == meta_b_bytes, "rewrote invalid paper source.json")
    record["checks"].append("later_invalid_paper_does_not_rewrite_earlier")

    shared = {
        "source.json": _sha((FIX / "source.json").read_bytes()),
        "source.md": _sha((FIX / "source.md").read_bytes()),
        "index.v1.json": _sha((FIX / "index.v1.json").read_bytes()),
    }
    _assert(shared["source.json"] == "4aab5a9a49b3d8aae1ba252d80c2963d4afa1e7f22960767b409f8452f69a5db", "shared source.json")
    _assert(shared["source.md"] == "f985d353c7b2f643e2b2addd76182b3c99641b64814e3001ff43ee34c2266804", "shared source.md")
    _assert(shared["index.v1.json"] == "5d8a185db8177b6dc59ad201ef94f62dab1a0d902b54269377cdd84002f7347f", "shared index")
    record["shared_fixture_untouched"] = shared
    record["ok"] = True
    record["module_sha256"] = _sha(
        Path(
            "/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r06-v1/"
            "terminal-1/src/video_paper_wiki_research/light_index.py"
        ).read_bytes()
    )
    return record


if __name__ == "__main__":
    try:
        payload = main()
    except Exception as exc:
        payload = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in payload if k not in {"before_rebuild", "after_rebuild"}}, ensure_ascii=False, indent=2))
    sys.exit(0 if payload.get("ok") else 1)
