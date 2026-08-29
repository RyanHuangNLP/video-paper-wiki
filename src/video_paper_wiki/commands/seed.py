"""Empty seed commands. No network, no Vault writes."""

from __future__ import annotations

from video_paper_wiki.envelope import emit_error


def validate(_args: object | None = None) -> int:
    return emit_error(
        "seed.validate",
        "NOT_IMPLEMENTED",
        "seed.validate is an empty VPKB-000-04 stub",
    )


def status(_args: object | None = None) -> int:
    return emit_error(
        "seed.status",
        "NOT_IMPLEMENTED",
        "seed.status is an empty VPKB-000-04 stub",
    )
