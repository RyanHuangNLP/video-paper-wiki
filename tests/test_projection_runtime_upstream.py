"""Disposable pinned public CLI rebuilds; no upstream internal API imports.

The Markdown below is fixture input, not a production canonical projection.
Synthetic/no-egress command flags are not an OS network sandbox. Missing,
dirty or mismatched upstream checkouts fail through the shared pin checker.
"""
import hashlib

from tests.upstream._transaction_fixture import (
    UP, Runner, bundle, dump, init, snapshot, verify_sources,
)
from video_paper_wiki.projection_runtime import (
    markdown_projection_equal, parse_projection_json, runtime_projection_equal,
    runtime_projection_sha256, validate_runtime_record,
)


def test_pinned_public_rebuild_cjk_nfkc_and_overlap(tmp_path):
    out = tmp_path.resolve()
    before = verify_sources(out)
    runner = Runner(out)
    vault = out / "v"
    try:
        init(runner, vault, "runtime-fixture-init")
        # Publish fixture inputs via the public transaction CLI, with no
        # managed requests or invented source/evidence-unit relationships.
        long_body = "\n\n".join(
            f"Paragraph {n:03d}. " + "stable overlap context " * 25
            for n in range(12)
        )
        pages = {
            "wiki/papers/CJK.md": (
                "---\ntitle: CJK fixture\n---\n\n全文检索 ABC.\n"
            ).encode(),
            "wiki/papers/Overlap.md": (
                "---\ntitle: Overlap fixture\n---\n\n" + long_body + "\n"
            ).encode(),
        }
        operation = bundle(vault, "runtime-fixture-pages", "generic", pages)
        plan = runner.inspect("pages-inspect", vault, operation)
        runner.apply("pages-apply", vault, operation, plan)
        markdown_before = {
            p.relative_to(vault).as_posix(): p.read_bytes()
            for p in sorted((vault / "wiki").rglob("*.md"))
        }
        rounds = []
        for number in (1, 2):
            runner.run(f"chunks-rebuild-{number}", [
                UP / "scripts/contextual-prefix.py", "--vault", vault,
                "--all", "--no-llm", "--rebuild",
            ])
            runner.run(f"bm25-rebuild-{number}", [
                UP / "scripts/bm25-index.py", "--vault", vault, "build",
            ])
            chunks = {}
            for path in sorted((vault / ".vault-meta/chunks").glob("*/chunk-*.json")):
                raw = path.read_bytes()
                rel = path.relative_to(vault).as_posix()
                document = validate_runtime_record("chunk", parse_projection_json(raw))
                assert document["prefix_source"] == "synthetic"
                assert document["page_address"] == "syn-" + hashlib.sha256(
                    document["page_path"].encode("utf-8")
                ).hexdigest()
                chunks[rel] = document
                artifact = out / f"round-{number}" / rel
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_bytes(raw)
            index_raw = (vault / ".vault-meta/bm25/index.json").read_bytes()
            index = validate_runtime_record("bm25", parse_projection_json(index_raw))
            (out / f"round-{number}/index.json").write_bytes(index_raw)
            assert chunks and len(chunks) == index["doc_count"]
            assert {d["path"] for d in index["docs"].values()} == set(chunks)
            for identity, doc in index["docs"].items():
                chunk = chunks[doc["path"]]
                assert identity == f'{chunk["page_address"]}:{chunk["chunk_index"]}'
                assert doc["body_hash"] == chunk["body_hash"]
                assert doc["page_body_hash"] == chunk["page_body_hash"]
            rounds.append((chunks, index))

        first_chunks, first_index = rounds[0]
        second_chunks, second_index = rounds[1]
        assert first_chunks.keys() == second_chunks.keys()
        for path in first_chunks:
            assert runtime_projection_equal("chunk", first_chunks[path], second_chunks[path])
        assert runtime_projection_equal("bm25", first_index, second_index)
        markdown_after = {
            p.relative_to(vault).as_posix(): p.read_bytes()
            for p in sorted((vault / "wiki").rglob("*.md"))
        }
        assert markdown_before.keys() == markdown_after.keys()
        assert all(markdown_projection_equal(raw, markdown_after[path])
                   for path, raw in markdown_before.items())
        cjk_terms = {"全", "文", "检", "索", "全文", "文检", "检索", "全文检", "文检索"}
        # Every Chinese term in this fixture comes solely from 全文检索.
        observed_cjk = {term for term in second_index["vocab"]
                        if any("\u4e00" <= c <= "\u9fff" for c in term)}
        assert observed_cjk == cjk_terms
        query_results = []
        for name, query in (("ascii", "全文检索 ABC"), ("nfkc", "全文检索 ＡＢＣ")):
            results = runner.run(f"query-{name}", [
                UP / "scripts/bm25-index.py", "--vault", vault, "query", query,
            ])
            assert isinstance(results, list) and results
            assert any(second_chunks[result["path"]]["page_path"] == "wiki/papers/CJK.md"
                       and result["score"] > 0 for result in results)
            query_results.append(results)
        assert query_results[0] == query_results[1]
        overlap = sorted(
            (c for c in second_chunks.values() if c["page_path"] == "wiki/papers/Overlap.md"),
            key=lambda c: c["chunk_index"],
        )
        assert len(overlap) > 1
        assert [c["chunk_index"] for c in overlap] == list(range(len(overlap)))
        assert all(left["raw_text"][-200:] == right["raw_text"][:200]
                   for left, right in zip(overlap, overlap[1:]))
        dump(out / "runtime-results.json", {
            "rounds": 2, "cjk_terms": sorted(cjk_terms),
            "chunk_count": len(second_chunks), "overlap_chunks": len(overlap),
            "chunk_comparison_sha256": {
                path: runtime_projection_sha256("chunk", doc)
                for path, doc in second_chunks.items()
            },
            "bm25_comparison_sha256": runtime_projection_sha256("bm25", second_index),
            "markdown_sha256": {
                path: hashlib.sha256(raw).hexdigest() for path, raw in markdown_after.items()
            },
        })
    finally:
        after = snapshot(UP)
        dump(out / "source-after.json", after)
        assert before == after, "Pinned upstream source inventory changed during fixture"
