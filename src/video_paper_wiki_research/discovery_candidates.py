"""Pure identity components, provenance, mirror-aware ranks and round metrics."""
from __future__ import annotations

import unicodedata
from fractions import Fraction

from video_paper_wiki.jcs import canonicalize
from video_paper_wiki_research.discovery_contracts import (
    ordered, reference, seal, sha, source_url, unique, unversioned,
)


class Components:
    def __init__(self):
        self.parents = {}

    def find(self, value):
        self.parents.setdefault(value, value)
        root = value
        while self.parents[root] != root:
            root = self.parents[root]
        while self.parents[value] != value:
            parent = self.parents[value]
            self.parents[value] = root
            value = parent
        return root

    def join(self, left, right):
        a, b = self.find(left), self.find(right)
        if a != b:
            self.parents[max(a, b)] = min(a, b)


def identity_key(value):
    return canonicalize(unversioned(value))


def fact_key(fact):
    return canonicalize(fact["observation"]), fact["result"]["ordinal"]


def fact_ref(fact):
    return {"observation": fact["observation"], "ordinal": fact["result"]["ordinal"]}


def list_key(spec):
    return {key: spec[key] for key in ("provider", "seed_key", "lens", "operation")}


def normalized_term(value):
    return unicodedata.normalize("NFC", value.lower())


def matching_terms(config, spec, result):
    lens = next(v for v in config["lenses"] if v["lens"] == spec["lens"])
    terms = list(config["query_terms"]) + lens["terms"]
    if spec["operation"] == "project":
        seed = next(v for v in config["seeds"] if v["key"] == spec["seed_key"])
        terms += seed["author_terms"] + seed["project_terms"]
    texts = [normalized_term(result[field]) for field in ("title", "summary") if result[field] is not None]
    return unique([normalized_term(term) for term in terms
                   if any(normalized_term(term) in text for text in texts)])


def signals(facts):
    counts = [f["result"]["cited_by_count"] for f in facts if f["result"]["cited_by_count"] is not None]
    dates = [f["result"]["published_at"] for f in facts if f["result"]["published_at"] is not None]
    return {"min_depth": min(f["spec"]["depth"] for f in facts),
            "max_cited_by_count": max(counts) if counts else None,
            "latest_published_at": max(dates) if dates else None}


def build_components(config, observations, requests):
    """Join only shared identifiers and explicit same_work edges, across all facts."""
    groups, identifiers, facts = Components(), {}, []
    for observation in sorted(observations, key=lambda d: canonicalize(reference(d))):
        data = observation["data"]
        if data["payload"] is None:
            continue
        request = requests[data["request"]["id"]]
        spec = request["data"]["spec"]
        for result in data["payload"]["results"]:
            for value in result["ids"]:
                key = identity_key(value)
                identifiers[key] = unversioned(value)
                groups.find(key)
            for link in result["identity_links"]:
                if link["relation"] == "same_work":
                    groups.join(identity_key(link["left"]), identity_key(link["right"]))
            facts.append({"observation": reference(observation), "request": reference(request),
                          "spec": spec, "result": result,
                          "matched_terms": matching_terms(config, spec, result)})
    components = {}
    for key in identifiers:
        components.setdefault(groups.find(key), {"ids": [], "facts": []})["ids"].append(identifiers[key])
    for fact in facts:
        for root in {groups.find(identity_key(value)) for value in fact["result"]["ids"]}:
            components[root]["facts"].append(fact)
    result = {}
    for component in components.values():
        ids = unique(component["ids"])
        key = sha(canonicalize(ids))
        result[key] = {"ids": ids, "facts": sorted(component["facts"], key=fact_key)}
    return dict(sorted(result.items()))


