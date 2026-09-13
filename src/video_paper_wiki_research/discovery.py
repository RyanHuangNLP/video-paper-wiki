"""Public, zero-egress discovery workflow over one immutable retained graph."""
from __future__ import annotations

import html
from contextlib import contextmanager

from video_paper_wiki.jcs import canonicalize
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.discovery_contracts import (
    CAPS, KINDS, config_input as normalize_config, fail, invalid, reference,
    resource_state, seal, sha, timestamp, unique, validate_shape,
)
from video_paper_wiki_research.discovery_graph import Graph, budget, validate_budget
from video_paper_wiki_research.discovery_plan import frontier, plan_document, selected_lineages, validate_explicit
from video_paper_wiki_research.discovery_storage import open_store


def _sync(store):
    graph = store.graph
    store.pending_plan = graph.pending_plan
    store.preflight()
    return graph


@contextmanager
def _session(session):
    with open_store(session) as store:
        yield store, _sync(store)


def _initialized(graph):
    if graph.session is None:
        fail("DISCOVERY_PENDING", "initialize the complete discovery session first")


def _active(graph):
    if graph.user_stopped:
        fail("DISCOVERY_STOPPED", "explicit user_stop is active; record an explicit resume control first")


def _artifact(store, document):
    return {"reference": reference(document),
            "path": str(store.root / KINDS[document["kind"]] / store.filename(document))}


def _choose(store, graph, specs=None):
    available = frontier(graph.config, graph.plans, graph.observations, graph.requests,
                         candidate_set=graph.candidates, rank=graph.rank)
    bounds = graph.config["limits"]
    reserved = graph.current_budget()["request_slots_reserved"]
    count = min(bounds["per_round_requests"], bounds["requests"] - reserved, bounds["observations"] - reserved)
    if specs is not None:
        selected = validate_explicit(specs, available, graph.plans, graph.observations, graph.requests, graph.config)
        choices = [selected]
    else:
        choices = [available["specs"][:n] for n in range(min(count, len(available["specs"])), 0, -1)]
    selected_plan, limiting = None, []
    for selected in choices:
        try:
            if len(selected) > count:
                fail("DISCOVERY_LIMIT_EXCEEDED", "explicit plan exceeds remaining slot reservations")
            proposal = plan_document(graph.session, len(graph.plans) + 1, graph.last_event,
                                     graph.control_head, selected, graph.plans)
            value = budget(graph.plans + [proposal], len(graph.events), graph.requests, graph.observations,
                           graph.candidate_slots, graph.component_count)
            validate_budget(value, graph.config)
            physical = store.capacity([proposal], pending_plan=proposal)
            if not physical["fits"]:
                limiting.extend(physical["limiting_bounds"])
                continue
            selected_plan = proposal
            break
        except ResearchError as exc:
            if specs is not None or exc.code != "DISCOVERY_LIMIT_EXCEEDED":
                raise
            limiting.append(exc.details.get("field", exc.message))
    if specs is not None and selected_plan is None:
        fail("DISCOVERY_LIMIT_EXCEEDED", "explicit specification set cannot fit", limiting_bounds=unique(limiting))
    chosen = 0 if selected_plan is None else len(selected_plan["data"]["request_specs"])
    if selected_plan is None and available["specs"] and not limiting:
        limiting.append("request_or_observation_slots" if count <= 0 else "round_or_plan_bounds")
    return {"plan": selected_plan, "available_frontier_count": len(available["specs"]),
            "chosen_count": chosen, "omitted_count": max(0, len(available["specs"]) - chosen),
            "limiting_bounds": unique(limiting), "capability_entries": available["capability_entries"],
            "selection_lineages": available["selection_lineages"]}


