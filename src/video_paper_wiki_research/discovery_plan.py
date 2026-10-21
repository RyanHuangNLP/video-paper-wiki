"""Deterministic bounded host request descriptions; this module performs no I/O."""
from __future__ import annotations

import copy
from urllib.parse import quote

from video_paper_wiki.jcs import canonicalize
from video_paper_wiki_research.discovery_candidates import (
    build_components, fact_key, identity_key,
)
from video_paper_wiki_research.discovery_contracts import (
    LENSES, OPERATIONS, PROVIDERS, fail, invalid, reference, resource_state,
    seal, source_url, spec_key, unique, unversioned, validate_spec,
)


def _keys(ids):
    return {identity_key(v) for v in ids}


def expanded_ids(ids, components):
    keys = _keys(ids)
    result = list(ids)
    for component in components.values():
        if keys & {canonicalize(v) for v in component["ids"]}:
            result.extend({**v, "version": None} for v in component["ids"])
    return unique(result)


def intersects(left, right, components):
    return bool(_keys(expanded_ids(left, components)) & _keys(expanded_ids(right, components)))


def selected_lineages(config, plans, observations, requests):
    lineages = []
    for plan in plans:
        sequence = plan["data"]["sequence"]
        prior = [o for o in observations if requests[o["data"]["request"]["id"]]["data"]["sequence"] < sequence]
        graph = build_components(config, prior, requests)
        for spec in plan["data"]["request_specs"]:
            if spec["subject_origin"] is None:
                continue
            matches = [l for l in lineages if intersects(spec["subject_ids"], l["initial_ids"], graph)]
            if matches:
                earliest = matches[0]
                if (spec["depth"], spec["seed_key"]) != (earliest["depth"], earliest["seed_key"]):
                    invalid("expanded request changes its durable seed or depth")
            else:
                if len(lineages) >= 3:
                    fail("DISCOVERY_LIMIT_EXCEEDED", "a fourth expansion selection is prohibited")
                lineages.append({"plan_sequence": sequence, "request_key": spec["request_key"],
                                 "origin": spec["subject_origin"], "initial_ids": spec["subject_ids"],
                                 "seed_key": spec["seed_key"], "depth": spec["depth"]})
    return lineages


def chosen_id(ids):
    for namespace in ("openalex", "doi", "arxiv"):
        choices = [v for v in ids if v["namespace"] == namespace]
        values = {v["value"] for v in choices}
        if len(values) > 1:
            fail("DISCOVERY_IDENTITY_UNRESOLVED", "subject has conflicting identifiers")
        if choices:
            return unique(choices)[0]
    invalid("request subject has no supported identifier")


def _lookup_query(value):
    if value["namespace"] == "arxiv":
        return value["value"] + ("v" + str(value["version"]) if value["version"] is not None else "")
    return value["value"]


def target(spec):
    validate_spec(spec)
    operation, provider = spec["operation"], spec["provider"]
    profile = resource_state()[2]["providers"][provider]
    if provider == PROVIDERS[1]:
        if operation not in profile["operations"] or spec["cursor"] is not None:
            fail("DISCOVERY_CAPABILITY_UNAVAILABLE", "Web profile does not support this operation or cursor")
        query = _lookup_query(chosen_id(spec["subject_ids"])) if operation == "lookup" else spec["query"]
        if query is None or len(query) > 2048:
            invalid("Web query is missing or too long")
        return {"kind": "web_search", "query": query, "max_results": spec["per_page"]}
    if operation == "project":
        fail("DISCOVERY_CAPABILITY_UNAVAILABLE", "OpenAlex profile has no project operation")
    base = profile["base_url"]
    select = profile["select"]
    if operation == "lookup":
        chosen = chosen_id(spec["subject_ids"])
        if chosen["namespace"] == "arxiv":
            fail("DISCOVERY_CAPABILITY_UNAVAILABLE", "OpenAlex has no direct arXiv singleton capability")
        suffix = chosen["value"] if chosen["namespace"] == "openalex" else "doi:" + quote(chosen["value"], safe="/-._~")
        url = base + "/" + suffix + "?select=" + quote(select, safe="-._~")
    else:
        params = []
        if operation == "topic":
            if spec["query"] is None:
                invalid("topic query is required")
            params.append(("search", spec["query"]))
        elif operation == "citations":
            values = {i["value"] for i in spec["subject_ids"] if i["namespace"] == "openalex"}
            if len(values) != 1:
                fail("DISCOVERY_CAPABILITY_UNAVAILABLE", "citations require one observed OpenAlex ID")
            params.append(("filter", profile["citation_filter"] + ":" + next(iter(values))))
        elif operation in {"references", "related"}:
            if not spec["neighbor_ids"] or any(v["namespace"] != "openalex" for v in spec["neighbor_ids"]):
                invalid("OpenAlex batch requires declared OpenAlex neighbor IDs")
            params.append(("filter", profile["batch_filter"] + ":" + "|".join(v["value"] for v in spec["neighbor_ids"])))
        else:
            invalid("unsupported operation")
        params += [("per_page", str(spec["per_page"])), ("select", select),
                   ("sort", profile["sort_topic"] if operation == "topic" else profile["sort_neighbors"])]
        if spec["cursor"] is not None:
            if operation not in profile["cursor_operations"]:
                fail("DISCOVERY_CAPABILITY_UNAVAILABLE", "operation has no cursor capability")
            params.append(("cursor", spec["cursor"]))
        url = base + "?" + "&".join(name + "=" + quote(value, safe="-._~") for name, value in params)
    if len(url.encode("ascii")) > 4094:
        fail("DISCOVERY_LIMIT_EXCEEDED", "regenerated OpenAlex target exceeds 4094 bytes")
    source_url(url)
    return {"kind": "http_get", "url": url}


