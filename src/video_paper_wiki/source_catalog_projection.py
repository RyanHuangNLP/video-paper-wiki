"""Complete source-state projection and exact retained citation resolution."""
from __future__ import annotations

import copy
import json
import re
from urllib.parse import unquote

from video_paper_wiki.code_evidence_contracts import normalize_code_bytes, validate_code_locator
from video_paper_wiki.identity import repo_id
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_locator import decode_evidence, resolve_markdown_locator
from video_paper_wiki.source_catalog_contracts import (
    KEYS, MAX_DOCUMENT, MAX_EXCERPT, MAX_INVENTORY, PROFILE, REASONS, SCHEMA,
    digest, encode, fail, invalid, limit, ordered, row_key,
)
from video_paper_wiki.source_publication_contracts import CLAIM_LEDGER, SOURCE_LEDGER
from video_paper_wiki.source_registration import historical_source_ledger
from video_paper_wiki.source_semantics_contracts import sha


def _evidence_invalid(message):
    fail("SOURCE_CATALOG_EVIDENCE_INVALID", message, "/rows/evidence")


def _resolution(path, raw, position, *, excerpt=None, reason=None):
    if excerpt is not None and len(excerpt.encode()) > MAX_EXCERPT:
        excerpt, reason = None, "excerpt_limit"
    if reason is None and (type(excerpt) is not str or not excerpt):
        _evidence_invalid("resolved evidence text must be nonempty")
    return {"state": "RESOLVED" if reason is None else "UNSUPPORTED_LEGACY_RESOLUTION",
            "reason": reason, "excerpt": excerpt,
            "excerpt_sha256": None if excerpt is None else sha(excerpt.encode()),
            "source_path": path, "source_sha256": sha(raw), "position": position}


def _pointer(document, pointer):
    """JSON Pointer and its URI fragment representation; no heuristic lookup."""
    if pointer.startswith("#"):
        if re.search(r"%(?![0-9a-fA-F]{2})", pointer):
            raise ValueError
        pointer = unquote(pointer[1:], encoding="utf-8", errors="strict")
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError
    current = document
    for raw in pointer[1:].split("/"):
        if re.search(r"~(?![01])", raw):
            raise ValueError
        key = raw.replace("~1", "/").replace("~0", "~")
        if type(current) is dict:
            current = current[key]
        elif type(current) is list and re.fullmatch(r"0|[1-9][0-9]*", key):
            current = current[int(key)]
        else:
            raise ValueError
    return current


def _pdf_resolution(loc, data):
    path = loc["artifact_path"]
    raw = data[path]
    if sha(raw) != loc["artifact_sha256"]:
        _evidence_invalid("PDF parser artifact hash differs")
    span = loc.get("charspan")
    if "charspan" in loc and (type(span) is not list or len(span) != 2
            or any(type(x) is not int for x in span) or not 0 <= span[0] < span[1]):
        _evidence_invalid("PDF character span is invalid")
    try:
        value = _pointer(json.loads(raw), loc["ref"])
    except (KeyError, IndexError, ValueError, TypeError, UnicodeError):
        return _resolution(path, raw, None, reason="legacy_json_pointer_unavailable")
    if type(value) is not dict or type(value.get("text")) is not str:
        return _resolution(path, raw, None, reason="legacy_object_not_text")
    text = value["text"]
    if span is not None and span[1] > len(text):
        _evidence_invalid("PDF character span is outside the parser text")
    if span is not None and sha(text[span[0]:span[1]].encode()) != loc["text_sha256"]:
        _evidence_invalid("PDF excerpt hash differs from the parser text")
    prov = value.get("prov")
    if type(prov) is not list or not any(type(p) is dict and type(p.get("page_no")) is int
                                        and p["page_no"] == loc["page"] for p in prov):
        return _resolution(path, raw, None, reason="legacy_page_not_reconstructable")
    if span is None:
        return _resolution(path, raw, None, reason="legacy_charspan_unavailable")
    return _resolution(path, raw, {"kind": "pdf", "page": loc["page"], "ref": loc["ref"], "charspan": span},
                       excerpt=text[span[0]:span[1]])


