"""Replay the entire closed discovery graph and reconstruct valid crash prefixes."""
from __future__ import annotations

from video_paper_wiki.jcs import canonicalize
from video_paper_wiki_research.discovery_candidates import projections, round_counts
from video_paper_wiki_research.discovery_contracts import (
    KINDS, LENSES, REASONS, fail, graph_invalid, invalid, limit, reference,
    require_set, saved_bytes, seal, sha, timestamp, unique, validate,
)
from video_paper_wiki_research.discovery_plan import (
    frontier, plan_document, request_document, selected_lineages, validate_explicit,
)


def resolve(documents, ref, kind):
    document = documents.get(ref["id"])
    if document is None or document["kind"] != kind or reference(document) != ref:
        graph_invalid("reference is missing, has wrong kind, or hashes different saved bytes", kind=kind)
    return document


def observation_binding(observation, request, config):
    data, spec = observation["data"], request["data"]["spec"]
    if data["request"] != reference(request) or data["executor"]["capability_profile"] != spec["provider"]:
        graph_invalid("observation request or executor capability profile differs")
    payload = data["payload"]
    if payload is not None:
        if len(canonicalize(payload)) > config["limits"]["payload_bytes"] or len(payload["results"]) > config["limits"]["results_per_observation"]:
            limit("observation payload or result count exceeds configured limits")
        if payload["next_cursor"] is not None and (spec["provider"] != "openalex-rest-normalized-v1" or spec["operation"] not in {"topic", "citations"}):
            invalid("this provider operation cannot return a usable cursor")
        for result in payload["results"]:
            if result["relation"] != spec["operation"]:
                graph_invalid("result relation differs from its requested operation")
            if spec["neighbor_ids"] is not None:
                requested = {v["value"] for v in spec["neighbor_ids"]}
                observed = {v["value"] for v in result["ids"] if v["namespace"] == "openalex"}
                if not observed or not observed <= requested:
                    graph_invalid("batch result does not belong to the requested OpenAlex IDs")


def assessment_binding(assessment, config, session, plan, observations):
    data = assessment["data"]
    refs = unique([reference(o) for o in observations])
    if (data["session"] != reference(session) or data["sequence"] != plan["data"]["sequence"]
            or data["plan_id"] != plan["id"] or data["observations"] != refs
            or data["input_set_sha256"] != sha(canonicalize(refs))):
        graph_invalid("assessment must bind the exact complete cumulative terminal inputs")
    obsmap = {o["id"]: o for o in observations}
    for configured, lens in zip(config["lenses"], data["lenses"]):
        if lens["lens"] != configured["lens"] or lens["scope"] != configured["scope"]:
            graph_invalid("assessment lens scope differs from the immutable config")
        for citation in lens["evidence"]:
            observation = resolve(obsmap, citation["observation"], "discovery-observation")
            payload = observation["data"]["payload"]
            if payload is None or not 1 <= citation["ordinal"] <= len(payload["results"]):
                graph_invalid("assessment cites an unavailable result")
            text = payload["results"][citation["ordinal"] - 1][citation["field"]]
            if (text is None or not 0 <= citation["start"] < citation["end"] <= len(text)
                    or sha(text[citation["start"]:citation["end"]].encode("utf-8")) != citation["excerpt_sha256"]):
                graph_invalid("assessment excerpt does not resolve to the exact observed text")


def budget(plans, completed, requests, observations, candidate_slots, components):
    reserved = sum(len(p["data"]["request_specs"]) for p in plans)
    payloads = [o["data"]["payload"] for o in observations if o["data"]["payload"] is not None]
    return {"rounds_planned": len(plans), "rounds_completed": completed,
            "request_slots_reserved": reserved, "requests_materialized": len(requests),
            "pending_request_files": reserved - len(requests), "observation_slots_reserved": reserved,
            "terminal_observations": len(observations), "pending_observations": reserved - len(observations),
            "retry_slots": sum(s["retry"] is not None for p in plans for s in p["data"]["request_specs"]),
            "result_records": sum(len(p["results"]) for p in payloads),
            "normalized_payload_bytes": sum(len(canonicalize(p)) for p in payloads),
            "candidate_slots_reserved": candidate_slots, "current_candidate_components": components}