def candidate_items(components):
    result = []
    for key, component in components.items():
        ids, facts = component["ids"], component["facts"]
        idkeys = {canonicalize(v) for v in ids}
        versions = unique([v for f in facts for v in f["result"]["ids"]
                           if v["namespace"] == "arxiv" and identity_key(v) in idkeys])
        conflicts = []
        for namespace in ("arxiv", "doi", "openalex"):
            local = [v for v in ids if v["namespace"] == namespace]
            if len(local) > 1:
                refs = unique([fact_ref(f) for f in facts if any(
                    v["namespace"] == namespace and identity_key(v) in idkeys for v in f["result"]["ids"])])
                conflicts.append({"namespace": namespace, "ids": local, "facts": refs})
        why = [{"request": f["request"], "observation": f["observation"],
                "ordinal": f["result"]["ordinal"], "locator": f["result"]["locator"],
                "seed_key": f["spec"]["seed_key"], "lens": f["spec"]["lens"],
                "relation": f["result"]["relation"], "matched_terms": f["matched_terms"],
                "depth": f["spec"]["depth"]} for f in facts]
        terms = unique([term for f in facts for term in f["matched_terms"]])
        titles = [f["result"]["title"] for f in facts if f["result"]["title"]]
        result.append({"candidate_key": key, "ids": ids, "versions": versions,
                       "title": titles[0] if titles else None, "conflicts": ordered(conflicts),
                       "why_found": unique(why), "relevance": {"relevant": bool(terms),
                       "matched_terms": terms, "assessment": "provisional_scientific_assessment"},
                       "signals": signals(facts)})
    return sorted(result, key=lambda v: v["candidate_key"])


def _list_order(entry):
    signal = entry["signals"]
    count, date = signal["max_cited_by_count"], signal["latest_published_at"]
    # YYYY-MM-DD has lexicographic calendar order; negate its integer digits
    # for descending order while keeping unavailable dates after known dates.
    return (not bool(entry["matched_terms"]), -len(entry["matched_terms"]), signal["min_depth"],
            count is None, -(count or 0), date is None, -int(date.replace("-", "")) if date else 0,
            entry["best_ordinal"], entry["candidate_key"])


def mirror_classes(facts):
    components, locators, labels = Components(), {}, {}
    for index, fact in enumerate(facts):
        components.find(index)
        locator = source_url(fact["result"]["locator"], grouping=True)
        if locator in locators:
            components.join(index, locators[locator])
        locators[locator] = index
        mirror = fact["result"]["mirror"]
        if mirror["provenance"] != "unknown":
            group = mirror["group"]
            if group in labels:
                components.join(index, labels[group])
            labels[group] = index
    sets = {}
    for i in range(len(facts)):
        sets.setdefault(components.find(i), []).append(facts[i])
    classes, lookup = [], {}
    for members in sets.values():
        citations = unique([fact_ref(f) for f in members])
        labels = unique([f["result"]["mirror"]["group"] for f in members
                         if f["result"]["mirror"]["provenance"] != "unknown"])
        item = {"class_key": sha(canonicalize(citations)), "known": bool(labels),
                "group_labels": labels, "facts": citations}
        classes.append(item)
        for member in members:
            lookup[fact_key(member)] = item
    return sorted(classes, key=lambda c: c["class_key"]), lookup


