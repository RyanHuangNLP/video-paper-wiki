"""Command compatibility exports for domain operations."""
from video_paper_wiki.domain_cli import (audit, backup_build, backup_verify,
    catalog_report, compile_render, compile_validate, evidence_join, index_status, init_inspect,
    init_plan, inspect_document, query, retrieval_evaluate, retrieval_validate,
    seed_render, seed_status, seed_validate)


def gate_prepare(args):
    from video_paper_wiki.domain_cli import gate_prepare as implementation
    return implementation(args)


def gate_inspect(args):
    from video_paper_wiki.domain_cli import gate_inspect as implementation
    return implementation(args)
