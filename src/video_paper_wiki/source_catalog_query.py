"""Deterministic multilingual lexical queries over a reconstructed catalog."""
from __future__ import annotations

import unicodedata
from collections import Counter

from video_paper_wiki.identity import is_canonical_paper_id
from video_paper_wiki.source_catalog_contracts import choice, integer, invalid, limit, text as exact_text


def _category(char):
    code = ord(char)
    if 0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF or 0x20000 <= code <= 0x2FA1F:
        return "han"
    if "a" <= char <= "z" or "0" <= char <= "9":
        return "ascii"
    if char.isalpha() or char.isdigit():
        return "other"
    return None


def normalize(text):
    return unicodedata.normalize("NFKC", text).casefold()


def tokens(text, *, normalized=False):
    value = text if normalized else normalize(text)
    output, run, previous = [], [], None
    def flush():
        if previous == "han":
            output.extend(run)
            output.extend(run[i] + run[i + 1] for i in range(len(run) - 1))
        elif run:
            output.append("".join(run))
    for char in value:
        category = _category(char)
        if category != previous or category is None:
            flush()
            run = []
        if category is not None:
            run.append(char)
        previous = category
    flush()
    return output


def query_parameters(text, scope, paper_id, assessment, lifecycle, limit_value, offset):
    value = exact_text(text, "/text")
    for stage in (value, normalize(value)):
        if len(stage) > 512 or len(stage.encode()) > 4096:
            limit("query exceeds its raw or normalized text bounds", "/text")
    terms = tokens(normalize(value), normalized=True)
    if not terms:
        invalid("query has no searchable tokens", "/text")
    if len(terms) > 1000:
        limit("query exceeds its token bound", "/text")
    choice(scope, {"claims", "source_excerpts", "all"}, "/scope")
    choice(assessment, {"all", "accepted", "provisional", "contested", "unsupported", "deprecated"}, "/assessment")
    choice(lifecycle, {"all", "active", "retired"}, "/lifecycle")
    if paper_id is not None:
        exact_text(paper_id, "/paper_id")
        if not is_canonical_paper_id(paper_id):
            invalid("paper filter requires a canonical identity", "/paper_id")
    integer(limit_value, "/limit", 1, 1000)
    integer(offset, "/offset", 0, 1000000)
    return Counter(terms)


def search(rows, query, *, scope, paper_id, assessment, lifecycle, limit, offset):
    repos = {r["repo_id"]: r for r in rows["repositories"]}
    selected = {}
    for claim in rows["claims"]:
        if assessment != "all" and claim["assessment"] != assessment:
            continue
        if lifecycle != "all" and claim["reference"]["lifecycle"] != lifecycle:
            continue
        if paper_id is not None:
            if claim["owner_kind"] == "paper" and claim["owner_id"] != paper_id:
                continue
            if claim["owner_kind"] == "repo" and paper_id not in repos[claim["owner_id"]]["paper_ids"]:
                continue
        selected[claim["claim_id"]] = claim
    hits, query_count = [], sum(query.values())
    def add(kind, claim, text, evidence=None):
        document = Counter(tokens(text))
        overlap = sum(min(count, document[token]) for token, count in query.items())
        if not overlap:
            return
        score = 2000000 * overlap // (query_count + sum(document.values()))
        if not score:
            return
        hits.append({"kind": kind, "claim_id": claim["claim_id"], "owner_kind": claim["owner_kind"],
            "owner_id": claim["owner_id"], "source_id": None if evidence is None else evidence["source_id"],
            "association_id": None if evidence is None else evidence["association_id"],
            "display_association_id": None if evidence is None else evidence["display_association_id"],
            "evidence_ordinal": None if evidence is None else evidence["ordinal"], "text": text, "score": score,
            "assessment": claim["assessment"], "lifecycle": claim["reference"]["lifecycle"]})
    if scope in {"all", "claims"}:
        for claim in selected.values():
            add("claims", claim, claim["text"])
    if scope in {"all", "source_excerpts"}:
        for evidence in rows["evidence"]:
            if evidence["claim_id"] in selected and evidence["resolution"]["state"] == "RESOLVED":
                add("source_excerpts", selected[evidence["claim_id"]], evidence["resolution"]["excerpt"], evidence)
    hits.sort(key=lambda x: (-x["score"], x["kind"] != "claims", x["claim_id"].encode(),
                             -1 if x["evidence_ordinal"] is None else x["evidence_ordinal"]))
    return {"hits": hits[offset:offset + limit], "total_matches": len(hits), "offset": offset, "limit": limit,
            "next_offset": offset + limit if offset + limit < len(hits) else None}


def lookup(rows, kind, key):
    group, identity = {"paper": ("papers", "paper_id"), "repository": ("repositories", "repo_id"),
                       "source": ("sources", "source_id"), "claim": ("claims", "claim_id")}[kind]
    def matches(row):
        if row[identity] == key:
            return True
        if kind == "paper":
            return key in [row["title"], row["title_zh"], *row["aliases"]]
        return kind == "repository" and key.casefold() == row["canonical_repository"].casefold()
    found = [r for r in rows[group] if matches(r)]
    ids = {r[identity] for r in found}
    cids = set()
    sids = set(ids) if kind == "source" else set()
    for claim in rows["claims"]:
        if (kind == "claim" and claim["claim_id"] in ids
                or kind == "paper" and claim["owner_kind"] == "paper" and claim["owner_id"] in ids
                or kind == "repository" and claim["owner_kind"] == "repo" and claim["owner_id"] in ids):
            cids.add(claim["claim_id"])
    if kind == "paper":
        for paper in found:
            sids.update(paper["source_ids"])
        related = {r["repo_id"] for r in rows["repositories"] if set(r["paper_ids"]) & ids}
        cids.update(c["claim_id"] for c in rows["claims"] if c["owner_kind"] == "repo" and c["owner_id"] in related)
    evidence = [e for e in rows["evidence"] if e["claim_id"] in cids or kind == "source" and e["source_id"] in ids]
    sids.update(e["source_id"] for e in evidence)
    return {"kind": kind, "key": key, "matches": found, "evidence": evidence,
            "coverage": [r for r in rows["coverage"] if set(r["source_ids"]) & sids],
            "associations": [r for r in rows["associations"] if r["document"]["source_id"] in sids]}
