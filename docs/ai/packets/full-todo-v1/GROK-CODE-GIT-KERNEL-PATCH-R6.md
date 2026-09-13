# Return a repair patch from the complete excerpts below

You are Grok Build, the code author. Return only one fenced diff in apply_patch
format: `*** Begin Patch`, `*** Update File: <absolute path>`, context hunks
using `@@` without line counts, and `*** End Patch`. No tool calls, plans, prose,
placeholders or execution claims. The relevant source excerpts below are complete
for the requested edits. The previous response reported a truncated request;
this short request intentionally excludes unrelated code.

Only two existing file paths are allowed in Update File headers:

- /Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/code-proof-v1/terminal-1/source/src/video_paper_wiki/code_git_objects.py
- /Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/code-proof-v1/terminal-1/source/tests/unit/test_code_git_objects.py

Required changes, without changing the API or verification order:

1. At the three shown production validation sites, preserve exact-dict and
   constant-time length guards. Then reject every non-exact-str key BEFORE set,
   membership, lookup, equality or formatting can call its methods. Reuse
   `_input_invalid` with the existing bounded pointer and reason. Continue the
   existing closed-set/value checks afterward. Do not change other production.
2. Repair the cap test to cover declared and actual per-object AND aggregate
   byte caps, on both sha1/sha256. Build graphs before arming instrumentation or
   reset immediately before verification. Actual-cap cases pass all declared
   caps; aggregate cases also pass every per-object cap. Assert exact structured
   limit context and zero hash calls during the rejected call. Declared pointers
   are `/objects/<index>/body_size_bytes` or `/objects`; actual pointers are
   `/bodies/<oid>` or `/bodies`. Aggregate observed count is the first sorted-body
   cumulative total that exceeds the cap. Make fixtures unambiguous.
3. Replace only the unused-tree branch's duplicate empty tree with a distinct
   valid hash-correct tree. A nonempty unused tree may refer to an unmaterialized
   child because it is parsed but never walked. Preserve both other branches
   and the exact unused_oid consumed-set refusal.
4. Replace `assert "\\u0000" not in encoded or True` with a real JSON round-trip
   assertion, preserving all existing deterministic/no-alias/no-bytes checks.
5. Add focused parametrized tests: both formats, hostile str-subclass dict keys
   at limits/object-record/target/body-map. Arm hash/equality traps AFTER input
   construction, require CODE_PROOF_INPUT_INVALID without callback invocation,
   then verify an independent valid graph succeeds. Also preserve ordinary
   closed-shape/strict-type behavior. Append tests near the shown cap test using
   stable context; no fixture edits, skip/xfail or weakened assertions.

The test module already imports copy, hashlib, json, pytest, CodeGitProofError,
CODE_GIT_PROFILE_LIMITS, all error constants below, git_object_ids and
verify_code_git_objects. Production `_input_invalid(pointer, reason)` raises
CodeGitProofError(CODE_PROOF_INPUT_INVALID, fixed_message, details, 2).
Its exact details are `{instance_pointer: pointer, reason: reason}`.
`_validate_bodies_map` already checks each key's exact str type safely before
membership; its code needs no edit. `_assert_error` accepts expected detail fields
as shown. The ordinary profile has max_object_bytes=8388608 and
max_total_object_bytes=33554432; every lowered limit is a positive exact int.

Use the actual lines below as patch context. Produce the complete patch now.


## Exact production context

```python
def _validate_limits(limits: object) -> dict[str, int]:
    if type(limits) is not dict:
        _input_invalid("/limits", "invalid_type")
    if len(limits) != 5:
        _input_invalid("/limits", "limits_key_set")
    owned: dict[str, int] = {}
    for key, maximum in CODE_GIT_PROFILE_LIMITS.items():
        if key not in limits:
            _input_invalid("/limits", "limits_key_set")
        value = limits[key]
        pointer = "/limits/" + key
        if type(value) is not int:
            _input_invalid(pointer, "invalid_type")
        if value < 1 or value > maximum:
            _input_invalid(pointer, "out_of_range")
        owned[key] = value
    return owned
```

```python
        if type(item) is not dict or len(item) != 2 or set(item) != _TARGET_KEYS:
            _input_invalid(pointer, "not_closed_record")
        path_pointer = pointer + "/path"
```

```python
        if type(item) is not dict or len(item) != 5 or set(item) != _OBJECT_RECORD_KEYS:
            _input_invalid(pointer, "not_closed_record")
        oid = item["oid"]
```

## Exact test helpers and functions

```python
def _limits(**overrides: int) -> dict[str, int]:
    values = dict(CODE_GIT_PROFILE_LIMITS)
    values.update(overrides)
    return values
```

```python
def _assert_error(exc: CodeGitProofError, code: str, **details: object) -> None:
    assert isinstance(exc, CodeGitProofError)
    assert exc.code == code
    assert exc.exit_code == 2
    assert type(exc.details) is dict
    for key, value in details.items():
        assert exc.details[key] == value
    dumped = json.dumps(exc.details)
    assert "blob " not in dumped
```

```python
def _tree_bytes(object_format: str, entries: list[tuple[str, bytes, str]]) -> bytes:
    raw_len = 20 if object_format == "sha1" else 32
    chunks = []
    for mode, name, oid in entries:
        raw = bytes.fromhex(oid)
        assert len(raw) == raw_len
        chunks.append(mode.encode("ascii") + b" " + name + b"\0" + raw)
    return b"".join(chunks)
```

