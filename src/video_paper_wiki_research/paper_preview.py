"""Offline public request, observation, abstract preview and explicit decision flow."""
from __future__ import annotations

import re
from datetime import timedelta

from video_paper_wiki.envelope import emit_success
from video_paper_wiki_research.arxiv_preview import ADAPTER, derive_metadata, normalize_arxiv
from video_paper_wiki_research.contracts import ResearchError
from video_paper_wiki_research.preview_contracts import (
    BUDGET, SECTIONS, VERSION_FIELDS, current_time, fail, parse_json, preflight,
    reference, seal, sha, task_prompt, timestamp, validate_graph, validate_proposal,
)
from video_paper_wiki_research.preview_storage import open_preview_session, read_input


def _artifact(store, document):
    return {"path": store.path(document).as_posix(), "reference": reference(document)}


def make_request(arxiv):
    entity, version = normalize_arxiv(arxiv)
    return seal("request", {"entity_id": entity, "requested_version": version,
                           "resolution_policy": "explicit" if version is not None else "latest_observation",
                           "source_url": "https://arxiv.org/abs/" + entity + (f"v{version}" if version else ""),
                           "method": "GET", "adapter": ADAPTER, "budget": BUDGET})


def request_paper(*, arxiv, session, now=None, refresh=False):
    request = make_request(arxiv)
    clock = timestamp(current_time() if now is None else now)
    if type(refresh) is not bool:
        fail("USAGE_ERROR", "refresh must be boolean")
    with open_preview_session(session, create=True) as store:
        store.write(request)
        matches = [metadata for metadata in store.all("metadata")
                   if metadata["data"]["request"] == reference(request)
                   and timedelta(0) <= clock - timestamp(metadata["data"]["observed_at"]) <= timedelta(hours=24)]
        matches.sort(key=lambda item: (item["data"]["observed_at"], reference(item)["sha256"]))
        result = {"request": _artifact(store, request), "source_url": request["data"]["source_url"],
                  "budget": dict(BUDGET), "fetch_required": refresh or not matches, "cache": None}
        if matches and not refresh:
            metadata = matches[-1]
            observation = store.resolve(metadata["data"]["observation"], "observation")
            result["cache"] = {"metadata": _artifact(store, metadata),
                               "observation": _artifact(store, observation),
                               "observed_at": metadata["data"]["observed_at"],
                               "resolved_version": metadata["data"]["resolved_version"],
                               "latest_at_observation": metadata["data"]["latest_at_observation"],
                               "capability_profile": observation["data"]["capability_profile"]}
        return result


def observe_paper(*, session, request, observation):
    # Parse all unsealed local input before creating an immutable observation.
    with read_input(observation) as raw:
        data = parse_json(raw)
        observed = seal("observation", data)
        with open_preview_session(session) as store:
            requested = store.load_path(request, "request")
            if data["request"] != reference(requested) or data["source_url"] != requested["data"]["source_url"]:
                fail("OBSERVATION_BINDING_MISMATCH", "observation differs from the selected request")
            if data["capability_profile"] == "byte-exact":
                fail("CONNECTOR_CAPABILITY_UNAVAILABLE", "byte-exact execution and raw parsing are unavailable")
            store.write(observed)
            try:
                metadata = seal("metadata", derive_metadata(requested, observed))
            except ResearchError as exc:
                raise ResearchError(exc.code, exc.message,
                                    {**exc.details, "observation": _artifact(store, observed)},
                                    exit_code=exc.exit_code) from exc
            store.write(metadata)
            return {"request": _artifact(store, requested), "observation": _artifact(store, observed),
                    "metadata": _artifact(store, metadata), "resolved_version": metadata["data"]["resolved_version"],
                    "latest_at_observation": metadata["data"]["latest_at_observation"],
                    "ingest_authorized": False}


