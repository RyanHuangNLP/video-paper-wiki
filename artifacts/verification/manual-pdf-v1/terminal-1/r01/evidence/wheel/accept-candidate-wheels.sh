#!/bin/sh
# Repeatable wheel build/install probe for the current extraction candidate.
# Verifies installability only. Does not claim an integrated product.
# Does not modify the source tree, shared .venv, pyproject.toml, or uv.lock.
# Does not download Docling or models.
#
# Usage:
#   accept-candidate-wheels.sh <source-tree> [output-dir]
#
# <source-tree> must contain pyproject.toml, src/video_paper_wiki,
# src/video_paper_wiki_research (this candidate), and optionally
# operator/parser_executor.
#
# Environment:
#   VPWIKI_PYTHON   interpreter that already has jsonschema/pypdf (locked runtime)
#                   default: /Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python
#   UV              uv binary; default: uv on PATH, else ~/.hermes/bin/uv

set -eu

SRC=${1:-}
OUT=${2:-/private/tmp/vpwiki-wheel-handoff}
if [ -z "$SRC" ] || [ ! -f "$SRC/pyproject.toml" ]; then
  echo "usage: $0 <source-tree> [output-dir]" >&2
  exit 2
fi
SRC=$(cd "$SRC" && pwd)
OUT=$(mkdir -p "$OUT" && cd "$OUT" && pwd)
UV_BIN=${UV:-}
if [ -z "$UV_BIN" ]; then
  if command -v uv >/dev/null 2>&1; then
    UV_BIN=$(command -v uv)
  elif [ -x /Users/huangzhanpeng/.hermes/bin/uv ]; then
    UV_BIN=/Users/huangzhanpeng/.hermes/bin/uv
  else
    echo "uv is required" >&2
    exit 2
  fi
fi
LOCKED_PY=${VPWIKI_PYTHON:-/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python}
if [ ! -x "$LOCKED_PY" ]; then
  echo "VPWIKI_PYTHON is not executable: $LOCKED_PY" >&2
  exit 2
fi

WORK=$OUT/work
LOG=$OUT/logs
mkdir -p "$LOG" "$WORK/wheels" "$WORK/probe-cwd" "$WORK/empty-home"
BUILD_VENV=$WORK/build-venv
INSTALL_VENV=$WORK/install-venv
WHEELS=$WORK/wheels

copy_or_use_src() {
  # Never write into SRC. Build from a copy when SRC is the frozen worktree
  # or when untracked files need to travel with the tree.
  CANDIDATE=$WORK/candidate
  rm -rf "$CANDIDATE"
  mkdir -p "$CANDIDATE"
  # Portable copy of the packaging surface, including untracked research code.
  if command -v rsync >/dev/null 2>&1; then
    rsync -a \
      --exclude '.git/' \
      --exclude '.venv/' \
      --exclude '.pytest_cache/' \
      --exclude '__pycache__/' \
      --exclude '.DS_Store' \
      --include '/pyproject.toml' \
      --include '/README.md' \
      --include '/src/' \
      --include '/src/video_paper_wiki/' \
      --include '/src/video_paper_wiki/***' \
      --include '/src/video_paper_wiki_research/' \
      --include '/src/video_paper_wiki_research/***' \
      --include '/schemas/' \
      --include '/schemas/***' \
      --include '/docs/' \
      --include '/docs/seed/' \
      --include '/docs/seed/***' \
      --include '/taxonomy/' \
      --include '/taxonomy/***' \
      --include '/catalog/' \
      --include '/catalog/***' \
      --include '/operator/' \
      --include '/operator/parser_executor/' \
      --include '/operator/parser_executor/***' \
      --exclude '*' \
      "$SRC/" "$CANDIDATE/"
  else
    echo "rsync is required to copy untracked candidate files" >&2
    exit 2
  fi
  if [ ! -d "$CANDIDATE/src/video_paper_wiki_research" ]; then
    echo "src/video_paper_wiki_research is missing from $SRC" >&2
    exit 2
  fi
}

copy_or_use_src

{
  echo "source=$SRC"
  echo "candidate=$WORK/candidate"
  echo "locked_python=$LOCKED_PY"
  echo "uv=$UV_BIN"
  "$LOCKED_PY" -c "import tomllib; print('build-system', tomllib.load(open('$WORK/candidate/pyproject.toml','rb'))['build-system'])"
} > "$LOG/dependency-probe.log"

# Isolated build venv (not the shared .venv)
rm -rf "$BUILD_VENV"
"$UV_BIN" venv --python "$LOCKED_PY" "$BUILD_VENV" > "$LOG/build-venv-create.log" 2>&1
BUILD_PY=$BUILD_VENV/bin/python

