"""Parser-free replay check for the R4 CONFIG oracle correction.

This checks the immutable R3 baseline, the two allowed R4 field corrections,
all retained source annotation hashes, and the R4 provenance contract. It does
not import production code or run a parser.
"""
from __future__ import annotations
import bisect, copy, hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
DIR = ROOT / "artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/config-r1"
R3 = DIR / "static-vectors-r3.json"
R4 = DIR / "static-vectors-r4.json"

R3_SHA = "fed1611965d5745439983c1b96789051f0b012a45432d1281869a73fe954402e"
assert hashlib.sha256(R3.read_bytes()).hexdigest() == R3_SHA
r3 = json.loads(R3.read_text(encoding="utf-8"))
r4 = json.loads(R4.read_text(encoding="utf-8"))
assert r4["$schema"] == "video-paper-wiki.code-config-kernel-fixture-r4.v1"
assert r4["revision"] == 4
assert r4["r3_immutable_source"] == {
    "path": str(R3.relative_to(ROOT)), "sha256": R3_SHA, "size_bytes": R3.stat().st_size,
    "preserved_fields": ["all R3 content except the two explicitly corrected expected fields and R4 provenance metadata"],
}

# Strip only R4 metadata and the two named field corrections; every remaining
# parsed R3 datum must be byte/structure equal.
def baseline_shape(data):
    data = copy.deepcopy(data)
    for key in ("$schema", "revision", "status", "r3_immutable_source", "r4_oracle_contract"):
        data.pop(key, None)
    vectors = {v["id"]: v for v in data["refusal_vectors"]}
    vectors["json-tuple-exponent-over"]["expected"]["reason_description"] = "__R4_TUPLE_REASON__"
    vectors["json-tuple-exponent-over"]["expected"]["limit_context"] = {"limit_name":"__R4_TUPLE_LIMIT__","limit":0,"observed":0}
    vectors["toml-duplicate-header"]["expected"]["source_anchor_span"] = {"__R4_DUP_SPAN__": True}
    return data

assert baseline_shape(r3) == baseline_shape(r4)

# Exact tuple correction.
tuple_expected = {v["id"]: v for v in r4["refusal_vectors"]}["json-tuple-exponent-over"]["expected"]
assert tuple_expected["limit_context"] == {"limit_name":"max_numeric_lexeme_bytes","limit":128,"observed":131}
assert tuple_expected["reason_description"] == "numeric lexeme exceeds profile before exact Decimal tuple exponent analysis"
assert tuple_expected["code"] == "CODE_CONFIG_LIMIT_EXCEEDED"

# Exact second-header correction and independent coordinate/hash calculation.
dup = {v["id"]: v for v in r4["refusal_vectors"]}["toml-duplicate-header"]
source = dup["source_utf8"]
assert source == "[a]\nx = 1\n[a]\ny = 2\n"
span = dup["expected"]["source_anchor_span"]
assert source[span["codepoint_start"]:span["codepoint_end"]] == "[a]"
assert span == {"byte_start":10,"byte_end":13,"codepoint_start":10,"codepoint_end":13,"line_start":3,"column_start":1,"line_end":3,"column_end":4,"raw_sha256":"32332ffee853ef6d87d16e1dbc55f72288c4fa960b2c44ee80d34b9993e0f7aa","snippet_sha256":"32332ffee853ef6d87d16e1dbc55f72288c4fa960b2c44ee80d34b9993e0f7aa"}

# Recheck every retained source annotation against its source slice and the
# CRLF-normalized snippet convention.
def snippet_sha(source, line_start, line_end):
    raw = source.replace("\r\n", "\n").encode("utf-8")
    lines = raw.splitlines(keepends=True)
    selected = b"".join(lines[line_start-1:line_end])
    if selected.endswith(b"\n"):
        selected = selected[:-1]
    return hashlib.sha256(selected).hexdigest()

def check_span(source, span):
    a, b = span["codepoint_start"], span["codepoint_end"]
    assert 0 <= a < b <= len(source)
    raw = source[a:b].encode("utf-8")
    assert (span["byte_start"], span["byte_end"]) == (len(source[:a].encode()), len(source[:b].encode()))
    starts = [0]
    for i, ch in enumerate(source):
        if ch == "\n": starts.append(i + 1)
    def lc(offset):
        line = bisect.bisect_right(starts, offset)
        return line, offset - starts[line-1] + 1
    assert (span["line_start"], span["column_start"]) == lc(a)
    assert (span["line_end"], span["column_end"]) == lc(b)
    assert hashlib.sha256(raw).hexdigest() == span["raw_sha256"]
    assert snippet_sha(source, span["line_start"], span["line_end"]) == span["snippet_sha256"]

source_spans = 0
for vector in r4["refusal_vectors"]:
    expected = vector["expected"]
    if "source_anchor_span" in expected:
        check_span(vector["source_utf8"], expected["source_anchor_span"])
        source_spans += 1
assert source_spans == 25
assert r4["r4_oracle_contract"]["all_other_r3_content_unchanged"] is True

print(json.dumps({
    "runtime": sys.version.split()[0],
    "result": "PASS_R4_CONFIG_ORACLE_CORRECTION_REPLAY",
    "r3_sha256": R3_SHA,
    "r4_sha256": hashlib.sha256(R4.read_bytes()).hexdigest(),
    "r4_size_bytes": R4.stat().st_size,
    "allowed_corrections": 2,
    "retained_source_annotations_checked": source_spans,
    "production_imported": False,
    "network_or_provider": False,
}, sort_keys=True))