def _code_match(loc, docs):
    matches = [(path, m) for path, m in docs["code-evidence-manifest"].items()
               if repo_id(m["origin"]["repository"]) == repo_id(loc["repository"])
               and m["origin"]["commit"] == loc["commit"] and m["origin"]["path"] == loc["path"]
               and m["capture"]["source_id"] == loc["source_id"]]
    if len(matches) != 1:
        _evidence_invalid("code citation requires one inspected source manifest")
    return matches[0]


def _code_resolution(loc, docs, data):
    _, manifest = _code_match(loc, docs)
    path = manifest["capture"]["stored_path"]
    raw = data[path]
    validate_code_locator({k: v for k, v in loc.items() if k != "relation"}, manifest, raw)
    normalized = normalize_code_bytes(raw)
    start, end = loc["lines"]["start"], loc["lines"]["end"]
    first = 0
    for _ in range(start - 1):
        first = normalized.find(b"\n", first) + 1
    last = first
    for _ in range(end - start + 1):
        newline = normalized.find(b"\n", last)
        if newline < 0:
            last = len(normalized) + 1
            break
        last = newline + 1
    excerpt = normalized[first:last - 1]
    if sha(excerpt) != loc["snippet_sha256"]:
        _evidence_invalid("code excerpt differs from the established line hash")
    return _resolution(path, raw, {"kind": "code", "lines": loc["lines"]}, excerpt=excerpt.decode())


def _resolve(wire, docs, data):
    loc = decode_evidence(wire)
    if loc["kind"] == "markdown":
        aid = loc["association"]["association_id"]
        found = [a for a in docs["association"].values() if a["association_id"] == aid]
        if len(found) != 1:
            _evidence_invalid("Markdown citation has no unique bound association")
        raw = data[found[0]["raw"]["path"]]
        excerpt = resolve_markdown_locator({k: v for k, v in loc.items() if k != "relation"}, found[0], raw)
        if len(excerpt.encode()) > MAX_EXCERPT:
            limit("Markdown excerpt exceeds its exact resolution bound", "/rows/evidence")
        return loc, aid, _resolution(loc["path"], raw,
            {"kind": "markdown", "charspan": loc["charspan"], "page_anchor": loc["page_anchor"]}, excerpt=excerpt)
    if loc["kind"] == "pdf":
        return loc, None, _pdf_resolution(loc, data)
    return loc, None, _code_resolution(loc, docs, data)


def _ancestry(state):
    """Attribution and canonical use are distinct relations over actual files."""
    docs, data, sources = state["documents"], state["bytes"], state["source_ledger"]["sources"]
    raw_paths = {p for p in data if p.startswith(".raw/")}
    attributed = {p: set() for p in raw_paths}
    referenced = set()
    paper_owners, repo_owners = {s: set() for s in sources}, {s: set() for s in sources}
    for record in docs["paper"].values():
        for sid in record["source_ids"]:
            paper_owners[sid].add(record["paper_id"])
    for cid, owner in state["owners"].items():
        if owner["kind"] == "repo":
            for wire in state["claim_ledger"]["claims"][cid]["evidence"]:
                repo_owners[wire["source_id"]].add(owner["subject"][5:])

    def link(paths, source_ids, *, used=False):
        for path in paths:
            if path in attributed:
                attributed[path].update(s for s in source_ids if s in sources)
                if used:
                    referenced.add(path)

    for sid, row in sources.items():
        if row["origin"]["kind"] == "file":
            link([row["origin"]["locator"]], [sid])
    for path, raw in state["ledger_snapshots"].items():
        link([path], historical_source_ledger(raw)["sources"])
    for path, observed in docs["observation"].items():
        raw_path = ".raw/captured/" + observed["markdown"]["sha256"] + ".md"
        link([path], attributed.get(raw_path, ()))
    for path, association in docs["association"].items():
        link([association["raw"]["path"], association["extraction"]["path"],
              association["registration"]["source_ledger_path"]], [association["source_id"]], used=True)
    active = {r["active_extraction_path"] for r in docs["paper"].values() if r["active_extraction_path"] is not None}
    cited = {loc["artifact_path"] for c in state["claims"] for loc in c["evidence"] if loc["kind"] == "pdf"}
    for path, run in docs["run-manifest"].items():
        raw_sha = path.split("/")[2]
        captures = [p for p in attributed if p.startswith(".raw/captured/" + raw_sha + ".")]
        sids = set().union(*(attributed[p] for p in captures))
        relatives = [path, *captures]
        fp = run.get("pipeline_fingerprint")
        if fp is not None:
            stem = f".raw/derived/{raw_sha}/docling/{fp}/"
            relatives += [stem + n for n in ("document.json", "parser-config.json", "model-manifest.json")]
        link(relatives, sids, used=bool(set(relatives) & (active | cited)))
    for path, manifest in docs["code-evidence-manifest"].items():
        sid = manifest["capture"]["source_id"]
        related = [path, manifest["capture"]["stored_path"]]
        related += [p for p, a in docs["alignment-manifest"].items()
                    if repo_id(a["repository"]) == repo_id(manifest["origin"]["repository"])
                    and a["commit"] == manifest["origin"]["commit"]]
        link(related, [sid], used=True)
    return attributed, referenced, paper_owners, repo_owners