def _status(store, graph):
    base = graph.base_state
    planning = None
    if base in {"session_ready", "complete_continue"} and not graph.user_stopped:
        planning = _choose(store, graph)
        if planning["plan"] is None:
            base = "needs_scope" if not planning["available_frontier_count"] else "calculated_stopped"
    reasons = [] if not graph.stops else list(graph.stops[-1]["data"]["matched_reasons"])
    if planning is not None and planning["available_frontier_count"] and planning["plan"] is None:
        reasons = unique(reasons + ["budget_exhausted"])
    if graph.user_stopped:
        reasons = ["user_stop", *reasons]
    effective = "user_stopped" if graph.user_stopped else base
    remaining = None
    if graph.config is not None:
        used = graph.current_budget()
        limits = graph.config["limits"]
        remaining = {"rounds": limits["rounds"] - used["rounds_planned"],
                     "requests": limits["requests"] - used["request_slots_reserved"],
                     "observations": limits["observations"] - used["observation_slots_reserved"],
                     "candidate_slots": limits["unique_candidates"] - used["candidate_slots_reserved"],
                     "results": limits["total_results"] - used["result_records"],
                     "payload_bytes": limits["total_payload_bytes"] - used["normalized_payload_bytes"]}
    completed_assessment = None if graph.last_event is None else graph.documents[
        graph.last_event["data"]["assessment"]["id"]]
    return {"session_key": store.session, "base_state": base, "effective_state": effective,
            "session": None if graph.session is None else _artifact(store, graph.session),
            "control_head": None if graph.control_head is None else reference(graph.control_head),
            "last_complete_round": None if graph.last_event is None else reference(graph.last_event),
            "pending_plan": None if graph.pending_plan is None else reference(graph.pending_plan),
            "missing_requests": [reference(d) for d in graph.missing_requests],
            "missing_observations": unique(graph.missing_observations),
            "assessment_required": graph.base_state == "assessment_required",
            "budget": graph.current_budget(), "remaining_budgets": remaining,
            "pending_candidate_introductions": graph.pending_introductions,
            "selection_lineages": [] if graph.config is None else selected_lineages(
                graph.config, graph.plans, graph.observations, graph.requests),
            "physical": store.capacity(), "matched_reasons": reasons,
            "next_action": "stop" if reasons else "needs_scope" if base == "needs_scope" else
                "initialize" if base == "absent" else "resume" if base in {"init_pending", "projection_pending", "plan_pending_requests"} else
                "observe" if base == "plan_pending_observations" else "assess" if base == "assessment_required" else "plan",
            "planning": None if planning is None else {k: v for k, v in planning.items() if k != "plan"},
            "candidate_set": None if graph.candidates is None else _artifact(store, graph.candidates),
            "rank": None if graph.rank is None else _artifact(store, graph.rank),
            "last_completed_assessment": _assessment_summary(store, completed_assessment),
            "pending_assessment": _assessment_summary(store, graph.assessment),
            "last_completed_stop": None if not graph.stops else {
                "artifact": _artifact(store, graph.stops[-1]),
                "round_sequence": graph.stops[-1]["data"]["sequence"],
                "metrics": graph.stops[-1]["data"]["metrics"]},
            "operation_health": _operation_health(graph),
            "scientific_assessment": "provisional_scientific_assessment", "formal_admission": False}


def _assessment_summary(store, document):
    if document is None:
        return None
    data = document["data"]
    return {"artifact": _artifact(store, document), "round_sequence": data["sequence"],
            "plan_id": data["plan_id"], "input_set_sha256": data["input_set_sha256"],
            "generator": data["generator"], "recorded_at": data["recorded_at"],
            "lenses": data["lenses"]}


def _operation_health(graph):
    requests = {(r["data"]["sequence"], r["data"]["slot"]): r for r in graph.requests.values()}
    observations = {o["data"]["request"]["id"]: o for o in graph.observations}
    result = []
    for plan in graph.plans:
        for slot, spec in enumerate(plan["data"]["request_specs"]):
            sequence = plan["data"]["sequence"]
            request = requests.get((sequence, slot))
            observation = None if request is None else observations.get(request["id"])
            result.append({"round_sequence": sequence, "slot": slot,
                           "request_key": spec["request_key"], "provider": spec["provider"],
                           "operation": spec["operation"], "lens": spec["lens"],
                           "request": None if request is None else reference(request),
                           "observation": None if observation is None else reference(observation),
                           "state": "request_pending" if request is None else
                               "observation_pending" if observation is None else "terminal",
                           "outcome": None if observation is None else observation["data"]["outcome"],
                           "failure": None if observation is None else observation["data"]["failure"]})
    return result


