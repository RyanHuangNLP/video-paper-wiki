"""Complete prospective legacy/versioned compilation from explicit source bytes.

Rendering produces no publication authority. The retained publisher must bind
the supplied historical inventory and immutable event prefix to actual state.
"""
from __future__ import annotations

import html
import json
import unicodedata

from video_paper_wiki import canonical_compiler as legacy
from video_paper_wiki.assessment_history_v2 import derive_assessment_heads
from video_paper_wiki.domain import compile_concept_page
from video_paper_wiki.identity import (
    IdentityError, is_canonical_paper_id, normalize_arxiv_id, normalize_doi,
    paper_page_slug, repo_page_slug,
)
from video_paper_wiki.markdown_locator import encode_evidence, resolve_markdown_locator
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.resources import read_projection_resource_bytes
from video_paper_wiki.source_semantics_contracts import (
    COMPILE, PAPER, association_reference, fail, preflight, validate,
)
from video_paper_wiki.source_versions import derive_display_heads, validate_source_inventory


def _bad(message, at=""):
    fail("COMPILE_INPUT_INVALID", message, at)


def _escape(value):
    text = html.escape(str(value).replace("\r", " ").replace("\n", " "), quote=False)
    for char in ("\\", "[", "]", "*", "_", "`", "|", "!"):
        text = text.replace(char, "\\" + char)
    return "".join(c if ord(c) >= 32 and ord(c) != 127 else " " for c in text)


def concept_items_for_papers(records):
    preflight(records)
    if type(records) is not list:
        _bad("prospective paper records must be an array")
    taxonomy = json.loads(read_projection_resource_bytes("taxonomy", "v1.json"))
    allowed = {(axis["slug"], term["slug"]): {
        "axis": axis["slug"], "slug": term["slug"], "label_zh": term["label_zh"],
        "label_en": term.get("label_en", term["slug"]),
    } for axis in taxonomy["axes"] for term in axis["terms"]}
    selected = set()
    for record in records:
        doc = validate(record, PAPER if type(record) is dict and record.get("schema") == PAPER
                       else "video-paper-wiki.paper-record.v1")
        for item in doc["taxonomy"]:
            key = item["axis"], item["slug"]
            if key not in allowed:
                _bad("prospective taxonomy term is not in the pinned vocabulary")
            selected.add(key)
    return [allowed[key] for key in sorted(selected)]


def _owners(groups):
    owners, claims = {}, set()
    for group in groups:
        record = group["record"]
        pid = record["paper_id"]
        if not is_canonical_paper_id(pid):
            _bad("prospective paper identity is not canonical")
        reserved = [pid, *(x for x in record["aliases"] if is_canonical_paper_id(x))]
        if pid in owners:
            _bad("prospective primary paper identity is duplicated or aliased")
        for alias in reserved:
            if alias in owners and owners[alias] != pid:
                _bad("canonical alias has more than one primary owner")
            owners[alias] = pid
        if record["schema"] == PAPER:
            for field, normalize in (("arxiv_id", normalize_arxiv_id), ("doi", normalize_doi)):
                if field in record:
                    try:
                        normalized = normalize(record[field])
                    except IdentityError:
                        _bad("explicit paper identifier is invalid", "/papers/record/" + field)
                    if normalized not in reserved:
                        _bad("explicit paper identifier lacks a declared identity binding", "/papers/record/" + field)
        refs = [x["claim_id"] for x in record["section_claim_refs"]]
        actual = [x["claim_id"] for x in group["claims"]]
        if len(refs) != len(set(refs)) or len(actual) != len(set(actual)) or set(refs) != set(actual):
            _bad("prospective claim inventory differs from complete record references")
        if claims.intersection(actual):
            _bad("one claim has multiple primary paper owners")
        claims.update(actual)
        if any(x["stable_subject_id"] != "paper:" + pid for x in group["claims"]):
            _bad("claim subject differs from its primary paper owner")


