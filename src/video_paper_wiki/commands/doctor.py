"""Empty doctor command: local health only. No network, no Vault."""

from __future__ import annotations

import shutil
import sys

from video_paper_wiki.envelope import emit_success


def run(_args: object | None = None) -> int:
    py = sys.version_info
    return emit_success(
        "doctor",
        {
            "status": "ok",
            "package": "video-paper-wiki",
            "python": f"{py.major}.{py.minor}.{py.micro}",
            "vpwiki_admin_on_path": shutil.which("vpwiki-admin") is not None,
        },
    )
