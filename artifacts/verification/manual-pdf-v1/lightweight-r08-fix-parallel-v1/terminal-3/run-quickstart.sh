#!/bin/sh
# Replay the Terminal-3 quickstart as real shell statements (Bash and zsh).
#
# Document mapping (draft/docs/lightweight-pdf-quickstart.md):
#   section 2  — CLI array + PDF/WS/OUT/QUESTION/TOPIC/REQUIREMENTS + CTX/ANS/QA_MD/...
#   section 3.1 — mkdir; "${CLI[@]}" pdf add
#   section 3.2 — "${CLI[@]}" index build
#   section 3.3 — "${CLI[@]}" qa export > "$CTX"
#   section 3.4 — current-session / protocol JSON (helper, not a model call)
#   section 3.5 — "${CLI[@]}" qa import
#   section 3.6 — writing export / protocol draft / writing import
#   section 1   — --help; source form uses CLI=(python -B -m ...) + PYTHONPATH
#
# Substituted only via flags/env: --python --pdf --workspace --output
#   [--question --topic --requirements --title --source-src --mode --step --log]
# No Terminal-3 write-paths are hardcoded.
#
# Invoke:
#   /bin/bash --noprofile --norc run-quickstart.sh ...
#   /bin/zsh -f run-quickstart.sh ...

PYTHON="${PYTHON:-}"
PDF="${PDF:-}"
WS="${WS:-}"
OUT="${OUT:-}"
QUESTION="${QUESTION:-What method does this paper propose?}"
TOPIC="${TOPIC:-video diffusion models}"
REQUIREMENTS="${REQUIREMENTS:-Two short paragraphs citing original PDF file pages}"
TITLE="${TITLE:-Video Diffusion Models}"
SOURCE_SRC="${SOURCE_SRC:-}"
MODE="${MODE:-installed}"
STEP="${STEP:-walkthrough}"
LOG="${LOG:-}"
HELPER="${HELPER:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --python) PYTHON=$2; shift 2 ;;
    --pdf) PDF=$2; shift 2 ;;
    --workspace) WS=$2; shift 2 ;;
    --output) OUT=$2; shift 2 ;;
    --question) QUESTION=$2; shift 2 ;;
    --topic) TOPIC=$2; shift 2 ;;
    --requirements) REQUIREMENTS=$2; shift 2 ;;
    --title) TITLE=$2; shift 2 ;;
    --source-src) SOURCE_SRC=$2; shift 2 ;;
    --mode) MODE=$2; shift 2 ;;
    --step) STEP=$2; shift 2 ;;
    --log) LOG=$2; shift 2 ;;
    --helper) HELPER=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

record() {
  name=$1
  code=$2
  if [ -n "$LOG" ]; then
    printf '%s %s\n' "$name" "$code" >> "$LOG"
  fi
}

if [ -z "$PYTHON" ]; then
  echo "need --python" >&2
  exit 2
fi

# Documented installed custom-interpreter form (section 2 comment):
#   CLI=("/absolute/path/to/python" -I -B -m video_paper_wiki_research)
# Documented source form:
#   CLI=(python -B -m video_paper_wiki_research)  with PYTHONPATH set.
# Replay uses the quoted-python array so a path with spaces stays one word.
if [ "$MODE" = "source" ]; then
  if [ -z "$SOURCE_SRC" ]; then
    echo "source mode needs --source-src" >&2
    exit 2
  fi
  export PYTHONPATH=$SOURCE_SRC
  export PYTHONDONTWRITEBYTECODE=1
  CLI=("$PYTHON" -B -m video_paper_wiki_research)
else
  unset PYTHONPATH
  CLI=("$PYTHON" -I -B -m video_paper_wiki_research)
fi

if [ "$STEP" = "help" ]; then
  "${CLI[@]}" --help
  code=$?
  record help "$code"
  exit "$code"
fi

if [ -z "$WS" ] || [ -z "$OUT" ]; then
  echo "need --workspace and --output" >&2
  exit 2
fi

# Documented output-file names (section 2 second block). Paths with spaces stay quoted.
CTX="$OUT/qa-context.json"
ANS="$OUT/qa-answer.json"
QA_MD="$OUT/qa answer.md"
WCTX="$OUT/writing-context.json"
DRAFT="$OUT/writing-draft.json"
WMD="$OUT/writing draft.md"

if [ "$STEP" = "export" ]; then
  "${CLI[@]}" qa export --question "$QUESTION" --workspace "$WS" > "$CTX"
  code=$?
  record qa-export "$code"
  exit "$code"
fi

if [ "$STEP" != "walkthrough" ]; then
  echo "unknown --step $STEP" >&2
  exit 2
fi

if [ -z "$PDF" ]; then
  echo "walkthrough needs --pdf" >&2
  exit 2
fi

mkdir -p "$WS" "$OUT"
"${CLI[@]}" pdf add --pdf "$PDF" --workspace "$WS" --title "$TITLE"
code=$?
record pdf-add "$code"
[ "$code" -eq 0 ] || exit "$code"

"${CLI[@]}" index build --workspace "$WS"
code=$?
record index-build "$code"
[ "$code" -eq 0 ] || exit "$code"

"${CLI[@]}" qa export --question "$QUESTION" --workspace "$WS" > "$CTX"
code=$?
record qa-export "$code"
[ "$code" -eq 0 ] || exit "$code"

if [ -n "$HELPER" ]; then
  "$PYTHON" -B "$HELPER" --context "$CTX" --answer "$ANS"
  code=$?
  record protocol-answer "$code"
  [ "$code" -eq 0 ] || exit "$code"
fi

"${CLI[@]}" qa import --context "$CTX" --answer "$ANS" --output "$QA_MD" --workspace "$WS"
code=$?
record qa-import "$code"
[ "$code" -eq 0 ] || exit "$code"

"${CLI[@]}" writing export --topic "$TOPIC" --requirements "$REQUIREMENTS" --workspace "$WS" > "$WCTX"
code=$?
record writing-export "$code"
[ "$code" -eq 0 ] || exit "$code"

if [ -n "$HELPER" ]; then
  "$PYTHON" -B "$HELPER" --context "$WCTX" --draft "$DRAFT"
  code=$?
  record protocol-draft "$code"
  [ "$code" -eq 0 ] || exit "$code"
fi

"${CLI[@]}" writing import --context "$WCTX" --draft "$DRAFT" --output "$WMD" --workspace "$WS"
code=$?
record writing-import "$code"
exit "$code"