if ! "$BUILD_PY" -c "import hatchling" >/dev/null 2>&1; then
  # One isolated install of only build-system.requires. Not Docling.
  # Offline cache miss is the known gap; allow network for hatchling only.
  if ! env -u PYTHONPATH -u PYTHONHOME \
      "$UV_BIN" pip install --python "$BUILD_PY" hatchling \
      > "$LOG/hatchling-install.log" 2>&1; then
    echo "FAILED: could not install hatchling into isolated build venv" >&2
    cat "$LOG/hatchling-install.log" >&2
    exit 1
  fi
else
  echo "hatchling already present in isolated build venv" > "$LOG/hatchling-install.log"
fi
"$BUILD_PY" -c "import hatchling,importlib.metadata as m; print('hatchling', m.version('hatchling'), hatchling.__file__)" \
  > "$LOG/hatchling-import.log"

rm -rf "$WHEELS"
mkdir -p "$WHEELS"
( cd "$WORK/candidate" && env -u PYTHONPATH -u PYTHONHOME \
    "$BUILD_PY" -m hatchling build --target wheel ) \
  > "$LOG/hatchling-build.log" 2>&1
cp "$WORK/candidate"/dist/*.whl "$WHEELS/"
if [ -f "$WORK/candidate/operator/parser_executor/pyproject.toml" ]; then
  ( cd "$WORK/candidate/operator/parser_executor" && env -u PYTHONPATH -u PYTHONHOME \
      "$BUILD_PY" -m hatchling build --target wheel ) \
    >> "$LOG/hatchling-build.log" 2>&1
  cp "$WORK/candidate/operator/parser_executor"/dist/*.whl "$WHEELS/"
fi
ls -l "$WHEELS" >> "$LOG/hatchling-build.log"

rm -rf "$INSTALL_VENV"
"$UV_BIN" venv --python "$LOCKED_PY" "$INSTALL_VENV" > "$LOG/install-venv-create.log" 2>&1
INST_PY=$INSTALL_VENV/bin/python
# Product wheels only; runtime jsonschema/pypdf come from a .pth to the locked env.
env -u PYTHONPATH -u PYTHONHOME UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never \
  "$UV_BIN" pip install --offline --no-cache --no-deps --python "$INST_PY" "$WHEELS"/*.whl \
  > "$LOG/wheel-install.log" 2>&1

LOCKED_PURELIB=$("$LOCKED_PY" -c "import sysconfig; print(sysconfig.get_path('purelib'))")
INST_PURELIB=$("$INST_PY" -c "import sysconfig; print(sysconfig.get_path('purelib'))")
printf '%s\n' "$LOCKED_PURELIB" > "$INST_PURELIB/vpwiki-locked-runtime.pth"

PROBE_PY='
import json, os, sys, importlib.resources as r
import video_paper_wiki_research as pkg
schema = r.files("video_paper_wiki_research").joinpath("schemas/manual-pdf-intake.v1.schema.json")
prompt = r.files("video_paper_wiki_research").joinpath("prompts/paper-analysis-v1.md")
schema_text = schema.read_text(encoding="utf-8") if schema.is_file() else ""
prompt_text = prompt.read_text(encoding="utf-8") if prompt.is_file() else ""
print(json.dumps({
  "python": sys.executable,
  "prefix": sys.prefix,
  "cwd": os.getcwd(),
  "PYTHONPATH": os.environ.get("PYTHONPATH"),
  "module": pkg.__file__,
  "schema_is_file": schema.is_file(),
  "schema_repr": str(schema),
  "schema_has_intake_title": "video-paper-wiki-research.manual-pdf-intake.v1" in schema_text,
  "prompt_is_file": prompt.is_file(),
  "prompt_repr": str(prompt),
  "prompt_has_heading": "Paper analysis task" in prompt_text,
}, ensure_ascii=False, indent=2))
'

(
  cd "$WORK/probe-cwd"
  env -i PATH="$INSTALL_VENV/bin:/usr/bin:/bin" HOME="$WORK/empty-home" PYTHONDONTWRITEBYTECODE=1 \
    "$INST_PY" -I -c "$PROBE_PY"
) > "$LOG/installed-probe.log"

(
  cd "$WORK/probe-cwd"
  env -i PATH="$INSTALL_VENV/bin:/usr/bin:/bin" HOME="$WORK/empty-home" PYTHONDONTWRITEBYTECODE=1 \
    vpwiki-research pdf intake
) > "$LOG/installed-entry.log" 2>&1 || true

"$INST_PY" -c "
import json
from pathlib import Path
probe=json.loads(Path('$LOG/installed-probe.log').read_text())
prefix=Path(probe['prefix']).resolve()
module=Path(probe['module']).resolve()
src=Path('$SRC').resolve()
assert probe['PYTHONPATH'] is None
assert module.is_relative_to(prefix), (module, prefix)
assert not module.is_relative_to(src), module
assert probe['schema_is_file'] and probe['schema_has_intake_title']
assert probe['prompt_is_file'] and probe['prompt_has_heading']
print('PROBE_ASSERT_OK', module)
"

echo "OK: installed research module, schema, and prompt resolve from $INSTALL_VENV"
echo "This verifies the given candidate tree's wheel installability only."
