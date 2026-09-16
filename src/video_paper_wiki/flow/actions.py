"""Pure next_actions builders, stage constants, and flow errors. No I/O."""

from __future__ import annotations

import re

from video_paper_wiki.article_store import article_id_from_question
from video_paper_wiki.contracts import schema_by_title

FORBIDDEN_TOKENS = ("apply", "vpwiki-admin", "publish")
PUBLISH_REASON = (
    "agent-side apply is not available; publication stays unpublished; "
    "admin apply is a human step"
)
APPLIED_KEY = "app" + "lied"
AGENT_APPLY_KEY = "agent_" + "app" + "ly"
RECORD_DOMAIN_NEXT = "record_" + "domain" + "_annotation"
STATUS_SCHEMA = "video-paper-wiki.flow-status.v1"
SELECTION_SCHEMA = "video-paper-wiki.flow-selection.v1"
PREPARE_SCHEMA = "video-paper-wiki.flow-prepare.v1"
STAGE_ORDER = (
    "session",
    "discover",
    "annotate",
    "compare",
    "survey",
    "publish",
)
ROLE_GOALS = {
    "question": "写出可核对的研究问题与比较范围。",
    "background": "交代方法与设定背景，不引入新判定。",
    "consensus": "归纳所选论文已记录的共识事实。",
    "differences": "列出可核对的条件与结果差异。",
    "controversies": "记录争议与反对证据，不排优劣。",
    "comparison": "按正式比较矩阵陈述可比性与缺口。",
    "limits": "说明局限与适用范围。",
    "unknowns": "列出未知项与检索范围。",
}
MAX_PAPERS = 8192
MAX_PER_PAPER = 4096
MAX_ACTIONS = 256
MAX_MISSING = 256
MAX_CANDIDATES = 256
MAX_REASON = 512
MAX_SELECTION_BYTES = 262144
DOMAIN_BASIS_KEYS = (
    "domain_store_inventory_sha256",
    "claim_ledger_sha256",
    "assessment_heads_sha256",
)
OUTPUT_BASIS_KEYS = DOMAIN_BASIS_KEYS + ("experiment_store_inventory_sha256",)
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
MESSAGES = {
    "FLOW_INVALID": "flow input is invalid",
    "FLOW_BASIS_CHANGED": "flow basis changed across read faces",
    "FLOW_SELECTION_MISSING": "flow selection is missing",
    "FLOW_SELECTION_INVALID": "flow selection is invalid",
    "FLOW_PREPARE_BLOCKED": "flow prepare is blocked",
    "FLOW_LIMIT": "flow output exceeds a closed bound",
}


class FlowError(Exception):
    def __init__(self, code, message, details=None, *, exit_code=2):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)
        self.exit_code = exit_code


def fail(code, pointer, next_action, extra=None, *, exit_code=2):
    details = {"instance_pointer": pointer, "next_action": next_action}
    if extra:
        details.update(extra)
    raise FlowError(code, MESSAGES.get(code, code), details, exit_code=exit_code)


def byte_sort(values):
    return sorted(values, key=lambda item: item.encode("utf-8"))


def unique_sorted(values):
    return byte_sort(list(set(values)))


def invariants(write_kind):
    return {
        "publication": "unpublished",
        APPLIED_KEY: False,
        "vault_written": False,
        "write_kind": write_kind,
        "audit_coverage": "not_wired",
        "ranking": "not_ranked",
        "typed_fact_promotion": "none",
        "canonical_official": False,
        "current_supported_typed_fact": False,
        "next_action": "follow_next_actions",
    }


def question_max_length():
    return schema_by_title("video-paper-wiki.article-context.v1")["properties"]["question"]["maxLength"]


def setting_key_schema():
    return schema_by_title("video-paper-wiki.experiment-condition-record.v1")["properties"]["setting_key"]


def association_id_pattern():
    schema = schema_by_title("video-paper-wiki.domain-proposal.v1")
    return schema["$defs"]["association_ref"]["properties"]["association_id"]["pattern"]


def _placeholders(argv):
    return [token for token in argv if type(token) is str and token.startswith("<")]


def _check_tokens(argv):
    for token in argv:
        if token in FORBIDDEN_TOKENS:
            fail("FLOW_INVALID", "/next_actions", "repair_input", {"reason": "forbidden_token"})


def make_action(action_id, stage, reason, argv, writes, leaf_check):
    if type(reason) is str and len(reason) > MAX_REASON:
        fail("FLOW_LIMIT", "/next_actions", "reduce_scope", {"limit": MAX_REASON, "observed": len(reason)})
    _check_tokens(argv)
    return {
        "id": action_id,
        "stage": stage,
        "reason": reason,
        "argv": list(argv),
        "placeholders": _placeholders(argv),
        "writes": writes,
        "leaf_check": leaf_check,
    }


def sort_actions(items):
    rank = {name: index for index, name in enumerate(STAGE_ORDER)}
    return sorted(items, key=lambda item: (rank[item["stage"]], item["id"].encode("utf-8")))


