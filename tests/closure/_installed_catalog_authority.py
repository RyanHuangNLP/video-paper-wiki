"""Emit independently reconstructed catalog authority from the installed wheel."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from video_paper_wiki.catalog_collector import collect_current_catalog_material
from video_paper_wiki.catalog_store import (
    canonical_export_from_database,
    canonical_search_catalog_export,
    prepare_catalog_material,
)


def main() -> None:
    vault, upstream, config_path = map(Path, sys.argv[1:4])
    config = json.loads(config_path.read_bytes())
    prepared = prepare_catalog_material(
        collect_current_catalog_material(
            vault_root=vault, upstream_root=upstream, retrieval_config=config
        )
    )
    raw = canonical_export_from_database(vault / ".vault-meta/catalog.sqlite")
    assert canonical_search_catalog_export(prepared) == raw
    print(
        json.dumps(
            {
                "generation": prepared["generation"],
                "meta": prepared["meta"],
                "export_sha256": hashlib.sha256(raw).hexdigest(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
