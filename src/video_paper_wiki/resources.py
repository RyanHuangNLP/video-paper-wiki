"""Load packaged schema/seed, then the repo trees. No network."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

_PACKAGE = "video_paper_wiki"
_SEED_DIR = "seed"
_SCHEMA_DIR = "schemas"
_REPO_SEED = Path("docs") / "seed"
_REPO_SCHEMAS = Path("schemas")
_TAXONOMY_DIR = "taxonomy"
_CATALOG_DIR = "catalog"
_REPO_TAXONOMY = Path("taxonomy")
_REPO_CATALOG = Path("catalog")


def _package_text(*parts: str) -> str | None:
    try:
        traversable = resources.files(_PACKAGE).joinpath(*parts)
    except (ModuleNotFoundError, AttributeError, TypeError, ValueError):
        return None
    try:
        if not traversable.is_file():
            return None
        return traversable.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        from video_paper_wiki.notes.encoding import InvalidEncoding

        path = Path(traversable) if isinstance(traversable, Path) else Path(*parts)
        raise InvalidEncoding(path) from exc
    except (OSError, FileNotFoundError, IsADirectoryError, AttributeError):
        return None


def _repo_file(relative: Path) -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / relative
        if candidate.is_file():
            return candidate
    cwd_candidate = Path.cwd() / relative
    if cwd_candidate.is_file():
        return cwd_candidate
    return None


def _repo_text(relative: Path) -> str | None:
    path = _repo_file(relative)
    if path is None:
        return None
    from video_paper_wiki.notes.encoding import read_utf8

    try:
        return read_utf8(path)
    except OSError:
        return None


def _source_checkout_root() -> Path | None:
    """Return the repo root only for the exact src/package/module layout."""

    module = Path(__file__).resolve()
    package = module.parent
    if (module.name != "resources.py" or package.name != _PACKAGE
            or package.parent.name != "src"):
        return None
    return package.parent.parent


def read_seed_text(filename: str) -> str | None:
    """Package resources first, then repo docs/seed."""
    text = _package_text(_SEED_DIR, filename)
    if text is not None:
        return text
    return _repo_text(_REPO_SEED / filename)


def _schema_text_without_cwd(filename: str) -> str | None:
    """Load a schema from package resources or the repo tree next to this module.

    The production registry must not depend on the process working directory.
    """

    text = _package_text(_SCHEMA_DIR, filename)
    if text is not None:
        return text
    root = _source_checkout_root()
    candidate = root / _REPO_SCHEMAS / filename if root is not None else None
    if candidate is not None and candidate.is_file():
        from video_paper_wiki.notes.encoding import read_utf8

        try:
            return read_utf8(candidate)
        except OSError:
            return None
    return None


def read_schema_text(filename: str) -> str | None:
    """Package resources first, then repo schemas/."""
    text = _schema_text_without_cwd(filename)
    if text is not None:
        return text
    return _repo_text(_REPO_SCHEMAS / filename)


def load_schema_json(filename: str) -> dict[str, Any] | None:
    text = _schema_text_without_cwd(filename)
    if text is None:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def read_projection_resource_bytes(kind: str, filename: str) -> bytes | None:
    """Read one fixed projection resource, package-first without a CWD fallback."""

    choices = {
        "schema": (_SCHEMA_DIR, _REPO_SCHEMAS),
        "taxonomy": (_TAXONOMY_DIR, _REPO_TAXONOMY),
        "catalog": (_CATALOG_DIR, _REPO_CATALOG),
    }
    if kind not in choices or type(filename) is not str or "/" in filename or "\\" in filename:
        return None
    package_dir, repo_dir = choices[kind]
    try:
        traversable = resources.files(_PACKAGE).joinpath(package_dir, filename)
        if traversable.is_file():
            return traversable.read_bytes()
    except (ModuleNotFoundError, AttributeError, TypeError, ValueError, OSError):
        pass
    root = _source_checkout_root()
    candidate = root / repo_dir / filename if root is not None else None
    if candidate is not None and candidate.is_file():
        try:
            return candidate.read_bytes()
        except OSError:
            return None
    return None


def schema_resource_names() -> tuple[str, ...]:
    names: list[str] = []
    try:
        traversable = resources.files(_PACKAGE).joinpath(_SCHEMA_DIR)
        if traversable.is_dir():
            names.extend(sorted(item.name for item in traversable.iterdir() if item.name.endswith(".schema.json")))
    except (ModuleNotFoundError, AttributeError, TypeError, ValueError, OSError):
        names = []
    if names:
        return tuple(names)
    root = _source_checkout_root()
    directory = root / _REPO_SCHEMAS if root is not None else None
    if directory is not None and directory.is_dir():
        return tuple(sorted(path.name for path in directory.glob("*.schema.json")))
    return ()


def load_seed_json(filename: str) -> Any | None:
    text = read_seed_text(filename)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def resolve_seed_path(filename: str) -> Path | None:
    """On-disk repo path when the checkout is present."""
    return _repo_file(_REPO_SEED / filename)


def resolve_schema_path(filename: str) -> Path | None:
    return _repo_file(_REPO_SCHEMAS / filename)


def load_string_map(filename: str, key: str) -> dict[str, str] | None:
    payload = load_seed_json(filename)
    if not isinstance(payload, dict) or not isinstance(payload.get(key), dict):
        return None
    mapping: dict[str, str] = {}
    for raw_id, raw_text in payload[key].items():
        if not isinstance(raw_id, str) or not raw_id.strip():
            continue
        if not isinstance(raw_text, str) or not raw_text.strip():
            continue
        mapping[raw_id.strip()] = raw_text.strip()
    return mapping
