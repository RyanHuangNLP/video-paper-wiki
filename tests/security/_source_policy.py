"""AST import policy for agent source, not an interpreter or OS sandbox.

Reject known network imports and dynamic import entrypoints, regardless of the
requested module expression. Alias analysis is deliberately scope-insensitive
and monotone: rebinding cannot erase a previously identified import capability.
It covers ordinary imports and assignment aliases, not arbitrary Python data
flow. Runtime network and filesystem boundary tests remain separate controls.
"""
from __future__ import annotations

import ast

FORBIDDEN_MODULES = ("requests", "httpx", "urllib.request", "http.client", "aiohttp")
_DYNAMIC = frozenset({"__import__", "builtins.__import__", "importlib.import_module", "importlib.__import__"})
_PROVIDERS = frozenset({"builtins", "importlib"})
_CAPABILITIES = _DYNAMIC | _PROVIDERS | {"getattr", "builtins.getattr", "vars", "builtins.vars"}


def assert_no_network_imports(source: str, *, filename: str = "<source>") -> None:
    """Fail closed on forbidden imports or recognized dynamic loader access."""
    try:
        tree = ast.parse(source, filename=filename)
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise AssertionError(f"{filename}: source cannot be parsed for import policy") from exc
    nodes = list(ast.walk(tree))
    aliases: dict[str, set[str]] = {
        "__import__": {"__import__"}, "__builtins__": {"builtins"},
        "getattr": {"getattr"}, "vars": {"vars"},
    }

    def reject(node: ast.AST, reason: str) -> None:
        raise AssertionError(f"{filename}:{getattr(node, 'lineno', 0)}: {reason}")

    def bind(name: str, qualified: set[str]) -> bool:
        old = aliases.setdefault(name, set())
        added = (qualified & _CAPABILITIES) - old
        old.update(added)
        return bool(added)

    def names(node: ast.AST) -> set[str]:
        if isinstance(node, ast.Name):
            return aliases.get(node.id, set())
        if isinstance(node, ast.Attribute):
            return {name + "." + node.attr for name in names(node.value)} & _CAPABILITIES
        if isinstance(node, ast.NamedExpr):
            return names(node.value)
        return set()

    def assignment_aliases(target: ast.AST, value: ast.AST) -> bool:
        if isinstance(target, ast.Name):
            return bind(target.id, names(value))
        if isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)):
            changed = False
            if len(target.elts) == len(value.elts):
                for destination, item in zip(target.elts, value.elts):
                    changed = assignment_aliases(destination, item) or changed
            return changed
        return False

    for node in nodes:
        if isinstance(node, ast.Import):
            imported = [(item.name, item.asname or item.name.split(".")[0],
                         item.name if item.asname else item.name.split(".")[0])
                        for item in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported = [(f"{node.module}.{item.name}" if node.module else item.name,
                         item.asname or item.name,
                         f"{node.module}.{item.name}" if node.module else item.name)
                        for item in node.names]
            if any(item.name == "*" for item in node.names) and node.module in {
                "builtins", "importlib", "urllib", "http", *FORBIDDEN_MODULES,
            }:
                reject(node, "wildcard import can expose forbidden capabilities")
        else:
            continue
        for qualified, local, bound in imported:
            if any(qualified == banned or qualified.startswith(banned + ".")
                   for banned in FORBIDDEN_MODULES):
                reject(node, f"forbidden network import: {qualified}")
            if qualified in _DYNAMIC:
                reject(node, f"dynamic import entrypoint: {qualified}")
            bind(local, {bound})

    # Reach a fixed point for ordinary aliases, including aliases declared in a
    # different syntactic scope. This intentionally does not execute the source.
    changed = True
    while changed:
        changed = False
        for node in nodes:
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
                targets, value = [node.target], node.value
            else:
                continue
            if value is None:
                continue
            for target in targets:
                changed = assignment_aliases(target, value) or changed

    for node in nodes:
        if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
            if names(node) & _DYNAMIC:
                reject(node, "dynamic import entrypoint access")
        if isinstance(node, ast.Call):
            if names(node.func) & {"getattr", "builtins.getattr", "vars", "builtins.vars"} and node.args and names(node.args[0]) & _PROVIDERS:
                reject(node, "reflective dynamic import provider access")
        if isinstance(node, ast.Attribute) and node.attr == "__dict__":
            if names(node.value) & _PROVIDERS:
                reject(node, "reflective dynamic import provider namespace")
        if isinstance(node, ast.Subscript) and names(node.value) & _PROVIDERS:
            reject(node, "reflective dynamic import provider subscript")
