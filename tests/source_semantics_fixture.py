"""Explicit synthetic source/receipt/reviewer data, never real authorization."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from video_paper_wiki.identity import assessment_event_id, claim_id, receipt_intent_sha256
from video_paper_wiki.jcs import canonicalize
from video_paper_wiki.markdown_locator import evidence_fingerprint_versioned, evidence_profile
from video_paper_wiki.markdown_source_contracts import OBSERVATION
from video_paper_wiki.source_semantics_contracts import (
    COMPILE, EVENT, PAPER, association_reference, decision_reference, sha, source_id,
)
from video_paper_wiki.source_versions import associate_source, make_display_decision

FIXTURES = Path(__file__).parent / "fixtures/contracts/valid"
PAPER_ID = "sha256:" + "a" * 64
STAMP = "2026-09-09T00:00:00Z"


def fixture(name):
    return json.loads((FIXTURES / (name + ".json")).read_bytes())


def observed_source(*, label=None, text="精确 e\u0301 😀 evidence.\r\nSecond line.", paper_id=PAPER_ID):
    prefix = '# Synthetic fixture\n\n<a id="page-1"></a>\n\n## PDF 第 1 页\n\n'
    source = prefix + text + '\n\n<a id="page-2"></a>\n\n## PDF 第 2 页\n\nSecond page.\n\n'
    raw = source.encode("utf-8")
    second = source.index("Second page.")
    observation = {"schema": OBSERVATION, "paper_id": paper_id, "light_paper_id": PAPER_ID,
                   "title": "Synthetic source", "version": {"kind": "unknown" if label is None else "declared", "label": label},
                   "markdown": {"sha256": sha(raw), "size_bytes": len(raw)},
                   "source_metadata_sha256": "b" * 64, "original_pdf_sha256": None,
                   "pages": [{"page": 1, "anchor": "page-1", "text_start": len(prefix), "text_end": len(prefix) + len(text), "text_sha256": sha(text.encode())},
                             {"page": 2, "anchor": "page-2", "text_start": second, "text_end": second + len("Second page."), "text_sha256": sha(b"Second page.")}]}
    return observation, raw


def reseal_receipts(receipts):
    """Seal a synthetic chronological list, never infer an actual capture receipt."""
    previous, by_path = None, {}
    for sequence, receipt in enumerate(receipts, 1):
        receipt["sequence"] = sequence
        receipt["previous"] = previous
        receipt["intent_sha256"] = receipt_intent_sha256(receipt)
        path = f"wiki/meta/operations/{sequence:012d}-{receipt['operation_id']}.json"
        raw = canonicalize(receipt)
        by_path[path] = raw
        previous = {"path": path, "sha256": sha(raw)}
    head = {"schema": "video-paper-wiki.operation-head.v1", "sequence": len(receipts),
            "receipt_path": previous["path"], "receipt_sha256": previous["sha256"]}
    return canonicalize(head), by_path


def registration_material(observation):
    raw = {"path": f".raw/captured/{observation['markdown']['sha256']}.md", **observation["markdown"]}
    sid = source_id(raw)
    ledger = {"schema": "claude-obsidian.source-ledger.v1", "generated_at": STAMP,
              "sources": {sid: {"origin": {"kind": "file", "locator": raw["path"]},
                        "content_kind": "document", "title": "Synthetic fixture source", "authority": "primary",
                        "review_status": "unreviewed", "pages": [], "content_sha256": raw["sha256"],
                        "ingested_at": "2026-09-09", "retrieved_at": None, "refresh_due": None,
                        "independence_key": None, "supersedes": None}}}
    ledger_bytes = canonicalize(ledger)
    receipt = {"schema": "video-paper-wiki.operation-receipt.v1", "sequence": 1, "previous": None,
               "operation_id": "synthetic-registration", "operation_type": "ingest", "intent_sha256": "0" * 64,
               "writes": [{"path": "wiki/meta/ledgers/source-ledger.json", "mode": "create", "before_sha256": None,
                           "after_sha256": sha(ledger_bytes)}],
               "claimed_inputs": [{"path": raw["path"], "mode": "read", "sha256": raw["sha256"]}]}
    head, receipts = reseal_receipts([receipt])
    return {"head_bytes": head, "receipt_bytes": receipts, "ledger_bytes": ledger_bytes}


def source_fixture(**kwargs):
    observation, raw = observed_source(**kwargs)
    authority = registration_material(observation)
    association = associate_source(observation, raw_bytes=raw, existing=[], **authority)["association"]
    return association, raw, authority


def inventory_arguments(associations, raw, authority):
    return {"raw_sources": {x["raw"]["path"]: raw for x in associations},
            "extraction_artifacts": {x["extraction"]["path"]: canonicalize(x["observation"]) for x in associations},
            "registration_ledgers": {x["registration"]["source_ledger_path"]: authority["ledger_bytes"] for x in associations},
            "head_bytes": authority["head_bytes"], "receipt_bytes": authority["receipt_bytes"]}


def locator_for(association, raw, *, span=None, anchor="page-1"):
    page = association["observation"]["pages"][0]
    start, end = span or (page["text_start"], page["text_end"])
    return {"kind": "markdown", "source_id": association["source_id"], "association": association_reference(association),
            "path": association["raw"]["path"], "sha256": association["raw"]["sha256"], "charspan": [start, end],
            "page_anchor": anchor, "excerpt_sha256": sha(raw.decode()[start:end].encode())}


def claim_for(evidence, *, text="A synthetic exact source claim.", subject="paper:" + PAPER_ID):
    return {"claim_id": claim_id(subject, text), "stable_subject_id": subject, "canonical_claim_text": text,
            "evidence": copy.deepcopy(evidence), "assessment": "provisional", "reviewed_at": None}


def event_for(claim, *, previous=None, human=False, state="accepted", legacy=False, **changes):
    event = {"schema": "video-paper-wiki.assessment-event.v1" if legacy else EVENT,
             "event_id": "ase-" + "0" * 20, "claim_id": claim["claim_id"],
             "previous_event_id": None if previous is None else previous["event_id"],
             "actor_kind": "human" if human else "system",
             "transition_kind": "genesis" if previous is None else "human_assessment" if human else "evidence_invalidation",
             "from_assessment": None if previous is None else previous["to_assessment"],
             "to_assessment": state if human else "provisional", "claim_text_sha256": sha(claim["canonical_claim_text"].encode()),
             "evidence_fingerprint": evidence_fingerprint_versioned(claim["evidence"]),
             "decided_by": "synthetic-fixture-reviewer", "decided_at": STAMP, "reason": "Synthetic test event."}
    if not legacy:
        event["evidence_profile"] = evidence_profile(claim["evidence"])
    event.update(changes)
    event["event_id"] = assessment_event_id(event)
    return event


def selection(source_association, *, previous=None, **changes):
    fields = {"paper_id": source_association["paper_id"], "sequence": 1 if previous is None else previous["sequence"] + 1,
              "previous_decision_id": None if previous is None else previous["decision_id"],
              "association": association_reference(source_association), "actor": {"kind": "human", "identity": "synthetic-reviewer"},
              "choice": {"source": "fixture", "reference": "tests/source_semantics_fixture.py", "text": "Synthetic display selection."},
              "decided_at": STAMP, "reason": "Synthetic test selection."}
    return make_display_decision(**(fields | changes))


def compile_fixture(*, selected=False, accepted=False):
    association, raw, authority = source_fixture()
    claim = claim_for([{**locator_for(association, raw), "relation": "supports"}])
    events = [event_for(claim)]
    if accepted:
        events.append(event_for(claim, previous=events[-1], human=True))
        claim.update(assessment="accepted", reviewed_at="2026-09-09")
    record = fixture("video-paper-wiki.paper-record.v1")
    record.pop("arxiv_id")
    record.update(schema=PAPER, paper_id=PAPER_ID, title="Synthetic source", title_zh="合成来源示例",
                  source_ids=[association["source_id"]], source_associations=[association_reference(association)],
                  display_head=None, active_extraction_path=None, active_extraction_sha256=None,
                  section_claim_refs=[{"section": "one_sentence_conclusion", "claim_id": claim["claim_id"], "core": True, "lifecycle": "active"}],
                  aliases=[], code_urls=[], taxonomy=[], created_at=STAMP, updated_at=STAMP)
    decisions = []
    if selected:
        decisions = [selection(association)]
        record.update(display_head=decision_reference(decisions[0]), active_extraction_path=association["extraction"]["path"],
                      active_extraction_sha256=association["extraction"]["sha256"])
    group = {"record": record, "claims": [claim], "events": events, "associations": [association], "display_decisions": decisions}
    material = {"schema": COMPILE, "operation_id": "synthetic-compile", "papers": [group], "code": [], "concepts": []}
    return material, inventory_arguments([association], raw, authority)


# Independently reviewed complete synthetic vectors, copied without regeneration.
# Review c23c5a5209293a10d1df6981a3a929a7eabb21b589388d0df720bbbec7e5e17e.
GOLDEN_LEGACY = {'code': [{'alignment': {'archived': False,
                         'capabilities': [{'locators': [{'commit': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                                                         'kind': 'code',
                                                         'lines': {'end': 30, 'start': 10},
                                                         'path': 'train.py',
                                                         'repository': 'ExampleOrg/VideoModel',
                                                         'snippet_sha256': '6faeb3d225b44cb26c72c014816416598922cbdaec9a9c313af92d8090fc6688',
                                                         'source_id': 'src-repo',
                                                         'symbol': 'train'}],
                                           'name': 'training',
                                           'status': 'present'},
                                          {'locators': [{'commit': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                                                         'kind': 'code',
                                                         'lines': {'end': 30, 'start': 10},
                                                         'path': 'train.py',
                                                         'repository': 'ExampleOrg/VideoModel',
                                                         'snippet_sha256': '6faeb3d225b44cb26c72c014816416598922cbdaec9a9c313af92d8090fc6688',
                                                         'source_id': 'src-repo',
                                                         'symbol': 'train'}],
                                           'name': 'inference',
                                           'status': 'present'},
                                          {'locators': [{'commit': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                                                         'kind': 'code',
                                                         'lines': {'end': 30, 'start': 10},
                                                         'path': 'train.py',
                                                         'repository': 'ExampleOrg/VideoModel',
                                                         'snippet_sha256': '6faeb3d225b44cb26c72c014816416598922cbdaec9a9c313af92d8090fc6688',
                                                         'source_id': 'src-repo',
                                                         'symbol': 'train'}],
                                           'name': 'data',
                                           'status': 'partial'},
                                          {'absence_scope': {'commit': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                                                             'search_patterns': ['eval', 'benchmark'],
                                                             'tree_prefix': 'eval'},
                                           'locators': [],
                                           'name': 'evaluation',
                                           'status': 'absent'},
                                          {'checkpoint_kind': 'link_only',
                                           'locators': [],
                                           'name': 'checkpoints',
                                           'status': 'unverified'}],
                         'commit': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                         'license': {'notes': 'Declared in LICENSE.', 'spdx_id': 'Apache-2.0'},
                         'officiality': {'evidence': [{'artifact_path': '.raw/derived/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/docling/fp/document.json',
                                                       'artifact_sha256': 'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
                                                       'bbox': [10, 20, 100, 40],
                                                       'charspan': [0, 47],
                                                       'kind': 'pdf',
                                                       'page': 3,
                                                       'ref': '#/texts/7',
                                                       'source_id': 'src-paper',
                                                       'text_sha256': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'}],
                                         'status': 'official'},
                         'paper_id': 'arxiv:2311.15127',
                         'repository': 'ExampleOrg/VideoModel',
                         'schema': 'video-paper-wiki.paper-code-alignment.v1'},
           'manifest': {'capture': {'inspection_approval_hash': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                                    'operation_id': 'vertical-code',
                                    'source_id': 'src-repo',
                                    'source_identity': '1925e1ce1d893badd5fd239eb305c4d385b8b35f3048640faaf975b55d230311',
                                    'stored_path': '.raw/captured/1925e1ce1d893badd5fd239eb305c4d385b8b35f3048640faaf975b55d230311.bin'},
                        'encoding': 'utf-8',
                        'ends_with_newline': True,
                        'line_canonicalization': 'utf8-lf-v1',
                        'line_count': 33,
                        'manifest_sha256': '070cb28455cf6ade6d5fba34236422ed98eb8b5b7e03324501e8a63d7928eb7e',
                        'media_type': 'text/plain',
                        'newline_style': 'lf',
                        'normalized_sha256': '1925e1ce1d893badd5fd239eb305c4d385b8b35f3048640faaf975b55d230311',
                        'origin': {'commit': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                                   'path': 'train.py',
                                   'repository': 'ExampleOrg/VideoModel'},
                        'payload': {'sha256': '1925e1ce1d893badd5fd239eb305c4d385b8b35f3048640faaf975b55d230311',
                                    'size_bytes': 423},
                        'proposal_sha256': '6825554d344e9bf033ec9e72a44f323aa9c60f3ef60860d808290bcb826d043e',
                        'schema': 'video-paper-wiki.code-evidence-manifest.v1',
                        'state': 'inspected'},
           'repo_record': {'archived': False,
                           'canonical_commit': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                           'canonical_repository': 'ExampleOrg/VideoModel',
                           'capability_claim_refs': [{'capability': 'training',
                                                      'claim_id': 'clm-64fd1d8c5e92e6b4a97a',
                                                      'lifecycle': 'active'}],
                           'created_at': '2026-08-29T12:00:00Z',
                           'license': {'notes': 'Declared in LICENSE.', 'spdx_id': 'Apache-2.0'},
                           'officiality': 'official',
                           'paper_ids': ['arxiv:2311.15127'],
                           'repo_id': 'github:exampleorg/videomodel',
                           'schema': 'video-paper-wiki.repo-record.v1',
                           'updated_at': '2026-08-29T12:00:00Z'}}],
 'concepts': [{'axis': 'backbone', 'label_en': 'dit', 'label_zh': '扩散 Transformer', 'slug': 'dit'}],
 'operation_id': 'compile-test',
 'papers': [{'assessment_heads': {'clm-070856211205617b9eb8': 'ase-a27e1bff61545a014e99'},
             'claims': [{'assessment': 'accepted',
                         'canonical_claim_text': 'A verified compiler claim.',
                         'claim_id': 'clm-070856211205617b9eb8',
                         'evidence': [{'commit': 'cccccccccccccccccccccccccccccccccccccccc',
                                       'kind': 'code',
                                       'lines': {'end': 3, 'start': 1},
                                       'path': 'src/model.py',
                                       'relation': 'uncertain',
                                       'repository': 'Owner/Repo',
                                       'snippet_sha256': 'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
                                       'source_id': 'src-history-code',
                                       'symbol': 'Model.forward'}],
                         'reviewed_at': '2026-09-01',
                         'stable_subject_id': 'paper:arxiv:2311.15127'}],
             'events': [{'actor_kind': 'human',
                         'claim_id': 'clm-070856211205617b9eb8',
                         'claim_text_sha256': 'a2466fd58fdc403e6c06328cacf9643cca1d7c5edb096d26e7557cb98f86235f',
                         'decided_at': '2026-09-01T00:00:00Z',
                         'decided_by': 'reviewer',
                         'event_id': 'ase-a27e1bff61545a014e99',
                         'evidence_fingerprint': '4bb48c31bd69d6365239c1d76bc43d1b9087ecf84c86b1a03e5f6bd5b11d5945',
                         'from_assessment': 'provisional',
                         'previous_event_id': 'ase-ffb81f13f7e717225691',
                         'reason': 'Fixture acceptance.',
                         'schema': 'video-paper-wiki.assessment-event.v1',
                         'to_assessment': 'accepted',
                         'transition_kind': 'human_assessment'},
                        {'actor_kind': 'system',
                         'claim_id': 'clm-070856211205617b9eb8',
                         'claim_text_sha256': 'a2466fd58fdc403e6c06328cacf9643cca1d7c5edb096d26e7557cb98f86235f',
                         'decided_at': '2026-09-01T00:00:00Z',
                         'decided_by': 'fixture',
                         'event_id': 'ase-ffb81f13f7e717225691',
                         'evidence_fingerprint': '4bb48c31bd69d6365239c1d76bc43d1b9087ecf84c86b1a03e5f6bd5b11d5945',
                         'from_assessment': None,
                         'previous_event_id': None,
                         'reason': 'Fixture genesis.',
                         'schema': 'video-paper-wiki.assessment-event.v1',
                         'to_assessment': 'provisional',
                         'transition_kind': 'genesis'}],
             'record': {'active_extraction_path': '.raw/derived/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/docling/fp/document.json',
                        'active_extraction_sha256': 'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
                        'aliases': ['Video Paper'],
                        'arxiv_id': '2311.15127',
                        'authors': ['Ada Example'],
                        'code_urls': ['https://github.com/ExampleOrg/VideoModel'],
                        'created_at': '2026-08-29T12:00:00Z',
                        'paper_id': 'arxiv:2311.15127',
                        'published_at': '2023-11-25',
                        'schema': 'video-paper-wiki.paper-record.v1',
                        'section_claim_refs': [{'claim_id': 'clm-070856211205617b9eb8',
                                                'core': True,
                                                'lifecycle': 'active',
                                                'section': 'one_sentence_conclusion'}],
                        'source_ids': ['src-paper'],
                        'taxonomy': [{'axis': 'backbone', 'slug': 'dit'}],
                        'title': 'A Video Paper',
                        'title_zh': '一篇视频论文',
                        'updated_at': '2026-08-29T12:00:00Z'}}],
 'schema': 'video-paper-wiki.compile-input.v1'}

GOLDEN_MIXED = {'code': [{'alignment': {'archived': False,
                         'capabilities': [{'locators': [{'commit': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                                                         'kind': 'code',
                                                         'lines': {'end': 30, 'start': 10},
                                                         'path': 'train.py',
                                                         'repository': 'ExampleOrg/VideoModel',
                                                         'snippet_sha256': '6faeb3d225b44cb26c72c014816416598922cbdaec9a9c313af92d8090fc6688',
                                                         'source_id': 'src-repo',
                                                         'symbol': 'train'}],
                                           'name': 'training',
                                           'status': 'present'},
                                          {'locators': [{'commit': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                                                         'kind': 'code',
                                                         'lines': {'end': 30, 'start': 10},
                                                         'path': 'train.py',
                                                         'repository': 'ExampleOrg/VideoModel',
                                                         'snippet_sha256': '6faeb3d225b44cb26c72c014816416598922cbdaec9a9c313af92d8090fc6688',
                                                         'source_id': 'src-repo',
                                                         'symbol': 'train'}],
                                           'name': 'inference',
                                           'status': 'present'},
                                          {'locators': [{'commit': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                                                         'kind': 'code',
                                                         'lines': {'end': 30, 'start': 10},
                                                         'path': 'train.py',
                                                         'repository': 'ExampleOrg/VideoModel',
                                                         'snippet_sha256': '6faeb3d225b44cb26c72c014816416598922cbdaec9a9c313af92d8090fc6688',
                                                         'source_id': 'src-repo',
                                                         'symbol': 'train'}],
                                           'name': 'data',
                                           'status': 'partial'},
                                          {'absence_scope': {'commit': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                                                             'search_patterns': ['eval', 'benchmark'],
                                                             'tree_prefix': 'eval'},
                                           'locators': [],
                                           'name': 'evaluation',
                                           'status': 'absent'},
                                          {'checkpoint_kind': 'link_only',
                                           'locators': [],
                                           'name': 'checkpoints',
                                           'status': 'unverified'}],
                         'commit': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                         'license': {'notes': 'Declared in LICENSE.', 'spdx_id': 'Apache-2.0'},
                         'officiality': {'evidence': [{'artifact_path': '.raw/derived/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/docling/fp/document.json',
                                                       'artifact_sha256': 'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
                                                       'bbox': [10, 20, 100, 40],
                                                       'charspan': [0, 47],
                                                       'kind': 'pdf',
                                                       'page': 3,
                                                       'ref': '#/texts/7',
                                                       'source_id': 'src-paper',
                                                       'text_sha256': 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'}],
                                         'status': 'official'},
                         'paper_id': 'arxiv:2311.15127',
                         'repository': 'ExampleOrg/VideoModel',
                         'schema': 'video-paper-wiki.paper-code-alignment.v1'},
           'manifest': {'capture': {'inspection_approval_hash': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                                    'operation_id': 'vertical-code',
                                    'source_id': 'src-repo',
                                    'source_identity': '1925e1ce1d893badd5fd239eb305c4d385b8b35f3048640faaf975b55d230311',
                                    'stored_path': '.raw/captured/1925e1ce1d893badd5fd239eb305c4d385b8b35f3048640faaf975b55d230311.bin'},
                        'encoding': 'utf-8',
                        'ends_with_newline': True,
                        'line_canonicalization': 'utf8-lf-v1',
                        'line_count': 33,
                        'manifest_sha256': '070cb28455cf6ade6d5fba34236422ed98eb8b5b7e03324501e8a63d7928eb7e',
                        'media_type': 'text/plain',
                        'newline_style': 'lf',
                        'normalized_sha256': '1925e1ce1d893badd5fd239eb305c4d385b8b35f3048640faaf975b55d230311',
                        'origin': {'commit': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                                   'path': 'train.py',
                                   'repository': 'ExampleOrg/VideoModel'},
                        'payload': {'sha256': '1925e1ce1d893badd5fd239eb305c4d385b8b35f3048640faaf975b55d230311',
                                    'size_bytes': 423},
                        'proposal_sha256': '6825554d344e9bf033ec9e72a44f323aa9c60f3ef60860d808290bcb826d043e',
                        'schema': 'video-paper-wiki.code-evidence-manifest.v1',
                        'state': 'inspected'},
           'repo_record': {'archived': False,
                           'canonical_commit': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                           'canonical_repository': 'ExampleOrg/VideoModel',
                           'capability_claim_refs': [{'capability': 'training',
                                                      'claim_id': 'clm-64fd1d8c5e92e6b4a97a',
                                                      'lifecycle': 'active'}],
                           'created_at': '2026-08-29T12:00:00Z',
                           'license': {'notes': 'Declared in LICENSE.', 'spdx_id': 'Apache-2.0'},
                           'officiality': 'official',
                           'paper_ids': ['arxiv:2311.15127'],
                           'repo_id': 'github:exampleorg/videomodel',
                           'schema': 'video-paper-wiki.repo-record.v1',
                           'updated_at': '2026-08-29T12:00:00Z'}}],
 'concepts': [{'axis': 'backbone', 'label_en': 'dit', 'label_zh': '扩散 Transformer', 'slug': 'dit'}],
 'operation_id': 'mixed-golden',
 'papers': [{'assessment_heads': {'clm-070856211205617b9eb8': 'ase-a27e1bff61545a014e99'},
             'claims': [{'assessment': 'accepted',
                         'canonical_claim_text': 'A verified compiler claim.',
                         'claim_id': 'clm-070856211205617b9eb8',
                         'evidence': [{'commit': 'cccccccccccccccccccccccccccccccccccccccc',
                                       'kind': 'code',
                                       'lines': {'end': 3, 'start': 1},
                                       'path': 'src/model.py',
                                       'relation': 'uncertain',
                                       'repository': 'Owner/Repo',
                                       'snippet_sha256': 'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
                                       'source_id': 'src-history-code',
                                       'symbol': 'Model.forward'}],
                         'reviewed_at': '2026-09-01',
                         'stable_subject_id': 'paper:arxiv:2311.15127'}],
             'events': [{'actor_kind': 'human',
                         'claim_id': 'clm-070856211205617b9eb8',
                         'claim_text_sha256': 'a2466fd58fdc403e6c06328cacf9643cca1d7c5edb096d26e7557cb98f86235f',
                         'decided_at': '2026-09-01T00:00:00Z',
                         'decided_by': 'reviewer',
                         'event_id': 'ase-a27e1bff61545a014e99',
                         'evidence_fingerprint': '4bb48c31bd69d6365239c1d76bc43d1b9087ecf84c86b1a03e5f6bd5b11d5945',
                         'from_assessment': 'provisional',
                         'previous_event_id': 'ase-ffb81f13f7e717225691',
                         'reason': 'Fixture acceptance.',
                         'schema': 'video-paper-wiki.assessment-event.v1',
                         'to_assessment': 'accepted',
                         'transition_kind': 'human_assessment'},
                        {'actor_kind': 'system',
                         'claim_id': 'clm-070856211205617b9eb8',
                         'claim_text_sha256': 'a2466fd58fdc403e6c06328cacf9643cca1d7c5edb096d26e7557cb98f86235f',
                         'decided_at': '2026-09-01T00:00:00Z',
                         'decided_by': 'fixture',
                         'event_id': 'ase-ffb81f13f7e717225691',
                         'evidence_fingerprint': '4bb48c31bd69d6365239c1d76bc43d1b9087ecf84c86b1a03e5f6bd5b11d5945',
                         'from_assessment': None,
                         'previous_event_id': None,
                         'reason': 'Fixture genesis.',
                         'schema': 'video-paper-wiki.assessment-event.v1',
                         'to_assessment': 'provisional',
                         'transition_kind': 'genesis'}],
             'record': {'active_extraction_path': '.raw/derived/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/docling/fp/document.json',
                        'active_extraction_sha256': 'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
                        'aliases': ['Video Paper'],
                        'arxiv_id': '2311.15127',
                        'authors': ['Ada Example'],
                        'code_urls': ['https://github.com/ExampleOrg/VideoModel'],
                        'created_at': '2026-08-29T12:00:00Z',
                        'paper_id': 'arxiv:2311.15127',
                        'published_at': '2023-11-25',
                        'schema': 'video-paper-wiki.paper-record.v1',
                        'section_claim_refs': [{'claim_id': 'clm-070856211205617b9eb8',
                                                'core': True,
                                                'lifecycle': 'active',
                                                'section': 'one_sentence_conclusion'}],
                        'source_ids': ['src-paper'],
                        'taxonomy': [{'axis': 'backbone', 'slug': 'dit'}],
                        'title': 'A Video Paper',
                        'title_zh': '一篇视频论文',
                        'updated_at': '2026-08-29T12:00:00Z'}},
            {'assessment_heads': {'clm-d377b59001b98187ed1e': 'ase-adb44714c03657b6500c'},
             'associations': [{'association_id': 'sva-87474ae4adfa8b817b9904938d9d77b1da0639b65dbca6672a55bdfbf04760a1',
                               'extraction': {'path': '.raw/derived/markdown-source/d5060293eeecc873493ce8395d3d2f77308c98a0854ceb9dc117ee90ec368c52/b046e8c73484f9998e96405d6406ee133ebb5b9e0836573b101f3f38b0b6556b.json',
                                              'sha256': 'b046e8c73484f9998e96405d6406ee133ebb5b9e0836573b101f3f38b0b6556b',
                                              'size_bytes': 623},
                               'observation': {'light_paper_id': 'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
                                               'markdown': {'sha256': 'd5060293eeecc873493ce8395d3d2f77308c98a0854ceb9dc117ee90ec368c52',
                                                            'size_bytes': 88},
                                               'original_pdf_sha256': None,
                                               'pages': [{'anchor': 'page-1',
                                                          'page': 1,
                                                          'text_end': 82,
                                                          'text_sha256': 'fa3bde3f1ffed3ca3cec13503d733c3cda558e35418d408ecb932f5516825c79',
                                                          'text_start': 51}],
                                               'paper_id': 'arxiv:2311.15128',
                                               'schema': 'video-paper-wiki.markdown-source-observation.v1',
                                               'source_metadata_sha256': 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
                                               'title': 'Second Paper',
                                               'version': {'kind': 'declared', 'label': 'v1.0'}},
                               'paper_id': 'arxiv:2311.15128',
                               'raw': {'path': '.raw/captured/d5060293eeecc873493ce8395d3d2f77308c98a0854ceb9dc117ee90ec368c52.md',
                                       'sha256': 'd5060293eeecc873493ce8395d3d2f77308c98a0854ceb9dc117ee90ec368c52',
                                       'size_bytes': 88},
                               'registration': {'receipt_path': 'wiki/meta/operations/000000000002-md-ingest.json',
                                                'receipt_sha256': 'a2252e1d0b22572fee436e6a7c71ead5ad0f42e68d32c563c7bb641d397c0c8e',
                                                'source_ledger_path': '.raw/derived/source-ledgers/5b0e4a1ad0710721c8ece55cbcb87d48408a91429692b262570e02245ab0ee77.json',
                                                'source_ledger_sha256': '5b0e4a1ad0710721c8ece55cbcb87d48408a91429692b262570e02245ab0ee77'},
                               'schema': 'video-paper-wiki.source-version-association.v1',
                               'source_id': 'src-13ea0ff610b50ce22aed',
                               'version': {'kind': 'declared', 'label': 'v1.0'}}],
             'claims': [{'assessment': 'accepted',
                         'canonical_claim_text': 'A Markdown-backed conclusion.',
                         'claim_id': 'clm-d377b59001b98187ed1e',
                         'evidence': [{'commit': 'cccccccccccccccccccccccccccccccccccccccc',
                                       'kind': 'code',
                                       'lines': {'end': 3, 'start': 1},
                                       'path': 'src/model.py',
                                       'relation': 'uncertain',
                                       'repository': 'Owner/Repo',
                                       'snippet_sha256': 'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
                                       'source_id': 'src-history-code',
                                       'symbol': 'Model.forward'},
                                      {'association': {'association_id': 'sva-87474ae4adfa8b817b9904938d9d77b1da0639b65dbca6672a55bdfbf04760a1',
                                                       'sha256': 'f34a0e523929cc9857ab90a5f8c82616fec0fbb36540dcc64b1ecefca595b8a8'},
                                       'charspan': [51, 82],
                                       'excerpt_sha256': 'fa3bde3f1ffed3ca3cec13503d733c3cda558e35418d408ecb932f5516825c79',
                                       'kind': 'markdown',
                                       'page_anchor': 'page-1',
                                       'path': '.raw/captured/d5060293eeecc873493ce8395d3d2f77308c98a0854ceb9dc117ee90ec368c52.md',
                                       'relation': 'supports',
                                       'sha256': 'd5060293eeecc873493ce8395d3d2f77308c98a0854ceb9dc117ee90ec368c52',
                                       'source_id': 'src-13ea0ff610b50ce22aed'}],
                         'reviewed_at': '2026-09-09',
                         'stable_subject_id': 'paper:arxiv:2311.15128'}],
             'display_decisions': [{'actor': {'identity': 'fixture reviewer', 'kind': 'human'},
                                    'association': {'association_id': 'sva-87474ae4adfa8b817b9904938d9d77b1da0639b65dbca6672a55bdfbf04760a1',
                                                    'sha256': 'f34a0e523929cc9857ab90a5f8c82616fec0fbb36540dcc64b1ecefca595b8a8'},
                                    'choice': {'reference': 'fixture://display/1',
                                               'source': 'fixture',
                                               'text': 'Select declared v1.0 source.'},
                                    'decided_at': '2026-09-09T00:30:00Z',
                                    'decision_id': 'svd-ba01fc31ab4b8dcfb9b91dd0a26fe319ddcd87947ada6935d19ad6cde67f3ce2',
                                    'paper_id': 'arxiv:2311.15128',
                                    'previous_decision_id': None,
                                    'reason': 'Synthetic fixture choice.',
                                    'schema': 'video-paper-wiki.source-display-decision.v1',
                                    'sequence': 1}],
             'events': [{'actor_kind': 'human',
                         'claim_id': 'clm-d377b59001b98187ed1e',
                         'claim_text_sha256': 'f6b31ac0a9da25e94059f0b5669f00428fde12135d9fc9e894fb6428b3eb94f3',
                         'decided_at': '2026-09-09T01:00:00Z',
                         'decided_by': 'fixture-reviewer',
                         'event_id': 'ase-adb44714c03657b6500c',
                         'evidence_fingerprint': '7197a9441950fcd6d338ed23e922da13b99a9138090eae0bb19e08f47fc5e3ba',
                         'evidence_profile': 'mixed-v2',
                         'from_assessment': 'provisional',
                         'previous_event_id': 'ase-9ff39e7a9a93cad28e48',
                         'reason': 'Synthetic v2 assessment.',
                         'schema': 'video-paper-wiki.assessment-event.v2',
                         'to_assessment': 'accepted',
                         'transition_kind': 'human_assessment'},
                        {'actor_kind': 'system',
                         'claim_id': 'clm-d377b59001b98187ed1e',
                         'claim_text_sha256': 'f6b31ac0a9da25e94059f0b5669f00428fde12135d9fc9e894fb6428b3eb94f3',
                         'decided_at': '2026-09-09T00:00:00Z',
                         'decided_by': 'fixture',
                         'event_id': 'ase-9ff39e7a9a93cad28e48',
                         'evidence_fingerprint': '7197a9441950fcd6d338ed23e922da13b99a9138090eae0bb19e08f47fc5e3ba',
                         'evidence_profile': 'mixed-v2',
                         'from_assessment': None,
                         'previous_event_id': None,
                         'reason': 'Synthetic v2 genesis.',
                         'schema': 'video-paper-wiki.assessment-event.v2',
                         'to_assessment': 'provisional',
                         'transition_kind': 'genesis'}],
             'record': {'active_extraction_path': '.raw/derived/markdown-source/d5060293eeecc873493ce8395d3d2f77308c98a0854ceb9dc117ee90ec368c52/b046e8c73484f9998e96405d6406ee133ebb5b9e0836573b101f3f38b0b6556b.json',
                        'active_extraction_sha256': 'b046e8c73484f9998e96405d6406ee133ebb5b9e0836573b101f3f38b0b6556b',
                        'aliases': ['Second Paper Alias'],
                        'arxiv_id': '2311.15128',
                        'authors': ['Ada Example'],
                        'code_urls': ['https://github.com/ExampleOrg/VideoModel'],
                        'created_at': '2026-09-09T00:00:00Z',
                        'display_head': {'decision_id': 'svd-ba01fc31ab4b8dcfb9b91dd0a26fe319ddcd87947ada6935d19ad6cde67f3ce2',
                                         'sha256': '3bf809e3d590493b2444a36e988505297869f8ea181ee7458399fd66a26b2323'},
                        'paper_id': 'arxiv:2311.15128',
                        'published_at': '2023-11-26',
                        'schema': 'video-paper-wiki.paper-record.v2',
                        'section_claim_refs': [{'claim_id': 'clm-d377b59001b98187ed1e',
                                                'core': True,
                                                'lifecycle': 'active',
                                                'section': 'one_sentence_conclusion'}],
                        'source_associations': [{'association_id': 'sva-87474ae4adfa8b817b9904938d9d77b1da0639b65dbca6672a55bdfbf04760a1',
                                                 'sha256': 'f34a0e523929cc9857ab90a5f8c82616fec0fbb36540dcc64b1ecefca595b8a8'}],
                        'source_ids': ['src-13ea0ff610b50ce22aed', 'src-history-code'],
                        'taxonomy': [{'axis': 'backbone', 'slug': 'dit'}],
                        'title': 'Second Paper',
                        'title_zh': '第二篇论文',
                        'updated_at': '2026-09-09T01:00:00Z'}}],
 'schema': 'video-paper-wiki.compile-input.v2'}

GOLDEN_AUTHORITY = {'raw_sources': {'.raw/captured/d5060293eeecc873493ce8395d3d2f77308c98a0854ceb9dc117ee90ec368c52.md': b'# Se'
                                                                                                      b'cond'
                                                                                                      b' Pap'
                                                                                                      b'er\n\n'
                                                                                                      b'<a i'
                                                                                                      b'd="p'
                                                                                                      b'age-'
                                                                                                      b'1"><'
                                                                                                      b'/a>\n'
                                                                                                      b'\n## '
                                                                                                      b'PDF '
                                                                                                      b'\xe7\xac\xac '
                                                                                                      b'1 \xe9\xa1'
                                                                                                      b'\xb5\n\nA'
                                                                                                      b' ver'
                                                                                                      b'ifie'
                                                                                                      b'd Ma'
                                                                                                      b'rkdo'
                                                                                                      b'wn c'
                                                                                                      b'oncl'
                                                                                                      b'usio'
                                                                                                      b'n.\n\n'},
 'extraction_artifacts': {'.raw/derived/markdown-source/d5060293eeecc873493ce8395d3d2f77308c98a0854ceb9dc117ee90ec368c52/b046e8c73484f9998e96405d6406ee133ebb5b9e0836573b101f3f38b0b6556b.json': b'{"li'
                                                                                                                                                                                                 b'ght_'
                                                                                                                                                                                                 b'pape'
                                                                                                                                                                                                 b'r_id'
                                                                                                                                                                                                 b'":"s'
                                                                                                                                                                                                 b'ha25'
                                                                                                                                                                                                 b'6:bb'
                                                                                                                                                                                                 b'bbbb'
                                                                                                                                                                                                 b'bbbb'
                                                                                                                                                                                                 b'bbbb'
                                                                                                                                                                                                 b'bbbb'
                                                                                                                                                                                                 b'bbbb'
                                                                                                                                                                                                 b'bbbb'
                                                                                                                                                                                                 b'bbbb'
                                                                                                                                                                                                 b'bbbb'
                                                                                                                                                                                                 b'bbbb'
                                                                                                                                                                                                 b'bbbb'
                                                                                                                                                                                                 b'bbbb'
                                                                                                                                                                                                 b'bbbb'
                                                                                                                                                                                                 b'bbbb'
                                                                                                                                                                                                 b'bbbb'
                                                                                                                                                                                                 b'bbbb'
                                                                                                                                                                                                 b'bb",'
                                                                                                                                                                                                 b'"mar'
                                                                                                                                                                                                 b'kdow'
                                                                                                                                                                                                 b'n":{'
                                                                                                                                                                                                 b'"sha'
                                                                                                                                                                                                 b'256"'
                                                                                                                                                                                                 b':"d5'
                                                                                                                                                                                                 b'0602'
                                                                                                                                                                                                 b'93ee'
                                                                                                                                                                                                 b'ecc8'
                                                                                                                                                                                                 b'7349'
                                                                                                                                                                                                 b'3ce8'
                                                                                                                                                                                                 b'395d'
                                                                                                                                                                                                 b'3d2f'
                                                                                                                                                                                                 b'7730'
                                                                                                                                                                                                 b'8c98'
                                                                                                                                                                                                 b'a085'
                                                                                                                                                                                                 b'4ceb'
                                                                                                                                                                                                 b'9dc1'
                                                                                                                                                                                                 b'17ee'
                                                                                                                                                                                                 b'90ec'
                                                                                                                                                                                                 b'368c'
                                                                                                                                                                                                 b'52",'
                                                                                                                                                                                                 b'"siz'
                                                                                                                                                                                                 b'e_by'
                                                                                                                                                                                                 b'tes"'
                                                                                                                                                                                                 b':88}'
                                                                                                                                                                                                 b',"or'
                                                                                                                                                                                                 b'igin'
                                                                                                                                                                                                 b'al_p'
                                                                                                                                                                                                 b'df_s'
                                                                                                                                                                                                 b'ha25'
                                                                                                                                                                                                 b'6":n'
                                                                                                                                                                                                 b'ull,'
                                                                                                                                                                                                 b'"pag'
                                                                                                                                                                                                 b'es":'
                                                                                                                                                                                                 b'[{"a'
                                                                                                                                                                                                 b'ncho'
                                                                                                                                                                                                 b'r":"'
                                                                                                                                                                                                 b'page'
                                                                                                                                                                                                 b'-1",'
                                                                                                                                                                                                 b'"pag'
                                                                                                                                                                                                 b'e":1'
                                                                                                                                                                                                 b',"te'
                                                                                                                                                                                                 b'xt_e'
                                                                                                                                                                                                 b'nd":'
                                                                                                                                                                                                 b'82,"'
                                                                                                                                                                                                 b'text'
                                                                                                                                                                                                 b'_sha'
                                                                                                                                                                                                 b'256"'
                                                                                                                                                                                                 b':"fa'
                                                                                                                                                                                                 b'3bde'
                                                                                                                                                                                                 b'3f1f'
                                                                                                                                                                                                 b'fed3'
                                                                                                                                                                                                 b'ca3c'
                                                                                                                                                                                                 b'ec13'
                                                                                                                                                                                                 b'503d'
                                                                                                                                                                                                 b'733c'
                                                                                                                                                                                                 b'3cda'
                                                                                                                                                                                                 b'558e'
                                                                                                                                                                                                 b'3541'
                                                                                                                                                                                                 b'8d40'
                                                                                                                                                                                                 b'8ecb'
                                                                                                                                                                                                 b'932f'
                                                                                                                                                                                                 b'5516'
                                                                                                                                                                                                 b'825c'
                                                                                                                                                                                                 b'79",'
                                                                                                                                                                                                 b'"tex'
                                                                                                                                                                                                 b't_st'
                                                                                                                                                                                                 b'art"'
                                                                                                                                                                                                 b':51}'
                                                                                                                                                                                                 b'],"p'
                                                                                                                                                                                                 b'aper'
                                                                                                                                                                                                 b'_id"'
                                                                                                                                                                                                 b':"ar'
                                                                                                                                                                                                 b'xiv:'
                                                                                                                                                                                                 b'2311'
                                                                                                                                                                                                 b'.151'
                                                                                                                                                                                                 b'28",'
                                                                                                                                                                                                 b'"sch'
                                                                                                                                                                                                 b'ema"'
                                                                                                                                                                                                 b':"vi'
                                                                                                                                                                                                 b'deo-'
                                                                                                                                                                                                 b'pape'
                                                                                                                                                                                                 b'r-wi'
                                                                                                                                                                                                 b'ki.m'
                                                                                                                                                                                                 b'arkd'
                                                                                                                                                                                                 b'own-'
                                                                                                                                                                                                 b'sour'
                                                                                                                                                                                                 b'ce-o'
                                                                                                                                                                                                 b'bser'
                                                                                                                                                                                                 b'vati'
                                                                                                                                                                                                 b'on.v'
                                                                                                                                                                                                 b'1","'
                                                                                                                                                                                                 b'sour'
                                                                                                                                                                                                 b'ce_m'
                                                                                                                                                                                                 b'etad'
                                                                                                                                                                                                 b'ata_'
                                                                                                                                                                                                 b'sha2'
                                                                                                                                                                                                 b'56":'
                                                                                                                                                                                                 b'"ccc'
                                                                                                                                                                                                 b'cccc'
                                                                                                                                                                                                 b'cccc'
                                                                                                                                                                                                 b'cccc'
                                                                                                                                                                                                 b'cccc'
                                                                                                                                                                                                 b'cccc'
                                                                                                                                                                                                 b'cccc'
                                                                                                                                                                                                 b'cccc'
                                                                                                                                                                                                 b'cccc'
                                                                                                                                                                                                 b'cccc'
                                                                                                                                                                                                 b'cccc'
                                                                                                                                                                                                 b'cccc'
                                                                                                                                                                                                 b'cccc'
                                                                                                                                                                                                 b'cccc'
                                                                                                                                                                                                 b'cccc'
                                                                                                                                                                                                 b'cccc'
                                                                                                                                                                                                 b'c","'
                                                                                                                                                                                                 b'titl'
                                                                                                                                                                                                 b'e":"'
                                                                                                                                                                                                 b'Seco'
                                                                                                                                                                                                 b'nd P'
                                                                                                                                                                                                 b'aper'
                                                                                                                                                                                                 b'","v'
                                                                                                                                                                                                 b'ersi'
                                                                                                                                                                                                 b'on":'
                                                                                                                                                                                                 b'{"ki'
                                                                                                                                                                                                 b'nd":'
                                                                                                                                                                                                 b'"dec'
                                                                                                                                                                                                 b'lare'
                                                                                                                                                                                                 b'd","'
                                                                                                                                                                                                 b'labe'
                                                                                                                                                                                                 b'l":"'
                                                                                                                                                                                                 b'v1.0'
                                                                                                                                                                                                 b'"}}'},
 'head_bytes': b'{"receipt_path":"wiki/meta/operations/000000000002-md-ingest.json","receipt_sha256":"a2252e1'
               b'd0b22572fee436e6a7c71ead5ad0f42e68d32c563c7bb641d397c0c8e","schema":"video-paper-wiki.operat'
               b'ion-head.v1","sequence":2}',
 'receipt_bytes': {'wiki/meta/operations/000000000001-genesis.json': b'{"claimed_inputs":[],"intent_sha256"'
                                                                     b':"1d6c44d77433884027bc60cbae60c4bca6'
                                                                     b'e60eb2c683edb23b9d8181e90f5440","ope'
                                                                     b'ration_id":"genesis","operation_type'
                                                                     b'":"generic","previous":null,"schema"'
                                                                     b':"video-paper-wiki.operation-receipt'
                                                                     b'.v1","sequence":1,"writes":[{"after_'
                                                                     b'sha256":"70668ccb9f199d031816459d298'
                                                                     b'c8b5c89af7c3b52ce05433d4e59548459bc1'
                                                                     b'b","before_sha256":null,"mode":"crea'
                                                                     b'te","path":"wiki/meta/ledgers/claim-'
                                                                     b'ledger.json"},{"after_sha256":"67fb1'
                                                                     b'673adba8159663819a75f5f97172ff12bb59'
                                                                     b'54b1fb51fbf4a1f4c77331d","before_sha'
                                                                     b'256":null,"mode":"create","path":"wi'
                                                                     b'ki/meta/ledgers/source-ledger.json"}'
                                                                     b']}',
                   'wiki/meta/operations/000000000002-md-ingest.json': b'{"claimed_inputs":[{"mode":"read","p'
                                                                       b'ath":".raw/captured/d5060293eeecc873'
                                                                       b'493ce8395d3d2f77308c98a0854ceb9dc117'
                                                                       b'ee90ec368c52.md","sha256":"d5060293e'
                                                                       b'eecc873493ce8395d3d2f77308c98a0854ce'
                                                                       b'b9dc117ee90ec368c52"}],"intent_sha25'
                                                                       b'6":"c40365e98aab756e9cde6b332a445b56'
                                                                       b'e704c9a9dc8c603c0b81a17bb8eb395c","o'
                                                                       b'peration_id":"md-ingest","operation_'
                                                                       b'type":"ingest","previous":{"path":"w'
                                                                       b'iki/meta/operations/000000000001-gen'
                                                                       b'esis.json","sha256":"63572c4dc9418b3'
                                                                       b'1b2f522e0aa095f9a0b46b8bcb81edaada51'
                                                                       b'e0f7324d848ca"},"schema":"video-pape'
                                                                       b'r-wiki.operation-receipt.v1","sequen'
                                                                       b'ce":2,"writes":[{"after_sha256":"5b0'
                                                                       b'e4a1ad0710721c8ece55cbcb87d48408a914'
                                                                       b'29692b262570e02245ab0ee77","before_s'
                                                                       b'ha256":"67fb1673adba8159663819a75f5f'
                                                                       b'97172ff12bb5954b1fb51fbf4a1f4c77331d'
                                                                       b'","mode":"replace","path":"wiki/meta'
                                                                       b'/ledgers/source-ledger.json"}]}'},
 'registration_ledgers': {'.raw/derived/source-ledgers/5b0e4a1ad0710721c8ece55cbcb87d48408a91429692b262570e02245ab0ee77.json': b'{"ge'
                                                                                                                               b'nera'
                                                                                                                               b'ted_'
                                                                                                                               b'at":'
                                                                                                                               b'"202'
                                                                                                                               b'6-09'
                                                                                                                               b'-09T'
                                                                                                                               b'00:0'
                                                                                                                               b'0:00'
                                                                                                                               b'Z","'
                                                                                                                               b'sche'
                                                                                                                               b'ma":'
                                                                                                                               b'"cla'
                                                                                                                               b'ude-'
                                                                                                                               b'obsi'
                                                                                                                               b'dian'
                                                                                                                               b'.sou'
                                                                                                                               b'rce-'
                                                                                                                               b'ledg'
                                                                                                                               b'er.v'
                                                                                                                               b'1","'
                                                                                                                               b'sour'
                                                                                                                               b'ces"'
                                                                                                                               b':{"s'
                                                                                                                               b'rc-1'
                                                                                                                               b'3ea0'
                                                                                                                               b'ff61'
                                                                                                                               b'0b50'
                                                                                                                               b'ce22'
                                                                                                                               b'aed"'
                                                                                                                               b':{"a'
                                                                                                                               b'utho'
                                                                                                                               b'rity'
                                                                                                                               b'":"p'
                                                                                                                               b'rima'
                                                                                                                               b'ry",'
                                                                                                                               b'"con'
                                                                                                                               b'tent'
                                                                                                                               b'_kin'
                                                                                                                               b'd":"'
                                                                                                                               b'docu'
                                                                                                                               b'ment'
                                                                                                                               b'","c'
                                                                                                                               b'onte'
                                                                                                                               b'nt_s'
                                                                                                                               b'ha25'
                                                                                                                               b'6":"'
                                                                                                                               b'd506'
                                                                                                                               b'0293'
                                                                                                                               b'eeec'
                                                                                                                               b'c873'
                                                                                                                               b'493c'
                                                                                                                               b'e839'
                                                                                                                               b'5d3d'
                                                                                                                               b'2f77'
                                                                                                                               b'308c'
                                                                                                                               b'98a0'
                                                                                                                               b'854c'
                                                                                                                               b'eb9d'
                                                                                                                               b'c117'
                                                                                                                               b'ee90'
                                                                                                                               b'ec36'
                                                                                                                               b'8c52'
                                                                                                                               b'","i'
                                                                                                                               b'ndep'
                                                                                                                               b'ende'
                                                                                                                               b'nce_'
                                                                                                                               b'key"'
                                                                                                                               b':nul'
                                                                                                                               b'l,"i'
                                                                                                                               b'nges'
                                                                                                                               b'ted_'
                                                                                                                               b'at":'
                                                                                                                               b'"202'
                                                                                                                               b'6-09'
                                                                                                                               b'-09"'
                                                                                                                               b',"or'
                                                                                                                               b'igin'
                                                                                                                               b'":{"'
                                                                                                                               b'kind'
                                                                                                                               b'":"f'
                                                                                                                               b'ile"'
                                                                                                                               b',"lo'
                                                                                                                               b'cato'
                                                                                                                               b'r":"'
                                                                                                                               b'.raw'
                                                                                                                               b'/cap'
                                                                                                                               b'ture'
                                                                                                                               b'd/d5'
                                                                                                                               b'0602'
                                                                                                                               b'93ee'
                                                                                                                               b'ecc8'
                                                                                                                               b'7349'
                                                                                                                               b'3ce8'
                                                                                                                               b'395d'
                                                                                                                               b'3d2f'
                                                                                                                               b'7730'
                                                                                                                               b'8c98'
                                                                                                                               b'a085'
                                                                                                                               b'4ceb'
                                                                                                                               b'9dc1'
                                                                                                                               b'17ee'
                                                                                                                               b'90ec'
                                                                                                                               b'368c'
                                                                                                                               b'52.m'
                                                                                                                               b'd"},'
                                                                                                                               b'"pag'
                                                                                                                               b'es":'
                                                                                                                               b'["wi'
                                                                                                                               b'ki/p'
                                                                                                                               b'aper'
                                                                                                                               b's/ar'
                                                                                                                               b'xiv-'
                                                                                                                               b'2311'
                                                                                                                               b'.151'
                                                                                                                               b'28.m'
                                                                                                                               b'd"],'
                                                                                                                               b'"ref'
                                                                                                                               b'resh'
                                                                                                                               b'_due'
                                                                                                                               b'":nu'
                                                                                                                               b'll,"'
                                                                                                                               b'retr'
                                                                                                                               b'ieve'
                                                                                                                               b'd_at'
                                                                                                                               b'":nu'
                                                                                                                               b'll,"'
                                                                                                                               b'revi'
                                                                                                                               b'ew_s'
                                                                                                                               b'tatu'
                                                                                                                               b's":"'
                                                                                                                               b'acti'
                                                                                                                               b've",'
                                                                                                                               b'"sup'
                                                                                                                               b'erse'
                                                                                                                               b'des"'
                                                                                                                               b':nul'
                                                                                                                               b'l,"t'
                                                                                                                               b'itle'
                                                                                                                               b'":"S'
                                                                                                                               b'econ'
                                                                                                                               b'd Pa'
                                                                                                                               b'per"'
                                                                                                                               b'}}}'}}

GOLDEN_LEGACY_PAGES = {'wiki/code/github-c75bb408b0db72b7f71083c4ed259711df47bf2fcb9d58ad813a095356f865bf.md': '---\n'
                                                                                         'title: '
                                                                                         '"ExampleOrg/VideoModel '
                                                                                         '· train.py"\n'
                                                                                         'type: code\n'
                                                                                         'status: generated\n'
                                                                                         'created: '
                                                                                         '2026-01-01\n'
                                                                                         'updated: '
                                                                                         '2026-01-01\n'
                                                                                         'tags: '
                                                                                         '["code","video-paper"]\n'
                                                                                         'repo_id: '
                                                                                         '"github:exampleorg/videomodel"\n'
                                                                                         'repository: '
                                                                                         '"ExampleOrg/VideoModel"\n'
                                                                                         'commit: '
                                                                                         '"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n'
                                                                                         'source_path: '
                                                                                         '"train.py"\n'
                                                                                         '---\n'
                                                                                         '\n'
                                                                                         '# '
                                                                                         'ExampleOrg/VideoModel '
                                                                                         '· train.py\n'
                                                                                         '\n'
                                                                                         '## 捕获证据\n'
                                                                                         '\n'
                                                                                         '- manifest: '
                                                                                         '`070cb28455cf6ade6d5fba34236422ed98eb8b5b7e03324501e8a63d7928eb7e`\n'
                                                                                         '- payload: '
                                                                                         '`1925e1ce1d893badd5fd239eb305c4d385b8b35f3048640faaf975b55d230311`\n'
                                                                                         '\n'
                                                                                         '## 能力矩阵\n'
                                                                                         '\n'
                                                                                         '- checkpoints: '
                                                                                         '`unverified`; '
                                                                                         'evidence=0\n'
                                                                                         '- data: `partial`; '
                                                                                         'evidence=1\n'
                                                                                         '- evaluation: '
                                                                                         '`absent`; '
                                                                                         'evidence=0\n'
                                                                                         '- inference: '
                                                                                         '`present`; '
                                                                                         'evidence=1\n'
                                                                                         '- training: '
                                                                                         '`present`; '
                                                                                         'evidence=1\n'
                                                                                         '\n'
                                                                                         '## 关联论文\n'
                                                                                         '\n'
                                                                                         '- '
                                                                                         '[[../papers/arxiv-2311.15127|arxiv:2311.15127]]\n',
 'wiki/concepts/backbone-dit.md': '---\n'
                                  'title: "扩散 Transformer"\n'
                                  'type: concept\n'
                                  'status: generated\n'
                                  'created: 2026-01-01\n'
                                  'updated: 2026-01-01\n'
                                  'tags: ["concept","backbone/dit"]\n'
                                  'axis: "backbone"\n'
                                  'slug: "dit"\n'
                                  '---\n'
                                  '\n'
                                  '# 扩散 Transformer\n'
                                  '\n'
                                  'dit\n'
                                  '\n'
                                  '## 关联\n'
                                  '\n'
                                  '- [[../papers/arxiv-2311.15127|arxiv-2311.15127]]\n',
 'wiki/papers/arxiv-2311.15127.md': '---\n'
                                    'type: "paper"\n'
                                    'paper_id: "arxiv:2311.15127"\n'
                                    'title: "A Video Paper"\n'
                                    'title_zh: "一篇视频论文"\n'
                                    'authors: ["Ada Example"]\n'
                                    'published_at: "2023-11-25"\n'
                                    'arxiv_id: "2311.15127"\n'
                                    'doi: null\n'
                                    'aliases: ["Video Paper"]\n'
                                    'source_ids: ["src-paper"]\n'
                                    'claim_ids: ["clm-070856211205617b9eb8"]\n'
                                    'topics: ["backbone/dit"]\n'
                                    'code_urls: ["https://github.com/ExampleOrg/VideoModel"]\n'
                                    'active_extraction_path: '
                                    '".raw/derived/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/docling/fp/document.json"\n'
                                    'active_extraction_sha256: '
                                    '"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"\n'
                                    'created_at: "2026-08-29T12:00:00Z"\n'
                                    'updated_at: "2026-08-29T12:00:00Z"\n'
                                    'status: "generated"\n'
                                    'created: "2026-08-29"\n'
                                    'updated: "2026-08-29"\n'
                                    'tags: ["backbone/dit"]\n'
                                    '---\n'
                                    '\n'
                                    '# 一篇视频论文\n'
                                    '\n'
                                    '## 一句话结论\n'
                                    '\n'
                                    '- A verified compiler claim.  ^clm-070856211205617b9eb8\n'
                                    '  - lifecycle: `active`; assessment: `accepted`\n'
                                    '\n'
                                    '## 研究问题\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 方法\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 表征与架构\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 训练与数据\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 实验与结果\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 局限\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 代码与资源\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 证据状态\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 关联\n'
                                    '\n'
                                    '- [[../concepts/backbone-dit|backbone-dit]]\n'
                                    '- '
                                    '[[../code/github-c75bb408b0db72b7f71083c4ed259711df47bf2fcb9d58ad813a095356f865bf|ExampleOrg/VideoModel]]\n'}

GOLDEN_MIXED_PAGES = {'wiki/code/github-c75bb408b0db72b7f71083c4ed259711df47bf2fcb9d58ad813a095356f865bf.md': '---\n'
                                                                                         'title: '
                                                                                         '"ExampleOrg/VideoModel '
                                                                                         '· train.py"\n'
                                                                                         'type: code\n'
                                                                                         'status: generated\n'
                                                                                         'created: '
                                                                                         '2026-01-01\n'
                                                                                         'updated: '
                                                                                         '2026-01-01\n'
                                                                                         'tags: '
                                                                                         '["code","video-paper"]\n'
                                                                                         'repo_id: '
                                                                                         '"github:exampleorg/videomodel"\n'
                                                                                         'repository: '
                                                                                         '"ExampleOrg/VideoModel"\n'
                                                                                         'commit: '
                                                                                         '"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n'
                                                                                         'source_path: '
                                                                                         '"train.py"\n'
                                                                                         '---\n'
                                                                                         '\n'
                                                                                         '# '
                                                                                         'ExampleOrg/VideoModel '
                                                                                         '· train.py\n'
                                                                                         '\n'
                                                                                         '## 捕获证据\n'
                                                                                         '\n'
                                                                                         '- manifest: '
                                                                                         '`070cb28455cf6ade6d5fba34236422ed98eb8b5b7e03324501e8a63d7928eb7e`\n'
                                                                                         '- payload: '
                                                                                         '`1925e1ce1d893badd5fd239eb305c4d385b8b35f3048640faaf975b55d230311`\n'
                                                                                         '\n'
                                                                                         '## 能力矩阵\n'
                                                                                         '\n'
                                                                                         '- checkpoints: '
                                                                                         '`unverified`; '
                                                                                         'evidence=0\n'
                                                                                         '- data: `partial`; '
                                                                                         'evidence=1\n'
                                                                                         '- evaluation: '
                                                                                         '`absent`; '
                                                                                         'evidence=0\n'
                                                                                         '- inference: '
                                                                                         '`present`; '
                                                                                         'evidence=1\n'
                                                                                         '- training: '
                                                                                         '`present`; '
                                                                                         'evidence=1\n'
                                                                                         '\n'
                                                                                         '## 关联论文\n'
                                                                                         '\n'
                                                                                         '- '
                                                                                         '[[../papers/arxiv-2311.15127|arxiv:2311.15127]]\n',
 'wiki/concepts/backbone-dit.md': '---\n'
                                  'title: "扩散 Transformer"\n'
                                  'type: concept\n'
                                  'status: generated\n'
                                  'created: 2026-01-01\n'
                                  'updated: 2026-01-01\n'
                                  'tags: ["concept","backbone/dit"]\n'
                                  'axis: "backbone"\n'
                                  'slug: "dit"\n'
                                  '---\n'
                                  '\n'
                                  '# 扩散 Transformer\n'
                                  '\n'
                                  'dit\n'
                                  '\n'
                                  '## 关联\n'
                                  '\n'
                                  '- [[../papers/arxiv-2311.15127|arxiv-2311.15127]]\n'
                                  '- [[../papers/arxiv-2311.15128|arxiv-2311.15128]]\n',
 'wiki/papers/arxiv-2311.15127.md': '---\n'
                                    'type: "paper"\n'
                                    'paper_id: "arxiv:2311.15127"\n'
                                    'title: "A Video Paper"\n'
                                    'title_zh: "一篇视频论文"\n'
                                    'authors: ["Ada Example"]\n'
                                    'published_at: "2023-11-25"\n'
                                    'arxiv_id: "2311.15127"\n'
                                    'doi: null\n'
                                    'aliases: ["Video Paper"]\n'
                                    'source_ids: ["src-paper"]\n'
                                    'claim_ids: ["clm-070856211205617b9eb8"]\n'
                                    'topics: ["backbone/dit"]\n'
                                    'code_urls: ["https://github.com/ExampleOrg/VideoModel"]\n'
                                    'active_extraction_path: '
                                    '".raw/derived/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/docling/fp/document.json"\n'
                                    'active_extraction_sha256: '
                                    '"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"\n'
                                    'created_at: "2026-08-29T12:00:00Z"\n'
                                    'updated_at: "2026-08-29T12:00:00Z"\n'
                                    'status: "generated"\n'
                                    'created: "2026-08-29"\n'
                                    'updated: "2026-08-29"\n'
                                    'tags: ["backbone/dit"]\n'
                                    '---\n'
                                    '\n'
                                    '# 一篇视频论文\n'
                                    '\n'
                                    '## 一句话结论\n'
                                    '\n'
                                    '- A verified compiler claim.  ^clm-070856211205617b9eb8\n'
                                    '  - lifecycle: `active`; assessment: `accepted`\n'
                                    '\n'
                                    '## 研究问题\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 方法\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 表征与架构\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 训练与数据\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 实验与结果\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 局限\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 代码与资源\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 证据状态\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 关联\n'
                                    '\n'
                                    '- [[../concepts/backbone-dit|backbone-dit]]\n'
                                    '- '
                                    '[[../code/github-c75bb408b0db72b7f71083c4ed259711df47bf2fcb9d58ad813a095356f865bf|ExampleOrg/VideoModel]]\n',
 'wiki/papers/arxiv-2311.15128.md': '---\n'
                                    'type: "paper"\n'
                                    'paper_id: "arxiv:2311.15128"\n'
                                    'title: "Second Paper"\n'
                                    'title_zh: "第二篇论文"\n'
                                    'authors: ["Ada Example"]\n'
                                    'published_at: "2023-11-26"\n'
                                    'arxiv_id: "2311.15128"\n'
                                    'doi: null\n'
                                    'aliases: ["Second Paper Alias"]\n'
                                    'source_ids: ["src-13ea0ff610b50ce22aed","src-history-code"]\n'
                                    'source_associations: '
                                    '[{"association_id":"sva-87474ae4adfa8b817b9904938d9d77b1da0639b65dbca6672a55bdfbf04760a1","sha256":"f34a0e523929cc9857ab90a5f8c82616fec0fbb36540dcc64b1ecefca595b8a8"}]\n'
                                    'display_head: '
                                    '{"decision_id":"svd-ba01fc31ab4b8dcfb9b91dd0a26fe319ddcd87947ada6935d19ad6cde67f3ce2","sha256":"3bf809e3d590493b2444a36e988505297869f8ea181ee7458399fd66a26b2323"}\n'
                                    'claim_ids: ["clm-d377b59001b98187ed1e"]\n'
                                    'topics: ["backbone/dit"]\n'
                                    'code_urls: ["https://github.com/ExampleOrg/VideoModel"]\n'
                                    'active_extraction_path: '
                                    '".raw/derived/markdown-source/d5060293eeecc873493ce8395d3d2f77308c98a0854ceb9dc117ee90ec368c52/b046e8c73484f9998e96405d6406ee133ebb5b9e0836573b101f3f38b0b6556b.json"\n'
                                    'active_extraction_sha256: '
                                    '"b046e8c73484f9998e96405d6406ee133ebb5b9e0836573b101f3f38b0b6556b"\n'
                                    'created_at: "2026-09-09T00:00:00Z"\n'
                                    'updated_at: "2026-09-09T01:00:00Z"\n'
                                    'status: "generated"\n'
                                    'created: "2026-09-09"\n'
                                    'updated: "2026-09-09"\n'
                                    'tags: ["backbone/dit"]\n'
                                    '---\n'
                                    '\n'
                                    '# 第二篇论文\n'
                                    '\n'
                                    '## 来源版本\n'
                                    '\n'
                                    '- 展示版本：v1.0；association: '
                                    '`sva-87474ae4adfa8b817b9904938d9d77b1da0639b65dbca6672a55bdfbf04760a1`\n'
                                    '- v1.0 (declared); '
                                    '[Markdown](../../.raw/captured/d5060293eeecc873493ce8395d3d2f77308c98a0854ceb9dc117ee90ec368c52.md); '
                                    'association: '
                                    '`sva-87474ae4adfa8b817b9904938d9d77b1da0639b65dbca6672a55bdfbf04760a1`\n'
                                    '\n'
                                    '## 一句话结论\n'
                                    '\n'
                                    '- A Markdown-backed conclusion.  ^clm-d377b59001b98187ed1e\n'
                                    '  - lifecycle: `active`; assessment: `accepted`\n'
                                    '  - evidence: uncertain; source: `src-history-code`; repository: '
                                    'Owner/Repo; commit: `cccccccccccccccccccccccccccccccccccccccc`; path: '
                                    'src/model.py; lines: 1-3\n'
                                    '  - evidence: supports; source: `src-13ea0ff610b50ce22aed`; '
                                    'association: '
                                    '`sva-87474ae4adfa8b817b9904938d9d77b1da0639b65dbca6672a55bdfbf04760a1`; '
                                    '[Markdown](../../.raw/captured/d5060293eeecc873493ce8395d3d2f77308c98a0854ceb9dc117ee90ec368c52.md#page-1); '
                                    'span: [51, 82); excerpt_sha256: '
                                    '`fa3bde3f1ffed3ca3cec13503d733c3cda558e35418d408ecb932f5516825c79`\n'
                                    '\n'
                                    '## 研究问题\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 方法\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 表征与架构\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 训练与数据\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 实验与结果\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 局限\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 代码与资源\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 证据状态\n'
                                    '\n'
                                    '- 暂无。\n'
                                    '\n'
                                    '## 关联\n'
                                    '\n'
                                    '- [[../concepts/backbone-dit|backbone-dit]]\n'}