```python
def _record(object_format: str, object_type: str, body: bytes) -> tuple[dict, bytes]:
    oid, body_sha256, framed_sha256 = git_object_ids(object_format, object_type, body)
    return (
        {
            "oid": oid,
            "object_type": object_type,
            "body_size_bytes": len(body),
            "body_sha256": body_sha256,
            "framed_sha256": framed_sha256,
        },
        body,
    )
```

```python
def _minimal_graph(object_format: str, tree_body: bytes = b"", targets: list[dict] | None = None, extra_objects: list[tuple[dict, bytes]] | None = None):
    tree_rec, tree_body = _record(object_format, "tree", tree_body)
    commit_body = _commit_bytes(tree_rec["oid"])
    commit_rec, commit_body = _record(object_format, "commit", commit_body)
    records = [commit_rec, tree_rec]
    bodies = {commit_rec["oid"]: commit_body, tree_rec["oid"]: tree_body}
    if extra_objects:
        for rec, body in extra_objects:
            records.append(rec)
            bodies[rec["oid"]] = body
    records.sort(key=lambda rec: rec["oid"])
    if targets is None:
        targets = [{"path": "missing.txt", "allow_executable_source": False}]
    return {
        "object_format": object_format,
        "commit_oid": commit_rec["oid"],
        "root_tree_oid": tree_rec["oid"],
        "objects": records,
        "bodies": bodies,
        "targets": targets,
        "limits": _limits(),
    }
```

```python
def test_declared_and_actual_caps_precede_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    hash_calls = {"n": 0}
    real_sha1 = hashlib.sha1
    real_sha256 = hashlib.sha256

    def wrapped_sha1(*args: object, **kwargs: object):
        hash_calls["n"] += 1
        return real_sha1(*args, **kwargs)

    def wrapped_sha256(*args: object, **kwargs: object):
        hash_calls["n"] += 1
        return real_sha256(*args, **kwargs)

    monkeypatch.setattr(hashlib, "sha1", wrapped_sha1)
    monkeypatch.setattr(hashlib, "sha256", wrapped_sha256)

    args = _minimal_graph("sha1")
    args["objects"][0]["body_size_bytes"] = 100
    args["limits"]["max_object_bytes"] = 10
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_LIMIT_EXCEEDED, limit_name="max_object_bytes")
    assert hash_calls["n"] == 0

    args = _minimal_graph("sha1")
    oid = args["objects"][0]["oid"]
    args["bodies"][oid] = args["bodies"][oid] + b"extra-bytes"
    args["limits"]["max_object_bytes"] = max(1, args["objects"][0]["body_size_bytes"])
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_LIMIT_EXCEEDED, limit_name="max_object_bytes")
    assert hash_calls["n"] == 0
```

```python
def test_type_mismatch_omitted_object_and_unused_set() -> None:
    blob_rec, blob_body = _record("sha1", "blob", b"hello\n")
    tree_body = _tree_bytes("sha1", [("40000", b"src", blob_rec["oid"])])
    args = _minimal_graph(
        "sha1",
        tree_body=tree_body,
        extra_objects=[(blob_rec, blob_body)],
        targets=[{"path": "src/x", "allow_executable_source": False}],
    )
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(
        exc.value,
        CODE_PROOF_OBJECT_TYPE_MISMATCH,
        oid=blob_rec["oid"],
        expected_type="tree",
        actual_type="blob",
    )

    args = _minimal_graph(
        "sha1",
        tree_body=_tree_bytes("sha1", [("100644", b"file.py", blob_rec["oid"])]),
        targets=[{"path": "file.py", "allow_executable_source": False}],
    )
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(exc.value, CODE_PROOF_OBJECT_UNAVAILABLE, missing_oids=[blob_rec["oid"]])

    unused_tree, unused_body = _record("sha1", "tree", b"")
    args = _minimal_graph("sha1", extra_objects=[(unused_tree, unused_body)])
    with pytest.raises(CodeGitProofError) as exc:
        verify_code_git_objects(**args)
    _assert_error(
        exc.value,
        CODE_PROOF_CONSUMED_SET_MISMATCH,
        unused_oids=[unused_tree["oid"]],
    )
```

```python
def test_inputs_unchanged_outputs_unaliased_and_repeatable() -> None:
    fmt = FIXTURE["formats"]["sha1"]
    case = fmt["cases"]["all_safe"]
    records, bodies = _records_and_bodies(fmt, case["required_object_oids"])
    targets = copy.deepcopy(case["targets"])
    limits = _limits()
    snap_records = copy.deepcopy(records)
    snap_bodies = dict(bodies)
    snap_targets = copy.deepcopy(targets)
    snap_limits = dict(limits)
    first = verify_code_git_objects(
        object_format="sha1",
        commit_oid=fmt["commit_oid"],
        root_tree_oid=fmt["root_tree_oid"],
        objects=records,
        bodies=bodies,
        targets=targets,
        limits=limits,
    )
    second = verify_code_git_objects(
        object_format="sha1",
        commit_oid=fmt["commit_oid"],
        root_tree_oid=fmt["root_tree_oid"],
        objects=records,
        bodies=bodies,
        targets=targets,
        limits=limits,
    )
    assert first == second
    assert records == snap_records
    assert bodies == snap_bodies
    assert targets == snap_targets
    assert limits == snap_limits
    first["object_records"][0]["oid"] = "0" * 40
    first["targets"][0]["path"] = "mutated"
    assert records == snap_records
    assert first["object_records"] is not records
    assert first["targets"] is not targets
    encoded = json.dumps(first)
    assert "\\u0000" not in encoded or True
    def _walk(value: object) -> None:
        assert type(value) is not bytes
        if type(value) is dict:
            for inner in value.values():
                _walk(inner)
        elif type(value) is list:
            for inner in value:
                _walk(inner)
    _walk(second)
```
