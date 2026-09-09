"""Complete source state derived from one retained, receipt-audited snapshot.

Local consistency is separate from the pinned inspector's ledger validation.
This module neither changes a Vault nor manufactures a registration or review.
"""
from __future__ import annotations

import re

from video_paper_wiki.assessment_history_v2 import derive_assessment_heads, validate_claim
from video_paper_wiki.canonical_compiler_v2 import compile_pages, concept_items_for_papers
from video_paper_wiki.code_evidence_contracts import validate_code_evidence_manifest, validate_code_locator
from video_paper_wiki.contracts import ContractError, validate_document
from video_paper_wiki.identity import claim_id, paper_page_slug, repo_id, repo_page_slug
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_locator import decode_evidence
from video_paper_wiki.markdown_source import validate_payload
from video_paper_wiki.markdown_source_contracts import OBSERVATION
from video_paper_wiki.projection_input import _BRANCHES
from video_paper_wiki.projection_runtime import parse_projection_json
from video_paper_wiki.receipt_audit import HEAD, _walk_inventory
from video_paper_wiki.source_publication_contracts import (
    ASSESSMENT_HEADS, CLAIM_LEDGER, DISPLAY_HEADS, HEADS, IMMUTABLE, MAX_FILE, PATTERNS,
    SOURCE_LEDGER, invalid, kind_for_path, parse_json, payload_map,
)
from video_paper_wiki.source_registration import historical_source_ledger, receipt_chain
from video_paper_wiki.source_semantics_contracts import (
    ASSOCIATION, COMPILE, DECISION, EVENT, HEADS as DISPLAY_SCHEMA, PAPER,
    calendar, fail, preflight, sha,
)
from video_paper_wiki.source_versions import derive_display_heads
from video_paper_wiki.transaction_contracts import _collisions

LEGACY_PAPER = "video-paper-wiki.paper-record.v1"
LEGACY_EVENT = "video-paper-wiki.assessment-event.v1"
REPO = "video-paper-wiki.repo-record.v1"
_PREFIXES = {
    "paper": "wiki/meta/records/papers/", "repo": "wiki/meta/records/repos/",
    "association": "wiki/meta/records/source-versions/",
    "decision": "wiki/meta/reviews/source-display/",
    "snapshot": ".raw/derived/source-ledgers/",
    "observation": ".raw/derived/markdown-source/",
    "code-evidence-manifest": ".raw/derived/code-manifests/",
    "alignment-manifest": ".raw/derived/alignment-manifests/",
}
_SCHEMAS = {
    "paper": {LEGACY_PAPER, PAPER}, "repo": {REPO}, "event": {LEGACY_EVENT, EVENT},
    "association": {ASSOCIATION}, "decision": {DECISION}, "observation": {OBSERVATION},
    "assessment_heads": {HEADS}, "display_heads": {DISPLAY_SCHEMA},
    "code-evidence-manifest": {"video-paper-wiki.code-evidence-manifest.v1"},
    "alignment-manifest": {"video-paper-wiki.paper-code-alignment.v1"},
    "run-manifest": {"video-paper-wiki.run-manifest.v1"},
}


def _conflict(message, path=""):
    fail("SOURCE_HISTORY_CONFLICT", message, path, exit_code=75)


def inventory_digest(inventory):
    return sha(canonicalize([{"path": p, "sha256": v[0], "size_bytes": v[1], "mode": v[2]}
                            for p, v in sorted(inventory.items(), key=lambda x: x[0].encode())]))


def snapshot_material(snapshot):
    inventory = _walk_inventory(snapshot, read_bytes=True)
    if HEAD not in inventory:
        fail("RECEIPT_BOOTSTRAP_REQUIRED", "source publication requires an actual genesis receipt", "/basis")
    return inventory, {p: snapshot.files[p][1] for p in inventory}