def _artifact_kind(path, docs):
    if path.startswith(".raw/captured/"):
        return "captured"
    if path.startswith(".raw/derived/source-ledgers/"):
        return "source-ledger-snapshot"
    for role, kind in (("observation", "markdown-observation"), ("code-evidence-manifest", "code-manifest"),
                       ("alignment-manifest", "alignment-manifest"), ("run-manifest", "run-manifest")):
        if path in docs[role]:
            return kind
    if re.fullmatch(r"\.raw/derived/[0-9a-f]{64}/docling/[^/]+/(?:document|parser-config|model-manifest)\.json", path):
        return "parser-artifact"
    return "derived"


def project_rows(state):
    docs, data = state["documents"], state["bytes"]
    rows = {key: [] for key in KEYS}
    document_paths = [(role, path) for role, values in docs.items() for path in values]
    document_paths += [("source-ledger", SOURCE_LEDGER), ("claim-ledger", CLAIM_LEDGER)]
    document_paths += [("source-ledger-snapshot", p) for p in state["ledger_snapshots"]]
    for kind, path in document_paths:
        raw = data[path]
        if len(raw) > MAX_DOCUMENT:
            limit("exact semantic document exceeds its byte bound", "/rows/documents")
        rows["documents"].append({"kind": kind, "path": path, "sha256": sha(raw), "json_text": raw.decode()})
    display = {h["paper_id"]: h for h in state["display_heads"]["heads"]}
    selected = {pid: h["association"]["association_id"] for pid, h in display.items()}
    for path, record in docs["paper"].items():
        row = {k: copy.deepcopy(record[k]) for k in ("paper_id", "title", "title_zh", "authors", "published_at", "aliases", "taxonomy", "source_ids", "active_extraction_path", "active_extraction_sha256")}
        row.update(record_path=path, record_schema=record["schema"], code_urls=copy.deepcopy(record.get("code_urls", [])),
                   association_ids=sorted(a["association_id"] for a in record.get("source_associations", [])),
                   display_association_id=selected.get(record["paper_id"]))
        rows["papers"].append(row)
    for path, record in docs["repo"].items():
        row = {k: copy.deepcopy(record[k]) for k in ("repo_id", "canonical_repository", "canonical_commit", "paper_ids", "officiality", "license")}
        row.update(record_path=path, archived=record.get("archived"))
        rows["repositories"].append(row)
    for cid, ledger in state["claim_ledger"]["claims"].items():
        owner = state["owners"][cid]
        record = docs[owner["kind"]][owner["record_path"]]
        reference = next(r for r in record["section_claim_refs" if owner["kind"] == "paper" else "capability_claim_refs"] if r["claim_id"] == cid)
        head = state["assessment_heads"]["heads"][cid]
        row = {k: copy.deepcopy(ledger[k]) for k in ("text", "assessment", "reviewed_at", "risk", "confidence", "location")}
        row.update(claim_id=cid, owner_kind=owner["kind"], owner_id=owner["subject"].split(":", 1)[1],
                   page=owner["page"], reference=copy.deepcopy(reference), head_event_id=head["event_id"],
                   head_event_sha256=head["event_sha256"], evidence_profile=head["evidence_profile"])
        rows["claims"].append(row)
        for ordinal, wire in enumerate(ledger["evidence"]):
            loc, association, resolution = _resolve(wire, docs, data)
            rows["evidence"].append({"claim_id": cid, "ordinal": ordinal, "source_id": wire["source_id"],
                "kind": loc["kind"], "wire": copy.deepcopy(wire), "association_id": association,
                "display_association_id": selected.get(row["owner_id"]) if owner["kind"] == "paper" else None,
                "resolution": resolution})
    rows["sources"] = [{"source_id": sid, "row": copy.deepcopy(row)} for sid, row in state["source_ledger"]["sources"].items()]
    for role, group, identity in (("association", "associations", "association_id"), ("decision", "display_decisions", "decision_id")):
        rows[group] = [{identity: doc[identity], "path": path, "sha256": sha(data[path]), "document": copy.deepcopy(doc)}
                       for path, doc in docs[role].items()]
    rows["assessment_heads"] = [{"claim_id": cid, **copy.deepcopy(head)} for cid, head in state["assessment_heads"]["heads"].items()]
    rows["display_heads"] = [{"paper_id": pid, "head": copy.deepcopy(head)} for pid, head in display.items()]
    rows["compiled_pages"] = [{"path": path, "sha256": sha(raw), "text": raw.decode()} for path, raw in state["pages"].items()]
    attributed, referenced, paper_owners, repo_owners = _ancestry(state)
    for sid in state["source_ledger"]["sources"]:
        status = "registered_owned" if paper_owners[sid] or repo_owners[sid] else "registered_unclaimed"
        rows["coverage"].append({"kind": "source", "id": sid, "state": status, "source_ids": [sid],
            "paper_ids": sorted(paper_owners[sid]), "repo_ids": sorted(repo_owners[sid]), "reason": REASONS[status]})
    for path, source_ids in attributed.items():
        raw = data[path]
        rows["artifacts"].append({"path": path, "kind": _artifact_kind(path, docs), "sha256": sha(raw),
                                  "size_bytes": len(raw), "source_ids": sorted(source_ids)})
        if path.startswith(".raw/captured/"):
            status = "captured_registered" if source_ids else "captured_unregistered"
        else:
            status = "derived_referenced" if path in referenced else "derived_unreferenced"
        rows["coverage"].append({"kind": "artifact", "id": path, "state": status, "source_ids": sorted(source_ids),
            "paper_ids": sorted(set().union(*(paper_owners[s] for s in source_ids))),
            "repo_ids": sorted(set().union(*(repo_owners[s] for s in source_ids))), "reason": REASONS[status]})
    return ordered(rows)