def init(*, session, config_input):
    with _session(session) as (store, graph):
        _active(graph)
        value = store.input(config_input, maximum=CAPS["research-config"])
        config = seal("research-config", normalize_config(value))
        session_doc = seal("research-session", {"session_key": session, "config": reference(config)})
        if graph.config_doc is not None and graph.config_doc != config:
            fail("DISCOVERY_CONFLICT", "session was initialized with different immutable inputs")
        store.preflight([config, session_doc])
        store.install(config)
        store.install(session_doc)
        return _status(store, _sync(store))


def status(*, session):
    with _session(session) as (store, graph):
        return _status(store, graph)


def plan(*, session, specs_input=None):
    with _session(session) as (store, graph):
        _initialized(graph)
        _active(graph)
        supplied = None if specs_input is None else store.input(specs_input, maximum=CAPS["research-round-plan"])
        if graph.pending_plan is not None:
            if supplied is not None:
                expected = graph.pending_plan["data"]["request_specs"]
                if type(supplied) is not list or sorted(supplied, key=lambda s: canonicalize(s)) != sorted(expected, key=canonicalize):
                    fail("DISCOVERY_CONFLICT", "pending plan has different committed specifications")
            for request in graph.missing_requests:
                store.install(request)
            return _status(store, _sync(store))
        if graph.stops and graph.stops[-1]["data"]["primary_reason"] is not None:
            fail("DISCOVERY_STOPPED", "calculated stopping conditions prevent a new plan")
        choice = _choose(store, graph, supplied)
        if choice["plan"] is None:
            return _status(store, graph)
        pending = choice["plan"]
        # Reserve the complete plan before its first create-only installation.
        store.preflight([pending], pending_plan=pending)
        store.pending_plan = pending
        store.install(pending)
        graph = _sync(store)
        for request in graph.missing_requests:
            store.install(request)
        return _status(store, _sync(store))


def observe(*, session, request, observation_input):
    with _session(session) as (store, graph):
        _initialized(graph)
        _active(graph)
        if request not in graph.requests:
            invalid("request must be an installed exact discovery request id")
        request_doc = graph.requests[request]
        value = store.input(observation_input, maximum=CAPS["discovery-observation"])
        if type(value) is not dict or set(value) != {"observed_at", "executor", "outcome", "payload", "failure"}:
            invalid("observation input must contain exactly the normalized observation fields")
        observation = seal("discovery-observation", {"request": reference(request_doc), **value})
        prior = [o for o in graph.observations if o["data"]["request"] == reference(request_doc)]
        if prior:
            if prior[0] != observation:
                fail("DISCOVERY_CONFLICT", "request already has a different terminal observation")
            return _status(store, graph)
        if graph.pending_plan is None or request_doc["data"]["plan_id"] != graph.pending_plan["id"]:
            fail("DISCOVERY_PENDING", "new observation must fill the pending plan")
        # Graph construction includes tentative candidate/rank serialized bounds
        # and strict cumulative introductions before the observation is installed.
        Graph({**store.documents, observation["id"]: observation}, session)
        store.install(observation)
        return _status(store, _sync(store))


def _repair(store, graph):
    for document in graph.missing_requests:
        store.install(document)
    graph = _sync(store)
    for document in graph.pending_projection:
        store.install(document)
    return _sync(store)


def finish(*, session, assessment_input):
    with _session(session) as (store, graph):
        _initialized(graph)
        _active(graph)
        if graph.pending_plan is not None and (graph.missing_requests or graph.missing_observations):
            return _status(store, graph)
        plan_doc = graph.pending_plan or (graph.plans[-1] if graph.plans else None)
        if plan_doc is None:
            fail("DISCOVERY_PENDING", "no round is ready for an assessment")
        value = store.input(assessment_input, maximum=CAPS["research-assessment"])
        validate_shape(value, "assessment_input", definition=True)
        refs = unique([reference(o) for o in graph.observations])
        assessment = seal("research-assessment", {"session": reference(graph.session), "sequence": plan_doc["data"]["sequence"],
                          "plan_id": plan_doc["id"], "input_set_sha256": sha(canonicalize(refs)), "observations": refs, **value})
        if graph.pending_plan is None:
            existing = graph.documents[graph.last_event["data"]["assessment"]["id"]]
            if existing != assessment:
                fail("DISCOVERY_CONFLICT", "completed round has a different assessment")
            return _status(store, graph)
        if graph.assessment is not None and graph.assessment != assessment:
            fail("DISCOVERY_CONFLICT", "pending projections bind a different assessment")
        prospective = Graph({**store.documents, assessment["id"]: assessment}, session)
        store.preflight([assessment, *prospective.pending_projection])
        store.install(assessment)
        return _status(store, _repair(store, _sync(store)))