def _role(path):
    role = kind_for_path(path)
    if role is not None:
        return role
    for name, pattern in _BRANCHES.items():
        if pattern.fullmatch(path):
            return name
    for prefix in _PREFIXES.values():
        if path.startswith(prefix):
            invalid("unknown filename in a semantic namespace", "/inventory/" + path)
    if (path.startswith("wiki/meta/reviews/clm-")
            or re.match(r"\.raw/derived/[0-9a-f]{64}/(?:runs|docling)/", path)
            or path.startswith("wiki/meta/ledgers/")):
        invalid("unknown filename in a semantic namespace", "/inventory/" + path)
    return None


def require_legacy_profile(bytes_map):
    """Refuse the newer profile before a legacy consumer can filter its inputs."""
    for path, raw in bytes_map.items():
        if (path in {ASSESSMENT_HEADS, DISPLAY_HEADS}
                or any(path.startswith(_PREFIXES[k]) for k in ("association", "decision", "snapshot", "observation"))):
            fail("SOURCE_PROFILE_REQUIRED", "source-aware publication/catalog is required", path, exit_code=75)
        if path.startswith(("wiki/meta/records/", "wiki/meta/reviews/")) and path.endswith(".json"):
            try:
                doc = parse_json(raw, pointer=path, maximum=MAX_FILE)
            except ContractError:
                continue  # Opaque historical namespaces are validated by their existing consumer.
            if type(doc) is dict and doc.get("schema") in {PAPER, EVENT}:
                fail("SOURCE_PROFILE_REQUIRED", "source-aware publication/catalog is required", path, exit_code=75)


def _document(path, raw, role, *, fresh=False):
    if role == "alignment-manifest":
        # Legacy PDF bbox floats are admitted only in the old officiality slots.
        doc = parse_projection_json(raw)
        preflight({"papers": [], "code": [{"alignment": doc}]}, evidence_scope="compile")
    else:
        doc = parse_json(raw, pointer=path, maximum=MAX_FILE)
    if type(doc) is not dict or doc.get("schema") not in _SCHEMAS[role]:
        invalid("unknown schema in a semantic namespace", path + "/schema")
    validate_document(doc, doc["schema"])
    if fresh or role in {"association", "decision", "observation", "assessment_heads", "display_heads"} or doc["schema"] in {PAPER, EVENT}:
        if canonicalize(doc) != raw:
            invalid("new semantic artifacts require exact canonical JSON", path)
    match = PATTERNS[role].fullmatch(path) if role in PATTERNS else None
    if role == "event" and (match[1], match[2]) != (doc["claim_id"], doc["event_id"]):
        invalid("event path and identities differ", path)
    if role in {"association", "decision"} and match[1] != doc[role + "_id"]:
        invalid("immutable artifact filename and identity differ", path)
    if role == "observation" and (match[1] != doc["markdown"]["sha256"] or match[2] != sha(raw)):
        invalid("observation filename and bytes differ", path)
    if role in {"code-evidence-manifest", "alignment-manifest"} and path.rsplit("/", 1)[1] != sha(raw) + ".json":
        invalid("content-addressed legacy artifact filename differs", path)
    for field in ("published_at", "created_at", "updated_at", "decided_at", "started_at", "ended_at"):
        if field in doc:
            calendar(doc[field], path + "/" + field,
                     timestamp=field != "published_at" or len(doc[field]) != 10)
    return doc


def validate_payload_documents(payloads):
    """Shape and calendar checks run before acquiring current-state authority."""
    values = payload_map(payloads)
    for path, raw in values.items():
        role = kind_for_path(path)
        if role in _SCHEMAS:
            _document(path, raw, role, fresh=True)
        elif role in {"source", "snapshot"}:
            doc = historical_source_ledger(raw)
            if role == "source" and canonicalize(doc) != raw:
                invalid("new ledger bytes require canonical JSON", path)
            if role == "snapshot" and PATTERNS[role].fullmatch(path)[1] != sha(raw):
                invalid("ledger snapshot filename differs", path)
        elif role == "claim":
            doc = _claim_ledger(raw, structural=False)
            if canonicalize(doc) != raw:
                invalid("new claim ledger bytes require canonical JSON", path)
        elif role == "page":
            try:
                raw.decode("utf-8", "strict")
            except UnicodeError:
                invalid("compiled page is not UTF-8", path)
    return values