def validate_budget(value, config, *, pending_introductions=0):
    limits = config["limits"]
    mapping = {"rounds_planned": "rounds", "request_slots_reserved": "requests",
               "observation_slots_reserved": "observations", "result_records": "total_results",
               "normalized_payload_bytes": "total_payload_bytes", "current_candidate_components": "unique_candidates"}
    for field, bound in mapping.items():
        if value[field] > limits[bound]:
            limit("cumulative discovery budget exceeded", field=field, maximum=limits[bound])
    if value["candidate_slots_reserved"] + pending_introductions > limits["unique_candidates"]:
        limit("strict per-observation candidate admission exceeded", field="candidate_slots_reserved")


def exhausted(value, config):
    limits = config["limits"]
    return any(value[field] >= limits[bound] for field, bound in (
        ("rounds_planned", "rounds"), ("request_slots_reserved", "requests"),
        ("observation_slots_reserved", "observations"), ("result_records", "total_results"),
        ("normalized_payload_bytes", "total_payload_bytes"), ("candidate_slots_reserved", "unique_candidates")))


def complete_projections(config, session, plan, requests, observations, previous_observations,
                         previous_events, previous_stops, previous_round, assessment, control_head,
                         all_plans, candidate_slots):
    candidates, rank, components = projections(config, session, plan, observations, requests)
    assessment_binding(assessment, config, session, plan, observations)
    current = [o for o in observations if requests[o["data"]["request"]["id"]]["data"]["sequence"] == plan["data"]["sequence"]]
    counts = round_counts(components, previous_observations, current)
    value = budget(all_plans, len(previous_events) + 1, requests, observations,
                   candidate_slots + counts["new_components"], len(components))
    validate_budget(value, config)
    outcomes = [o["data"]["outcome"] for o in current]
    metrics = {"successful_requests": outcomes.count("success"), "partial_requests": outcomes.count("partial"),
               "failed_requests": sum(v not in {"success", "partial"} for v in outcomes),
               "raw_hits": sum(len(o["data"]["payload"]["results"]) for o in current if o["data"]["payload"] is not None),
               **counts, "unresolved_components": sum(bool(i["conflicts"]) for i in candidates["data"]["items"]),
               "pending_requests": 0, "lens_states": [{"lens": l["lens"], "state": l["state"]} for l in assessment["data"]["lenses"]],
               "budget": value}
    conflicted_facts = {canonicalize({"observation": w["observation"], "ordinal": w["ordinal"]})
                       for i in candidates["data"]["items"] if i["conflicts"] for w in i["why_found"]}
    cited_conflicts = any(canonicalize({"observation": c["observation"], "ordinal": c["ordinal"]}) in conflicted_facts
                         for l in assessment["data"]["lenses"] for c in l["evidence"])
    window = config["stopping"]["consecutive_rounds"]
    recent = [s["data"]["metrics"] for s in previous_stops] + [metrics]
    recent = recent[-window:]
    qualify = {
        "budget_exhausted": exhausted(value, config),
        "paths_covered": all(l["state"] != "gap" for l in assessment["data"]["lenses"]) and not cited_conflicts,
        "duplicate_ratio": len(recent) == window and all(m["total_hits"] > 0 and m["repeated_hits"] * 100 >= config["stopping"]["duplicate_percent"] * m["total_hits"] for m in recent),
        "yield_below_threshold": len(recent) == window and all(m["new_relevant"] < config["stopping"]["min_new_relevant"] for m in recent),
    }
    matched = [r for r in REASONS if qualify[r]]
    common = {k: candidates["data"][k] for k in ("session", "sequence", "plan_id", "input_set_sha256")}
    stop = seal("research-stop-decision", {**common, "assessment": reference(assessment), "candidate_set": reference(candidates),
                "rank": reference(rank), "metrics": metrics, "matched_reasons": matched,
                "primary_reason": matched[0] if matched else None, "next_action": "stop" if matched else "continue"})
    current_requests = [r for r in requests.values() if r["data"]["sequence"] == plan["data"]["sequence"]]
    event = seal("research-round-event", {"session": reference(session), "sequence": plan["data"]["sequence"],
                 "plan": reference(plan), "previous_round": None if previous_round is None else reference(previous_round),
                 "control_head": None if control_head is None else reference(control_head),
                 "requests": unique([reference(r) for r in current_requests]), "observations": unique([reference(o) for o in current]),
                 "assessment": reference(assessment), "candidate_set": reference(candidates), "rank": reference(rank),
                 "stop": reference(stop), "budget_after": value})
    return candidates, rank, stop, event


