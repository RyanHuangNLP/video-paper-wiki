"""Conservative ASCII wire-size bounds; these are NOT valid Git proof fixtures."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("ascii")


def envelope(kind, data):
    return {"schema": "video-paper-wiki." + kind + ".v1", "kind": kind,
            "id": "ce1:" + kind + ":" + "f" * 64, "data": data}


def reference(kind):
    return {"id": "ce1:" + kind + ":" + "f" * 64, "sha256": "f" * 64}


def run():
    oid = "f" * 64
    record = dict(oid=oid, object_type="commit", body_size_bytes=8388608,
                  body_sha256=oid, framed_sha256=oid)
    blob = {k: record[k] for k in ("oid", "body_size_bytes", "body_sha256", "framed_sha256")}
    # Any valid requested path has <=512 ASCII bytes; aggregate walk name_hex
    # has <=1024 chars. There are <=32 edges. Give every edge its maximum-size
    # mode/OIDs and distribute the aggregate name budget across all 32 edges.
    edge = dict(tree_oid=oid, name_hex="f" * 32, mode="100644", oid=oid)
    target = dict(path="p" * 512, outcome="permitted_regular_blob", reason=None,
                  walk=[edge] * 32,
                  stopped_at=dict(component_index=31, tree_oid=oid,
                                  name_hex="f" * 1024, mode="100644", oid=oid),
                  blob=blob)
    proof = dict(object_format="sha256", commit_oid=oid, root_tree_oid=oid,
                 object_records=[record] * 2048, consumed_oids=[oid] * 2048,
                 budget=dict(object_count=2048, declared_body_bytes=33554432,
                             actual_body_bytes=33554432, parsed_tree_entries=32768,
                             target_count=32, walk_edges=1024), targets=[target] * 32)
    text = dict(normalized_size_bytes=8388608, normalized_sha256=oid,
                newline_style="mixed", ends_with_newline=False, line_count=8388608)
    # This combined row is a size upper bound, not a valid status/text union.
    # Maximal status/reason length and maximal metadata may coexist only here.
    row = dict(path="p" * 512, status="unsupported_source_bytes",
               reason="non_directory_intermediate", text=text)
    observation = envelope("code-proof-observation", dict(
        request=reference("code-proof-request"), intent=reference("code-acquisition-intent"),
        bundle=reference("code-git-bundle"), mode="git_objects", git_proof=proof,
        targets=[row] * 32,
        capabilities=dict(git_objects_verified=False, raw_bytes_retained=False,
                          repository_assertion="host_asserted", source_association_verified=False),
        eligibility=dict(complete_target_set=False, repository_requirement_met=False,
                         source_handoff_eligible=False)))
    # Batch has <=128 ASCII chars. Widths independently maximize every field;
    # aggregate size validity and cryptographic validity are intentionally absent.
    raw_body = dict(path=".work/" + "b" * 128 + "/code-evidence-v1/objects/" + oid + ".body",
                    size_bytes=8388608, sha256=oid)
    handoff = envelope("code-source-handoff", dict(
        successor_only=True, request=reference("code-proof-request"),
        observation=reference("code-proof-observation"), bundle=reference("code-git-bundle"),
        paper_id="p" * 512, source_association=dict(association_id="sva-" + oid, sha256=oid),
        repository="r" * 100 + "/" + "r" * 100, object_format="sha256",
        commit_oid=oid, root_tree_oid=oid, path="p" * 512,
        roles=["citation", "configuration", "entrypoint", "implementation", "license", "readme"],
        allow_executable_source=False, blob=blob, raw_body=raw_body,
        text=text, proof=target, repository_assertion="host_asserted",
        source_association_verified=False))
    proof_bytes = encoded(proof)
    observation_bytes = encoded(observation) + b"\n"
    handoff_bytes = encoded(handoff) + b"\n"
    assert len(observation_bytes) < 2097152
    assert len(handoff_bytes) < 131072
    return {
        "schema": "full-todo.code-proof-structural-serialization-bound.v1",
        "status": "CONSERVATIVE_STRUCTURAL_BOUND_ONLY_NOT_A_VALID_GIT_FIXTURE",
        "git_proof_bytes_upper_bound": len(proof_bytes),
        "raw_observation_saved_bytes_upper_bound": len(observation_bytes),
        "handoff_saved_bytes_upper_bound": len(handoff_bytes),
        "default_caps": {"observation": 2097152, "handoff": 131072},
        "bound_construction_sha256": {"proof": hashlib.sha256(proof_bytes).hexdigest(),
                                      "observation": hashlib.sha256(observation_bytes).hexdigest(),
                                      "handoff": hashlib.sha256(handoff_bytes).hexdigest()},
        "limitations": [
            "Independent maxima deliberately violate cross-field and cryptographic constraints; never pass these as a valid kernel fixture.",
            "This bounds the R7 raw branch only; normalized intent/config bytes require actual canonical serialization and their own caps.",
            "Lowered request caps may refuse otherwise valid results before any output install.",
            "Byte identity with JCS follows ASCII-only strings, no escapable characters, integers within the safe JCS range, and compact sorted keys.",
            "Required target path/walk grammar, object count, OID width and source metadata caps are the premises of this bound."
        ]
    }


if __name__ == "__main__":
    output = Path(__file__).with_suffix(".json")
    assert not output.exists(), "preserve previous bound evidence"
    result = run()
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
