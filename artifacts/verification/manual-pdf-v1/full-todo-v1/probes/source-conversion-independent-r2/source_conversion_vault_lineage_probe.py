"""Independent Vault named-edge lineage probes for source conversion.

The candidate source is imported from the frozen working clone named by the
R1 local-candidate manifest. Every Vault is disposable and lives below
/private/tmp. This probe writes only its JSON evidence beside this file.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ORIGINAL_ROOT = Path(__file__).resolve().parents[6]
CANDIDATE_ROOT = Path(
    "/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/"
    "source-conversion-v1/terminal-1/source"
)
if str(CANDIDATE_ROOT) not in sys.path:
    sys.path.insert(0, str(CANDIDATE_ROOT))
if str(CANDIDATE_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(CANDIDATE_ROOT / "src"))

from tests.research.test_source_conversion import conversion_fixture
from tests.support import make_checkout
from tests.upstream.test_markdown_source import _snapshot
from video_paper_wiki.contracts import ContractError
from video_paper_wiki_research import source_conversion as conversion


@contextmanager
def _cwd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _replace_captured_file(path: Path) -> dict:
    original = path.read_bytes()
    mode = stat.S_IMODE(path.stat().st_mode)
    replacement = path.with_name(path.name + ".probe-replacement")
    replacement.write_bytes(original + b"\nprobe-replacement")
    os.chmod(replacement, mode)
    os.replace(replacement, path)
    return {"kind": "captured-file", "path": str(path), "original": original, "mode": mode}


def _replace_captured_ancestor(path: Path) -> dict:
    ancestor = path.parent
    moved = ancestor.with_name(ancestor.name + ".probe-original")
    os.rename(ancestor, moved)
    ancestor.mkdir(mode=stat.S_IMODE(moved.stat().st_mode))
    return {"kind": "captured-ancestor", "path": str(ancestor), "moved": moved}


def _restore_mutation(mutation: dict) -> None:
    if mutation["kind"] == "captured-file":
        path = Path(mutation["path"])
        replacement = path.with_name(path.name + ".probe-restore")
        replacement.write_bytes(mutation["original"])
        os.chmod(replacement, mutation["mode"])
        os.replace(replacement, path)
        return
    path = Path(mutation["path"])
    moved = Path(mutation["moved"])
    if path.exists():
        path.rmdir()
    os.rename(moved, path)


def _run_case(*, mutation_kind: str | None, ordinary_prepare_failure: bool) -> dict:
    trace = {
        "vault_enters": 0,
        "vault_exits": 0,
        "snapshot_ids": [],
        "collect_snapshot_ids": [],
        "prepare_snapshot_ids": [],
    }
    mutation: dict | None = None
    with tempfile.TemporaryDirectory(prefix="vp-source-conversion-vault-", dir="/private/tmp") as raw_tmp:
        checkout = make_checkout(Path(raw_tmp))
        with _cwd(checkout):
            kwargs, _document, _context, capture = conversion_fixture(checkout)
            vault = kwargs["vault_root"]
            before = _snapshot(vault)
            target = vault / capture["stored_path"]

            original_vault = conversion._vault
            original_collect = conversion.collect_source_state
            original_assemble = conversion.assemble_conversion
            original_prepare = conversion._prepare_source_publication_retained

            @contextmanager
            def traced_vault(*args, **call_kwargs):
                trace["vault_enters"] += 1
                try:
                    with original_vault(*args, **call_kwargs) as values:
                        trace["snapshot_ids"].append(id(values[1]))
                        yield values
                finally:
                    trace["vault_exits"] += 1

            def traced_collect(*args, **call_kwargs):
                trace["collect_snapshot_ids"].append(id(args[0]))
                return original_collect(*args, **call_kwargs)

            def traced_assemble(*args, **call_kwargs):
                nonlocal mutation
                result = original_assemble(*args, **call_kwargs)
                if mutation_kind == "captured-file":
                    mutation = _replace_captured_file(target)
                elif mutation_kind == "captured-ancestor":
                    mutation = _replace_captured_ancestor(target)
                return result

            def traced_prepare(*args, **call_kwargs):
                trace["prepare_snapshot_ids"].append(id(call_kwargs["snapshot"]))
                if ordinary_prepare_failure:
                    raise ContractError(
                        "SOURCE_CONVERSION_INJECTED",
                        "independent ordinary retained-prepare refusal",
                        {"instance_pointer": "/prepare"},
                        exit_code=75,
                    )
                return original_prepare(*args, **call_kwargs)

            conversion._vault = traced_vault
            conversion.collect_source_state = traced_collect
            conversion.assemble_conversion = traced_assemble
            conversion._prepare_source_publication_retained = traced_prepare
            error = None
            result = None
            try:
                try:
                    result = conversion.convert_source_knowledge(**kwargs)
                except ContractError as exc:
                    error = {
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                        "exit_code": exc.exit_code,
                    }
            finally:
                conversion._vault = original_vault
                conversion.collect_source_state = original_collect
                conversion.assemble_conversion = original_assemble
                conversion._prepare_source_publication_retained = original_prepare
                if mutation is not None:
                    _restore_mutation(mutation)

            after = _snapshot(vault)
            assert before == after, "Vault did not return to the pre-probe named state"
            assert trace["vault_enters"] == trace["vault_exits"] == 1
            assert len(trace["snapshot_ids"]) == 1
            snapshot_id = trace["snapshot_ids"][0]
            assert trace["collect_snapshot_ids"]
            assert all(item == snapshot_id for item in trace["collect_snapshot_ids"])
            assert all(item == snapshot_id for item in trace["prepare_snapshot_ids"])
            if mutation_kind is not None:
                # The retained snapshot must reject both mutations before a
                # successful publication request can escape.
                expected_code = "WORK_PATH_UNSAFE"
                outcome = "pass" if error and error["code"] == expected_code else "mismatch"
            elif ordinary_prepare_failure:
                expected_code = "SOURCE_CONVERSION_INJECTED"
                outcome = "pass" if error and error["code"] == expected_code else "mismatch"
            else:
                expected_code = None
                outcome = "pass" if error is None and result and result["state"] == "source_publication_prepared" else "mismatch"
            return {
                "mutation_kind": mutation_kind,
                "ordinary_prepare_failure": ordinary_prepare_failure,
                "expected_code": expected_code,
                "observed_error": error,
                "result_state": None if result is None else result["state"],
                "outcome": outcome,
                "vault_restored": before == after,
                "trace": trace,
            }


def main() -> None:
    cases = [
        _run_case(mutation_kind="captured-file", ordinary_prepare_failure=False),
        _run_case(mutation_kind="captured-file", ordinary_prepare_failure=True),
        _run_case(mutation_kind="captured-ancestor", ordinary_prepare_failure=False),
        _run_case(mutation_kind="captured-ancestor", ordinary_prepare_failure=True),
        _run_case(mutation_kind=None, ordinary_prepare_failure=True),
        _run_case(mutation_kind=None, ordinary_prepare_failure=False),
    ]
    result = {
        "schema": "video-paper-wiki.source-conversion-independent-vault-lineage-probe.v2",
        "candidate_root": str(CANDIDATE_ROOT),
        "source_hashes": {
            "source_conversion": hashlib.sha256((CANDIDATE_ROOT / "src/video_paper_wiki_research/source_conversion.py").read_bytes()).hexdigest(),
            "source_conversion_io": hashlib.sha256((CANDIDATE_ROOT / "src/video_paper_wiki_research/source_conversion_io.py").read_bytes()).hexdigest(),
            "source_publication": hashlib.sha256((CANDIDATE_ROOT / "src/video_paper_wiki/source_publication.py").read_bytes()).hexdigest(),
        },
        "cases": cases,
        "all_cases_pass": all(item["outcome"] == "pass" for item in cases),
        "notes": [
            "Vault mutations are injected after assembly returns and before the retained preparation helper is entered.",
            "Mutated disposable Vault names are restored before the final before/after comparison.",
            "A mismatch records the candidate's actual error classification instead of weakening the assertion.",
        ],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
