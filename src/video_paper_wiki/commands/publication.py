"""Thin agent-safe adapters for publication, review, and extraction commands."""
from __future__ import annotations
from video_paper_wiki.publication import run_publication_inspect_command,run_publication_prepare_command
from video_paper_wiki.review_workflow import run_review_prepare_command,run_review_invalidate_command
from video_paper_wiki.extraction_artifact import run_ingest_package_command

def inspect(args:object)->int:return run_publication_inspect_command(args)
def prepare(args:object)->int:return run_publication_prepare_command(args)
def review_prepare(args:object)->int:return run_review_prepare_command(args)
def review_invalidate(args:object)->int:return run_review_invalidate_command(args)
def ingest_package(args:object)->int:return run_ingest_package_command(args)
