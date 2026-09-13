"""Staged PDF capture inspection command."""
from __future__ import annotations

from video_paper_wiki.staged_capture import run_capture_inspect_command


def run(args: object) -> int:
    return run_capture_inspect_command(args)
