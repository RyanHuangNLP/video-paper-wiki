"""Workspace-local lexical index over light-paper Markdown. No embeddings."""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence

from video_paper_wiki_research.contracts import ResearchError

OK = "OK"
NO_RESULTS = "NO_RESULTS"
INDEX_STALE = "INDEX_STALE"
INDEX_DIRNAME = ".light-index"
INDEX_FILENAME = "index.v1.json"
SCHEMA = "video-paper-wiki.light-index.v1"
PAPER_SCHEMA = "video-paper-wiki.light-paper.v1"
LONG_PAGE = 4000
CHUNK_SIZE = 2000
BM25_K1 = 1.2
BM25_B = 0.75
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_PAGE_ANCHOR = re.compile(r'<a id="page-(\d+)"></a>')
_LATIN = re.compile(r"[a-z0-9]+(?:['-][a-z0-9]+)*")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_REEXTRACT = "page anchors are missing, duplicated, or out of order; re-extract the PDF"
_STOP = frozenset(
    "a an and are as at be by for from has have if in is it its of on or that the this to was with".split()
)


def _fail(code: str, message: str, details: dict[str, Any] | None = None) -> None:
    raise ResearchError(code, message, details)


def _result(*, ok: bool, status: str, query: str, index_id: str | None, evidence: list[dict[str, Any]], message: str) -> dict[str, Any]:
    return {
        "ok": ok,
        "status": status,
        "query": query,
        "index_id": index_id,
        "evidence": evidence,
        "message": message,
    }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _index_path(workspace_root: Path) -> Path:
    return workspace_root / INDEX_DIRNAME / INDEX_FILENAME