def _closed(value, required, optional=frozenset(), at=""):
    if type(value) is not dict or not required <= value.keys() or value.keys() - required - optional:
        invalid("object fields differ from the closed local projection", at)


def _claim_ledger(raw, *, structural):
    doc = parse_json(raw, pointer=CLAIM_LEDGER, maximum=MAX_FILE)
    _closed(doc, {"schema", "generated_at", "claims"}, at=CLAIM_LEDGER)
    if doc["schema"] != "claude-obsidian.claim-ledger.v1" or type(doc["claims"]) is not dict:
        invalid("claim ledger discriminator or rows differ", CLAIM_LEDGER)
    calendar(doc["generated_at"], CLAIM_LEDGER + "/generated_at")
    if len(doc["generated_at"]) != 20:
        invalid("ledger timestamp requires whole UTC seconds", CLAIM_LEDGER + "/generated_at")
    for cid, row in doc["claims"].items():
        at = CLAIM_LEDGER + "/claims/" + cid
        if re.fullmatch(r"clm-[0-9a-f]{20}", cid) is None:
            invalid("claim ID is outside the local identity grammar", at)
        required = {"text", "risk", "assessment", "confidence", "location", "evidence"}
        _closed(row, required if structural else required | {"reviewed_at"},
                {"reviewed_at", "notes", "supersedes"} if structural else {"notes", "supersedes"}, at)
        if type(row["text"]) is not str or not row["text"].strip() or len(row["text"].encode()) > 65536:
            invalid("claim text must be nonempty and bounded", at + "/text")
        for field, allowed in (("risk", {"normal", "high"}),
                               ("assessment", {"accepted", "provisional", "contested", "unsupported", "deprecated"}),
                               ("confidence", {"high", "medium", "low", "unknown"})):
            if type(row[field]) is not str or row[field] not in allowed:
                invalid("claim enum is outside the pinned domain", at + "/" + field)
        if row.get("reviewed_at") is not None:
            calendar(row["reviewed_at"], at + "/reviewed_at", timestamp=False)
        elif row["assessment"] == "accepted":
            invalid("accepted claim requires an explicit review date", at + "/reviewed_at")
        if row.get("notes") is not None and type(row["notes"]) is not str:
            invalid("claim notes must be text or null", at + "/notes")
        if row.get("supersedes") is not None and (type(row["supersedes"]) is not str or re.fullmatch(r"clm-[A-Za-z0-9][A-Za-z0-9._-]*", row["supersedes"]) is None):
            invalid("claim supersedes must be a safe claim ID", at + "/supersedes")
        _closed(row["location"], {"path"}, {"anchor"}, at + "/location")
        if type(row["location"]["path"]) is not str:
            invalid("claim location requires a canonical owner page", at + "/location/path")
        if row["location"].get("anchor") is not None and type(row["location"]["anchor"]) is not str:
            invalid("claim anchor must be text or null", at + "/location/anchor")
        if type(row["evidence"]) is not list:
            invalid("claim evidence must be an array", at + "/evidence")
        for evidence in row["evidence"]:
            decode_evidence(evidence)
        if row["assessment"] == "contested" and not (any(x["relation"] == "contradicts" for x in row["evidence"]) or (row.get("notes") or "").strip()):
            invalid("contested claim requires contradictory evidence or notes", at)
    return doc