def resume(*, session):
    with _session(session) as (store, graph):
        _active(graph)
        if graph.base_state == "init_pending":
            store.install(seal("research-session", {"session_key": session, "config": reference(graph.config_doc)}))
            graph = _sync(store)
        elif graph.pending_plan is not None:
            graph = _repair(store, graph)
        return _status(store, graph)


def context(*, session):
    with _session(session) as (store, graph):
        result = _status(store, graph)
        if graph.session is None:
            return {**result, "assessment_context": None}
        raw = resource_state()[3]["prompts/discovery-assessment-v1.md"]
        refs = unique([reference(o) for o in graph.observations])
        return {**result, "assessment_context": {"config": graph.config, "session": reference(graph.session),
                "plan": graph.pending_plan, "input_set_sha256": sha(canonicalize(refs)), "observation_refs": refs,
                "observations": sorted(graph.observations, key=lambda o: canonicalize(reference(o))),
                "requests": sorted(graph.requests.values(), key=lambda r: (r["data"]["sequence"], r["data"]["slot"])),
                "prompt": raw.decode("utf-8"), "prompt_sha256": sha(raw),
                "assessment_schema": "research-assessment.v1/assessment_input",
                "operation_health": [{"request": o["data"]["request"], "outcome": o["data"]["outcome"], "failure": o["data"]["failure"]} for o in graph.observations]}}


def _user_record(event_id, user_text, source, recorded_at):
    record = {"event_id": event_id, "text": user_text, "source": source, "recorded_at": recorded_at}
    validate_shape(record, "user_record", definition=True)
    timestamp(recorded_at)
    return record


def control(*, session, action, event_id, user_text, source, recorded_at):
    with _session(session) as (store, graph):
        _initialized(graph)
        record = _user_record(event_id, user_text, source, recorded_at)
        if action not in {"user_stop", "resume"}:
            invalid("control action must be user_stop or resume")
        previous = graph.control_head
        for old in graph.controls + graph.decisions:
            if old["data"]["user_record"]["event_id"] == event_id:
                if old["kind"] == "research-control-event" and old["data"]["action"] == action and old["data"]["user_record"] == record:
                    return _status(store, graph)
                fail("DISCOVERY_CONFLICT", "event id was used for different action, target or text")
        if (action == "user_stop") == graph.user_stopped:
            fail("DISCOVERY_CONFLICT", "redundant control or resume without an active user_stop")
        document = seal("research-control-event", {"session": reference(graph.session), "sequence": len(graph.controls) + 1,
                        "previous": None if previous is None else reference(previous),
                        "round": None if graph.last_event is None else reference(graph.last_event),
                        "action": action, "user_record": record})
        Graph({**store.documents, document["id"]: document}, session)
        store.install(document)
        return _status(store, _sync(store))


def decide(*, session, candidate_set, candidate_key, action, selected_arxiv, event_id, user_text, source, recorded_at):
    with _session(session) as (store, graph):
        _initialized(graph)
        record = _user_record(event_id, user_text, source, recorded_at)
        snapshot = graph.documents.get(candidate_set)
        event = next((e for e in graph.events if e["data"]["candidate_set"]["id"] == candidate_set), None)
        if snapshot is None or event is None:
            invalid("candidate selection must reference a completed snapshot")
        selected = None
        if selected_arxiv is not None:
            from video_paper_wiki_research.discovery_contracts import identifier
            selected = identifier({"namespace": "arxiv", "value": selected_arxiv, "version": None}, normalize=True)
        fields = {"round": reference(event), "candidate_set": reference(snapshot), "candidate_key": candidate_key,
                  "action": action, "selected_arxiv": selected, "user_record": record}
        for old in graph.controls + graph.decisions:
            if old["data"]["user_record"]["event_id"] == event_id:
                if old["kind"] == "candidate-decision" and all(old["data"][k] == v for k, v in fields.items()):
                    return {**_status(store, graph), "decision": _artifact(store, old)}
                fail("DISCOVERY_CONFLICT", "event id was used for a different decision")
        document = seal("candidate-decision", {"session": reference(graph.session), "sequence": len(graph.decisions) + 1,
                        "previous": None if not graph.decisions else reference(graph.decisions[-1]), **fields})
        Graph({**store.documents, document["id"]: document}, session)
        store.install(document)
        return {**_status(store, _sync(store)), "decision": _artifact(store, document)}