def make_spec(**fields):
    spec = {"request_key": "0" * 64, **fields}
    spec["request_key"] = spec_key(spec)
    target(spec)
    return spec


def request_document(session, plan, slot):
    spec = plan["data"]["request_specs"][slot]
    return seal("discovery-request", {"session": reference(session), "sequence": plan["data"]["sequence"],
                "plan_id": plan["id"], "slot": slot, "request_key": spec["request_key"],
                "spec": spec, "target": target(spec)})


def query(config, seed, lens_name, operation):
    lens = next(v for v in config["lenses"] if v["lens"] == lens_name)
    parts = [config["question"], lens["scope"], *config["query_terms"], *lens["terms"]]
    if operation == "project":
        parts += [seed["title"], *seed["author_terms"], *seed["project_terms"]]
    value = " ".join(p for p in parts if p)
    if len(value) > 2048:
        fail("DISCOVERY_LIMIT_EXCEEDED", "declared query text exceeds 2048 characters")
    return value


def _attempted(spec, plans, components):
    fields = ("provider", "operation", "seed_key", "lens")
    return any(all(spec[k] == prior[k] for k in fields) and intersects(spec["subject_ids"], prior["subject_ids"], components)
               for plan in plans for prior in plan["data"]["request_specs"])


def _source(ids, components, *, singleton=False):
    keys = _keys(ids)
    matching = [c for c in components.values() if keys & {canonicalize(v) for v in c["ids"]}]
    observed = []
    all_openalex = {v["value"] for c in matching for v in c["ids"] if v["namespace"] == "openalex"}
    if len(all_openalex) != 1:
        return None, "observed_openalex_identity_unavailable_or_ambiguous"
    value = next(iter(all_openalex))
    for component in matching:
        if any(sum(v["namespace"] == ns for v in component["ids"]) > 1 for ns in ("arxiv", "doi", "openalex")):
            return None, "identity_conflicted"
        for fact in component["facts"]:
            if singleton and fact["spec"]["operation"] != "lookup":
                continue
            if any(v["namespace"] == "openalex" and v["value"] == value for v in fact["result"]["ids"]):
                observed.append(fact)
    if not observed:
        return None, "singleton_neighborhood_observation_unavailable" if singleton else "observed_openalex_identity_unavailable"
    return min(observed, key=fact_key), None


