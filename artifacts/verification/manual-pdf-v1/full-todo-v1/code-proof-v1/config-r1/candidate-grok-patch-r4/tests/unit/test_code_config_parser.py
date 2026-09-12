"""Focused tests for the CODE configuration parser kernel."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import urllib.request
from contextlib import ExitStack
from decimal import ROUND_DOWN, Decimal, getcontext, localcontext
from pathlib import Path
from types import MappingProxyType
from unittest import TestCase, main
from unittest.mock import patch

from video_paper_wiki.code_config_parser import (
    CODE_CONFIG_PROFILE_LIMITS,
    CodeConfigError,
    parse_code_config_bytes,
)
from video_paper_wiki.code_evidence_contracts import (
    code_snippet_sha256,
    code_text_metadata,
)

FIXTURE_PATH = (
    Path(__file__).parents[1] / "fixtures" / "code-config-vectors-v1.json"
)
_LIMIT_ORDER = (
    "max_source_bytes",
    "max_depth",
    "max_nodes",
    "max_array_items",
    "max_object_keys",
    "max_key_bytes",
    "max_string_codepoints",
    "max_scalars",
    "max_numeric_lexeme_bytes",
    "max_numeric_coefficient_digits",
    "max_numeric_abs_exponent",
    "max_numeric_canonical_bytes",
    "max_declarations",
)


def _fresh_limits(**overrides: int) -> dict[str, int]:
    values = dict(CODE_CONFIG_PROFILE_LIMITS)
    values.update(overrides)
    return values


def _budget_from_nodes(nodes: list) -> dict:
    node_count = len(nodes)
    scalar_count = 0
    max_depth = 0
    decl_count = 0
    max_arr = 0
    max_obj = 0
    for node in nodes:
        if node["kind"] != "object" and node["kind"] != "array":
            scalar_count += 1
        depth = 0
        path = node["path"]
        for char in path:
            if char == "/":
                depth += 1
        if depth > max_depth:
            max_depth = depth
        decl_count += len(node["declarations"])
        if node["kind"] == "array":
            count = len(node["children"])
            if count > max_arr:
                max_arr = count
        elif node["kind"] == "object":
            count = len(node["children"])
            if count > max_obj:
                max_obj = count
    return {
        "node_count": node_count,
        "scalar_count": scalar_count,
        "max_depth_observed": max_depth,
        "declaration_count": decl_count,
        "max_array_items_observed": max_arr,
        "max_object_keys_observed": max_obj,
    }


def _span_lines(span: dict, line_count: int) -> tuple[int, int]:
    start = span["line_start"]
    end = span["line_end"]
    if span["column_end"] == 1 and end > start:
        end -= 1
    if end > line_count:
        end = line_count
    if end < start:
        end = start
    return start, end


def _assert_json_compatible(test: TestCase, value: object) -> None:
    kind = type(value)
    if kind is dict:
        for key, inner in value.items():
            test.assertIs(type(key), str)
            _assert_json_compatible(test, inner)
        return
    if kind is list:
        for inner in value:
            _assert_json_compatible(test, inner)
        return
    test.assertIn(kind, (str, int, bool, type(None)))


def _unescape_segment(segment: str) -> str:
    return segment.replace("~1", "/").replace("~0", "~")


def _semantic_from_nodes(nodes: list):
    by_path = {node["path"]: node for node in nodes}

    def build(path: str):
        node = by_path[path]
        kind = node["kind"]
        if kind == "object":
            out = {}
            for child_path in node["children"]:
                segment = child_path[len(path) :]
                if segment.startswith("/"):
                    segment = segment[1:]
                out[_unescape_segment(segment)] = build(child_path)
            return out
        if kind == "array":
            return [build(child_path) for child_path in node["children"]]
        if kind == "integer":
            return int(node["value"], 10)
        if kind == "decimal":
            return Decimal(node["value"])
        if kind == "boolean":
            return node["value"]
        if kind == "string":
            return node["value"]
        return None

    return build("")


def _pointer_last_key(parent: str, child: str) -> str:
    segment = child[len(parent) :]
    if segment.startswith("/"):
        segment = segment[1:]
    return _unescape_segment(segment)


class TestCodeConfigParser(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = FIXTURE_PATH.read_text(encoding="utf-8")
        cls.fixture = json.loads(raw)
        cls.success = list(cls.fixture["success_vectors"])
        cls.refusals = list(cls.fixture["refusal_vectors"])
        groups = cls.fixture["supplementary_groups"]
        cls.matrix = list(
            groups["toml_transition_matrix_r2"]["content"]["cases"]
        )
        cls.dynamic = list(
            groups["dynamic_offset_vectors_r2"]["content"]["vectors"]
        )

    def _parse(self, payload: bytes, fmt: str, limits: dict | None = None):
        if limits is None:
            limits = _fresh_limits()
        return parse_code_config_bytes(
            payload=payload, config_format=fmt, limits=limits
        )

    def _assert_span_parity(self, payload: bytes, span: dict, line_count: int) -> None:
        raw = hashlib.sha256(
            payload[span["byte_start"] : span["byte_end"]]
        ).hexdigest()
        self.assertEqual(span["raw_sha256"], raw)
        start, end = _span_lines(span, line_count)
        self.assertEqual(
            span["snippet_sha256"],
            code_snippet_sha256(payload, start, end),
        )

    def test_profile_limits_constant(self) -> None:
        self.assertEqual(list(CODE_CONFIG_PROFILE_LIMITS.keys()), list(_LIMIT_ORDER))
        self.assertEqual(
            dict(CODE_CONFIG_PROFILE_LIMITS),
            self.fixture["profile_limits"],
        )
        with self.assertRaises(TypeError):
            CODE_CONFIG_PROFILE_LIMITS["max_depth"] = 1
        copied = dict(CODE_CONFIG_PROFILE_LIMITS)
        copied["max_depth"] = 1
        self.assertEqual(CODE_CONFIG_PROFILE_LIMITS["max_depth"], 32)

    def test_success_vectors(self) -> None:
        self.assertGreaterEqual(len(self.success), 1)
        for vector in self.success:
            with self.subTest(vector["id"]):
                payload = vector["source_utf8"].encode("utf-8")
                result = self._parse(payload, vector["format"])
                self.assertEqual(
                    list(result.keys()),
                    ["config_format", "source", "budget", "nodes"],
                )
                self.assertEqual(result["config_format"], vector["format"])
                self.assertEqual(result["source"], vector["source"])
                self.assertEqual(result["nodes"], vector["expected_nodes"])
                self.assertEqual(
                    result["budget"],
                    _budget_from_nodes(vector["expected_nodes"]),
                )
                meta = code_text_metadata(payload)
                self.assertEqual(
                    result["source"]["newline_style"], meta["newline_style"]
                )
                self.assertEqual(
                    result["source"]["ends_with_newline"],
                    meta["ends_with_newline"],
                )
                self.assertEqual(
                    result["source"]["line_count"], meta["line_count"]
                )
                self.assertEqual(
                    result["source"]["normalized_sha256"],
                    meta["normalized_sha256"],
                )
                self.assertEqual(
                    result["source"]["body_size_bytes"], len(payload)
                )
                self.assertEqual(
                    result["source"]["body_sha256"],
                    hashlib.sha256(payload).hexdigest(),
                )
                _assert_json_compatible(self, result)
                line_count = result["source"]["line_count"]
                for node in result["nodes"]:
                    if node["value_span"] is not None:
                        self._assert_span_parity(
                            payload, node["value_span"], line_count
                        )
                    for decl in node["declarations"]:
                        self._assert_span_parity(
                            payload, decl["span"], line_count
                        )

    def test_refusal_vectors(self) -> None:
        self.assertGreaterEqual(len(self.refusals), 1)
        for vector in self.refusals:
            with self.subTest(vector["id"]):
                payload = vector["source_utf8"].encode("utf-8")
                expected = vector["expected"]
                limits = _fresh_limits()
                context = expected.get("limit_context")
                if context is not None:
                    name = context["limit_name"]
                    if context["limit"] != CODE_CONFIG_PROFILE_LIMITS[name]:
                        limits[name] = context["limit"]
                with self.assertRaises(CodeConfigError) as caught:
                    self._parse(payload, vector["format"], limits)
                err = caught.exception
                self.assertIsInstance(err, ValueError)
                self.assertEqual(err.exit_code, 2)
                self.assertEqual(err.code, expected["code"])
                if expected["code"] == "CODE_CONFIG_DYNAMIC_UNSUPPORTED":
                    if vector["id"] == "toml-dynamic-interpolation":
                        self.assertEqual(err.details["reason"], "dynamic_marker")
                    elif vector["id"] == "toml-dynamic-callable":
                        self.assertEqual(
                            err.details["reason"], "callable_string"
                        )
                    else:
                        self.assertIn(
                            err.details["reason"],
                            ("dynamic_key", "dynamic_marker", "callable_string"),
                        )
                elif "reason" in expected:
                    self.assertEqual(err.details["reason"], expected["reason"])
                if context is not None:
                    self.assertEqual(
                        err.details["limit_name"], context["limit_name"]
                    )
                    self.assertEqual(err.details["limit"], context["limit"])
                    self.assertEqual(
                        err.details["observed"], context["observed"]
                    )
                if "anchor_span" in expected and expected["code"] != (
                    "CODE_CONFIG_LIMIT_EXCEEDED"
                ):
                    self.assertEqual(
                        err.details["byte_offset"],
                        expected["anchor_span"]["byte_start"],
                    )
                    self.assertEqual(
                        err.details["codepoint_offset"],
                        expected["anchor_span"]["codepoint_start"],
                    )
                self.assertNotIn("anchor_lexeme", err.details)
                self.assertIn("instance_pointer", err.details)

    def test_toml_transition_matrix(self) -> None:
        self.assertEqual(len(self.matrix), 26)
        for case in self.matrix:
            with self.subTest(case["id"]):
                payload = case["source"].encode("utf-8")
                expected = case["expected"]
                if expected["accepted"]:
                    result = self._parse(payload, "toml")
                    self.assertEqual(
                        _semantic_from_nodes(result["nodes"]),
                        expected["semantic_value"],
                    )
                else:
                    with self.assertRaises(CodeConfigError) as caught:
                        self._parse(payload, "toml")
                    self.assertEqual(
                        caught.exception.code, expected["error_code"]
                    )

    def test_dynamic_offset_vectors(self) -> None:
        self.assertEqual(len(self.dynamic), 9)
        for vector in self.dynamic:
            with self.subTest(vector["id"]):
                payload = vector["source"].encode("utf-8")
                expected = vector["expected"]
                if expected.get("accepted"):
                    result = self._parse(payload, vector["format"])
                    self.assertEqual(result["config_format"], vector["format"])
                    continue
                with self.assertRaises(CodeConfigError) as caught:
                    self._parse(payload, vector["format"])
                err = caught.exception
                self.assertEqual(err.code, expected["code"])
                self.assertEqual(
                    err.details["instance_pointer"],
                    expected["instance_pointer"],
                )
                self.assertEqual(err.details["byte_offset"], expected["byte_offset"])
                self.assertEqual(
                    err.details["codepoint_offset"],
                    expected["codepoint_offset"],
                )
                self.assertEqual(err.details["reason"], expected["reason"])

    def test_limits_type_and_callback_traps(self) -> None:
        payload = b"1"

        class TrapStr(str):
            def __eq__(self, other):
                raise AssertionError("eq callback")

            def __hash__(self):
                return super().__hash__()

            def __str__(self):
                raise AssertionError("str callback")

            def __format__(self, spec):
                raise AssertionError("format callback")

        class TrapInt(int):
            def __eq__(self, other):
                raise AssertionError("eq callback")

            def __bool__(self):
                raise AssertionError("bool callback")

            def __format__(self, spec):
                raise AssertionError("format callback")

        class SubDict(dict):
            pass

        with self.assertRaises(CodeConfigError) as caught:
            self._parse(payload, "json", SubDict(dict(CODE_CONFIG_PROFILE_LIMITS)))
        self.assertEqual(caught.exception.code, "CODE_CONFIG_INPUT_INVALID")
        self.assertEqual(caught.exception.details["instance_pointer"], "/limits")

        with self.assertRaises(CodeConfigError) as caught:
            self._parse(payload, "json", list(_LIMIT_ORDER))
        self.assertEqual(caught.exception.code, "CODE_CONFIG_INPUT_INVALID")

        with self.assertRaises(CodeConfigError) as caught:
            self._parse(payload, "json", MappingProxyType(dict(CODE_CONFIG_PROFILE_LIMITS)))
        self.assertEqual(caught.exception.code, "CODE_CONFIG_INPUT_INVALID")

        short = dict(CODE_CONFIG_PROFILE_LIMITS)
        short.pop("max_depth")
        with self.assertRaises(CodeConfigError) as caught:
            self._parse(payload, "json", short)
        self.assertEqual(caught.exception.code, "CODE_CONFIG_INPUT_INVALID")

        extra = dict(CODE_CONFIG_PROFILE_LIMITS)
        extra["bonus"] = 1
        with self.assertRaises(CodeConfigError) as caught:
            self._parse(payload, "json", extra)
        self.assertEqual(caught.exception.code, "CODE_CONFIG_INPUT_INVALID")

        swapped = {}
        for name, value in CODE_CONFIG_PROFILE_LIMITS.items():
            swapped[name if name != "max_depth" else "max_deep"] = value
        with self.assertRaises(CodeConfigError) as caught:
            self._parse(payload, "json", swapped)
        self.assertEqual(caught.exception.code, "CODE_CONFIG_INPUT_INVALID")

        evil_keys = {}
        for name, value in CODE_CONFIG_PROFILE_LIMITS.items():
            evil_keys[TrapStr(name)] = value
        with self.assertRaises(CodeConfigError) as caught:
            self._parse(payload, "json", evil_keys)
        self.assertEqual(caught.exception.code, "CODE_CONFIG_INPUT_INVALID")

        evil_value = dict(CODE_CONFIG_PROFILE_LIMITS)
        evil_value["max_depth"] = TrapInt(1)
        with self.assertRaises(CodeConfigError) as caught:
            self._parse(payload, "json", evil_value)
        self.assertEqual(caught.exception.code, "CODE_CONFIG_INPUT_INVALID")
        self.assertEqual(
            caught.exception.details["instance_pointer"], "/limits/max_depth"
        )

        as_bool = dict(CODE_CONFIG_PROFILE_LIMITS)
        as_bool["max_depth"] = True
        with self.assertRaises(CodeConfigError) as caught:
            self._parse(payload, "json", as_bool)
        self.assertEqual(caught.exception.code, "CODE_CONFIG_INPUT_INVALID")

        zero = dict(CODE_CONFIG_PROFILE_LIMITS)
        zero["max_nodes"] = 0
        with self.assertRaises(CodeConfigError) as caught:
            self._parse(payload, "json", zero)
        self.assertEqual(caught.exception.code, "CODE_CONFIG_INPUT_INVALID")

        too_high = dict(CODE_CONFIG_PROFILE_LIMITS)
        too_high["max_depth"] = 33
        with self.assertRaises(CodeConfigError) as caught:
            self._parse(payload, "json", too_high)
        self.assertEqual(caught.exception.code, "CODE_CONFIG_INPUT_INVALID")

        class Payload(bytes):
            pass

        with self.assertRaises(CodeConfigError) as caught:
            parse_code_config_bytes(
                payload=Payload(b"1"),
                config_format="json",
                limits=_fresh_limits(),
            )
        self.assertEqual(caught.exception.code, "CODE_CONFIG_INPUT_INVALID")
        self.assertEqual(caught.exception.details["instance_pointer"], "/payload")

        class Format(str):
            pass

        with self.assertRaises(CodeConfigError) as caught:
            parse_code_config_bytes(
                payload=b"1",
                config_format=Format("json"),
                limits=_fresh_limits(),
            )
        self.assertEqual(caught.exception.code, "CODE_CONFIG_INPUT_INVALID")
        self.assertEqual(
            caught.exception.details["instance_pointer"], "/config_format"
        )

        with self.assertRaises(CodeConfigError) as caught:
            self._parse(payload, "JSON")
        self.assertEqual(caught.exception.code, "CODE_CONFIG_INPUT_INVALID")

        with self.assertRaises(TypeError):
            parse_code_config_bytes(b"1", "json", _fresh_limits())

    def test_every_limit_boundary_and_lowered(self) -> None:
        cases = [
            (
                "max_source_bytes",
                b"1",
                "json",
                1,
                b"12",
                2,
            ),
            (
                "max_depth",
                b'{"a":1}',
                "json",
                1,
                b'{"a":{"b":1}}',
                2,
            ),
            (
                "max_nodes",
                b"1",
                "json",
                1,
                b'{"a":1}',
                2,
            ),
            (
                "max_array_items",
                b"[1]",
                "json",
                1,
                b"[1,2]",
                2,
            ),
            (
                "max_object_keys",
                b'{"a":1}',
                "json",
                1,
                b'{"a":1,"b":2}',
                2,
            ),
            (
                "max_key_bytes",
                b'{"a":1}',
                "json",
                1,
                b'{"ab":1}',
                2,
            ),
            (
                "max_string_codepoints",
                b'"a"',
                "json",
                1,
                b'"ab"',
                2,
            ),
            (
                "max_scalars",
                b"1",
                "json",
                1,
                b"[1,2]",
                2,
            ),
            (
                "max_numeric_lexeme_bytes",
                b"1",
                "json",
                1,
                b"12",
                2,
            ),
            (
                "max_numeric_coefficient_digits",
                b"1",
                "json",
                1,
                b"12",
                2,
            ),
            (
                "max_numeric_abs_exponent",
                b"1e1",
                "json",
                1,
                b"1e2",
                2,
            ),
            (
                "max_numeric_canonical_bytes",
                b"1",
                "json",
                1,
                b"12",
                2,
            ),
            (
                "max_declarations",
                b'{"a":1}',
                "json",
                1,
                b'{"a":1,"b":2}',
                2,
            ),
        ]
        self.assertEqual(len(cases), 13)
        for name, ok_payload, fmt, lowered, bad_payload, observed in cases:
            with self.subTest(name):
                ok_limits = _fresh_limits(**{name: lowered})
                result = self._parse(ok_payload, fmt, ok_limits)
                self.assertEqual(result["config_format"], fmt)
                bad_limits = _fresh_limits(**{name: lowered})
                with self.assertRaises(CodeConfigError) as caught:
                    self._parse(bad_payload, fmt, bad_limits)
                err = caught.exception
                self.assertEqual(err.code, "CODE_CONFIG_LIMIT_EXCEEDED")
                self.assertEqual(err.details["limit_name"], name)
                self.assertEqual(err.details["limit"], lowered)
                self.assertEqual(err.details["observed"], observed)

        prefixes = b"a.b=1\na.c=2\na.d=3\n"
        result = self._parse(prefixes, "toml", _fresh_limits(max_declarations=6))
        self.assertEqual(result["budget"]["declaration_count"], 6)
        with self.assertRaises(CodeConfigError) as caught:
            self._parse(prefixes, "toml", _fresh_limits(max_declarations=5))
        self.assertEqual(caught.exception.code, "CODE_CONFIG_LIMIT_EXCEEDED")
        self.assertEqual(
            caught.exception.details["limit_name"], "max_declarations"
        )
        self.assertEqual(caught.exception.details["observed"], 6)

    def test_source_cap_before_hash_and_decode(self) -> None:
        payload = b"\xff" * 10
        limits = _fresh_limits(max_source_bytes=5)

        def boom(*_args, **_kwargs):
            raise AssertionError("hash or decode before source cap")

        with patch(
            "video_paper_wiki.code_config_parser.hashlib.sha256", boom
        ):
            with self.assertRaises(CodeConfigError) as caught:
                self._parse(payload, "json", limits)
        self.assertEqual(caught.exception.code, "CODE_CONFIG_LIMIT_EXCEEDED")
        self.assertEqual(
            caught.exception.details["limit_name"], "max_source_bytes"
        )
        self.assertEqual(caught.exception.details["observed"], 10)

    def test_parser_mismatch_instrumentation(self) -> None:
        import video_paper_wiki.code_config_parser as mod

        def wrong_bool(_source, **_kwargs):
            return True

        with patch.object(mod.json, "loads", wrong_bool):
            with self.assertRaises(CodeConfigError) as caught:
                self._parse(b"1", "json")
            self.assertEqual(
                caught.exception.code, "CODE_CONFIG_PARSER_MISMATCH"
            )

        def missing_keys(_source, **_kwargs):
            return {}

        with patch.object(mod.json, "loads", missing_keys):
            with self.assertRaises(CodeConfigError) as caught:
                self._parse(b'{"a":1}', "json")
            self.assertEqual(
                caught.exception.code, "CODE_CONFIG_PARSER_MISMATCH"
            )

        def extra_keys(_source, **_kwargs):
            return {"a": 1, "b": 2}

        with patch.object(mod.json, "loads", extra_keys):
            with self.assertRaises(CodeConfigError) as caught:
                self._parse(b'{"a":1}', "json")
            self.assertEqual(
                caught.exception.code, "CODE_CONFIG_PARSER_MISMATCH"
            )

        def reordered(_source, **_kwargs):
            return [2, 1]

        with patch.object(mod.json, "loads", reordered):
            with self.assertRaises(CodeConfigError) as caught:
                self._parse(b"[1,2]", "json")
            self.assertEqual(
                caught.exception.code, "CODE_CONFIG_PARSER_MISMATCH"
            )

        def wrong_string(_source, **_kwargs):
            return {"a": "y"}

        with patch.object(mod.json, "loads", wrong_string):
            with self.assertRaises(CodeConfigError) as caught:
                self._parse(b'{"a":"x"}', "json")
            self.assertEqual(
                caught.exception.code, "CODE_CONFIG_PARSER_MISMATCH"
            )

        def unsupported(_source, **_kwargs):
            return object()

        with patch.object(mod.json, "loads", unsupported):
            with self.assertRaises(CodeConfigError) as caught:
                self._parse(b"1", "json")
            self.assertEqual(
                caught.exception.code, "CODE_CONFIG_PARSER_MISMATCH"
            )

        def toml_bool(_source, **_kwargs):
            return {"a": True}

        with patch.object(mod.tomllib, "loads", toml_bool):
            with self.assertRaises(CodeConfigError) as caught:
                self._parse(b"a=1\n", "toml")
            self.assertEqual(
                caught.exception.code, "CODE_CONFIG_PARSER_MISMATCH"
            )

        def toml_float(_source, **_kwargs):
            return {"a": 1.0}

        with patch.object(mod.tomllib, "loads", toml_float):
            with self.assertRaises(CodeConfigError) as caught:
                self._parse(b"a=1\n", "toml")
            self.assertEqual(
                caught.exception.code, "CODE_CONFIG_PARSER_MISMATCH"
            )

    def test_stdlib_object_keys_must_be_exact_str(self) -> None:
        import video_paper_wiki.code_config_parser as mod

        callbacks = []

        class OrdinaryKey(str):
            pass

        class HostileKey(str):
            pass

        def trap(self, *args, **kwargs):
            callbacks.append("trap")
            raise AssertionError("hostile stdlib object key")

        ordinary_root = {OrdinaryKey("a"): True}
        hostile_root = {HostileKey("a"): True}
        ordinary_nested = {"outer": {OrdinaryKey("a"): True}}
        hostile_nested = {"outer": {HostileKey("a"): True}}
        int_root = {1: True}
        int_nested = {"outer": {1: True}}

        HostileKey.__hash__ = trap
        HostileKey.__eq__ = trap
        HostileKey.__str__ = trap
        HostileKey.__repr__ = trap

        cases = (
            ("json-root-ordinary", "json", "json", b'{"a":true}', ordinary_root),
            ("json-root-hostile", "json", "json", b'{"a":true}', hostile_root),
            (
                "json-nested-ordinary",
                "json",
                "json",
                b'{"outer":{"a":true}}',
                ordinary_nested,
            ),
            (
                "json-nested-hostile",
                "json",
                "json",
                b'{"outer":{"a":true}}',
                hostile_nested,
            ),
            ("toml-root-ordinary", "toml", "tomllib", b"a = true\n", ordinary_root),
            ("toml-root-hostile", "toml", "tomllib", b"a = true\n", hostile_root),
            (
                "toml-nested-ordinary",
                "toml",
                "tomllib",
                b"[outer]\na = true\n",
                ordinary_nested,
            ),
            (
                "toml-nested-hostile",
                "toml",
                "tomllib",
                b"[outer]\na = true\n",
                hostile_nested,
            ),
            ("json-root-int", "json", "json", b'{"a":true}', int_root),
            ("json-nested-int", "json", "json", b'{"outer":{"a":true}}', int_nested),
            ("toml-root-int", "toml", "tomllib", b"a = true\n", int_root),
            ("toml-nested-int", "toml", "tomllib", b"[outer]\na = true\n", int_nested),
        )

        for label, fmt, loader_name, payload, crafted in cases:
            with self.subTest(label=label):
                loader = getattr(mod, loader_name)
                with patch.object(loader, "loads", return_value=crafted):
                    with self.assertRaises(CodeConfigError) as caught:
                        self._parse(payload, fmt)
                err = caught.exception
                self.assertEqual(err.exit_code, 2)
                self.assertEqual(err.code, mod.CODE_CONFIG_PARSER_MISMATCH)
                self.assertEqual(
                    set(err.details), {"instance_pointer", "reason"}
                )
                self.assertEqual(err.details["instance_pointer"], "/payload")
                reason = err.details["reason"]
                self.assertIsInstance(reason, str)
                self.assertTrue(reason)
                self.assertEqual(callbacks, [])
                self._parse(payload, fmt)
                self.assertEqual(callbacks, [])

    def test_scanner_error_content_omits_source_sentinels(self) -> None:
        import video_paper_wiki.code_config_parser as mod

        cases = (
            (
                "duplicate-key",
                b'{"zzDupKeyQ9":true,"zzDupKeyQ9":false}',
                mod.CODE_CONFIG_DUPLICATE_KEY,
                20,
                20,
                ("zzDupKeyQ9",),
                None,
            ),
            (
                "trailing-comma",
                b'{"zzSynTokW7":true,}',
                mod.CODE_CONFIG_SYNTAX_INVALID,
                19,
                19,
                ("zzSynTokW7",),
                None,
            ),
            (
                "dynamic-string",
                b'{"zzDynKeyM3":"pre${zzDynValN5}"}',
                mod.CODE_CONFIG_DYNAMIC_UNSUPPORTED,
                14,
                14,
                ("zzDynKeyM3", "zzDynValN5", "pre${zzDynValN5}"),
                "dynamic_marker",
            ),
            (
                "negative-zero",
                b'{"zzNumKeyP2":-0.0}',
                mod.CODE_CONFIG_NUMBER_INVALID,
                14,
                14,
                ("zzNumKeyP2", "-0.0"),
                None,
            ),
        )

        for (
            label,
            payload,
            code,
            byte_offset,
            codepoint_offset,
            forbidden,
            reason_token,
        ) in cases:
            with self.subTest(label=label):
                with self.assertRaises(CodeConfigError) as caught:
                    self._parse(payload, "json")
                err = caught.exception
                self.assertEqual(err.exit_code, 2)
                self.assertEqual(err.code, code)
                self.assertEqual(
                    set(err.details),
                    {
                        "instance_pointer",
                        "reason",
                        "byte_offset",
                        "codepoint_offset",
                    },
                )
                self.assertEqual(err.details["instance_pointer"], "/payload")
                reason = err.details["reason"]
                self.assertIsInstance(reason, str)
                self.assertTrue(reason)
                if reason_token is not None:
                    self.assertIn(reason_token, reason)
                self.assertIsInstance(err.details["byte_offset"], int)
                self.assertIsInstance(err.details["codepoint_offset"], int)
                self.assertEqual(err.details["byte_offset"], byte_offset)
                self.assertEqual(
                    err.details["codepoint_offset"], codepoint_offset
                )
                raw = payload.decode("utf-8")
                serialized = json.dumps(err.details)
                for haystack in (err.message, str(err), serialized):
                    self.assertNotIn(raw, haystack)
                    for token in forbidden:
                        self.assertNotIn(token, haystack)

    def test_hostile_decimal_context(self) -> None:
        before = getcontext().copy()
        payload = b"1e-4"
        with localcontext() as ctx:
            ctx.prec = 1
            ctx.rounding = ROUND_DOWN
            ctx.Emin = 0
            ctx.Emax = 1
            ctx.clamp = 1
            result = self._parse(payload, "json")
            node = result["nodes"][0]
            self.assertEqual(node["kind"], "decimal")
            self.assertEqual(node["value"], "0.0001")
            self.assertEqual(node["numeric_lexeme"], "1e-4")
        after = getcontext()
        self.assertEqual(after.prec, before.prec)
        self.assertEqual(after.Emin, before.Emin)
        self.assertEqual(after.Emax, before.Emax)
        self.assertEqual(after.rounding, before.rounding)

    def test_no_io_during_success_and_refusal(self) -> None:
        success = self.success[0]
        ok_payload = success["source_utf8"].encode("utf-8")
        ok_fmt = success["format"]
        bad_payload = b""
        refusal = self.refusals[0]
        refusal_payload = refusal["source_utf8"].encode("utf-8")
        refusal_fmt = refusal["format"]

        def boom(*_args, **_kwargs):
            raise AssertionError(
                "unexpected filesystem/network/subprocess operation"
            )

        with ExitStack() as stack:
            stack.enter_context(patch("builtins.open", boom))
            stack.enter_context(patch("os.open", boom))
            stack.enter_context(patch("socket.socket", boom))
            stack.enter_context(patch("subprocess.Popen", boom))
            stack.enter_context(patch("subprocess.run", boom))
            stack.enter_context(patch("subprocess.call", boom))
            stack.enter_context(patch("urllib.request.urlopen", boom))
            result = self._parse(ok_payload, ok_fmt)
            self.assertEqual(result["nodes"], success["expected_nodes"])
            with self.assertRaises(CodeConfigError):
                self._parse(bad_payload, "json")
            with self.assertRaises(CodeConfigError):
                self._parse(refusal_payload, refusal_fmt)

    def test_determinism_and_no_alias(self) -> None:
        vector = self.success[0]
        payload = vector["source_utf8"].encode("utf-8")
        limits = _fresh_limits()
        first = self._parse(payload, vector["format"], limits)
        second = self._parse(payload, vector["format"], limits)
        self.assertEqual(first, second)
        first["nodes"].clear()
        first["budget"]["node_count"] = -1
        third = self._parse(payload, vector["format"], limits)
        self.assertEqual(second, third)
        limits["max_depth"] = 1
        fourth = self._parse(payload, vector["format"], _fresh_limits())
        self.assertEqual(second, fourth)
        self.assertIsNot(second["nodes"], fourth["nodes"])
        self.assertEqual(second["nodes"][0]["children"], vector["expected_nodes"][0]["children"])

    def test_unicode_surrogates_crlf_and_empty(self) -> None:
        pair = '"\\uD834\\uDD1E"'
        result = self._parse(pair.encode("utf-8"), "json")
        self.assertEqual(result["nodes"][0]["kind"], "string")
        self.assertEqual(result["nodes"][0]["value"], "\U0001d11e")
        with self.assertRaises(CodeConfigError) as caught:
            self._parse(b'"\\uD800"', "json")
        self.assertEqual(caught.exception.code, "CODE_CONFIG_SYNTAX_INVALID")
        with self.assertRaises(CodeConfigError) as caught:
            self._parse("\u2028".encode("utf-8"), "json")
        self.assertEqual(caught.exception.code, "CODE_CONFIG_BYTES_INVALID")
        empty_obj = self._parse(b"{}", "json")
        self.assertEqual(empty_obj["nodes"][0]["kind"], "object")
        self.assertEqual(empty_obj["nodes"][0]["children"], [])
        empty_arr = self._parse(b"[]", "json")
        self.assertEqual(empty_arr["nodes"][0]["kind"], "array")
        empty_table = self._parse(b"[a]\n", "toml")
        self.assertEqual(empty_table["nodes"][0]["children"], ["/a"])
        self.assertIsNone(empty_table["nodes"][1]["value_span"])
        crlf = self._parse(b"{\r\n}\r\n", "json")
        self.assertEqual(crlf["source"]["newline_style"], "crlf")
        mixed = self._parse(b"{\n}\r\n", "json")
        self.assertEqual(mixed["source"]["newline_style"], "mixed")
        result = self._parse(b'{"a":1,"b":1}', "json")
        self.assertEqual(result["nodes"][0]["children"], ["/a", "/b"])
        reversed_keys = self._parse(b'{"b":1,"a":1}', "json")
        self.assertEqual(reversed_keys["nodes"][0]["children"], ["/a", "/b"])
        self.assertEqual(reversed_keys["nodes"], result["nodes"])

    def test_dynamic_keys_markers_and_near_matches(self) -> None:
        for key in ("_target_", "include", "includes", "import"):
            payload = json.dumps({key: 1}).encode("utf-8")
            with self.assertRaises(CodeConfigError) as caught:
                self._parse(payload, "json")
            self.assertEqual(
                caught.exception.code, "CODE_CONFIG_DYNAMIC_UNSUPPORTED"
            )
            self.assertEqual(caught.exception.details["reason"], "dynamic_key")
        for marker, source in (
            ("${", b'{"x":"${a}"}'),
            ("$(", b'{"x":"$(a)"}'),
            ("{{", b'{"x":"{{a}}"}'),
            ("}}", b'{"x":"keep}}"}'),
            ("%(", b'{"x":"%(a)s"}'),
        ):
            with self.subTest(marker):
                with self.assertRaises(CodeConfigError) as caught:
                    self._parse(source, "json")
                self.assertEqual(
                    caught.exception.code, "CODE_CONFIG_DYNAMIC_UNSUPPORTED"
                )
                self.assertEqual(
                    caught.exception.details["reason"], "dynamic_marker"
                )
        with self.assertRaises(CodeConfigError) as caught:
            self._parse(b'{"x":"call(arg)"}', "json")
        self.assertEqual(
            caught.exception.code, "CODE_CONFIG_DYNAMIC_UNSUPPORTED"
        )
        self.assertEqual(caught.exception.details["reason"], "callable_string")
        near = self._parse(
            b'{"x":"cost $5","y":"factory(arg) tail"}', "json"
        )
        self.assertEqual(len(near["nodes"]), 3)
        comments = self._parse(b'# include = "${x}"\nx=1\n', "toml")
        self.assertEqual(comments["nodes"][1]["kind"], "integer")

    def test_closed_inline_and_key_order(self) -> None:
        with self.assertRaises(CodeConfigError) as caught:
            self._parse(b"a={b=1}\na.c=2\n", "toml")
        self.assertEqual(caught.exception.code, "CODE_CONFIG_DUPLICATE_KEY")
        with self.assertRaises(CodeConfigError) as caught:
            self._parse(b"a={b={c=1},b.d=2}\n", "toml")
        self.assertEqual(caught.exception.code, "CODE_CONFIG_DUPLICATE_KEY")
        nested = self._parse(b"a={b.c=1,b.d=2}\n", "toml")
        self.assertEqual(
            _semantic_from_nodes(nested["nodes"]),
            {"a": {"b": {"c": 1, "d": 2}}},
        )
        mixed = self._parse(b"arr=[1,true]\n", "toml")
        self.assertEqual(mixed["nodes"][1]["kind"], "array")
        self.assertEqual(mixed["nodes"][2]["kind"], "integer")
        self.assertEqual(mixed["nodes"][3]["kind"], "boolean")