def _ownership(papers, repos, ledger):
    owners, records, identities = {}, {}, {}
    for path, record in papers.items():
        pid = record["paper_id"]
        if pid in records:
            invalid("paper primary identity has multiple record paths", path)
        records[pid] = path
        from video_paper_wiki.identity import is_canonical_paper_id
        for identity in [pid, *(x for x in record["aliases"] if is_canonical_paper_id(x))]:
            if identity in identities and identities[identity] != pid:
                invalid("paper primary/alias ownership conflicts", path)
            identities[identity] = pid
    repo_paths = {}
    groups = [(p, r, "paper", "paper_id", "section_claim_refs") for p, r in papers.items()]
    groups += [(p, r, "repo", "repo_id", "capability_claim_refs") for p, r in repos.items()]
    for path, record, kind, key, refs in groups:
        identifier = record[key]
        if kind == "repo":
            if identifier in repo_paths or identifier != repo_id(record["canonical_repository"]):
                invalid("repository identity is duplicated or mismatched", path)
            repo_paths[identifier] = path
            if any(pid not in records for pid in record["paper_ids"]):
                invalid("repository references an unknown paper", path)
        page = "wiki/" + ("papers/" + paper_page_slug(identifier) if kind == "paper" else "code/" + repo_page_slug(identifier)) + ".md"
        for ref in record[refs]:
            cid = ref["claim_id"]
            if cid in owners or cid not in ledger["claims"]:
                invalid("claim has duplicate ownership or a missing ledger row", path)
            row = ledger["claims"][cid]
            if row["location"]["path"] != page:
                invalid("claim location differs from its canonical owner page", path)
            if record["schema"] == PAPER and row["location"] != {"path": page, "anchor": "^" + cid}:
                invalid("v2 paper claim requires its exact block anchor", path)
            subject = kind + ":" + identifier
            if cid != claim_id(subject, row["text"]):
                invalid("claim ID differs from its stable owner and exact text", path)
            owners[cid] = {"subject": subject, "record_path": path, "page": page, "kind": kind}
    if set(owners) != set(ledger["claims"]):
        invalid("claim ledger contains an orphan owner", CLAIM_LEDGER)
    claims = [{"claim_id": cid, "stable_subject_id": owners[cid]["subject"], "canonical_claim_text": row["text"],
               "evidence": [decode_evidence(x) for x in row["evidence"]],
               "assessment": row["assessment"], "reviewed_at": row.get("reviewed_at")}
              for cid, row in sorted(ledger["claims"].items())]
    for claim in claims:
        validate_claim(claim)
    return owners, claims


def _snapshots(snapshots, chain, pending_registration):
    authorized = {w["after_sha256"] for _, receipt in chain for w in receipt["writes"] if w["path"] == SOURCE_LEDGER}
    if chain and chain[0][1]["operation_type"] == "generic":
        authorized.update(x["sha256"] for x in chain[0][1]["claimed_inputs"] if x["path"] == SOURCE_LEDGER)
    for path, raw in snapshots.items():
        digest = sha(raw)
        historical_source_ledger(raw)
        if PATTERNS["snapshot"].fullmatch(path)[1] != digest:
            invalid("historical ledger filename differs from exact bytes", path)
        if digest not in authorized and not (pending_registration is not None and raw == pending_registration["ledger_bytes"] and path == pending_registration["snapshot_path"]):
            _conflict("ledger snapshot has no actual genesis claim or ledger-write proof", path)


def _legacy_artifacts(docs, data, sources):
    manifests = docs["code-evidence-manifest"]
    for path, manifest in manifests.items():
        captured = manifest["capture"]["stored_path"]
        if captured not in data:
            invalid("code manifest raw capture is missing", path)
        validate_code_evidence_manifest(manifest, payload=data[captured])
        row = sources.get(manifest["capture"]["source_id"])
        if row is None or row["origin"] != {"kind": "file", "locator": captured} or row["content_kind"] != "code" or row.get("content_sha256") != sha(data[captured]):
            invalid("code manifest source-ledger binding differs", path)
    used, qualifying = set(), set()
    for path, run in docs["run-manifest"].items():
        match = _BRANCHES["run-manifest"].fullmatch(path)
        raw_sha, name = path.split("/")[2], path.rsplit("/", 1)[1][:-5]
        if match is None or name != run["run_id"]:
            invalid("run filename differs from run identity", path)
        captures = [p for p in data if p.startswith(".raw/captured/" + raw_sha + ".")]
        if len(captures) != 1 or sha(data[captures[0]]) != raw_sha:
            invalid("run does not bind one actual raw capture", path)
        if not any(row["origin"] == {"kind": "file", "locator": captures[0]} for row in sources.values()):
            invalid("run capture has no logical source", path)
        if run["input_hashes"].get("source_sha256", raw_sha) != raw_sha:
            invalid("run source hash differs", path)
        fingerprint = run.get("pipeline_fingerprint")
        if fingerprint is None:
            if (set(run["input_hashes"]) & {"parser_config_sha256", "model_manifest_sha256"}
                    or "document_json_sha256" in run["output_hashes"]):
                invalid("unbound run declares parser artifacts", path)
            continue
        base = f".raw/derived/{raw_sha}/docling/{fingerprint}/"
        paths = {"document_json": base + "document.json", "model_manifest": base + "model-manifest.json",
                 "parser_config": base + "parser-config.json", "run_manifest": path}
        if not set(paths.values()) <= data.keys():
            invalid("run parser artifact set is incomplete", path)
        from video_paper_wiki.extraction_artifact import _profiles
        _, actual = _profiles({kind: data[p] for kind, p in paths.items()})
        if actual != fingerprint:
            invalid("run fingerprint differs from actual parser bytes", path)
        used.update(p for kind, p in paths.items() if kind != "run_manifest")
        if run["error_code"] is None:
            qualifying.add(paths["document_json"])
    expected = {p for p in data if any(_BRANCHES[k].fullmatch(p) for k in ("docling-document", "parser-config", "model-manifest"))}
    if used != expected or {p for p in expected if p.endswith("/document.json")} != qualifying:
        invalid("parser artifact inventory contains an orphan or failed-only document", "/inventory")
    return qualifying