def tokenize(text: str) -> list[str]:
    """Latin words plus CJK unigrams/bigrams. Not cross-lingual semantics."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    tokens: list[str] = []
    for match in _LATIN.finditer(folded):
        token = match.group(0)
        if token in _STOP:
            continue
        if len(token) > 1 or token.isdigit():
            tokens.append(token)
    for match in _CJK_RUN.finditer(folded):
        run = match.group(0)
        tokens.extend(run)
        tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return tokens


def _paper_dirs(workspace_root: Path) -> list[Path]:
    papers = workspace_root / "papers"
    if papers.is_symlink() or not papers.is_dir():
        return []
    found: list[Path] = []
    for item in sorted(papers.iterdir(), key=lambda path: path.name):
        if item.is_symlink() or not item.is_dir():
            continue
        if _HEX64.fullmatch(item.name):
            found.append(item)
    return found


def _read_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        _fail("SOURCE_INVALID", f"cannot parse {path.name}", {"path": str(path)})
        raise exc
    if type(value) is not dict:
        _fail("SOURCE_INVALID", f"{path.name} root must be an object", {"path": str(path)})
    return value


def _locate_pages(markdown: str, *, page_count: int) -> list[dict[str, Any]]:
    """Recompute half-open Unicode page slices from remaining anchors and titles."""
    if type(page_count) is not int or isinstance(page_count, bool) or page_count < 1:
        _fail("SOURCE_INVALID", _REEXTRACT)
    matches = list(_PAGE_ANCHOR.finditer(markdown))
    if not matches:
        _fail("SOURCE_INVALID", _REEXTRACT)
    numbers = [int(item.group(1)) for item in matches]
    if numbers != list(range(1, page_count + 1)):
        _fail("SOURCE_INVALID", _REEXTRACT)
    pages: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        page = numbers[index]
        heading = f"\n\n## PDF 第 {page} 页\n\n"
        if not markdown.startswith(heading, match.end()):
            _fail("SOURCE_INVALID", "page title does not match the anchor; re-extract the PDF")
        start = match.end() + len(heading)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        while end > start and markdown[end - 1] == "\n":
            end -= 1
        slice_text = markdown[start:end]
        pages.append(
            {
                "page": page,
                "anchor": f"page-{page}",
                "text_start": start,
                "text_end": end,
                "text_sha256": _sha256_text(slice_text),
                "text": slice_text,
            }
        )
    return pages


def _stored_pages(pages: object, markdown: str) -> list[dict[str, Any]] | None:
    if type(pages) is not list:
        return None
    verified: list[dict[str, Any]] = []
    for item in pages:
        if type(item) is not dict:
            return None
        page = item.get("page")
        start = item.get("text_start")
        end = item.get("text_end")
        digest = item.get("text_sha256")
        if type(page) is not int or page < 1 or type(start) is not int or type(end) is not int or type(digest) is not str:
            return None
        if not 0 <= start <= end <= len(markdown):
            return None
        slice_text = markdown[start:end]
        if _sha256_text(slice_text) != digest:
            return None
        verified.append(
            {
                "page": page,
                "anchor": item.get("anchor") or f"page-{page}",
                "text_start": start,
                "text_end": end,
                "text_sha256": digest,
                "text": slice_text,
            }
        )
    return verified


def _page_intervals_match(stored: object, located: Sequence[Mapping[str, Any]]) -> bool:
    """Accept stored records only when page numbers, complete set, and every offset/hash match live anchors."""
    if type(stored) is not list or len(stored) != len(located):
        return False
    live_pages = [item["page"] for item in located]
    if live_pages != list(range(1, len(located) + 1)):
        return False
    seen: list[int] = []
    for item, live in zip(stored, located):
        if type(item) is not dict:
            return False
        page = item.get("page")
        start = item.get("text_start")
        end = item.get("text_end")
        digest = item.get("text_sha256")
        if type(page) is not int or type(start) is not int or type(end) is not int or type(digest) is not str:
            return False
        if page != live["page"] or start != live["text_start"] or end != live["text_end"] or digest != live["text_sha256"]:
            return False
        stored_anchor = item.get("anchor")
        if stored_anchor is not None and stored_anchor != live["anchor"]:
            return False
        seen.append(page)
    return seen == live_pages


def _load_paper(directory: Path) -> dict[str, Any]:
    meta_path = directory / "source.json"
    md_path = directory / "source.md"
    if meta_path.is_symlink() or md_path.is_symlink() or not meta_path.is_file() or not md_path.is_file():
        _fail("SOURCE_INVALID", "paper directory must contain regular source.json and source.md", {"path": str(directory)})
    meta = _read_json(meta_path)
    markdown = md_path.read_text(encoding="utf-8")
    markdown_bytes = markdown.encode("utf-8")
    markdown_sha = _sha256_bytes(markdown_bytes)
    paper_id = meta.get("paper_id")
    expected_id = "sha256:" + directory.name
    if meta.get("schema") != PAPER_SCHEMA or paper_id != expected_id:
        _fail("SOURCE_INVALID", "source.json paper identity differs", {"path": str(meta_path)})
    document = meta.get("document")
    if type(document) is not dict:
        _fail("SOURCE_INVALID", "source.json document is missing", {"path": str(meta_path)})
    relative = "papers/" + directory.name + "/source.md"
    if document.get("path") != relative:
        _fail("SOURCE_INVALID", "source.md digest or path differs from source.json", {"path": str(md_path)})
    if type(meta.get("page_count")) is not int:
        _fail("SOURCE_INVALID", "source.json pages are invalid", {"path": str(meta_path)})
    # Live anchors/headings own the intervals. Matching document or slice hashes is not enough.
    located_pages = _locate_pages(markdown, page_count=meta["page_count"])
    metadata_stale = document.get("sha256") != markdown_sha or not _page_intervals_match(
        meta.get("pages"), located_pages
    )
    source = meta.get("source") if type(meta.get("source")) is dict else {}
    source_sha = source.get("sha256")
    if type(source_sha) is not str or source_sha != directory.name:
        source_sha = directory.name
    title = meta.get("title")
    if type(title) is not str or not title.strip():
        title = paper_id
    return {
        "paper_id": paper_id,
        "title": title,
        "source_sha256": source_sha,
        "markdown_path": relative,
        "markdown_sha256": markdown_sha,
        "source_json_sha256": _sha256_bytes(meta_path.read_bytes()),
        "page_count": meta["page_count"],
        "pages": located_pages,
        "markdown": markdown,
        "metadata_stale": metadata_stale,
        "metadata_path": meta_path,
        "metadata": meta,
    }


def _chunk_spans(page_start: int, page_text: str) -> list[tuple[int, int]]:
    length = len(page_text)
    if length == 0:
        return []
    if length <= LONG_PAGE:
        return [(page_start, page_start + length)]
    spans: list[tuple[int, int]] = []
    offset = 0
    while offset < length:
        limit = min(offset + CHUNK_SIZE, length)
        if limit < length:
            break_at = page_text.rfind("\n", offset + CHUNK_SIZE // 2, limit)
            if break_at > offset:
                limit = break_at + 1
        spans.append((page_start + offset, page_start + limit))
        offset = limit
    return spans


def _chunk_id(*, paper_id: str, page: int, text_start: int, text_end: int, text_sha256: str) -> str:
    payload = {
        "page": page,
        "paper_id": paper_id,
        "text_end": text_end,
        "text_sha256": text_sha256,
        "text_start": text_start,
    }
    return "chk-" + _sha256_bytes(_canonical(payload))[:24]


def _snapshot_id(papers: Sequence[Mapping[str, Any]]) -> str:
    rows = []
    for paper in papers:
        rows.append(
            {
                "markdown_sha256": paper["markdown_sha256"],
                "paper_id": paper["paper_id"],
                "source_json_sha256": paper["source_json_sha256"],
                "pages": [
                    {
                        "page": item["page"],
                        "text_end": item["text_end"],
                        "text_sha256": item["text_sha256"],
                        "text_start": item["text_start"],
                    }
                    for item in paper["pages"]
                ],
            }
        )
    rows.sort(key=lambda item: item["paper_id"])
    return _sha256_bytes(_canonical({"papers": rows, "schema": SCHEMA}))


def _chunk_records(paper: Mapping[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for page in paper["pages"]:
        for start, end in _chunk_spans(page["text_start"], page["text"]):
            text = paper["markdown"][start:end]
            if not text:
                continue
            digest = _sha256_text(text)
            tokens = tokenize(text)
            tf: dict[str, int] = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            chunks.append(
                {
                    "chunk_id": _chunk_id(
                        paper_id=paper["paper_id"],
                        page=page["page"],
                        text_start=start,
                        text_end=end,
                        text_sha256=digest,
                    ),
                    "paper_id": paper["paper_id"],
                    "title": paper["title"],
                    "source_sha256": paper["source_sha256"],
                    "page": page["page"],
                    "markdown_path": paper["markdown_path"],
                    "markdown_sha256": paper["markdown_sha256"],
                    "text_start": start,
                    "text_end": end,
                    "text_sha256": digest,
                    "text": text,
                    "tf": tf,
                    "token_count": len(tokens),
                }
            )
    return chunks


def _document_frequency(chunks: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    df: dict[str, int] = {}
    for chunk in chunks:
        for token in chunk["tf"]:
            df[token] = df.get(token, 0) + 1
    return df


def _freshness_fingerprint(papers: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    return {
        paper["paper_id"]: paper["markdown_sha256"] + ":" + paper["source_json_sha256"]
        for paper in papers
    }


def _refreshed_metadata_bytes(paper: dict[str, Any]) -> bytes:
    meta = dict(paper["metadata"])
    document = dict(meta.get("document") or {})
    document["sha256"] = paper["markdown_sha256"]
    meta["document"] = document
    meta["pages"] = [
        {
            "page": item["page"],
            "anchor": item["anchor"],
            "text_start": item["text_start"],
            "text_end": item["text_end"],
            "text_sha256": item["text_sha256"],
        }
        for item in paper["pages"]
    ]
    return (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def build_index(workspace_root: Path) -> dict[str, Any]:
    """Scan workspace papers, verify slices, and write a rebuildable lexical index."""
    if not isinstance(workspace_root, Path):
        workspace_root = Path(workspace_root)
    if workspace_root.is_symlink() or not workspace_root.is_dir():
        _fail("WORKSPACE_INVALID", "workspace_root must be a regular directory")
    loaded = [_load_paper(directory) for directory in _paper_dirs(workspace_root)]
    pending: list[tuple[Path, bytes, dict[str, Any]]] = []
    for paper in loaded:
        if paper.get("metadata_stale"):
            pending.append((paper["metadata_path"], _refreshed_metadata_bytes(paper), paper))
    for path, encoded, paper in pending:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(encoded)
        tmp.replace(path)
        paper["source_json_sha256"] = _sha256_bytes(encoded)
        paper["metadata_stale"] = False
    chunks: list[dict[str, Any]] = []
    for paper in loaded:
        chunks.extend(_chunk_records(paper))
    chunks.sort(key=lambda item: (item["paper_id"], item["page"], item["text_start"], item["chunk_id"]))
    index_id = _snapshot_id(loaded)
    payload = {
        "schema": SCHEMA,
        "index_id": index_id,
        "papers": [
            {
                "paper_id": paper["paper_id"],
                "title": paper["title"],
                "source_sha256": paper["source_sha256"],
                "markdown_path": paper["markdown_path"],
                "markdown_sha256": paper["markdown_sha256"],
                "source_json_sha256": paper["source_json_sha256"],
                "page_count": paper["page_count"],
                "pages": [
                    {
                        "page": item["page"],
                        "text_start": item["text_start"],
                        "text_end": item["text_end"],
                        "text_sha256": item["text_sha256"],
                    }
                    for item in paper["pages"]
                ],
            }
            for paper in loaded
        ],
        "chunks": chunks,
        "df": _document_frequency(chunks),
        "chunk_count": len(chunks),
        "paper_count": len(loaded),
    }
    target = _index_path(workspace_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    tmp = target.with_name(INDEX_FILENAME + ".tmp")
    tmp.write_bytes(encoded)
    tmp.replace(target)
    return {
        "ok": True,
        "status": OK,
        "index_id": index_id,
        "paper_count": len(loaded),
        "chunk_count": len(chunks),
        "index_path": str(target.resolve()),
        "size_bytes": len(encoded),
        "message": "built workspace lexical index",
    }


def _load_index(workspace_root: Path) -> dict[str, Any] | None:
    path = _index_path(workspace_root)
    if path.is_symlink() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if type(payload) is not dict or payload.get("schema") != SCHEMA:
        return None
    if type(payload.get("chunks")) is not list or type(payload.get("papers")) is not list:
        return None
    return payload


def _current_papers(workspace_root: Path) -> list[dict[str, Any]] | None:
    try:
        return [_load_paper(directory) for directory in _paper_dirs(workspace_root)]
    except ResearchError:
        return None


def _index_papers_match_current(stored: Mapping[str, Any], current: Sequence[Mapping[str, Any]]) -> bool:
    stored_papers = stored.get("papers")
    if type(stored_papers) is not list or len(stored_papers) != len(current):
        return False
    current_by_id = {paper["paper_id"]: paper for paper in current}
    seen: set[str] = set()
    for item in stored_papers:
        if type(item) is not dict:
            return False
        paper_id = item.get("paper_id")
        if type(paper_id) is not str or paper_id in seen or paper_id not in current_by_id:
            return False
        seen.add(paper_id)
        paper = current_by_id[paper_id]
        if item.get("markdown_sha256") != paper["markdown_sha256"]:
            return False
        if item.get("source_json_sha256") != paper["source_json_sha256"]:
            return False
        if item.get("page_count") != paper["page_count"]:
            return False
        if not _page_intervals_match(item.get("pages"), paper["pages"]):
            return False
    return seen == set(current_by_id)


def _index_is_current(stored: Mapping[str, Any], current: Sequence[Mapping[str, Any]]) -> bool:
    if stored.get("index_id") != _snapshot_id(current):
        return False
    stored_fp = {
        item["paper_id"]: item["markdown_sha256"] + ":" + item["source_json_sha256"]
        for item in stored.get("papers") or []
        if type(item) is dict and type(item.get("paper_id")) is str
    }
    if stored_fp != _freshness_fingerprint(current):
        return False
    return _index_papers_match_current(stored, current)


def _idf(df: int, chunk_count: int) -> float:
    return math.log((chunk_count - df + 0.5) / (df + 0.5) + 1.0)


def _bm25(query_tokens: Sequence[str], chunk: Mapping[str, Any], df: Mapping[str, Any], chunk_count: int, avgdl: float) -> float:
    score = 0.0
    tf_map = chunk.get("tf") or {}
    dl = chunk.get("token_count") or 0
    seen: set[str] = set()
    for token in query_tokens:
        if token in seen:
            continue
        seen.add(token)
        tf = tf_map.get(token) or 0
        if tf <= 0:
            continue
        freq = df.get(token) or 0
        denom = tf + BM25_K1 * (1.0 - BM25_B + BM25_B * (dl / avgdl if avgdl else 0.0))
        score += _idf(int(freq), chunk_count) * (tf * (BM25_K1 + 1.0)) / denom
    return float(score)


def _evidence_item(chunk: Mapping[str, Any], score: float) -> dict[str, Any]:
    return {
        "chunk_id": chunk["chunk_id"],
        "paper_id": chunk["paper_id"],
        "title": chunk["title"],
        "source_sha256": chunk["source_sha256"],
        "page": chunk["page"],
        "markdown_path": chunk["markdown_path"],
        "markdown_sha256": chunk["markdown_sha256"],
        "text_start": chunk["text_start"],
        "text_end": chunk["text_end"],
        "text_sha256": chunk["text_sha256"],
        "text": chunk["text"],
        "score": score,
    }


def search(
    workspace_root: Path,
    query: str,
    *,
    top_k: int = 8,
    paper_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Lexically search the workspace index. Misses and staleness are closed statuses."""
    if not isinstance(workspace_root, Path):
        workspace_root = Path(workspace_root)
    if type(query) is not str:
        _fail("QUERY_INVALID", "query must be a string")
    if type(top_k) is not int or isinstance(top_k, bool) or top_k < 1:
        _fail("QUERY_INVALID", "top_k must be a positive integer")
    allowed: set[str] | None = None
    if paper_ids is not None:
        if not isinstance(paper_ids, list) or any(type(item) is not str for item in paper_ids):
            _fail("QUERY_INVALID", "paper_ids must be a list of strings")
        allowed = {item for item in paper_ids if item}
    stored = _load_index(workspace_root)
    current = _current_papers(workspace_root)
    if stored is None or current is None or not _index_is_current(stored, current):
        return _result(
            ok=False,
            status=INDEX_STALE,
            query=query,
            index_id=None if stored is None else stored.get("index_id"),
            evidence=[],
            message="workspace Markdown or paper set disagrees with the stored index",
        )
    tokens = tokenize(query)
    if not tokens:
        return _result(
            ok=False,
            status=NO_RESULTS,
            query=query,
            index_id=stored["index_id"],
            evidence=[],
            message="query produced no lexical matches",
        )
    chunks = [item for item in stored["chunks"] if type(item) is dict]
    if allowed is not None:
        chunks = [item for item in chunks if item.get("paper_id") in allowed]
    chunk_count = len(stored["chunks"])
    avgdl = (
        sum(int(item.get("token_count") or 0) for item in stored["chunks"] if type(item) is dict) / chunk_count
        if chunk_count
        else 0.0
    )
    df = stored.get("df") if type(stored.get("df")) is dict else {}
    ranked: list[tuple[float, str, dict[str, Any]]] = []
    for chunk in chunks:
        score = _bm25(tokens, chunk, df, chunk_count, avgdl)
        if not math.isfinite(score) or score <= 0.0:
            continue
        markdown = None
        for paper in current:
            if paper["paper_id"] == chunk["paper_id"]:
                markdown = paper["markdown"]
                break
        if markdown is None:
            return _result(
                ok=False,
                status=INDEX_STALE,
                query=query,
                index_id=stored["index_id"],
                evidence=[],
                message="workspace Markdown or paper set disagrees with the stored index",
            )
        start = chunk["text_start"]
        end = chunk["text_end"]
        slice_text = markdown[start:end]
        if slice_text != chunk.get("text") or _sha256_text(slice_text) != chunk.get("text_sha256"):
            return _result(
                ok=False,
                status=INDEX_STALE,
                query=query,
                index_id=stored["index_id"],
                evidence=[],
                message="workspace Markdown or paper set disagrees with the stored index",
            )
        ranked.append((-score, chunk["chunk_id"], chunk))
    ranked.sort()
    evidence = [_evidence_item(chunk, -key) for key, _cid, chunk in ranked[:top_k]]
    if not evidence:
        return _result(
            ok=False,
            status=NO_RESULTS,
            query=query,
            index_id=stored["index_id"],
            evidence=[],
            message="query produced no lexical matches",
        )
    return _result(
        ok=True,
        status=OK,
        query=query,
        index_id=stored["index_id"],
        evidence=evidence,
        message="retrieved lexical evidence from the workspace index",
    )