def rank_candidates(config, components, items):
    eligible = {i["candidate_key"] for i in items if not i["conflicts"]}
    buckets = {}
    for candidate in eligible:
        for fact in components[candidate]["facts"]:
            key = list_key(fact["spec"])
            bucket = buckets.setdefault(canonicalize(key), {"key": key, "candidates": {}})
            bucket["candidates"].setdefault(candidate, []).append(fact)
    lists, ranks = [], {}
    for wirekey, bucket in sorted(buckets.items()):
        entries = []
        for candidate, facts in bucket["candidates"].items():
            entries.append({"candidate_key": candidate, "rank": 1,
                            "matched_terms": unique([t for f in facts for t in f["matched_terms"]]),
                            "signals": signals(facts), "best_ordinal": min(f["result"]["ordinal"] for f in facts)})
        entries.sort(key=_list_order)
        for rank, entry in enumerate(entries, 1):
            entry["rank"] = rank
            ranks[(wirekey, entry["candidate_key"])] = rank
        lists.append({"key": bucket["key"], "entries": entries})
    fused = []
    for candidate in sorted(eligible):
        facts = components[candidate]["facts"]
        classes, lookup = mirror_classes(facts)
        provisional, suppressed = [], []
        for wirekey, bucket in sorted(buckets.items()):
            local = bucket["candidates"].get(candidate)
            if local is None:
                continue
            ranked = sorted(local, key=lambda f: (not lookup[fact_key(f)]["known"],
                             lookup[fact_key(f)]["class_key"], fact_key(f)))
            for index, fact in enumerate(ranked):
                mirror = lookup[fact_key(fact)]
                term = {"list_key": bucket["key"], "rank": ranks[(wirekey, candidate)],
                        "class_key": mirror["class_key"], "fact": fact_ref(fact),
                        "reason": None if index == 0 else "same_list_candidate"}
                if index == 0:
                    provisional.append(term)
                else:
                    suppressed.append(term)
        def term_key(term):
            return (term["rank"], canonicalize(term["list_key"]), term["class_key"],
                    canonicalize(term["fact"]["observation"]), term["fact"]["ordinal"])
        known = {c["class_key"] for c in classes if c["known"]}
        has_known = any(t["class_key"] in known for t in provisional)
        kept, used, unknown_used = [], set(), False
        for term in sorted(provisional, key=term_key):
            key, reason = term["class_key"], None
            if key in known:
                if key in used:
                    reason = "same_mirror_class"
                else:
                    used.add(key)
            elif has_known:
                reason = "independence_unknown_with_known"
            elif unknown_used:
                reason = "independence_unknown_duplicate"
            else:
                unknown_used = True
            if reason:
                suppressed.append({**term, "reason": reason})
            else:
                kept.append(term)
        score = sum((Fraction(1, config["ranking"]["rrf_k"] + t["rank"]) for t in kept), Fraction())
        fused.append({"candidate_key": candidate, "numerator": str(score.numerator),
                      "denominator": str(score.denominator),
                      "score": config["ranking"]["score_scale"] * score.numerator // score.denominator,
                      "classes": classes, "contributions": kept,
                      "suppressed": sorted(suppressed, key=lambda t: (*term_key(t), t["reason"]))})
    fused.sort(key=lambda v: (-Fraction(int(v["numerator"]), int(v["denominator"])), v["candidate_key"]))
    return lists, fused


def projections(config, session, plan, observations, requests):
    refs = unique([reference(v) for v in observations])
    common = {"session": reference(session), "sequence": plan["data"]["sequence"],
              "plan_id": plan["id"], "input_set_sha256": sha(canonicalize(refs))}
    components = build_components(config, observations, requests)
    items = candidate_items(components)
    candidates = seal("paper-candidate-set", {**common, "observations": refs, "items": items})
    lists, fused = rank_candidates(config, components, items)
    rank = seal("paper-rank", {**common, "candidate_set": reference(candidates), "lists": lists, "fused": fused})
    return candidates, rank, components


def identifiers_in(observations):
    return {identity_key(v) for o in observations if o["data"]["payload"] is not None
            for r in o["data"]["payload"]["results"] for v in r["ids"]}


def round_counts(components, previous_observations, current_observations):
    previous_ids = identifiers_in(previous_observations)
    current_refs = {canonicalize(reference(o)) for o in current_observations}
    total, repeated, new, relevant = 0, 0, 0, 0
    for component in components.values():
        intersects = any(canonicalize(i) in previous_ids for i in component["ids"])
        current = [f for f in component["facts"] if canonicalize(f["observation"]) in current_refs]
        total += len(current)
        repeated += len(current) if intersects else max(0, len(current) - 1)
        if current and not intersects:
            new += 1
            relevant += any(f["matched_terms"] for f in current)
    return {"total_hits": total, "repeated_hits": repeated, "new_components": new, "new_relevant": relevant}