def frontier(config, plans, observations, requests, *, candidate_set=None, rank=None):
    components = build_components(config, observations, requests)
    selections = selected_lineages(config, plans, observations, requests)
    families, capabilities = {o: [] for o in OPERATIONS}, []
    seeds = sorted(config["seeds"], key=lambda s: s["key"])

    def add(seed, ids, origin, depth, operation, *, lens="method", provider=None):
        ids = expanded_ids(ids, components)
        available_namespaces = {v["namespace"] for v in ids}
        selected_provider = provider or (PROVIDERS[1] if operation == "project" or
            operation == "lookup" and not available_namespaces & {"openalex", "doi"} else PROVIDERS[0])
        def unavailable(reason):
            capabilities.append({"operation": operation, "seed_key": seed["key"],
                                 "subject_origin": origin, "subject_ids": ids, "lens": lens,
                                 "provider": selected_provider, "depth": depth, "reason": reason})
        if any(len({v["value"] for v in ids if v["namespace"] == namespace}) > 1
               for namespace in ("arxiv", "doi", "openalex")):
            unavailable("identity_conflicted")
            return False
        chosen_id(ids)
        probe = {"provider": selected_provider, "operation": operation, "seed_key": seed["key"],
                 "subject_ids": ids, "subject_origin": origin, "lens": lens, "depth": depth,
                 "query": query(config, seed, lens, operation) if operation in {"topic", "project"} else None,
                 "per_page": config["limits"]["per_page"], "cursor": None, "continuation": None,
                 "retry": None, "neighbor_ids": None}
        if _attempted(probe, plans, components):
            return False
        if operation in {"references", "citations", "related"}:
            source, reason = _source(ids, components, singleton=operation != "citations")
            if source is None:
                unavailable(reason)
                return False
            probe["continuation"] = source["observation"]
            if operation != "citations":
                field = "referenced_ids" if operation == "references" else "related_ids"
                neighbors = source["result"][field]
                if neighbors is None:
                    unavailable("neighbor_list_unavailable")
                    return False
                neighbors = unique([v for v in neighbors if v["namespace"] == "openalex"])
                if not neighbors:
                    unavailable("observed_neighbor_list_exhausted")
                    return False
                probe["neighbor_ids"] = neighbors[:probe["per_page"]]
        spec = make_spec(**probe)
        families[operation].append(spec)
        return True

    for seed in seeds:
        ids = expanded_ids(seed["ids"], components)
        # An observed matching DOI/OpenAlex record already supplies lookup
        # metadata. A plain lookup slot that failed remains attempted forever.
        observed_record = any(_keys(ids) & {canonicalize(v) for v in c["ids"]}
                              and any(v["namespace"] in {"doi", "openalex"} for v in c["ids"])
                              for c in components.values())
        if not observed_record:
            add(seed, seed["ids"], None, 0, "lookup")
        for operation in ("references", "citations", "related"):
            add(seed, seed["ids"], None, 0, operation, lens="counterevidence" if operation == "citations" else "method")
        if seed["author_terms"] or seed["project_terms"]:
            add(seed, seed["ids"], None, 0, "project", lens="implementation")
    for index, lens in enumerate(LENSES):
        for offset, provider in enumerate(PROVIDERS):
            seed = seeds[(index + offset) % len(seeds)]
            add(seed, seed["ids"], None, 0, "topic", lens=lens, provider=provider)

    if not any(families.values()) and candidate_set is not None and rank is not None:
        items = {i["candidate_key"]: i for i in candidate_set["data"]["items"]}
        tentative = 0
        for fused in rank["data"]["fused"]:
            item = items[fused["candidate_key"]]
            ids = unique([{**v, "version": None} for v in item["ids"]] + item["versions"])
            existing = [l for l in selections if intersects(ids, l["initial_ids"], components)]
            if existing:
                seed_key, depth = existing[0]["seed_key"], existing[0]["depth"]
            else:
                if len(selections) + tentative >= 3:
                    continue
                why = min(item["why_found"], key=lambda w: (w["depth"], w["seed_key"], canonicalize(w["request"])))
                seed_key, depth = why["seed_key"], why["depth"] + 1
            if depth > 2:
                continue
            seed = next(s for s in seeds if s["key"] == seed_key)
            origin = {"candidate_set": reference(candidate_set), "candidate_key": item["candidate_key"]}
            before = sum(len(v) for v in families.values())
            add(seed, ids, origin, depth, "lookup")
            for operation in ("references", "citations", "related"):
                add(seed, ids, origin, depth, operation, lens="counterevidence" if operation == "citations" else "method")
            if not existing and sum(len(v) for v in families.values()) > before:
                tentative += 1

    def order(spec):
        return (spec["depth"], spec["seed_key"], LENSES.index(spec["lens"]), PROVIDERS.index(spec["provider"]),
                canonicalize(spec["subject_ids"]), spec["request_key"])
    for family in families.values():
        family.sort(key=order)
    ordered_frontier = []
    while any(families.values()):
        for operation in OPERATIONS:
            if families[operation]:
                ordered_frontier.append(families[operation].pop(0))
    return {"specs": ordered_frontier, "capability_entries": unique(capabilities), "selection_lineages": selections}


