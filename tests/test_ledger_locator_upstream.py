"""Real pinned public CLI evidence transport, not an artifact-closure fixture.

Synthetic PDF/document metadata does not establish real PDF ref/coordinates.
Only the shared helper's isolated stable_source_id subprocess imports upstream;
all capture/transaction operations use public CLI in this disposable directory.
"""
import copy
import json

from tests.upstream._transaction_fixture import (
    DAY, REPO, STAMP, UP, Runner, bundle, dump, init, jsonbytes, sha, snapshot,
    stable_source, verify_sources,
)
from video_paper_wiki.identity import claim_id, evidence_fingerprint
from video_paper_wiki.ledger_locator import decode_ledger_evidence, encode_ledger_evidence


def test_pinned_public_cli_preserves_tagged_locator_and_context(tmp_path):
    out = tmp_path.resolve()
    before = verify_sources(out)
    runner = Runner(out)
    vault = out / "v"
    try:
        init(runner, vault, "locator-codec-init")
        raw = (REPO / "tests/fixtures/pdfs/tiny.pdf").read_bytes()
        (vault / "inbox/source.pdf").write_bytes(raw)
        args = ["capture", "apply", "--vault", vault, "--operation-id", "locator-codec-capture",
                "--generated-at", STAMP, "inbox/source.pdf"]
        preview = runner.cli("capture-dry", *args)
        assert preview["status"] == "dry-run"
        capture = runner.cli("capture-apply", *args, "--approved-plan-sha256", preview["approved_plan_sha256"], "--apply")
        assert len(capture["items"]) == 1
        captured = capture["items"][0]
        digest, stored = sha(raw), captured["stored_path"]
        assert captured["source_identity"] == digest
        assert (vault / stored).read_bytes() == raw
        sid = stable_source(runner, "file", stored, digest)
        paper_id = "sha256:" + digest
        page_path = f"wiki/papers/sha256-{digest}.md"
        text = "This synthetic fixture checks canonical locator transport."
        cid = claim_id("paper:" + paper_id, text)
        # Fake derived document stays outside the disposable Vault. The codec
        # validates shape/transport, and must not claim artifact closure.
        document = jsonbytes({"fixture_only": True, "text": "Synthetic extraction text."})
        (out / "fixture-document.json").write_bytes(document)
        domain = {
            "kind": "pdf", "source_id": sid, "page": 1, "ref": "#/texts/0",
            "artifact_path": ".raw/derived/fixture/docling/fp/document.json",
            "artifact_sha256": sha(document), "text_sha256": sha(b"Synthetic extraction text."),
            "bbox": [10.25, 20.5, 100.125, 40.75], "charspan": [0, 12],
            "relation": "uncertain",
        }
        evidence = encode_ledger_evidence(domain)
        assert evidence["relation"] == "context"
        assert decode_ledger_evidence(evidence) == domain
        page = ("---\ntitle: Locator fixture\n---\n\n" + text + " ^" + cid + "\n").encode()
        sources = {
            "schema": "claude-obsidian.source-ledger.v1", "generated_at": STAMP,
            "sources": {sid: {
                "origin": {"kind": "file", "locator": stored}, "content_kind": "synthetic",
                "authority": "synthetic", "title": "Synthetic fixture PDF", "content_sha256": digest,
                "ingested_at": DAY, "retrieved_at": None, "refresh_due": "2099-01-01",
                "review_status": "unreviewed", "independence_key": None,
                "pages": [page_path], "supersedes": None,
            }},
        }
        claims = {
            "schema": "claude-obsidian.claim-ledger.v1", "generated_at": STAMP,
            "claims": {cid: {
                "text": text, "risk": "normal", "assessment": "provisional", "confidence": "low",
                "location": {"path": page_path, "anchor": "^" + cid}, "reviewed_at": None,
                "notes": "Fixture only; no human assessment or scientific claim.",
                "supersedes": None, "evidence": [evidence],
            }},
        }
        legacy_before = (vault / ".raw/.manifest.json").read_bytes()
        source_path, claim_path = "wiki/meta/ledgers/source-ledger.json", "wiki/meta/ledgers/claim-ledger.json"
        context_operation = None
        context_plan = None
        for relation in ("supports", "uncertain", "context"):
            candidate = copy.deepcopy(claims)
            candidate["claims"][cid]["evidence"][0]["relation"] = relation
            contents = {source_path: jsonbytes(sources), claim_path: jsonbytes(candidate), page_path: page}
            operation = bundle(vault, "locator-codec-publish", "ingest", contents, reads={stored: digest})
            if relation == "uncertain":
                path = out / "uncertain.bundle.json"
                dump(path, operation)
                refused = runner.cli("uncertain-refusal", "transaction", "inspect", path, "--vault", vault, allowed=(2,))
                assert "INVALID_PROVENANCE_LEDGER" in refused["stderr"]
                assert "unsupported relation" in refused["stderr"]
            else:
                plan = runner.inspect(relation + "-inspect", vault, operation)
                assert set(plan["changed_paths"]) == {source_path, claim_path, page_path}
                if relation == "context":
                    context_operation, context_plan = operation, plan
        assert context_operation is not None and context_plan is not None
        runner.apply("context-apply", vault, context_operation, context_plan)
        assert (vault / source_path).read_bytes() == jsonbytes(sources)
        assert (vault / claim_path).read_bytes() == jsonbytes(claims)
        assert (vault / page_path).read_bytes() == page
        assert (vault / ".raw/.manifest.json").read_bytes() == legacy_before
        persisted = json.loads((vault / claim_path).read_bytes())["claims"][cid]["evidence"][0]
        restored = decode_ledger_evidence(persisted)
        assert restored == domain
        assert evidence_fingerprint([restored]) == evidence_fingerprint([domain])
        dump(out / "codec-transport-results.json", {
            "source_id": sid, "wire": persisted["locator"], "wire_sha256": sha(persisted["locator"].encode()),
            "restored_locator": restored, "supports_control": True, "context_preserved": True,
            "wire_uncertain_refused": True, "legacy_manifest_unchanged": True,
            "limitations": "Synthetic coordinate metadata; no real extraction, artifact closure, record/receipt/head or human acceptance proof.",
        })
    finally:
        after = snapshot(UP)
        dump(out / "source-after.json", after)
        assert before == after, "Pinned source inventory changed during locator transport fixture"