class Graph:
    def __init__(self, documents, session_key):
        self.documents, self.session_key = dict(documents), session_key
        self.by_kind = {k: [] for k in KINDS}
        for document in self.documents.values():
            validate(document)
            self.by_kind[document["kind"]].append(document)
        self.session = self.config_doc = self.config = None
        self.plans, self.events, self.controls, self.decisions, self.stops = [], [], [], [], []
        self.requests, self.observations = {}, []
        self.pending_plan = self.assessment = self.candidates = self.rank = None
        self.missing_requests, self.missing_observations, self.pending_projection = [], [], []
        self.candidate_slots = self.pending_introductions = self.component_count = 0
        self.used = set()
        self.base_state = "absent"
        self._replay()

    def use(self, document):
        self.used.add(document["id"])
        return document

    def only(self, kind, *, optional=False):
        docs = self.by_kind[kind]
        if len(docs) > 1 or not docs and not optional:
            graph_invalid("expected exactly one discovery artifact", kind=kind)
        return self.use(docs[0]) if docs else None

    def stream(self, kind):
        docs = sorted(self.by_kind[kind], key=lambda d: d["data"]["sequence"])
        for sequence, document in enumerate(docs, 1):
            if document["data"]["sequence"] != sequence:
                graph_invalid("stream sequence has a gap or fork", kind=kind)
            if document["data"]["session"] != reference(self.session):
                graph_invalid("artifact belongs to a different session", kind=kind)
        return docs

    def _control_stream(self):
        self.controls = self.stream("research-control-event")
        previous, previous_round, stopped = None, 0, False
        for control in self.controls:
            data = control["data"]
            if data["previous"] != (None if previous is None else reference(previous)):
                graph_invalid("control previous reference is not the exact predecessor")
            round_doc = None if data["round"] is None else resolve(self.documents, data["round"], "research-round-event")
            round_sequence = 0 if round_doc is None else round_doc["data"]["sequence"]
            if round_sequence < previous_round or round_sequence > len(self.events):
                graph_invalid("control round interleaving is invalid")
            if previous is not None and timestamp(data["user_record"]["recorded_at"]) < timestamp(previous["data"]["user_record"]["recorded_at"]):
                graph_invalid("control timestamps are not monotone")
            if (data["action"] == "user_stop") == stopped:
                graph_invalid("control is redundant or resumes a session without user_stop")
            stopped = data["action"] == "user_stop"
            previous, previous_round = control, round_sequence
            self.use(control)

    def control_before_event(self, sequence):
        eligible = []
        for control in self.controls:
            ref = control["data"]["round"]
            round_sequence = 0 if ref is None else self.documents[ref["id"]]["data"]["sequence"]
            if round_sequence < sequence:
                eligible.append(control)
        return eligible[-1] if eligible else None

    def _plan_control(self, plan, previous_event, event_control):
        ref = plan["data"]["control_head"]
        control = None if ref is None else resolve(self.documents, ref, "research-control-event")
        sequence = 0 if control is None else control["data"]["sequence"]
        maximum = 0 if event_control is None else event_control["data"]["sequence"]
        minimum_ref = None if previous_event is None else previous_event["data"]["control_head"]
        minimum = 0 if minimum_ref is None else self.documents[minimum_ref["id"]]["data"]["sequence"]
        if not minimum <= sequence <= maximum or control is not None and control["data"]["action"] == "user_stop":
            graph_invalid("plan control head is not an active historical ancestor")
        return control

    def _replay(self):
        self.config_doc = self.only("research-config", optional=True)
        if self.config_doc is None:
            if self.documents:
                graph_invalid("artifacts exist without config")
            return
        self.config = self.config_doc["data"]
        self.session = self.only("research-session", optional=True)
        if self.session is None:
            if len(self.documents) != 1:
                graph_invalid("only the config may precede initialization")
            self.base_state = "init_pending"
            return
        expected_session = seal("research-session", {"session_key": self.session_key, "config": reference(self.config_doc)})
        if self.session != expected_session:
            graph_invalid("session does not match the retained config and directory key")
        self.plans = self.stream("research-round-plan")
        self.events = self.stream("research-round-event")
        if len(self.plans) not in {len(self.events), len(self.events) + 1}:
            graph_invalid("only one incomplete current plan is allowed")
        self._control_stream()
        previous_events, previous_stops, all_observations, all_requests = [], [], [], {}
        prior_candidates = prior_rank = previous_event = None
        for index, plan in enumerate(self.plans):
            sequence = index + 1
            if previous_stops and previous_stops[-1]["data"]["primary_reason"] is not None:
                graph_invalid("a plan follows a calculated stopping decision")
            if len(plan["data"]["request_specs"]) > self.config["limits"]["per_round_requests"]:
                limit("plan exceeds configured per-round requests")
            control = self.control_before_event(sequence)
            plan_control = self._plan_control(plan, previous_event, control)
            specs = plan["data"]["request_specs"]
            available = frontier(self.config, self.plans[:index], all_observations, all_requests,
                                 candidate_set=prior_candidates, rank=prior_rank)
            validate_explicit(specs, available, self.plans[:index], all_observations, all_requests, self.config)
            expected = plan_document(self.session, sequence, previous_event, plan_control, specs, self.plans[:index])
            if plan != expected:
                graph_invalid("plan reservations, predecessor or immutable fields differ")
            self.use(plan)
            current_requests, current_observations = {}, []
            missing_requests, missing_observations = [], []
            for slot in range(len(specs)):
                request = request_document(self.session, plan, slot)
                found = self.documents.get(request["id"])
                if found is None:
                    missing_requests.append(request)
                    missing_observations.append(reference(request))
                    continue
                if found != request:
                    graph_invalid("request does not equal its committed slot")
                self.use(found)
                current_requests[found["id"]] = found
                obs = [o for o in self.by_kind["discovery-observation"] if o["data"]["request"] == reference(found)]
                if len(obs) > 1:
                    fail("DISCOVERY_CONFLICT", "one request slot has competing terminal observations")
                if obs:
                    observation_binding(obs[0], found, self.config)
                    current_observations.append(self.use(obs[0]))
                else:
                    missing_observations.append(reference(found))
            prior_observations = list(all_observations)
            all_observations += current_observations
            all_requests.update(current_requests)
            candidates, rank, components = projections(self.config, self.session, plan, all_observations, all_requests)
            counts = round_counts(components, prior_observations, current_observations)
            value = budget(self.plans[:sequence], len(previous_events), all_requests, all_observations,
                           self.candidate_slots, len(components))
            validate_budget(value, self.config, pending_introductions=counts["new_components"])
            assessments = [a for a in self.by_kind["research-assessment"] if a["data"]["plan_id"] == plan["id"]]
            if len(assessments) > 1:
                fail("DISCOVERY_CONFLICT", "round has competing assessment inputs")
            assessment = assessments[0] if assessments else None
            complete = index < len(self.events)
            expected_projections = []
            if missing_requests or missing_observations:
                if assessment is not None or complete:
                    graph_invalid("assessment or event exists while committed slots are pending")
            elif assessment is not None:
                self.use(assessment)
                expected_projections = list(complete_projections(
                    self.config, self.session, plan, all_requests, all_observations,
                    prior_observations, previous_events, previous_stops, previous_event,
                    assessment, control, self.plans[:sequence], self.candidate_slots))
                candidates, rank, stop, event = expected_projections
                for projection in expected_projections:
                    if projection["id"] in self.documents:
                        if self.documents[projection["id"]] != projection:
                            graph_invalid("stored projection differs from deterministic replay")
                        self.use(projection)
            if complete:
                if not expected_projections or any(p["id"] not in self.documents for p in expected_projections):
                    graph_invalid("complete event is missing a required exact child")
                if self.events[index] != expected_projections[-1]:
                    graph_invalid("round event/control/counters differ from deterministic replay")
                if control is not None and control["data"]["action"] == "user_stop":
                    graph_invalid("round completed while its effective control was user_stop")
                self.candidate_slots += counts["new_components"]
                previous_events.append(event)
                previous_stops.append(stop)
                previous_event, prior_candidates, prior_rank = event, candidates, rank
            else:
                self.pending_plan, self.assessment = plan, assessment
                self.missing_requests = missing_requests
                self.missing_observations = missing_observations
                self.pending_introductions = counts["new_components"]
                self.pending_projection = [p for p in expected_projections if p["id"] not in self.documents]
                self.base_state = ("plan_pending_requests" if missing_requests else "plan_pending_observations" if missing_observations
                                   else "assessment_required" if assessment is None else "projection_pending")
            self.component_count = len(components)
        self.requests, self.observations, self.stops = all_requests, all_observations, previous_stops
        self.candidates, self.rank = prior_candidates, prior_rank
        if self.pending_plan is None:
            self.base_state = "calculated_stopped" if self.stops and self.stops[-1]["data"]["primary_reason"] is not None else "complete_continue" if self.events else "session_ready"
        self._decision_stream()
        selected_lineages(self.config, self.plans, self.observations, self.requests)
        if self.used != set(self.documents):
            graph_invalid("discovery tree contains an orphan or nonmatching projection", artifacts=sorted(set(self.documents) - self.used))

    def _decision_stream(self):
        self.decisions = self.stream("candidate-decision")
        previous = None
        for decision in self.decisions:
            data = decision["data"]
            if data["previous"] != (None if previous is None else reference(previous)):
                graph_invalid("candidate decision predecessor differs")
            round_doc = resolve(self.documents, data["round"], "research-round-event")
            candidate_set = resolve(self.documents, data["candidate_set"], "paper-candidate-set")
            if round_doc not in self.events or round_doc["data"]["candidate_set"] != data["candidate_set"]:
                graph_invalid("candidate decision must bind a completed round's exact snapshot")
            choices = [i for i in candidate_set["data"]["items"] if i["candidate_key"] == data["candidate_key"]]
            if len(choices) != 1:
                graph_invalid("candidate decision points to an unknown identity key")
            if data["action"] == "preview":
                if choices[0]["conflicts"] or data["selected_arxiv"] not in choices[0]["versions"]:
                    fail("DISCOVERY_IDENTITY_UNRESOLVED", "preview must select one actually observed nonconflicting arXiv identity/version")
            if previous is not None and timestamp(data["user_record"]["recorded_at"]) < timestamp(previous["data"]["user_record"]["recorded_at"]):
                graph_invalid("candidate decision timestamps are not monotone")
            previous = decision
            self.use(decision)
        event_ids = [d["data"]["user_record"]["event_id"] for d in self.controls + self.decisions]
        if len(event_ids) != len(set(event_ids)):
            fail("DISCOVERY_CONFLICT", "user event identity is reused across decision/control streams")

    @property
    def control_head(self):
        return self.controls[-1] if self.controls else None

    @property
    def user_stopped(self):
        return self.control_head is not None and self.control_head["data"]["action"] == "user_stop"

    @property
    def last_event(self):
        return self.events[-1] if self.events else None

    def current_budget(self):
        value = budget(self.plans, len(self.events), self.requests, self.observations,
                       self.candidate_slots, self.component_count)
        if self.config is not None:
            validate_budget(value, self.config, pending_introductions=self.pending_introductions)
        return value
