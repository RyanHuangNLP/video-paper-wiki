#!/bin/sh
set -u
ROOT=/Users/huangzhanpeng/python_code/video-paper-wiki
W="$ROOT/.work/parallel/code-proof-v1/terminal-1/source"
CF="$ROOT/artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/config-r1"
PATCH="$CF/architect-grok-regression-correction-r5.patch"
PY="$1"
LABEL="$2"
LOG="$CF/steward-patch-review-r5/${LABEL}.stdout.log"
ERR="$CF/steward-patch-review-r5/${LABEL}.stderr.log"
TMP=$(mktemp -d /private/tmp/config-r5-replay-XXXXXX)
printf 'temp=%s\npython=%s\n' "$TMP" "$PY" > "$CF/steward-patch-review-r5/${LABEL}.meta.txt"
mkdir -p "$TMP/src" "$TMP/tests/unit" "$TMP/tests/fixtures"
cp -R "$W/src/video_paper_wiki" "$TMP/src/"
cp "$W/tests/unit/test_code_config_parser.py" "$TMP/tests/unit/"
cp "$W/tests/fixtures/code-config-vectors-v1.json" "$TMP/tests/fixtures/"
touch "$TMP/tests/__init__.py" "$TMP/tests/unit/__init__.py"
git -C "$TMP" init -q
git -C "$TMP" add src/video_paper_wiki tests
if ! git -C "$TMP" apply --check "$PATCH" >"$ERR" 2>&1; then
  printf 'PATCH_APPLY_CHECK=FAIL\n' >> "$ERR"
  exit 2
fi
git -C "$TMP" apply "$PATCH" >>"$ERR" 2>&1
cat > "$TMP/run_selected.py" <<PYRUNNER
import sys
import unittest
sys.path.insert(0, r"$TMP/src")
sys.path.insert(0, r"$TMP")
suite = unittest.TestLoader().loadTestsFromNames([
    "tests.unit.test_code_config_parser.TestCodeConfigParser.test_stdlib_object_keys_must_be_exact_str",
    "tests.unit.test_code_config_parser.TestCodeConfigParser.test_scanner_error_content_omits_source_sentinels",
])
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
PYRUNNER
PYTHONDONTWRITEBYTECODE=1 "$PY" -I -B "$TMP/run_selected.py" >"$LOG" 2>"$ERR"
status=$?
printf 'TEST_EXIT=%s\nTEMP=%s\n' "$status" "$TMP" > "$CF/steward-patch-review-r5/${LABEL}.meta.txt"
exit "$status"
