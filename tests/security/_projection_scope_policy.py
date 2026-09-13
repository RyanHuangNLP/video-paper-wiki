"""Narrow VPKB-000 source scope guard, not semantic or OS isolation proof.

Only the released runtime comparator and central profile dispatch may mention
BM25. Direct engine/tokenizer, I/O and CLI additions remain outside that release.
This checks ordinary AST names/imports/calls, not arbitrary Python data flow;
runtime I/O, CLI registration and network-import tests remain separate controls.
"""
from __future__ import annotations

import ast
import re

_APPROVED = frozenset({"projection_runtime.py", "contracts.py", "projection_generation.py"})
_THIN_UPSTREAM = frozenset({"domain_cli.py", "upstream_runtime.py"})
_DOMAIN_RETRIEVAL = frozenset({"retrieval.py", "evidence_join.py"})
_CATALOG_COLLECTOR = frozenset({"catalog_collector.py"})
_CATALOG_STORE = frozenset({"catalog_store.py"})
_VOLATILE_INVENTORY = frozenset({"backup_manifest.py"})
_THIN_ALLOWED_NAMES = frozenset({"bm25_query", "bm25_status"})
_GOLD = ("retrieval-gold", "retrieval_gold")
_PROFILE_LITERALS = frozenset({
    "bm25", "claude-obsidian.bm25.v2",
    "bm25_profile",
    "video-paper-wiki.upstream-bm25-profile.v1",
    "video-paper-wiki.retrieval-config.v1",
    "video-paper-wiki.retrieval-gold.v1",
    "runtime kind must be chunk or bm25",
})
_RUNTIME_NAMES = frozenset({"_bm25_fields", "_bm25_content"})
_GENERATION_NAMES = frozenset({"bm25_profile"})
_FORBIDDEN_IMPORTS = (
    "claude_obsidian", "rank_bm25", "bm25", "subprocess", "socket", "sqlite3",
    "os", "pathlib", "shutil", "argparse", "click", "typer", "importlib",
    "requests", "httpx", "aiohttp", "urllib.request", "http.client",
)
_ENGINE_ACTION = re.compile(
    r"(?:^|_)(?:build|query|tokenize|tokenizer|retrieve|retrieval|rank|ranking|render|write|writer|save)(?:_|$)"
)
_IO_ACTIONS = frozenset({
    "open", "read_text", "read_bytes", "read", "mkdir", "unlink", "rename",
    "connect", "execute", "executemany", "add_parser", "add_command",
    "run", "Popen", "system", "exec", "eval", "__import__",
})


def _assert_thin_upstream_bm25_adapter(relative_path: str, tree: ast.AST) -> None:
    """Allow named upstream delegation, while refusing a local BM25 engine."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports = [entry.name for entry in node.names]
        elif isinstance(node, ast.ImportFrom):
            imports = [node.module or ""] + [
                f"{node.module}.{entry.name}" if node.module else entry.name
                for entry in node.names
            ]
        else:
            imports = []
        for imported in imports:
            assert not (
                imported == "rank_bm25" or imported.startswith("rank_bm25.")
            ), (relative_path, imported)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name.lower()
            if "bm25" in name:
                assert name in _THIN_ALLOWED_NAMES, (relative_path, node.name)
            assert name not in {
                "build_index", "query_index", "tokenize", "tokenizer",
                "retrieve", "retrieval", "rank", "ranking",
            }, (relative_path, node.name)


def assert_projection_source_scope(relative_path: str, source: str | None = None) -> None:
    """Check a path relative to src/video_paper_wiki and optional Python text."""
    lowered_path = relative_path.lower()
    if relative_path not in _DOMAIN_RETRIEVAL and relative_path not in _CATALOG_COLLECTOR and relative_path not in _CATALOG_STORE:
        assert not any(marker in lowered_path for marker in _GOLD), relative_path
    assert "bm25" not in lowered_path, relative_path
    if source is None:
        return
    lowered_source = source.lower()
    if relative_path not in _DOMAIN_RETRIEVAL and relative_path not in _CATALOG_COLLECTOR and relative_path not in _CATALOG_STORE and relative_path not in {"contracts.py", "domain_cli.py"}:
        assert not any(marker in lowered_source for marker in _GOLD), relative_path
    if relative_path in _DOMAIN_RETRIEVAL or relative_path in _CATALOG_COLLECTOR:
        tree=ast.parse(source,filename=relative_path)
        for node in ast.walk(tree):
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                names=[x.name for x in node.names] if isinstance(node,ast.Import) else [node.module or ""]
                assert not any(name==bad or name.startswith(bad+".") for name in names for bad in ("rank_bm25","claude_obsidian","subprocess","socket")),(relative_path,names)
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                assert node.name.lower() not in {"build_index","tokenize","tokenizer","query_index"},(relative_path,node.name)
        return
    if relative_path in _CATALOG_STORE:
        tree=ast.parse(source,filename=relative_path)
        for node in ast.walk(tree):
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                names=[x.name for x in node.names] if isinstance(node,ast.Import) else [node.module or ""]
                assert not any(name==bad or name.startswith(bad+".") for name in names for bad in ("rank_bm25","claude_obsidian","socket")),(relative_path,names)
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                assert node.name.lower() not in {"build_index","tokenize","tokenizer","query_index"},(relative_path,node.name)
        return
    if relative_path not in _APPROVED and relative_path not in _THIN_UPSTREAM and relative_path not in _VOLATILE_INVENTORY:
        assert "bm25" not in lowered_source, relative_path
    tree = ast.parse(source, filename=relative_path)
    if relative_path in _VOLATILE_INVENTORY:
        for node in ast.walk(tree):
            if isinstance(node,ast.Constant) and isinstance(node.value,str) and "bm25" in node.value.lower():
                assert node.value==".vault-meta/bm25",(relative_path,node.value)
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Name,ast.Attribute)):
                name=getattr(node,"name",getattr(node,"id",getattr(node,"attr","")))
                assert "bm25" not in name.lower(),(relative_path,name)
        return
    if relative_path in _THIN_UPSTREAM:
        _assert_thin_upstream_bm25_adapter(relative_path, tree)
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports = [entry.name for entry in node.names]
        elif isinstance(node, ast.ImportFrom):
            imports = [node.module or ""] + [
                f"{node.module}.{entry.name}" if node.module else entry.name
                for entry in node.names
            ]
        else:
            imports = []
        for imported in imports:
            forbidden_imports = _FORBIDDEN_IMPORTS if relative_path in _APPROVED else ("claude_obsidian",)
            assert not any(imported == forbidden or imported.startswith(forbidden + ".")
                           for forbidden in forbidden_imports), (relative_path, imported)
            assert "bm25" not in imported.lower(), (relative_path, imported)
        if relative_path not in _APPROVED:
            continue
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "bm25" in node.value.lower():
            assert node.value in _PROFILE_LITERALS, (relative_path, node.value)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        else:
            name = ""
        if name:
            assert not _ENGINE_ACTION.search(name.lower()), (relative_path, name)
            assert name not in _IO_ACTIONS, (relative_path, name)
        if isinstance(node, (ast.Name, ast.Attribute)):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if "bm25" in name.lower():
                assert ((relative_path == "projection_runtime.py" and name in _RUNTIME_NAMES)
                        or (relative_path == "projection_generation.py" and name in _GENERATION_NAMES)), (relative_path, name)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and "bm25" in node.name.lower():
            assert relative_path == "projection_runtime.py" and node.name in _RUNTIME_NAMES, (relative_path, node.name)