def handoff(*, session, decision):
    with _session(session) as (store, graph):
        document = next((d for d in graph.decisions if d["id"] == decision), None)
        if document is None:
            invalid("handoff needs an existing exact candidate decision id")
        if document["data"]["action"] != "preview":
            return {"decision": reference(document), "handoff": None, "writes_preview_subtree": False}
        from importlib import resources
        from referencing import Registry, Resource
        from video_paper_wiki_research.contracts import _Validator
        from video_paper_wiki_research.discovery_contracts import parse_json
        from video_paper_wiki_research.paper_preview import make_request
        from video_paper_wiki_research.preview_contracts import SCHEMA_FILES as PREVIEW_SCHEMAS
        from video_paper_wiki_research.preview_contracts import reference as preview_reference
        package = resources.files("video_paper_wiki_research")
        schemas, entries = {}, []
        for name in PREVIEW_SCHEMAS:
            raw = store.tree.file(package.joinpath("schemas", name), maximum=1048576)["data"]
            schema = parse_json(raw, maximum=1048576)
            schemas[name] = schema
            entries.append((schema["$id"], Resource.from_contents(schema)))
        registry = Registry().with_resources(entries)
        selected = document["data"]["selected_arxiv"]
        arxiv = selected["value"] + ("v" + str(selected["version"]) if selected["version"] is not None else "")
        request = make_request(arxiv)
        error = next(_Validator(schemas["connector-request.v1.schema.json"], registry=registry).iter_errors(request), None)
        if error is not None:
            invalid("prospective W1 request differs from its retained installed schema")
        store.tree.verify()
        return {"decision": reference(document), "handoff": {"request_document": request,
                "prospective_request_reference": preview_reference(request), "created": False,
                "command": {"executable": "vpwiki-research", "arguments": ["paper", "request", "--arxiv", arxiv, "--session", session]}},
                "writes_preview_subtree": False}


def _literal(value):
    """Render one literal line, including when source text contains Markdown."""
    text = str(value)
    text = "".join(c if c.isprintable() else " " if c in "\r\n\t" else
                   "\\u" + format(ord(c), "04x") for c in text)
    text = html.escape(text, quote=True)
    for char in "\\`*_{}[]()#+-.!|>":
        text = text.replace(char, "\\" + char)
    return text


def _json_literal(value):
    return _literal(canonicalize(value).decode("utf-8"))


