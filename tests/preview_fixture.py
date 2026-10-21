"""Complete synthetic normalized pages and labeled fixture choices; never live evidence."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from video_paper_wiki_research.paper_preview import (
    make_request, observe_paper, preview_context, request_paper, validate_preview,
)
from video_paper_wiki_research.preview_contracts import reference, sha

NOW = "2026-09-09T01:00:00Z"
UNKNOWN = {"value": "unknown", "identity_source": "unknown", "reason": "Synthetic fixture identity unavailable"}


def page(*, entity="2408.06072", version=2, complete=True):
    history = "[v1] Mon, 12 Aug 2024 11:47:11 UTC (27,248 KB)\n"
    if version >= 2:
        history += "[v2] Tue, 8 Oct 2024 06:28:19 UTC (32,741 KB)\n"
    return ("# Title: Synthetic Video Paper\n"
            "Authors: 【4†Alice Example】, 【5†Bob Example】\n"
            "View PDF\n"
            "> Abstract: A synthetic method learns temporal consistency.\n"
            "\nA second synthetic paragraph reports a bounded comparison.\n"
            "Comments: Synthetic fixture, not a real publication\n"
            "Subjects: Computer Vision and Pattern Recognition (cs.CV); Machine Learning (cs.LG)\n"
            f"Cite as: 【6†arXiv:{entity}】 [cs.CV]\n"
            f"(or 【7†arXiv:{entity}v{version}】 [cs.CV] for this version)\n"
            "## Submission history\n"
            "From: Alice Example [【8†view email】]\n" + history + ("Full-text links:\n" if complete else ""))


def observation(request=None, *, text=None, status="ok", observed_at=NOW):
    request = make_request("2408.06072v2") if request is None else request
    text = page() if text is None else text
    return {"request": reference(request), "observed_at": observed_at,
            "executor": copy.deepcopy(UNKNOWN), "source_url": request["data"]["source_url"],
            "capability_profile": "normalized-content", "reported_content_type": "text/html",
            "transport": {key: {"value": None, "unavailable_reason": "Not exposed by synthetic normalized fixture"}
                          for key in ("final_url", "redirect_chain", "headers", "content_type", "dns_ips",
                                      "raw_response_sha256", "wire_bytes", "timeout_enforced", "redirect_policy_verified")},
            "outcome": {"status": status, "retry_after_seconds": None},
            "payload": {"format": "arxiv-abs-normalized-text-v1", "text": text, "sha256": sha(text.encode())}
            if status == "ok" else None}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
    return Path(path)


def metadata_flow(checkout, *, session="preview", arxiv="2408.06072v2", text=None, observed_at=NOW):
    requested = request_paper(arxiv=arxiv, session=session, now=NOW)
    request = json.loads(Path(requested["request"]["path"]).read_bytes())
    bridge = write_json(checkout / "observation.json", observation(request, text=text, observed_at=observed_at))
    return observe_paper(session=session, request=requested["request"]["path"], observation=bridge)


def preview_flow(checkout, *, session="preview", text=None):
    result = metadata_flow(checkout, session=session, text=text)
    context = preview_context(session=session, metadata=result["metadata"]["path"])
    proposal = context["expected_proposal"]
    proposal["generated_at"] = NOW
    proposal["sections"]["one_sentence"] = {"text": "该合成方法研究时序一致性。", "classification": "extracted"}
    proposal_path = write_json(checkout / "proposal.json", proposal)
    return validate_preview(session=session, metadata=result["metadata"]["path"], proposal=proposal_path)