def _versioned(group, inventory, raw_sources):
    record = validate(group["record"], PAPER)
    association_ids = {x["association_id"] for x in group["associations"]}
    associations = [inventory[aid] for aid in sorted(association_ids)]
    if any(x["paper_id"] != record["paper_id"] for x in associations):
        _bad("association belongs to a different prospective paper")
    if record["source_associations"] != [association_reference(x) for x in associations]:
        _bad("record association references differ from the complete group")
    if any(x["paper_id"] != record["paper_id"] for x in group["display_decisions"]):
        _bad("display decision belongs to another paper")
    heads = derive_display_heads(associations, group["display_decisions"])["heads"]
    head = heads[0] if heads else None
    expected = None if head is None else {"decision_id": head["decision_id"], "sha256": head["decision_sha256"]}
    if record["display_head"] != expected:
        fail("SOURCE_DISPLAY_INVALID", "paper display head differs from complete history", "/display_head")
    if head is not None:
        selected = inventory[head["association"]["association_id"]]
        if (record["active_extraction_path"] != selected["extraction"]["path"]
                or record["active_extraction_sha256"] != selected["extraction"]["sha256"]):
            fail("SOURCE_DISPLAY_INVALID", "paper extraction mirror differs from selected association")
    else:
        selected = None
    head_ids = derive_assessment_heads(claims=group["claims"], events=group["events"])
    if "assessment_heads" in group and group["assessment_heads"] != head_ids:
        _bad("assessment head materialization differs")
    source_ids = {x["source_id"] for x in associations}
    for claim in group["claims"]:
        if not claim["evidence"]:
            _bad("versioned canonical claim requires source evidence")
        for evidence in claim["evidence"]:
            encode_evidence(evidence)
            source_ids.add(evidence["source_id"])
            if evidence["kind"] == "markdown":
                aid = evidence["association"]["association_id"]
                if aid not in association_ids:
                    _bad("Markdown evidence points outside this paper's associations")
                resolve_markdown_locator({k: v for k, v in evidence.items() if k != "relation"},
                                         inventory[aid], raw_sources[evidence["path"]])
    if record["source_ids"] != sorted(source_ids):
        _bad("paper source IDs differ from associations and current evidence")
    return record, associations, selected


def _evidence_lines(evidence):
    result = []
    for item in sorted(evidence, key=lambda x: canonicalize(encode_evidence(x))):
        relation, sid = item["relation"], item["source_id"]
        if item["kind"] == "markdown":
            aid = item["association"]["association_id"]
            fragment = "#" + item["page_anchor"] if item["page_anchor"] else ""
            target = "../../" + item["path"] + fragment
            result.append(f"  - evidence: {relation}; source: `{sid}`; association: `{aid}`; "
                          f"[Markdown]({target}); span: [{item['charspan'][0]}, {item['charspan'][1]}); "
                          f"excerpt_sha256: `{item['excerpt_sha256']}`")
        elif item["kind"] == "pdf":
            result.append(f"  - evidence: {relation}; source: `{sid}`; [PDF text artifact](../../{item['artifact_path']}); "
                          f"page: {item['page']}; ref: {_escape(item['ref'])}")
        else:
            result.append(f"  - evidence: {relation}; source: `{sid}`; repository: {_escape(item['repository'])}; "
                          f"commit: `{item['commit']}`; path: {_escape(item['path'])}; "
                          f"lines: {item['lines']['start']}-{item['lines']['end']}")
    return result


def _paper(group, material):
    record, associations, selected = material
    refs = {item["claim_id"]: item for item in record["section_claim_refs"]}
    claims = {item["claim_id"]: (item, refs[item["claim_id"]]) for item in group["claims"]}
    taxonomy = sorted({f"{x['axis']}/{x['slug']}" for x in record["taxonomy"]})
    fields = (("type", "paper"), ("paper_id", record["paper_id"]), ("title", record["title"]),
              ("title_zh", record["title_zh"]), ("authors", record["authors"]), ("published_at", record["published_at"]),
              ("arxiv_id", record.get("arxiv_id")), ("doi", record.get("doi")), ("aliases", sorted(record["aliases"])),
              ("source_ids", record["source_ids"]), ("source_associations", record["source_associations"]),
              ("display_head", record["display_head"]), ("claim_ids", sorted(claims)), ("topics", taxonomy),
              ("code_urls", sorted(record.get("code_urls", []))), ("active_extraction_path", record["active_extraction_path"]),
              ("active_extraction_sha256", record["active_extraction_sha256"]), ("created_at", record["created_at"]),
              ("updated_at", record["updated_at"]), ("status", "generated"), ("created", record["created_at"][:10]),
              ("updated", record["updated_at"][:10]), ("tags", taxonomy or ["video-paper"]))
    frontmatter = "\n".join(["---", *[f"{key}: {json.dumps(value, ensure_ascii=False, separators=(',', ':'))}"
                                    for key, value in fields], "---"])
    lines = [frontmatter, "", "# " + _escape(record["title_zh"] or record["title"]), "", "## 来源版本", ""]
    if selected is None:
        lines.append("- 展示版本：未选择。")
    else:
        label = _escape(selected["version"]["label"] or "未知版本")
        lines.append(f"- 展示版本：{label}；association: `{selected['association_id']}`")
    for association in associations:
        label = "未知版本" if association["version"]["kind"] == "unknown" else _escape(association["version"]["label"])
        lines.append(f"- {label} ({association['version']['kind']}); [Markdown](../../{association['raw']['path']}); "
                     f"association: `{association['association_id']}`")
    lines.append("")
    for section, heading in legacy._SECTIONS:
        lines += ["## " + heading, ""]
        rows = [(claim, ref) for claim, ref in claims.values() if ref["lifecycle"] == "active" and ref["section"] == section]
        if section == "one_sentence_conclusion":
            rows = [x for x in rows if x[1]["core"] and x[0]["assessment"] in {"accepted", "contested"}]
            if len(rows) > 3:
                _bad("a paper may have at most three eligible core conclusions")
        if section == "evidence_status":
            rows += [(claim, ref) for claim, ref in claims.values()
                     if ref["lifecycle"] == "retired" or (
                         ref["section"] == "one_sentence_conclusion"
                         and not (ref["core"] and claim["assessment"] in {"accepted", "contested"}))]
        for claim, ref in sorted(rows, key=lambda x: x[0]["claim_id"]):
            lines.append(f"- {_escape(claim['canonical_claim_text'])}  ^{claim['claim_id']}")
            lines.append(f"  - lifecycle: `{ref['lifecycle']}`; assessment: `{claim['assessment']}`")
            lines += _evidence_lines(claim["evidence"])
        if section == "related":
            lines.append("- 暂无已发布的关联索引。")
        elif not rows:
            lines.append("- 暂无已审核的核心结论。" if section == "one_sentence_conclusion" else "- 暂无。")
        lines.append("")
    return "wiki/papers/" + paper_page_slug(record["paper_id"]) + ".md", unicodedata.normalize("NFC", "\n".join(lines).rstrip() + "\n").encode()