def _code_groups(docs):
    groups, used_manifests, used_alignments = [], set(), set()
    for path, record in docs["repo"].items():
        matches = [(p, x) for p, x in docs["code-evidence-manifest"].items()
                   if repo_id(x["origin"]["repository"]) == record["repo_id"] and x["origin"]["commit"] == record["canonical_commit"]]
        alignments = [(p, x) for p, x in docs["alignment-manifest"].items()
                      if repo_id(x["repository"]) == record["repo_id"] and x["commit"] == record["canonical_commit"]]
        if len(matches) != 1 or len(alignments) != 1:
            invalid("legacy code group is missing or ambiguous", path)
        mp, manifest = matches[0]
        ap, alignment = alignments[0]
        groups.append({"manifest": manifest, "repo_record": record, "alignment": alignment})
        used_manifests.add(mp)
        used_alignments.add(ap)
    if used_manifests != set(docs["code-evidence-manifest"]) or used_alignments != set(docs["alignment-manifest"]):
        invalid("legacy code artifacts have no complete repository owner", "/inventory")
    return groups


def _locators(claims, owners, docs, sources, data, qualifying):
    papers = {x["paper_id"]: x for x in docs["paper"].values()}
    repos = {x["repo_id"]: x for x in docs["repo"].values()}

    def check(item, paper_ids, rid=None):
        sid = item["source_id"]
        if sid not in sources:
            invalid("evidence source is absent from the current ledger", "/claims/evidence")
        if item["kind"] == "markdown":
            if rid is not None:
                invalid("repository Markdown claims require the CODE successor", "/claims/evidence")
            return  # Association ownership and exact excerpt are checked by the mixed compiler.
        if item["kind"] == "pdf":
            path = item["artifact_path"]
            match = _BRANCHES["docling-document"].fullmatch(path)
            source = sources[sid]
            origin = source["origin"]
            if (match is None or path not in qualifying or sha(data[path]) != item["artifact_sha256"]
                    or not any(sid in papers[pid]["source_ids"] for pid in paper_ids)
                    or origin["kind"] != "file" or origin["locator"] not in data
                    or sha(data[origin["locator"]]) != path.split("/")[2]):
                invalid("PDF locator source/document/owner binding differs", "/claims/evidence")
        else:
            target = repo_id(item["repository"])
            if rid is not None and target != rid:
                invalid("code evidence has a different repository owner", "/claims/evidence")
            if target not in repos or not set(paper_ids) & set(repos[target]["paper_ids"]):
                invalid("code evidence repository is outside its linked papers", "/claims/evidence")
            manifests = [m for m in docs["code-evidence-manifest"].values()
                         if repo_id(m["origin"]["repository"]) == target and m["origin"]["commit"] == item["commit"]
                         and m["origin"]["path"] == item["path"] and m["capture"]["source_id"] == sid]
            if len(manifests) != 1:
                invalid("code locator has no unique actual manifest", "/claims/evidence")
            manifest = manifests[0]
            validate_code_locator({k: v for k, v in item.items() if k != "relation"}, manifest, data[manifest["capture"]["stored_path"]])
    for claim in claims:
        owner = owners[claim["claim_id"]]
        if owner["kind"] == "paper":
            pids, rid = [owner["subject"][6:]], None
        else:
            rid = owner["subject"][5:]
            pids = repos[rid]["paper_ids"]
        for item in claim["evidence"]:
            check(item, pids, rid)
    for alignment in docs["alignment-manifest"].values():
        for item in alignment["officiality"]["evidence"]:
            check(item, [alignment["paper_id"]])
        for capability in alignment["capabilities"]:
            for item in capability["locators"]:
                check(item, [alignment["paper_id"]], repo_id(alignment["repository"]))