def preview_context(*, session, metadata):
    with open_preview_session(session) as store:
        document = store.load_path(metadata, "metadata")
        prompt = task_prompt(document)
        unknown = {"value": "unknown", "identity_source": "unknown", "reason": "Platform identity is unavailable"}
        return {"metadata": _artifact(store, document), "task_prompt": prompt.decode("utf-8"),
                "prompt_sha256": sha(prompt), "evidence_scope": "abstract-only",
                "expected_proposal": {"generator": {"model": dict(unknown), "runtime": dict(unknown)},
                                      "generated_at": "YYYY-MM-DDTHH:MM:SSZ", "prompt_sha256": sha(prompt),
                                      "sections": {key: {"text": "在此填写基于摘要的内容或明确缺失信息。",
                                                         "classification": "unknown"} for key in SECTIONS}}}


def validate_preview(*, session, metadata, proposal):
    with read_input(proposal) as raw:
        data = validate_proposal(parse_json(raw, code="PREVIEW_PROPOSAL_INVALID"))
        with open_preview_session(session) as store:
            source = store.load_path(metadata, "metadata")
            if data["prompt_sha256"] != sha(task_prompt(source)):
                fail("PREVIEW_SCOPE_INVALID", "proposal does not bind this metadata's exact task prompt")
            result = seal("preview", {"metadata": reference(source),
                                      **{key: source["data"][key] for key in VERSION_FIELDS},
                                      "evidence_scope": "abstract-only", **data,
                                      "preview_only": True, "ingest_authorized": False})
            store.write(result)
            return {"preview": _artifact(store, result), "metadata": _artifact(store, source),
                    "ingest_authorized": False}


def _literal(text):
    # Render untrusted fields as visible text, including instruction/link syntax.
    return re.sub(r"([\\`*_{}\[\]()<>#+!|])", r"\\\1", text)


def _identity_label(identity):
    text = f'{identity["value"]} ({identity["identity_source"]})'
    if identity["reason"] is not None:
        text += ": " + identity["reason"]
    if identity["identity_source"] == "self_reported":
        text += "；未经平台核实"
    return _literal(text)


def render_preview(*, session, preview):
    with open_preview_session(session) as store:
        document = store.load_path(preview, "preview")
        data = document["data"]
        metadata = store.resolve(data["metadata"], "metadata")
        meta = metadata["data"]
        latest = {True: "latest_at_observation", False: "older_at_observation", None: "latest_unknown"}[data["latest_at_observation"]]
        lines = ["# " + _literal(meta["title"]), "",
                 f'{_literal(data["entity_id"])} · v{data["resolved_version"]} · {latest}',
                 "观察时间：" + data["observed_at"], "", "范围：仅摘要（abstract-only）；完整论文尚未审阅。", ""]
        labels = ("一句话", "研究问题", "方法", "贡献与结果", "局限", "相关性")
        for key, label in zip(SECTIONS, labels):
            section = data["sections"][key]
            lines.extend([f'## {label} [{section["classification"]}]', "", _literal(section["text"]), ""])
        lines.extend(["[arXiv 摘要来源](" + meta["abstract_url"] + ")", "",
                      "模型：" + _identity_label(data["generator"]["model"]),
                      "运行环境：" + _identity_label(data["generator"]["runtime"]), "",
                      f'可选操作：ingest（明确选择 v{data["resolved_version"]}） / skip / later。',
                      "当前仅为预览，没有执行收录。", ""])
        return {"preview": _artifact(store, document), "markdown": "\n".join(lines),
                "latest_label": latest, "selected_version": None, "ingest_authorized": False}


def _handoff(store, decision):
    data = decision["data"]
    if data["action"] != "ingest":
        return None
    preview = store.resolve(data["preview"], "preview")
    metadata = store.resolve(preview["data"]["metadata"], "metadata")
    observation = store.resolve(metadata["data"]["observation"], "observation")
    return {"kind": "W2-reference-handoff", "decision": reference(decision),
            "preview": reference(preview), "metadata": reference(metadata), "observation": reference(observation),
            "selected_version": data["selected_version"], "source": data["user_record"]["source"],
            "ingested": False, "operator_authorized": False}