def compile_pages(material, *, raw_sources, extraction_artifacts, head_bytes, receipt_bytes, registration_ledgers):
    preflight(material, evidence_scope="compile")
    doc = validate(material, COMPILE)
    _owners(doc["papers"])
    modern = [group for group in doc["papers"] if group["record"]["schema"] == PAPER]
    associations = [a for group in modern for a in group["associations"]]
    inventory = validate_source_inventory(associations, raw_sources=raw_sources,
        extraction_artifacts=extraction_artifacts, head_bytes=head_bytes,
        receipt_bytes=receipt_bytes, registration_ledgers=registration_ledgers)
    validated = {group["record"]["paper_id"]: _versioned(group, inventory, raw_sources) for group in modern}
    concepts = concept_items_for_papers([group["record"] for group in doc["papers"]])
    if doc["concepts"] != concepts:
        _bad("concept inventory differs from the complete pinned paper taxonomy")
    if not modern:
        return legacy.compile_pages({**doc, "schema": legacy.SCHEMA})
    output = {}

    def add(path, raw):
        if (type(path) is not str or not path.startswith("wiki/") or not path.endswith(".md")
                or unicodedata.normalize("NFC", path) != path or "\\" in path
                or any(part in {"", ".", ".."} for part in path.split("/"))):
            _bad("compiled output path is not portable")
        folded = path.casefold()
        if any(other.casefold() == folded or other.casefold().startswith(folded + "/")
               or folded.startswith(other.casefold() + "/") for other in output):
            _bad("compiled output paths collide")
        output[path] = raw

    for group in doc["papers"]:
        if group["record"]["schema"] == PAPER:
            add(*_paper(group, validated[group["record"]["paper_id"]]))
        else:
            add(*legacy._paper(group))
    for item in doc["code"]:
        add(*legacy._code(item))
    for item in concepts:
        add(f"wiki/concepts/{item['axis'].replace('/', '-')}-{item['slug']}.md", compile_concept_page(**item).encode())
    paper_paths = sorted(path for path in output if path.startswith("wiki/papers/"))
    concept_paths = sorted(path for path in output if path.startswith("wiki/concepts/"))
    if paper_paths:
        concept_links = [f"- [[../concepts/{path.rsplit('/', 1)[-1][:-3]}|{path.rsplit('/', 1)[-1][:-3]}]]" for path in concept_paths]
        code_links = {path: [] for path in paper_paths}
        for item in doc["code"]:
            code_name = repo_page_slug(item["repo_record"]["repo_id"])
            for pid in item["repo_record"]["paper_ids"]:
                paper_path = "wiki/papers/" + paper_page_slug(pid) + ".md"
                if paper_path in code_links:
                    code_links[paper_path].append(f"- [[../code/{code_name}|{legacy._markdown(item['repo_record']['canonical_repository'])}]]")
        paper_links = "\n".join(f"- [[../papers/{path.rsplit('/', 1)[-1][:-3]}|{path.rsplit('/', 1)[-1][:-3]}]]" for path in paper_paths)
        for path in paper_paths:
            related = "\n".join(concept_links + sorted(code_links[path])) or "- 暂无已发布的关联索引。"
            modern_paths = {"wiki/papers/" + paper_page_slug(g["record"]["paper_id"]) + ".md" for g in modern}
            if path in modern_paths:
                prefix, marker, tail = output[path].decode().partition("\n## 关联\n")
                output[path] = (prefix + marker + tail.replace("\n- 暂无已发布的关联索引。\n", "\n" + related + "\n", 1)).encode()
            else:
                output[path] = output[path].decode().replace("- 暂无已发布的关联索引。", related).encode()
        for path in concept_paths:
            output[path] = (output[path].decode().rstrip() + "\n\n## 关联\n\n" + paper_links + "\n").encode()
    return {path: output[path] for path in sorted(output)}