def collect_source_state(snapshot, audit, *, overlay=None, require_rendered=True,
                         pending_registration=None, allow_legacy_structural=False):
    """Collect only bytes from the retained snapshot and exact proposed overlay."""
    writes = {} if overlay is None else validate_payload_documents(overlay)
    current_inventory, current_data = snapshot_material(snapshot)
    for path, raw in writes.items():
        if path in current_data and kind_for_path(path) in IMMUTABLE and raw != current_data[path]:
            _conflict("immutable stored history cannot be replaced", path)
    data = {**current_data, **writes}
    _collisions([(p, "/inventory") for p in data])
    inventory = {p: (sha(raw), len(raw), current_inventory[p][2] if p in current_inventory else 0o600)
                 for p, raw in data.items()}
    docs = {role: {} for role in _SCHEMAS}
    snapshots = {}
    for path, raw in sorted(data.items()):
        role = _role(path)
        if role in docs:
            docs[role][path] = _document(path, raw, role, fresh=path in writes)
        elif role == "snapshot":
            snapshots[path] = raw
        elif role == "captured-artifact" and path.rsplit("/", 1)[1][:64] != sha(raw):
            invalid("raw capture filename differs from its actual bytes", path)
    modern = any(d["schema"] in {PAPER, EVENT} for role in ("paper", "event") for d in docs[role].values()) or any(docs[k] for k in ("association", "decision", "assessment_heads", "display_heads"))
    structural = allow_legacy_structural and not modern
    if SOURCE_LEDGER not in data or CLAIM_LEDGER not in data:
        invalid("both actual ledgers are required", "/inventory")
    source = historical_source_ledger(data[SOURCE_LEDGER])
    ledger = _claim_ledger(data[CLAIM_LEDGER], structural=structural)
    owners, claims = _ownership(docs["paper"], docs["repo"], ledger)
    events = list(docs["event"].values())
    head_ids = derive_assessment_heads(claims=claims, events=events)
    event_paths = {event["event_id"]: path for path, event in docs["event"].items()}
    assessment_heads = {"schema": HEADS, "heads": {cid: {
        "event_id": eid, "event_sha256": sha(data[event_paths[eid]]),
        "evidence_profile": "legacy-v1" if docs["event"][event_paths[eid]]["schema"] == LEGACY_EVENT else docs["event"][event_paths[eid]]["evidence_profile"]}
        for cid, eid in sorted(head_ids.items())}}
    validate_document(assessment_heads, HEADS)
    receipts = {path: current_data[path] for path in audit["receipts"]}
    chain = receipt_chain(current_data[HEAD], receipts)
    _snapshots(snapshots, chain, pending_registration)
    for path, observed in docs["observation"].items():
        raw_path = ".raw/captured/" + observed["markdown"]["sha256"] + ".md"
        if raw_path not in data:
            invalid("Markdown observation has no actual raw bytes", path)
        validate_payload(data[raw_path], observed)
    for sid, row in source["sources"].items():
        if row["origin"]["kind"] == "file":
            path = row["origin"]["locator"]
            if path not in data or (row.get("content_sha256") is not None and sha(data[path]) != row["content_sha256"]):
                invalid("source file binding differs from current bytes", SOURCE_LEDGER + "/sources/" + sid)
        if row.get("ingested_at") is not None and row.get("content_sha256") is None:
            invalid("ingested source requires a content digest", SOURCE_LEDGER + "/sources/" + sid)
        if row["review_status"] == "active" and (row.get("retrieved_at") is None and row.get("ingested_at") is None or row.get("refresh_due") is None):
            invalid("active source requires observation and refresh dates", SOURCE_LEDGER + "/sources/" + sid)
    associations, decisions = list(docs["association"].values()), list(docs["decision"].values())
    display_heads = derive_display_heads(associations, decisions)
    paper_items = []
    consumed = set()
    for record in docs["paper"].values():
        pid = record["paper_id"]
        if any(sid not in source["sources"] for sid in record["source_ids"]):
            invalid("paper references a missing source", "/papers")
        owned = [c for c in claims if c["stable_subject_id"] == "paper:" + pid]
        group = {"record": record, "claims": owned,
                 "events": [e for e in events if e["claim_id"] in {c["claim_id"] for c in owned}]}
        if record["schema"] == PAPER:
            group["associations"] = [a for a in associations if a["paper_id"] == pid]
            group["display_decisions"] = [d for d in decisions if d["paper_id"] == pid]
            consumed.update(a["association_id"] for a in group["associations"])
        paper_items.append(group)
    if consumed != {a["association_id"] for a in associations}:
        invalid("association has no owning v2 paper record", "/associations")
    qualifying = _legacy_artifacts(docs, data, source["sources"])
    code = _code_groups(docs)
    _locators(claims, owners, docs, source["sources"], data, qualifying)
    for record in docs["paper"].values():
        if record["schema"] == LEGACY_PAPER:
            path = record["active_extraction_path"]
            if path not in qualifying or sha(data[path]) != record["active_extraction_sha256"]:
                invalid("legacy active extraction is not a qualifying actual parser artifact", "/papers/active_extraction_path")
    pages = {}
    if not structural:
        def subset(paths):
            result = {}
            for p in paths:
                if p not in data:
                    invalid("source material is unavailable: " + p, "/inventory/" + p)
                result[p] = data[p]
            return result
        material = {"schema": COMPILE, "operation_id": "source-state-compile", "papers": paper_items,
                    "code": code, "concepts": concept_items_for_papers(list(docs["paper"].values()))}
        pages = compile_pages(material,
            raw_sources=subset({a["raw"]["path"] for a in associations}),
            extraction_artifacts=subset({a["extraction"]["path"] for a in associations}),
            registration_ledgers=subset({a["registration"]["source_ledger_path"] for a in associations}),
            head_bytes=current_data[HEAD] if associations else None, receipt_bytes=receipts if associations else {})
        if require_rendered:
            actual_pages = {p: raw for p, raw in data.items() if p.startswith(("wiki/papers/", "wiki/code/", "wiki/concepts/"))}
            if actual_pages != pages:
                invalid("complete generated page set or bytes differ from the compiler", "/compiled_pages")
            if modern and (docs["assessment_heads"].get(ASSESSMENT_HEADS) != assessment_heads or docs["display_heads"].get(DISPLAY_HEADS) != display_heads):
                invalid("complete derived head registries differ", "/heads")
    return {"basis": {"operation_head_sha256": sha(current_data[HEAD]), "inventory_sha256": inventory_digest(current_inventory)},
            "inventory": inventory, "bytes": data, "current_inventory": current_inventory,
            "profile": "source-v1" if modern else "legacy-v1", "structural_only": structural,
            "source_ledger": source, "claim_ledger": ledger, "owners": owners, "claims": claims,
            "documents": docs, "assessment_heads": assessment_heads, "display_heads": display_heads,
            "pages": pages, "ledger_snapshots": snapshots, "chain": chain,
            "counts": {"files": len(data), "papers": len(docs["paper"]), "repos": len(docs["repo"]),
                       "claims": len(claims), "events": len(events), "associations": len(associations),
                       "display_decisions": len(decisions), "ledger_snapshots": len(snapshots), "compiled_pages": len(pages)}}


