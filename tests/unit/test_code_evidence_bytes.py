from __future__ import annotations

import hashlib

import pytest

from video_paper_wiki.code_evidence_contracts import (
    code_snippet_sha256, code_text_metadata, normalize_code_bytes,
)
from video_paper_wiki.contracts import ContractError


@pytest.mark.parametrize("raw,normalized,style,count,ends", [
    (b"", b"", "none", 0, False), (b"a", b"a", "none", 1, False),
    (b"\n", b"\n", "lf", 1, True), (b"a\n\n", b"a\n\n", "lf", 2, True),
    (b"a\r\nb\r\n", b"a\nb\n", "crlf", 2, True),
    (b"a\r\nb\n", b"a\nb\n", "mixed", 2, True),
    (b"a\n\r\nb", b"a\n\nb", "mixed", 3, False),
    ("Ａ\t e\u0301\ufeffZ".encode(), "Ａ\t e\u0301\ufeffZ".encode(), "none", 1, False),
])
def test_exact_line_canonicalization(raw, normalized, style, count, ends):
    assert normalize_code_bytes(raw) == normalized
    assert code_text_metadata(raw) == {
        "newline_style": style, "ends_with_newline": ends, "line_count": count,
        "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
    }


@pytest.mark.parametrize("raw", [
    b"\xff", b"\xc0\xaf", b"\xed\xa0\x80", b"\xef\xbb\xbftext", b"\r", b"a\rb", b"\r\r\n",
    *[bytes([value]) for value in [0, 1, 8, 11, 12, 14, 31, 127]],
    *[chr(value).encode() for value in [128, 159, 0x2028, 0x2029]],
])
def test_forbidden_code_text(raw):
    with pytest.raises(ContractError) as exc:
        normalize_code_bytes(raw)
    assert exc.value.code == "CODE_TEXT_INVALID"
    assert exc.value.details == {"instance_pointer": ""}


@pytest.mark.parametrize("value", ["text", bytearray(b"a"), memoryview(b"a"), 1, None])
@pytest.mark.parametrize("function", [normalize_code_bytes, code_text_metadata])
def test_byte_api_types(value, function):
    with pytest.raises(ContractError) as exc:
        function(value)
    assert exc.value.code == "SCHEMA_INVALID"


@pytest.mark.parametrize("raw,start,end,digest", [
    (b"a", 1, 1, "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"),
    (b"a\n", 1, 1, "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"),
    (b"\n", 1, 1, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    (b"a\n\n", 1, 2, "87428fc522803d31065e7bce3cf03fe475096631e5e07bbd7a0fde60c4cf25c7"),
    (b"before\r\na\r\nafter\n", 2, 2, "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"),
])
def test_known_snippet_hash_vectors(raw, start, end, digest):
    assert code_snippet_sha256(raw, start, end) == digest


@pytest.mark.parametrize("raw,start,end", [
    (b"", 1, 1), (b"a", 0, 1), (b"a", True, 1), (b"a", 1.0, 1),
    (b"a", 1, 2), (b"a\nb", 2, 1), (b"a", 1, False), (b"a", 1, "1"),
])
def test_snippet_range_errors(raw, start, end):
    with pytest.raises(ContractError) as exc:
        code_snippet_sha256(raw, start, end)
    assert exc.value.code == "CODE_LINE_RANGE_INVALID"
    assert exc.value.details["instance_pointer"] == "/lines"


def test_size_limit_precedes_utf8_decoding():
    with pytest.raises(ContractError) as exc:
        normalize_code_bytes(b"\xff" * (67108864 + 1))
    assert exc.value.code == "PAYLOAD_MISMATCH"


def test_many_empty_lines_do_not_change_count_or_snippet_rules():
    raw = b"\n" * 100000
    assert code_text_metadata(raw)["line_count"] == 100000
    assert code_snippet_sha256(raw, 1, 100000) == hashlib.sha256(raw[:-1]).hexdigest()
    assert code_snippet_sha256(raw, 100000, 100000) == hashlib.sha256(b"").hexdigest()