def validate_explicit(specs, available, plans, observations, requests, config):
    if type(specs) is not list or not specs or len(specs) > config["limits"]["per_round_requests"]:
        invalid("explicit plan must contain a bounded nonempty specification set")
    known = {s["request_key"]: s for s in available["specs"]}
    seen = {s["request_key"] for p in plans for s in p["data"]["request_specs"]}
    observation_map = {o["id"]: o for o in observations}
    result, new_keys = [], set()
    for spec in specs:
        validate_spec(spec)
        if spec["request_key"] in new_keys or spec["request_key"] in seen:
            fail("DISCOVERY_CONFLICT", "explicit plan repeats a committed or current specification")
        new_keys.add(spec["request_key"])
        if spec["request_key"] in known:
            if spec != known[spec["request_key"]]:
                invalid("specification key collision")
            result.append(spec)
            continue
        old_ref = spec["retry"]["observation"] if spec["retry"] is not None else spec["continuation"]
        old = observation_map.get(old_ref["id"]) if old_ref is not None else None
        if old is None or reference(old) != old_ref:
            invalid("explicit extra request needs an exact prior terminal observation")
        prior = requests[old["data"]["request"]["id"]]["data"]["spec"]
        if spec["retry"] is not None:
            reasons = {"timeout": "timeout", "rate_limited": "rate_limited", "failure": "transient_failure",
                       "partial": "transient_failure", "capability_unavailable": "capability_changed"}
            if reasons.get(old["data"]["outcome"]) != spec["retry"]["reason"]:
                invalid("retry reason does not match the actual terminal outcome")
            base = copy.deepcopy(prior)
            base["retry"] = spec["retry"]
        elif spec["cursor"] is not None:
            payload = old["data"]["payload"]
            if (prior["operation"] not in {"topic", "citations"} or prior["provider"] != PROVIDERS[0]
                    or payload is None or payload["next_cursor"] is None or spec["cursor"] != payload["next_cursor"]):
                invalid("cursor does not equal the prior supported next_cursor")
            base = copy.deepcopy(prior)
            base.update(cursor=spec["cursor"], continuation=old_ref, retry=None)
        elif spec["operation"] in {"references", "related"} and spec["neighbor_ids"] is not None:
            # Slices bind the original singleton observation; locate the earlier
            # batch job with that exact provenance and immutable base fields.
            matches = [s for p in plans for s in p["data"]["request_specs"]
                       if s["operation"] == spec["operation"] and s["continuation"] == old_ref
                       and all(s[k] == spec[k] for k in ("provider", "seed_key", "lens", "subject_ids", "subject_origin", "depth", "per_page"))]
            if not matches or prior["operation"] != "lookup" or old["data"]["payload"] is None:
                invalid("neighbor slice lacks its original singleton and batch lineage")
            base = copy.deepcopy(matches[0])
            used = {identity_key(v) for s in matches for v in s["neighbor_ids"]}
            field = "referenced_ids" if spec["operation"] == "references" else "related_ids"
            sources = [r for r in old["data"]["payload"]["results"] if _keys(r["ids"]) & _keys(spec["subject_ids"])]
            if not sources or sources[0][field] is None:
                invalid("singleton neighborhood is unavailable")
            remaining = unique([v for v in sources[0][field] if v["namespace"] == "openalex" and identity_key(v) not in used])
            if not remaining or spec["neighbor_ids"] != remaining[:spec["per_page"]]:
                invalid("neighbor slice must be the exact unseen canonical prefix")
            base.update(neighbor_ids=spec["neighbor_ids"], retry=None)
        else:
            invalid("explicit specification is not eligible, a retry, a cursor or an unseen neighbor slice")
        base["request_key"] = spec_key(base)
        if base != spec:
            invalid("explicit continuation/retry changed its immutable base fields")
        target(spec)
        result.append(spec)
    return sorted(result, key=lambda s: s["request_key"])


def plan_document(session, sequence, previous_round, control_head, specs, prior_plans):
    total = sum(len(p["data"]["request_specs"]) for p in prior_plans) + len(specs)
    retry_slots = sum(s["retry"] is not None for p in prior_plans for s in p["data"]["request_specs"]) + sum(s["retry"] is not None for s in specs)
    return seal("research-round-plan", {"session": reference(session), "sequence": sequence,
                "previous_round": None if previous_round is None else reference(previous_round),
                "control_head": None if control_head is None else reference(control_head),
                "request_specs": sorted(specs, key=lambda s: s["request_key"]),
                "reservation_after": {"rounds_planned": sequence, "request_slots_reserved": total,
                                      "observation_slots_reserved": total, "retry_slots": retry_slots}})