def preserve_history(current, prospective, writes, *, registration=False):
    """Bind immutability and owner preservation to actual current-state bytes."""
    old, new = current["bytes"], prospective["bytes"]
    for path, raw in writes.items():
        if path in old and kind_for_path(path) in IMMUTABLE and raw != old[path]:
            _conflict("immutable history bytes cannot be replaced", path)
    for role, key in (("paper", "paper_id"), ("repo", "repo_id")):
        for path, record in current["documents"][role].items():
            after = prospective["documents"][role].get(path)
            if after is None or after[key] != record[key]:
                _conflict("existing record path/identity cannot change", path)
            if role == "repo" and after != record:
                _conflict("repository changes require the CODE successor", path)
            if role == "paper":
                if record["schema"] == PAPER and after["schema"] != PAPER:
                    _conflict("paper schema cannot return to legacy", path)
                if record["aliases"] != after["aliases"]:
                    _conflict("existing aliases must retain their spelling and order", path)
                refs = {x["claim_id"]: x for x in after["section_claim_refs"]}
                for ref in record["section_claim_refs"]:
                    target = refs.get(ref["claim_id"])
                    if target is None or any(target[k] != v for k, v in ref.items() if k != "lifecycle") or (ref["lifecycle"] == "retired" and target["lifecycle"] != "retired"):
                        _conflict("existing claim references cannot be removed or rebound", path)
    old_claims, new_claims = current["claim_ledger"]["claims"], prospective["claim_ledger"]["claims"]
    for cid, row in old_claims.items():
        if cid not in new_claims or new_claims[cid]["text"] != row["text"] or current["owners"][cid] != prospective["owners"][cid]:
            _conflict("claim text and primary ownership are immutable", CLAIM_LEDGER + "/claims/" + cid)
    for cid in set(new_claims) - set(old_claims):
        if prospective["owners"][cid]["kind"] == "repo":
            _conflict("new repository claims require the CODE successor", CLAIM_LEDGER)
    if not registration:
        before, after = current["source_ledger"]["sources"], prospective["source_ledger"]["sources"]
        if set(before) != set(after):
            _conflict("knowledge publication cannot add or remove source identities", SOURCE_LEDGER)
        for sid, row in before.items():
            target = after[sid]
            for field in ("origin", "content_kind", "content_sha256", "ingested_at"):
                if (field in row) != (field in target) or row.get(field) != target.get(field):
                    _conflict("registered source identity fields are immutable", SOURCE_LEDGER + "/sources/" + sid)
            if target["pages"] != row["pages"]:
                if target["pages"] != sorted(set(target["pages"])) or not set(target["pages"]) <= prospective["pages"].keys():
                    invalid("changed source pages must be a sorted unique set of compiled pages", SOURCE_LEDGER)
        for path, record in prospective["documents"]["paper"].items():
            if old.get(path) == new[path]:
                continue
            page = "wiki/papers/" + paper_page_slug(record["paper_id"]) + ".md"
            for sid in record["source_ids"]:
                if page not in after[sid]["pages"]:
                    invalid("changed paper's source row lacks its page link", SOURCE_LEDGER)
        for cid, row in new_claims.items():
            if old_claims.get(cid) == row:
                continue
            for evidence in row["evidence"]:
                if prospective["owners"][cid]["page"] not in after[evidence["source_id"]]["pages"]:
                    invalid("changed evidence source lacks its owner page link", SOURCE_LEDGER)
    if old[SOURCE_LEDGER] != new[SOURCE_LEDGER]:
        path = ".raw/derived/source-ledgers/" + sha(old[SOURCE_LEDGER]) + ".json"
        if new.get(path) != old[SOURCE_LEDGER]:
            _conflict("source-ledger replacement must preserve the actual old snapshot", path)
    removed_pages = set(current["pages"]) - set(prospective["pages"])
    if removed_pages:
        fail("SOURCE_PUBLICATION_UNSUPPORTED_CHANGE", "page retirement requires a separate deletion path", "/compiled_pages", exit_code=75)
