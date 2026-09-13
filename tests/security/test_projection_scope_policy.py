"""Scope exceptions admit pure profiles, not an upstream execution adapter."""
import pytest

from tests.security._projection_scope_policy import assert_projection_source_scope


@pytest.mark.parametrize("path,source", [
    ("projection_runtime.py", 'PROFILE = "claude-obsidian.bm25.v2"\ndef _bm25_content(doc):\n    return len(doc)\n'),
    ("contracts.py", 'from video_paper_wiki.projection_runtime import validate_runtime_record\nTITLE = "video-paper-wiki.upstream-bm25-profile.v1"\ndef validate(doc):\n    return validate_runtime_record("bm25", doc)\n'),
    ("commands/search.py", 'def grep(text):\n    return "word" in text\n'),
    ("projection_runtime.py", 'def pointer(text):\n    return text.replace("/", "~1")\n'),
    ("projection_generation.py", 'def validate(runtime, profile):\n    return runtime["bm25_profile"] == profile["bm25_profile"]\n'),
    ("domain_cli.py", 'def status():\n    return bm25_status()\n'),
    ("upstream_runtime.py", 'SCRIPT = "scripts/bm25-index.py"\ndef bm25_status():\n    return delegate(SCRIPT)\n'),
    ("backup_manifest.py", 'EXCLUDED = (".vault-meta/bm25",)\ndef inventory(paths): return paths\n'),
])
def test_scope_allows_only_released_pure_profile_examples(path, source):
    assert_projection_source_scope(path, source)


@pytest.mark.parametrize("path,source", [
    ("bm25.py", ""),
    ("notes/bm25/data.json", None),
    ("notes/engine.py", 'PROFILE = "bm25"'),
    ("notes/projection_runtime.py", 'PROFILE = "bm25"'),
    ("commands/search.py", '# BM25 shortcut'),
    ("retrieval_gold.json", None),
    ("notes/retrieval-gold/data.json", None),
    ("projection_runtime.py", '# retrieval_gold stays out of scope'),
    ("projection_runtime.py", 'import claude_obsidian as upstream'),
    ("notes/engine.py", 'import claude_obsidian as upstream'),
    ("notes/engine.py", 'from claude_obsidian import ledgers as engine'),
    ("contracts.py", 'from claude_obsidian import ledgers'),
    ("projection_runtime.py", 'from rank_bm25 import BM25Okapi as engine'),
    ("projection_runtime.py", 'import subprocess as process'),
    ("projection_runtime.py", 'import sqlite3'),
    ("projection_runtime.py", 'from urllib import request'),
    ("projection_runtime.py", 'from pathlib import Path'),
    ("projection_runtime.py", 'import argparse'),
    ("contracts.py", 'def build_index(doc):\n    return doc'),
    ("projection_runtime.py", 'def tokenize(text):\n    return text.split()'),
    ("projection_runtime.py", 'def query_index(text):\n    return []'),
    ("projection_runtime.py", 'def bm25_engine(doc):\n    return doc'),
    ("projection_runtime.py", 'def validate(doc):\n    return backend.build(doc)'),
    ("projection_runtime.py", 'def validate(doc):\n    return backend.query(doc)'),
    ("projection_runtime.py", 'def validate(doc):\n    path.write_text(doc)'),
    ("projection_runtime.py", 'def validate(doc):\n    return open(doc)'),
    ("projection_runtime.py", 'parser.add_parser("index")'),
    ("projection_runtime.py", 'COMMAND = "bm25-index.py build"'),
    ("contracts.py", 'def _bm25_content(doc):\n    return doc'),
    ("projection_generation.py", 'def bm25_engine(doc):\n    return doc'),
    ("projection_generation.py", 'import claude_obsidian'),
    ("projection_generation.py", 'def validate(doc):\n    return backend.query(doc)'),
    ("upstream_runtime.py", 'from rank_bm25 import BM25Okapi'),
    ("upstream_runtime.py", 'def build_index(doc):\n    return doc'),
    ("domain_cli.py", 'def query_index(text):\n    return []'),
    ("backup_manifest.py", 'def bm25_backup(): return []'),
    ("backup_manifest.py", 'COMMAND = "bm25-index.py build"'),
])
def test_scope_refuses_unreleased_gold_engine_and_execution(path, source):
    with pytest.raises(AssertionError):
        assert_projection_source_scope(path, source)


def test_released_evaluator_terms_do_not_allow_local_engine_imports():
    assert_projection_source_scope("retrieval.py", "def evaluate_retrieval(gold, results): return results")
    with pytest.raises(AssertionError):
        assert_projection_source_scope("retrieval.py", "from rank_bm25 import BM25Okapi")
