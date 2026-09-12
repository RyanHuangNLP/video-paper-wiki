# Wheel-build dependency note (current extraction candidate)

This is **not** an integrated-product claim. It records why `uv build --offline`
failed on this machine and what was installed in an isolated temp environment.

## Declared build-system (unchanged)

Both `pyproject.toml` files declare:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- Root candidate: `/private/tmp/vpwiki-wheel-handoff/work/candidate/pyproject.toml`
- Parser executor: `operator/parser_executor/pyproject.toml` (same backend)

`uv.lock` does not pin hatchling. Runtime dependencies remain `jsonschema>=4.23` and `pypdf>=5.0`. Docling is optional and was **not** installed.

## Concrete gap

| Check | Result |
| --- | --- |
| Shared locked venv `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv` | `hatchling` missing |
| `uv cache dir` (`/Users/huangzhanpeng/.cache/uv`) | 0 paths matching `*hatchling*` |
| `uv build --offline` of the candidate copy | exit 2: `hatchling was not found in the cache` |

That is the same offline failure previously seen. It is a **build-backend cache miss**, not a missing research source file.

## Isolated install (once)

Created `/private/tmp/vpwiki-wheel-handoff/work/build-venv` with the locked Python 3.13.13. Then **one** `uv pip install --python <build-venv> hatchling` (network allowed only for this isolated env).

Installed into that venv only:

- hatchling==1.32.0
- packaging==26.3
- pathspec==1.1.1
- pluggy==1.6.0
- tomlkit==0.15.1
- trove-classifiers==2026.6.1.19

Shared `.venv` still has no hatchling. Frozen worktree `pyproject.toml` and `uv.lock` were not written. Docling/models were not downloaded.

## Runtime bridge (not build-system)

Product wheels were installed with `--no-deps`. jsonschema/pypdf were **not** reinstalled; a `.pth` points the install venv at:

`/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/lib/python3.13/site-packages`