def render(*, session):
    with _session(session) as (store, graph):
        result = _status(store, graph)
        lines = ["# Discovery " + _literal(session), "", "State: " + _literal(result["effective_state"]),
                 "", "All scientific coverage and relevance remain provisional."]
        if graph.config is not None:
            lines += ["", _literal(graph.config["question"]), "", "## Progress", "",
                      "Stop reasons: " + _json_literal(result["matched_reasons"]),
                      "", "Budget used: " + _json_literal(result["budget"]),
                      "", "Budget remaining: " + _json_literal(result["remaining_budgets"])]
        for name, label in (("last_completed_assessment", "Completed provisional coverage"),
                            ("pending_assessment", "Pending provisional coverage (round incomplete)")):
            assessment = result[name]
            if assessment is None:
                continue
            lines += ["", "## " + label, "",
                      "Round " + str(assessment["round_sequence"]) + ": " +
                      _json_literal(assessment["artifact"]["reference"]), "",
                      "Generator: " + _json_literal(assessment["generator"])]
            for lens in assessment["lenses"]:
                lines += ["", "- " + _literal(lens["lens"]) + ": " + _literal(lens["state"]),
                          "", "  Scope: " + _literal(lens["scope"]),
                          "", "  " + _literal(lens["statement"])]
                if lens["reason"] is not None:
                    lines += ["", "  Reason: " + _literal(lens["reason"])]
                if lens["evidence"]:
                    lines += ["", "  Evidence: " + _json_literal(lens["evidence"])]
        if result["last_completed_assessment"] is None and result["pending_assessment"] is None:
            lines += ["", "No caller assessment has been recorded."]
        if result["operation_health"]:
            lines += ["", "## Operation health", ""]
            for health in result["operation_health"]:
                lines += ["- Round " + str(health["round_sequence"]) + ", slot " + str(health["slot"]) +
                          ": " + _literal(health["provider"]) + " / " + _literal(health["operation"]) +
                          " / " + _literal(health["lens"]) + ": " +
                          _literal(health["outcome"] or health["state"]), "",
                          "  Request: " + _json_literal(health["request"]) + "; observation: " +
                          _json_literal(health["observation"]), ""]
                if health["failure"] is not None:
                    lines += ["  Failure: " + _json_literal(health["failure"]), ""]
        displayed, omitted = 0, 0
        candidate_limit, evidence_limit = 20, 3
        if graph.candidates is not None:
            items = {i["candidate_key"]: i for i in graph.candidates["data"]["items"]}
            fused = {v["candidate_key"]: (i + 1, v) for i, v in enumerate(graph.rank["data"]["fused"])}
            order = list(fused) + sorted(k for k in items if k not in fused)
            displayed, omitted = min(len(order), candidate_limit), max(0, len(order) - candidate_limit)
            lines += ["", "## Candidates from completed round " + str(graph.candidates["data"]["sequence"]),
                      "", "Showing " + str(displayed) + " of " + str(len(order)) +
                      " candidates; " + str(omitted) + " omitted from this preview.", "",
                      "Complete candidate evidence: " + _json_literal(result["candidate_set"]), "",
                      "Complete ranking evidence: " + _json_literal(result["rank"])]
            for key in order[:candidate_limit]:
                item = items[key]
                ranked = fused.get(key)
                lines += ["", "### " + _literal(item["title"] or key), "",
                          "Candidate key: " + key, "", "Identifiers: " + _json_literal(item["ids"]),
                          "", "Observed versions: " + _json_literal(item["versions"]), "",
                          "Provisional relevance: " + _json_literal(item["relevance"]), "",
                          "Ranking signals: " + _json_literal(item["signals"])]
                if item["conflicts"]:
                    lines += ["", "Identity conflict (unranked): " + _json_literal(item["conflicts"])]
                if ranked is not None:
                    position, value = ranked
                    reasons = {}
                    for term in value["suppressed"]:
                        reasons[term["reason"]] = reasons.get(term["reason"], 0) + 1
                    lines += ["", "Rank " + str(position) + "; exact RRF " + value["numerator"] + "/" +
                              value["denominator"] + "; scaled score " + str(value["score"]), "",
                              "Suppression reason counts: " + _json_literal(reasons)]
                    for field in ("contributions", "suppressed"):
                        values = value[field]
                        lines += ["", field.capitalize() + " (first " + str(min(len(values), evidence_limit)) +
                                  " of " + str(len(values)) + "; " + str(max(0, len(values) - evidence_limit)) +
                                  " omitted): " + _json_literal(values[:evidence_limit])]
                facts = item["why_found"]
                lines += ["", "Why found (first " + str(min(len(facts), evidence_limit)) + " of " +
                          str(len(facts)) + "; " + str(max(0, len(facts) - evidence_limit)) +
                          " omitted; complete set in candidate evidence above):"]
                for fact in facts[:evidence_limit]:
                    lines += ["", "- " + _json_literal(fact)]
        return {**result, "format": "markdown", "markdown": "\n".join(lines) + "\n",
                "render_limits": {"candidates": candidate_limit, "evidence_items_per_list": evidence_limit},
                "displayed_candidates": displayed, "omitted_candidates": omitted}