def decide_paper(*, session, preview, action, event_id, user_text, source, selected_version=None, recorded_at=None):
    preflight({"action": action, "event_id": event_id, "text": user_text, "source": source,
               "selected_version": selected_version, "recorded_at": recorded_at}, code="DECISION_INVALID")
    if type(event_id) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", event_id) is None:
        fail("DECISION_INVALID", "event ID must be a safe session-unique slug")
    if recorded_at is not None:
        timestamp(recorded_at)
    with open_preview_session(session) as store:
        document = store.load_path(preview, "preview")
        decisions = store.all("decision")
        existing = next((item for item in decisions if item["data"]["user_record"]["event_id"] == event_id), None)
        clock = (existing["data"]["user_record"]["recorded_at"] if existing and recorded_at is None
                 else current_time() if recorded_at is None else recorded_at)
        record = {"event_id": event_id, "text": user_text, "source": source, "recorded_at": clock}
        if existing:
            old = existing["data"]
            if any((old["preview"] != reference(document), old["action"] != action,
                    old["selected_version"] != selected_version, old["user_record"] != record)):
                fail("DECISION_CONFLICT", "event ID already records a different choice")
            return {"decision": _artifact(store, existing), "already_recorded": True, "handoff": _handoff(store, existing)}
        if len(decisions) >= 256:
            fail("SESSION_LIMIT_EXCEEDED", "session has 256 retained decisions")
        decision = seal("decision", {"preview": reference(document), "sequence": len(decisions) + 1,
                                     "previous": reference(decisions[-1]) if decisions else None,
                                     "action": action, "selected_version": selected_version, "user_record": record})
        validate_graph(decision, store.resolve, memo=dict(store.graph_memo))
        store.write(decision)
        return {"decision": _artifact(store, decision), "already_recorded": False, "handoff": _handoff(store, decision)}


def list_papers(*, session):
    with open_preview_session(session, create=True) as store:
        latest = {item["data"]["preview"]["id"]: item for item in store.all("decision")}
        rows = []
        for preview in store.all("preview"):
            decision = latest.get(preview["id"])
            metadata = store.resolve(preview["data"]["metadata"], "metadata")
            rows.append({"preview": _artifact(store, preview), "title": metadata["data"]["title"],
                         **{key: preview["data"][key] for key in VERSION_FIELDS},
                         "state": decision["data"]["action"] if decision else "pending",
                         "decision": _artifact(store, decision) if decision else None})
        return {"previews": rows, "decision_count": len(store.all("decision")), "ingest_authorized": False}


def _run(args):
    action = args.preview_action
    values = {key: value for key, value in vars(args).items()
              if key in {"arxiv", "session", "now", "refresh", "request", "observation", "metadata",
                         "proposal", "preview", "action", "event_id", "user_text", "source", "selected_version", "recorded_at"}}
    command, function = {
        "request": ("paper.request", request_paper), "observe": ("paper.observe", observe_paper),
        "context": ("paper.preview.context", preview_context), "validate": ("paper.preview.validate", validate_preview),
        "render": ("paper.preview.render", render_preview), "decide": ("paper.decide", decide_paper),
        "list": ("paper.list", list_papers),
    }[action]
    return emit_success(command, function(**values))


def register_preview_commands(subparsers):
    paper = subparsers.add_parser("paper", allow_abbrev=False)
    forms = paper.add_subparsers(dest="paper_command", required=True)
    preview = forms.add_parser("preview", allow_abbrev=False)
    preview_forms = preview.add_subparsers(dest="preview_command", required=True)
    for name in ("request", "observe", "context", "validate", "render", "decide", "list"):
        parent = preview_forms if name in {"context", "validate", "render"} else forms
        parser = parent.add_parser(name, allow_abbrev=False)
        parser.add_argument("--session", required=True)
        required = {"request": ("arxiv",), "observe": ("request", "observation"), "context": ("metadata",),
                    "validate": ("metadata", "proposal"), "render": ("preview",),
                    "decide": ("preview", "event-id", "user-text"), "list": ()}[name]
        for option in required:
            parser.add_argument("--" + option, required=True)
        if name == "request":
            parser.add_argument("--now")
            parser.add_argument("--refresh", action="store_true")
        if name == "decide":
            parser.add_argument("--action", choices=("ingest", "skip", "later"), required=True)
            parser.add_argument("--source", choices=("user_message", "fixture"), required=True)
            parser.add_argument("--selected-version", type=int)
            parser.add_argument("--recorded-at")
        parser.set_defaults(handler=_run, preview_action=name)