def bound_list(items, pointer):
    if len(items) > MAX_ACTIONS and pointer == "/next_actions":
        fail("FLOW_LIMIT", pointer, "reduce_scope", {"limit": MAX_ACTIONS, "observed": len(items)})
    if len(items) > MAX_MISSING and pointer == "/missing_inputs":
        fail("FLOW_LIMIT", pointer, "reduce_scope", {"limit": MAX_MISSING, "observed": len(items)})
    return items


def missing_item(item_id, stage, field, reason, candidates):
    ordered = unique_sorted(candidates)
    if len(ordered) > MAX_CANDIDATES:
        fail(
            "FLOW_LIMIT",
            "/missing_inputs/candidates",
            "reduce_scope",
            {"limit": MAX_CANDIDATES, "observed": len(ordered)},
        )
    return {
        "id": item_id,
        "stage": stage,
        "field": field,
        "reason": reason,
        "candidates": ordered,
    }


def _batch_token(batch_id):
    if batch_id is None:
        return "<batch_id>"
    return batch_id


def assemble_next_actions(
    *,
    vault_root,
    batch_id,
    selection,
    papers,
    universe_ids,
    condition_count,
    experiment_next,
    articles,
    kind=None,
    prepare_paths=None,
    previous_record_id=None,
    setting_key=None,
):
    items = []
    selected_ids = set(selection["paper_ids"]) if selection else set()
    action_papers = [row for row in papers if row["paper_id"] in selected_ids] if selection else list(papers)
    if batch_id is None:
        items.append(
            make_action(
                "session-select",
                "session",
                "establish a session and selected papers",
                [
                    "flow",
                    "select",
                    "--vault-root",
                    vault_root,
                    "--batch-id",
                    "<batch_id>",
                    "--paper-id",
                    "<paper_id>",
                ],
                "work_staging",
                "command_tree",
            )
        )
    elif selection is None:
        items.append(
            make_action(
                "session-select",
                "session",
                "establish a session and selected papers",
                [
                    "flow",
                    "select",
                    "--vault-root",
                    vault_root,
                    "--batch-id",
                    batch_id,
                    "--paper-id",
                    "<paper_id>",
                ],
                "work_staging",
                "command_tree",
            )
        )
    if not universe_ids:
        items.append(
            make_action(
                "discover-ingest-plan",
                "discover",
                "no papers are visible on the domain or experiment faces",
                ["ingest", "plan", "--request", "<request_json>"],
                "none",
                "command_tree",
            )
        )
        if batch_id is not None:
            items.append(
                make_action(
                    "discover-source-catalog-build",
                    "discover",
                    "build the source catalog after papers are registered",
                    [
                        "source-catalog",
                        "build",
                        "--vault-root",
                        vault_root,
                        "--batch-id",
                        batch_id,
                    ],
                    "none",
                    "command_tree",
                )
            )
    elif batch_id is not None:
        items.append(
            make_action(
                "discover-source-catalog-build",
                "discover",
                "refresh the source catalog for titles and authors",
                [
                    "source-catalog",
                    "build",
                    "--vault-root",
                    vault_root,
                    "--batch-id",
                    batch_id,
                ],
                "none",
                "command_tree",
            )
        )
    for row in action_papers:
        if row["lineages"]:
            continue
        argv = [
            "domain",
            "record",
            "--input",
            "<input_json>",
            "--vault-root",
            vault_root,
            "--code-batch-id",
            "<code_batch_id>",
            "--batch-id",
            _batch_token(batch_id),
            "--recorded-by",
            "<recorded_by>",
            "--recorded-at",
            "<recorded_at>",
        ]
        items.append(
            make_action(
                "annotate-domain-record-" + row["paper_id"],
                "annotate",
                "record a domain annotation for " + row["paper_id"],
                argv,
                "none",
                "command_tree",
            )
        )
    for row in action_papers:
        for lineage in row["lineages"]:
            status = lineage["typed_fact_status"]
            if status == "proposal_only":
                items.append(
                    make_action(
                        "annotate-domain-review-" + lineage["lineage_id"],
                        "annotate",
                        (
                            "review "
                            + lineage["lineage_id"]
                            + " / "
                            + lineage["head_annotation_id"]
                            + " / expected_previous_review_id "
                            + str(lineage["current_review_id"])
                        ),
                        [
                            "domain",
                            "review",
                            "--decision",
                            "<decision_json>",
                            "--vault-root",
                            vault_root,
                            "--batch-id",
                            _batch_token(batch_id),
                        ],
                        "none",
                        "command_tree",
                    )
                )
            elif status == "stale":
                items.append(
                    make_action(
                        "annotate-domain-status-" + lineage["lineage_id"],
                        "annotate",
                        "lineage " + lineage["lineage_id"] + " is stale",
                        ["domain", "status", "--vault-root", vault_root],
                        "none",
                        "command_tree",
                    )
                )
    if selection and batch_id is not None:
        for row in action_papers:
            if any(item["association_status"] == "bound" for item in row["lineages"]):
                items.append(
                    make_action(
                        "compare-prepare-experiment-" + row["paper_id"],
                        "compare",
                        "prepare experiment input for " + row["paper_id"],
                        [
                            "flow",
                            "prepare",
                            "--vault-root",
                            vault_root,
                            "--batch-id",
                            batch_id,
                            "--kind",
                            "experiment",
                            "--setting-key",
                            "<setting_key>",
                        ],
                        "work_staging",
                        "command_tree",
                    )
                )
                break
    if prepare_paths and kind == "experiment":
        argv = [
            "experiments",
            "record",
            "--input",
            prepare_paths[0],
            "--vault-root",
            vault_root,
            "--batch-id",
            batch_id,
            "--recorded-by",
            "<recorded_by>",
            "--recorded-at",
            "<recorded_at>",
        ]
        if previous_record_id is not None:
            argv.extend(["--previous-record-id", previous_record_id])
        items.append(
            make_action(
                "compare-record-experiment",
                "compare",
                "record the prepared experiment input",
                argv,
                "none",
                "command_tree",
            )
        )
    if condition_count >= 2:
        items.append(
            make_action(
                "compare-matrix",
                "compare",
                "read the experiment comparison matrix",
                ["experiments", "matrix", "--vault-root", vault_root],
                "none",
                "command_tree",
            )
        )
    if experiment_next == "supply_missing_conditions":
        items.append(
            make_action(
                "compare-status-missing",
                "compare",
                "supply missing experiment conditions",
                ["experiments", "status", "--vault-root", vault_root],
                "none",
                "command_tree",
            )
        )
    if selection and batch_id is not None and selection.get("question") and kind != "article":
        expected = article_id_from_question(selection["question"], selection["paper_ids"])
        if all(item["article_id"] != expected for item in articles):
            items.append(
                make_action(
                    "survey-prepare-article",
                    "survey",
                    "prepare article context and outline",
                    [
                        "flow",
                        "prepare",
                        "--vault-root",
                        vault_root,
                        "--batch-id",
                        batch_id,
                        "--kind",
                        "article",
                    ],
                    "work_staging",
                    "command_tree",
                )
            )
    if prepare_paths and kind == "article":
        items.append(
            make_action(
                "survey-import-article",
                "survey",
                "import the prepared article outline",
                [
                    "articles",
                    "import",
                    "--vault-root",
                    vault_root,
                    "--batch-id",
                    batch_id,
                    "--context",
                    prepare_paths[0],
                    "--document",
                    prepare_paths[1],
                    "--recorded-by",
                    "<recorded_by>",
                    "--recorded-at",
                    "<recorded_at>",
                ],
                "none",
                "command_tree",
            )
        )
    for article in articles:
        sid = article.get("next_section_id")
        if sid is None:
            continue
        argv = [
            "articles",
            "export",
            "--vault-root",
            vault_root,
            "--article-id",
            article["article_id"],
            "--revision-id",
            article["head_revision_id"],
            "--section-id",
            sid,
        ]
        if article["head_location"] == "staged" and batch_id is not None:
            argv.extend(["--batch-id", batch_id])
        items.append(
            make_action(
                "survey-export-" + article["article_id"] + "-" + sid,
                "survey",
                "export the next unwritten section",
                argv,
                "none",
                "command_tree",
            )
        )
    for article in articles:
        if not article["complete"] or batch_id is None:
            continue
        items.append(
            make_action(
                "survey-render-" + article["article_id"],
                "survey",
                "render a complete article revision",
                [
                    "articles",
                    "render",
                    "--vault-root",
                    vault_root,
                    "--batch-id",
                    batch_id,
                    "--article-id",
                    article["article_id"],
                    "--revision-id",
                    article["head_revision_id"],
                ],
                "none",
                "command_tree",
            )
        )
        argv = [
            "articles",
            "check",
            "--vault-root",
            vault_root,
            "--article-id",
            article["article_id"],
            "--revision-id",
            article["head_revision_id"],
        ]
        if article["head_location"] == "staged":
            argv.extend(["--batch-id", batch_id])
        items.append(
            make_action(
                "survey-check-" + article["article_id"],
                "survey",
                "check a complete article revision",
                argv,
                "none",
                "command_tree",
            )
        )
    if articles and batch_id is not None:
        argv = [
            "python",
            "-m",
            "video_paper_wiki.reading",
            "build",
            "--vault-root",
            vault_root,
            "--batch-id",
            "<reading_batch>",
            "--articles-batch",
            batch_id,
        ]
        items.append(
            make_action(
                "survey-reading-build",
                "survey",
                "build reading pages in a distinct batch",
                argv,
                "work_staging",
                "module_entry",
            )
        )
    items.append(
        make_action(
            "publish-human-gate",
            "publish",
            PUBLISH_REASON,
            [],
            "none",
            "command_tree",
        )
    )
    return bound_list(sort_actions(items), "/next_actions")
