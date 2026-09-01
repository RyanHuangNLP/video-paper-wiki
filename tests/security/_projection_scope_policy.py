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
_GOLD = ("retrieval-gold", "retrieval_gold")
_PROFILE_LITERALS = frozenset({
    "bm25", "claude-obsidian.bm25.v2",
    "bm25_profile",
    "video-paper-wiki.upstream-bm25-profile.v1",
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


def assert_projection_source_scope(relative_path: str, source: str | None = None) -> None:
    """Check a path relative to src/video_paper_wiki and optional Python text."""
    lowered_path = relative_path.lower()
    assert not any(marker in lowered_path for marker in _GOLD), relative_path
    assert "bm25" not in lowered_path, relative_path
    if source is None:
        return
    lowered_source = source.lower()
    assert not any(marker in lowered_source for marker in _GOLD), relative_path
    if relative_path not in _APPROVED:
        assert "bm25" not in lowered_source, relative_path
    tree = ast.parse(source, filename=relative_path)
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