def assert_projection(rows, state):
    """Assert complete producer closure against the independently audited state."""
    docs, data = state["documents"], state["bytes"]
    if set(rows) != set(KEYS):
        invalid("projection row groups are incomplete")
    for name, fields in KEYS.items():
        keys = [row_key(r, fields) for r in rows[name]]
        if keys != sorted(set(keys)):
            invalid("projection group keys are duplicated or unordered", "/rows/" + name)
    def identities(group, field, expected):
        if {r[field] for r in rows[group]} != set(expected):
            invalid("projection identities differ from current source", "/rows/" + group)
    for role, group, key in (("paper", "papers", "paper_id"), ("repo", "repositories", "repo_id"),
                             ("association", "associations", "association_id"), ("decision", "display_decisions", "decision_id")):
        identities(group, key, (d[key] for d in docs[role].values()))
    identities("sources", "source_id", state["source_ledger"]["sources"])
    identities("claims", "claim_id", state["claim_ledger"]["claims"])
    identities("assessment_heads", "claim_id", state["assessment_heads"]["heads"])
    identities("display_heads", "paper_id", (x["paper_id"] for x in state["display_heads"]["heads"]))
    identities("compiled_pages", "path", state["pages"])
    identities("artifacts", "path", (p for p in data if p.startswith(".raw/")))
    expected_documents = {p: kind for kind, values in docs.items() for p in values}
    expected_documents.update({SOURCE_LEDGER: "source-ledger", CLAIM_LEDGER: "claim-ledger"})
    expected_documents.update({p: "source-ledger-snapshot" for p in state["ledger_snapshots"]})
    identities("documents", "path", expected_documents)
    for row in rows["documents"]:
        if (row["kind"] != expected_documents[row["path"]] or row["json_text"].encode() != data[row["path"]]
                or row["sha256"] != sha(data[row["path"]])):
            invalid("semantic document projection differs from exact bytes", "/rows/documents")
    heads = {x["claim_id"]: x for x in rows["assessment_heads"]}
    sources = {x["source_id"] for x in rows["sources"]}
    associations = {x["association_id"] for x in rows["associations"]}
    paper_ids = {x["paper_id"] for x in rows["papers"]}
    repo_ids = {x["repo_id"] for x in rows["repositories"]}
    claims = {x["claim_id"]: x for x in rows["claims"]}
    display = {h["paper_id"]: h for h in state["display_heads"]["heads"]}
    selected = {pid: h["association"]["association_id"] for pid, h in display.items()}
    for claim in rows["claims"]:
        cid = claim["claim_id"]
        owner = state["owners"][cid]
        record = docs[owner["kind"]][owner["record_path"]]
        references = record["section_claim_refs" if owner["kind"] == "paper" else "capability_claim_refs"]
        ref = next(r for r in references if r["claim_id"] == cid)
        head = state["assessment_heads"]["heads"][cid]
        ledger = state["claim_ledger"]["claims"][cid]
        if (claim["reference"] != ref or claim["owner_kind"] != owner["kind"]
                or claim["owner_id"] != owner["subject"].split(":", 1)[1] or claim["page"] != owner["page"]
                or any(claim[k] != ledger[k] for k in ("text", "assessment", "reviewed_at", "risk", "confidence", "location"))
                or heads[cid] != {"claim_id": cid, **head}
                or (claim["head_event_id"], claim["head_event_sha256"], claim["evidence_profile"])
                   != (head["event_id"], head["event_sha256"], head["evidence_profile"])):
            invalid("claim owner, lifecycle or assessment history differs", "/rows/claims")
    expected_evidence = {(cid, i): wire for cid, row in state["claim_ledger"]["claims"].items() for i, wire in enumerate(row["evidence"])}
    if {(e["claim_id"], e["ordinal"]) for e in rows["evidence"]} != set(expected_evidence):
        invalid("evidence ordinals are incomplete", "/rows/evidence")
    for evidence in rows["evidence"]:
        key = evidence["claim_id"], evidence["ordinal"]
        if (evidence["wire"] != expected_evidence[key] or evidence["source_id"] != expected_evidence[key]["source_id"]
                or evidence["source_id"] not in sources or evidence["claim_id"] not in claims
                or any(a is not None and a not in associations for a in (evidence["association_id"], evidence["display_association_id"]))):
            invalid("evidence identity or original transport differs", "/rows/evidence")
        loc, aid, resolution = _resolve(expected_evidence[key], docs, data)
        owner = claims[evidence["claim_id"]]
        display_aid = selected.get(owner["owner_id"]) if owner["owner_kind"] == "paper" else None
        if (evidence["kind"] != loc["kind"] or evidence["association_id"] != aid
                or evidence["display_association_id"] != display_aid or evidence["resolution"] != resolution):
            invalid("projected citation or exact resolution differs", "/rows/evidence")
    for paper in rows["papers"]:
        if (not set(paper["source_ids"]) <= sources or not set(paper["association_ids"]) <= associations
                or paper["display_association_id"] is not None and paper["display_association_id"] not in associations):
            invalid("paper projection has an unresolved identity", "/rows/papers")
        record = docs["paper"].get(paper["record_path"])
        if (record is None or paper["record_schema"] != record["schema"]
                or any(paper[k] != record[k] for k in ("paper_id", "title", "title_zh", "authors", "published_at", "aliases", "taxonomy", "source_ids", "active_extraction_path", "active_extraction_sha256"))
                or paper["code_urls"] != record.get("code_urls", [])
                or paper["association_ids"] != sorted(a["association_id"] for a in record.get("source_associations", []))
                or paper["display_association_id"] != selected.get(paper["paper_id"])):
            invalid("paper projection differs from its exact record", "/rows/papers")
    for repo in rows["repositories"]:
        if not set(repo["paper_ids"]) <= paper_ids:
            invalid("repository projection has an unresolved paper", "/rows/repositories")
        record = docs["repo"].get(repo["record_path"])
        if (record is None or any(repo[k] != record[k] for k in ("repo_id", "canonical_repository", "canonical_commit", "paper_ids", "officiality", "license"))
                or repo["archived"] != record.get("archived")):
            invalid("repository projection differs from its exact record", "/rows/repositories")
    for source in rows["sources"]:
        if source["row"] != state["source_ledger"]["sources"][source["source_id"]]:
            invalid("source projection differs from its ledger row", "/rows/sources")
    for role, group, key in (("association", "associations", "association_id"), ("decision", "display_decisions", "decision_id")):
        for row in rows[group]:
            doc = docs[role].get(row["path"])
            if doc is None or row[key] != doc[key] or row["document"] != doc or row["sha256"] != sha(data[row["path"]]):
                invalid("immutable source history projection differs", "/rows/" + group)
    for row in rows["display_heads"]:
        if row["head"] != display[row["paper_id"]]:
            invalid("derived display head projection differs", "/rows/display_heads")
    for row in rows["compiled_pages"]:
        raw = state["pages"][row["path"]]
        if row["text"].encode() != raw or row["sha256"] != sha(raw):
            invalid("complete rendered page projection differs", "/rows/compiled_pages")
    attributed, referenced, paper_owners, repo_owners = _ancestry(state)
    for row in rows["artifacts"]:
        path = row["path"]
        if (row["sha256"] != sha(data[path]) or row["size_bytes"] != len(data[path])
                or row["kind"] != _artifact_kind(path, docs) or row["source_ids"] != sorted(attributed[path])):
            invalid("artifact attribution differs from retained ancestry", "/rows/artifacts")
    coverage_keys = {("source", s) for s in sources} | {("artifact", p) for p in data if p.startswith(".raw/")}
    if {(r["kind"], r["id"]) for r in rows["coverage"]} != coverage_keys:
        invalid("coverage does not cover the complete source and artifact sets", "/rows/coverage")
    for row in rows["coverage"]:
        if (not set(row["source_ids"]) <= sources or not set(row["paper_ids"]) <= paper_ids
                or not set(row["repo_ids"]) <= repo_ids):
            invalid("coverage references unknown canonical identities", "/rows/coverage")
        if row["kind"] == "source":
            sids = {row["id"]}
            status = "registered_owned" if paper_owners[row["id"]] or repo_owners[row["id"]] else "registered_unclaimed"
        else:
            sids = attributed[row["id"]]
            if row["id"].startswith(".raw/captured/"):
                status = "captured_registered" if sids else "captured_unregistered"
            else:
                status = "derived_referenced" if row["id"] in referenced else "derived_unreferenced"
        pids = sorted(set().union(*(paper_owners[s] for s in sids)))
        rids = sorted(set().union(*(repo_owners[s] for s in sids)))
        if (row["source_ids"] != sorted(sids) or row["paper_ids"] != pids or row["repo_ids"] != rids
                or row["state"] != status or row["reason"] != REASONS[status]):
            invalid("coverage differs from exact canonical use and attribution", "/rows/coverage")


def reconstruct(state, generation):
    if len(state["current_inventory"]) > MAX_INVENTORY:
        limit("complete Vault inventory exceeds its bound", "/basis/inventory")
    rows = project_rows(state)
    assert_projection(rows, state)
    inventory = [{"path": p, "sha256": v[0], "size_bytes": v[1], "mode": v[2]}
                 for p, v in sorted(state["current_inventory"].items(), key=lambda x: x[0].encode())]
    document = {"schema": SCHEMA, "profile": PROFILE, "basis": {**state["basis"], "inventory": inventory},
                "generation": generation.record(sha(canonicalize(rows))), "rows": rows}
    document["catalog_sha256"] = digest(document)
    return document, encode(document)
