"""Empty draft commands. No network, no Vault writes."""

from __future__ import annotations

from video_paper_wiki.envelope import emit_error


def export(_args: object | None = None) -> int:
    return emit_error(
        "draft.export",
        "NOT_IMPLEMENTED",
        "draft.export is an empty VPKB-000-04 stub",
    )


def validate(_args: object | None = None) -> int:
    return emit_error(
        "draft.validate",
        "NOT_IMPLEMENTED",
        "draft.validate is an empty VPKB-000-04 stub",
    )
