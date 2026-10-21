"""Bounded JSON/TOML configuration parser for CODE typed config."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from decimal import Decimal
from types import MappingProxyType

__all__ = [
    "CODE_CONFIG_PROFILE_LIMITS",
    "CodeConfigError",
    "parse_code_config_bytes",
]

_LIMIT_MAX_ITEMS = (
    ("max_source_bytes", 262144),
    ("max_depth", 32),
    ("max_nodes", 1024),
    ("max_array_items", 256),
    ("max_object_keys", 1024),
    ("max_key_bytes", 256),
    ("max_string_codepoints", 16384),
    ("max_scalars", 512),
    ("max_numeric_lexeme_bytes", 128),
    ("max_numeric_coefficient_digits", 64),
    ("max_numeric_abs_exponent", 128),
    ("max_numeric_canonical_bytes", 256),
    ("max_declarations", 4096),
)
_LIMIT_KEYS = tuple(item[0] for item in _LIMIT_MAX_ITEMS)
CODE_CONFIG_PROFILE_LIMITS = MappingProxyType(
    {name: value for name, value in _LIMIT_MAX_ITEMS}
)

_MESSAGES = {
    "CODE_CONFIG_INPUT_INVALID": "configuration input is invalid",
    "CODE_CONFIG_BYTES_INVALID": "configuration bytes are invalid",
    "CODE_CONFIG_EMPTY": "configuration document is empty",
    "CODE_CONFIG_SYNTAX_INVALID": "configuration syntax is invalid",
    "CODE_CONFIG_UNSUPPORTED": "configuration construct is unsupported",
    "CODE_CONFIG_DUPLICATE_KEY": "configuration key is duplicated",
    "CODE_CONFIG_LIMIT_EXCEEDED": "configuration profile limit is exceeded",
    "CODE_CONFIG_NUMBER_INVALID": "configuration number is invalid",
    "CODE_CONFIG_DYNAMIC_UNSUPPORTED": "configuration dynamic construct is unsupported",
    "CODE_CONFIG_PARSER_MISMATCH": "configuration parsers disagree",
}

_FORBIDDEN_SOURCE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u2028\u2029]"
)
_CALLABLE_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_.]*\s*\(.*\)",
    re.DOTALL,
)
_MARKERS = ("${", "$(", "{{", "}}", "%(")
_DYNAMIC_KEYS = frozenset(("_target_", "include", "includes", "import"))
_JSON_NUM_RE = re.compile(
    r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
)
_JSON_NUMLIKE_RE = re.compile(
    r"-?(?:[0-9_]+(?:\.[0-9_]*)?|\.[0-9_]+)(?:[eE][+-]?[0-9_]+)?"
)
_TOML_I = r"(?:0|[1-9](?:_?[0-9])*)"
_TOML_D = r"(?:[0-9](?:_?[0-9])*)"
_TOML_FLOAT_RE = re.compile(
    r"[+-]?"
    + _TOML_I
    + r"(?:\."
    + _TOML_D
    + r"(?:[eE][+-]?"
    + _TOML_D
    + r")?|[eE][+-]?"
    + _TOML_D
    + r")"
)
_TOML_INT_RE = re.compile(r"[+-]?" + _TOML_I)
_TOML_NUMLIKE_RE = re.compile(
    r"[+-]?[0-9_]+(?:\.[0-9_]+)?(?:[eE][+-]?[0-9_]+)?"
)
_TOML_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TOML_TIME_RE = re.compile(r"\d{2}:\d{2}")
_TOML_BASE_RE = re.compile(r"[+-]?0[xXoObB][0-9A-Fa-f_]*")
_TOML_NONFINITE_RE = re.compile(r"[+-]?(?:inf|nan)")
_BARE_KEY_RE = re.compile(r"[A-Za-z0-9_-]+")
_JSON_ESC = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}
_TOML_ESC = {
    "b": "\b",
    "t": "\t",
    "n": "\n",
    "f": "\f",
    "r": "\r",
    '"': '"',
    "\\": "\\",
}


class CodeConfigError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict,
        exit_code: int = 2,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details)
        self.exit_code = exit_code


class _Node:
    __slots__ = (
        "path",
        "kind",
        "value",
        "numeric_lexeme",
        "value_span",
        "declarations",
        "members",
        "elements",
        "state",
        "depth",
        "closed",
        "sign",
        "coeff",
        "tuple_exp",
        "_decl_sigs",
    )

    def __init__(self, path: str, kind: str, depth: int) -> None:
        self.path = path
        self.kind = kind
        self.value = None
        self.numeric_lexeme = None
        self.value_span = None
        self.declarations: list[dict] = []
        self.members: dict[str, _Node] | None = None
        self.elements: list[_Node] | None = None
        self.state: str | None = None
        self.depth = depth
        self.closed = False
        self.sign = 0
        self.coeff = "0"
        self.tuple_exp = 0
        self._decl_sigs: set[tuple] = set()


def _raise(
    code: str,
    *,
    instance_pointer: str,
    reason: str | None = None,
    byte_offset: int | None = None,
    codepoint_offset: int | None = None,
    limit_name: str | None = None,
    limit: int | None = None,
    observed: int | None = None,
) -> None:
    details: dict = {"instance_pointer": instance_pointer}
    if reason is not None:
        details["reason"] = reason
    if byte_offset is not None:
        details["byte_offset"] = byte_offset
    if codepoint_offset is not None:
        details["codepoint_offset"] = codepoint_offset
    if limit_name is not None:
        details["limit_name"] = limit_name
        details["limit"] = limit
        details["observed"] = observed
    raise CodeConfigError(code, _MESSAGES[code], details, 2)


def _escape_pointer(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _child_path(parent: str, key: str) -> str:
    return parent + "/" + _escape_pointer(key)


def _index_path(parent: str, index: int) -> str:
    return parent + "/" + str(index)


def _has_surrogate(text: str) -> bool:
    for char in text:
        code = ord(char)
        if 55296 <= code <= 57343:
            return True
    return False


def _snapshot_limits(limits: object) -> dict[str, int]:
    if type(limits) is not dict:
        _raise(
            "CODE_CONFIG_INPUT_INVALID",
            reason="limits must be an exact dict",
            instance_pointer="/limits",
        )
    if len(limits) != len(_LIMIT_KEYS):
        _raise(
            "CODE_CONFIG_INPUT_INVALID",
            reason="limits must contain exactly the profile keys",
            instance_pointer="/limits",
        )
    names: list[str] = []
    for key in limits:
        if type(key) is not str:
            _raise(
                "CODE_CONFIG_INPUT_INVALID",
                reason="limits key type is invalid",
                instance_pointer="/limits",
            )
        names.append(key)
    if set(names) != set(_LIMIT_KEYS):
        _raise(
            "CODE_CONFIG_INPUT_INVALID",
            reason="limits must contain exactly the profile keys",
            instance_pointer="/limits",
        )
    snap: dict[str, int] = {}
    for name in _LIMIT_KEYS:
        value = limits[name]
        if type(value) is not int:
            _raise(
                "CODE_CONFIG_INPUT_INVALID",
                reason="limits value type is invalid",
                instance_pointer="/limits/" + name,
            )
        maximum = CODE_CONFIG_PROFILE_LIMITS[name]
        if value < 1 or value > maximum:
            _raise(
                "CODE_CONFIG_INPUT_INVALID",
                reason="limits value out of range",
                instance_pointer="/limits/" + name,
            )
        snap[name] = value
    return snap


def _decode_source(payload: bytes) -> str:
    if payload.startswith(b"\xef\xbb\xbf"):
        _raise(
            "CODE_CONFIG_BYTES_INVALID",
            reason="initial UTF-8 BOM",
            instance_pointer="/payload",
            byte_offset=0,
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        _raise(
            "CODE_CONFIG_BYTES_INVALID",
            reason="payload is not strict UTF-8",
            instance_pointer="/payload",
            byte_offset=exc.start,
        )
    match = _FORBIDDEN_SOURCE.search(text)
    if match is not None:
        index = match.start()
        _raise(
            "CODE_CONFIG_BYTES_INVALID",
            reason="payload contains a forbidden control or line separator",
            instance_pointer="/payload",
            byte_offset=len(text[:index].encode("utf-8")),
        )
    index = 0
    nbytes = len(text)
    byte_pos = 0
    while index < nbytes:
        char = text[index]
        if char == "\r":
            if index + 1 < nbytes and text[index + 1] == "\n":
                index += 2
                byte_pos += 2
                continue
            _raise(
                "CODE_CONFIG_BYTES_INVALID",
                reason="bare CR",
                instance_pointer="/payload",
                byte_offset=byte_pos,
            )
        byte_pos += len(char.encode("utf-8"))
        index += 1
    return text


def _line_count(normalized: bytes) -> int:
    if not normalized:
        return 0
    return normalized.count(b"\n") + (not normalized.endswith(b"\n"))


def _source_metadata(payload: bytes) -> dict:
    normalized = payload.replace(b"\r\n", b"\n")
    crlf = payload.count(b"\r\n")
    lf_only = payload.count(b"\n") - crlf
    if crlf and lf_only:
        style = "mixed"
    elif crlf:
        style = "crlf"
    elif lf_only:
        style = "lf"
    else:
        style = "none"
    return {
        "body_size_bytes": len(payload),
        "body_sha256": hashlib.sha256(payload).hexdigest(),
        "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
        "newline_style": style,
        "ends_with_newline": normalized.endswith(b"\n"),
        "line_count": _line_count(normalized),
    }


def _snippet_hash(payload: bytes, start: int, end: int) -> str:
    normalized = payload.replace(b"\r\n", b"\n")
    count = _line_count(normalized)
    first = 0
    for _ in range(start - 1):
        first = normalized.find(b"\n", first) + 1
    if end == count:
        last = len(normalized) - normalized.endswith(b"\n")
    else:
        last = first
        for _ in range(end - start + 1):
            last = normalized.find(b"\n", last) + 1
        last -= 1
    return hashlib.sha256(normalized[first:last]).hexdigest()


def _build_coords(payload: bytes, text: str) -> tuple[list[int], list[int], list[int]]:
    nchars = len(text)
    byte_at = [0] * (nchars + 1)
    line_at = [0] * (nchars + 1)
    col_at = [0] * (nchars + 1)
    byte_pos = 0
    line = 1
    column = 1
    index = 0
    while index < nchars:
        byte_at[index] = byte_pos
        line_at[index] = line
        col_at[index] = column
        char = text[index]
        if char == "\r" and index + 1 < nchars and text[index + 1] == "\n":
            byte_pos += 1
            column += 1
            index += 1
            byte_at[index] = byte_pos
            line_at[index] = line
            col_at[index] = column
            byte_pos += 1
            line += 1
            column = 1
            index += 1
            continue
        if char == "\n":
            byte_pos += 1
            line += 1
            column = 1
            index += 1
            continue
        byte_pos += len(char.encode("utf-8"))
        column += 1
        index += 1
    byte_at[nchars] = len(payload)
    line_at[nchars] = line
    col_at[nchars] = column
    return byte_at, line_at, col_at


def _analyze_number(lexeme: str) -> tuple[str, int, str, int, int | None, int]:
    body = lexeme.replace("_", "")
    sign = 0
    if body[0] == "+":
        body = body[1:]
    elif body[0] == "-":
        sign = 1
        body = body[1:]
    explicit = None
    exp_at = -1
    for index, char in enumerate(body):
        if char in "eE":
            exp_at = index
            break
    if exp_at >= 0:
        exp_s = body[exp_at + 1 :]
        body = body[:exp_at]
        exp_sign = 1
        if exp_s[0] == "+":
            exp_s = exp_s[1:]
        elif exp_s[0] == "-":
            exp_sign = -1
            exp_s = exp_s[1:]
        explicit = exp_sign * int(exp_s, 10)
    if "." in body:
        integer_part, frac_part = body.split(".", 1)
        digits = integer_part + frac_part
        places = len(frac_part)
        kind = "decimal"
    else:
        digits = body
        places = 0
        kind = "decimal" if explicit is not None else "integer"
    stripped = digits.lstrip("0")
    if stripped == "":
        coeff = "0"
        ndigits = 1
    else:
        coeff = stripped
        ndigits = len(coeff)
    tuple_exp = -places + (0 if explicit is None else explicit)
    return kind, sign, coeff, tuple_exp, explicit, ndigits


def _expand_fixed(sign: int, coeff: str, exp: int) -> str:
    if coeff.strip("0") == "":
        return "0"
    if exp >= 0:
        magnitude = coeff + ("0" * exp)
    else:
        place = -exp
        if place >= len(coeff):
            magnitude = "0." + ("0" * (place - len(coeff))) + coeff
        else:
            cut = len(coeff) - place
            magnitude = coeff[:cut] + "." + coeff[cut:]
        magnitude = magnitude.rstrip("0").rstrip(".")
        if magnitude == "":
            magnitude = "0"
    if sign:
        return "-" + magnitude
    return magnitude


def _object_pairs_hook(pairs: list) -> dict:
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate")
        out[key] = value
    return out


def _reject_nonfinite(_name: str) -> None:
    raise ValueError("nonfinite")


class _Parser:
    def __init__(
        self,
        payload: bytes,
        text: str,
        coords: tuple[list[int], list[int], list[int]],
        limits: dict[str, int],
        fmt: str,
        line_count: int,
    ) -> None:
        self.payload = payload
        self.text = text
        self.n = len(text)
        self.i = 0
        self.byte_at, self.line_at, self.col_at = coords
        self.limits = limits
        self.fmt = fmt
        self.line_count = line_count
        self.node_count = 0
        self.scalar_count = 0
        self.max_depth_observed = 0
        self.decl_count = 0
        self.max_array_items_observed = 0
        self.max_object_keys_observed = 0
        self.root: _Node | None = None
        self.current: _Node | None = None
        self.dotted_current: list[_Node] = []

    def _peek(self) -> str:
        if self.i >= self.n:
            return ""
        return self.text[self.i]

    def _at_eof(self) -> bool:
        return self.i >= self.n

    def _advance(self, count: int = 1) -> None:
        self.i += count
        if self.i > self.n:
            self.i = self.n

    def _is_newline(self) -> bool:
        char = self._peek()
        return char == "\n" or char == "\r"

    def _consume_newline(self) -> None:
        if self._peek() == "\r":
            self._advance(2)
        elif self._peek() == "\n":
            self._advance()

    def _skip_json_ws(self) -> None:
        while not self._at_eof():
            char = self._peek()
            if char in " \t":
                self._advance()
            elif char == "\n":
                self._advance()
            elif char == "\r":
                self._advance(2)
            else:
                return

    def _skip_toml_space(self) -> None:
        while not self._at_eof() and self._peek() in " \t":
            self._advance()

    def _skip_comment(self) -> None:
        self._advance()
        while not self._at_eof() and not self._is_newline():
            self._advance()

    def _skip_toml_trivia(self) -> None:
        while not self._at_eof():
            self._skip_toml_space()
            if self._at_eof():
                return
            if self._peek() == "#":
                self._skip_comment()
                continue
            if self._is_newline():
                self._consume_newline()
                continue
            return

    def _make_span(self, start: int, end: int) -> dict:
        if end < start:
            end = start
        byte_start = self.byte_at[start]
        byte_end = self.byte_at[end]
        line_start = self.line_at[start]
        column_start = self.col_at[start]
        line_end = self.line_at[end]
        column_end = self.col_at[end]
        snippet_start = line_start
        snippet_end = line_end
        if column_end == 1 and line_end > line_start:
            snippet_end = line_end - 1
        if snippet_end > self.line_count:
            snippet_end = self.line_count
        if snippet_end < snippet_start:
            snippet_end = snippet_start
        return {
            "byte_start": byte_start,
            "byte_end": byte_end,
            "codepoint_start": start,
            "codepoint_end": end,
            "line_start": line_start,
            "column_start": column_start,
            "line_end": line_end,
            "column_end": column_end,
            "raw_sha256": hashlib.sha256(
                self.payload[byte_start:byte_end]
            ).hexdigest(),
            "snippet_sha256": _snippet_hash(
                self.payload, snippet_start, snippet_end
            ),
        }

    def _syntax(self, reason: str, at: int | None = None) -> None:
        index = self.i if at is None else at
        if index > self.n:
            index = self.n
        _raise(
            "CODE_CONFIG_SYNTAX_INVALID",
            reason=reason,
            instance_pointer="/payload",
            byte_offset=self.byte_at[index],
            codepoint_offset=index,
        )

    def _unsupported(self, reason: str, at: int | None = None) -> None:
        index = self.i if at is None else at
        if index > self.n:
            index = self.n
        _raise(
            "CODE_CONFIG_UNSUPPORTED",
            reason=reason,
            instance_pointer="/payload",
            byte_offset=self.byte_at[index],
            codepoint_offset=index,
        )

    def _duplicate(self, reason: str, at: int) -> None:
        if at > self.n:
            at = self.n
        _raise(
            "CODE_CONFIG_DUPLICATE_KEY",
            reason=reason,
            instance_pointer="/payload",
            byte_offset=self.byte_at[at],
            codepoint_offset=at,
        )

    def _dynamic(self, reason: str, at: int) -> None:
        if at > self.n:
            at = self.n
        _raise(
            "CODE_CONFIG_DYNAMIC_UNSUPPORTED",
            reason=reason,
            instance_pointer="/payload",
            byte_offset=self.byte_at[at],
            codepoint_offset=at,
        )

    def _number_invalid(self, reason: str, at: int) -> None:
        if at > self.n:
            at = self.n
        _raise(
            "CODE_CONFIG_NUMBER_INVALID",
            reason=reason,
            instance_pointer="/payload",
            byte_offset=self.byte_at[at],
            codepoint_offset=at,
        )

    def _limit(self, name: str, observed: int, reason: str | None = None) -> None:
        _raise(
            "CODE_CONFIG_LIMIT_EXCEEDED",
            reason=reason,
            instance_pointer="/payload",
            limit_name=name,
            limit=self.limits[name],
            observed=observed,
        )

    def _mismatch(self, reason: str) -> None:
        _raise(
            "CODE_CONFIG_PARSER_MISMATCH",
            reason=reason,
            instance_pointer="/payload",
        )

    def _empty(self, reason: str) -> None:
        _raise(
            "CODE_CONFIG_EMPTY",
            reason=reason,
            instance_pointer="/payload",
        )

    def _dynamic_key(self, name: str, at: int) -> None:
        if (
            name == "_target_"
            or name == "include"
            or name == "includes"
            or name == "import"
        ):
            self._dynamic("dynamic_key", at)

    def _dynamic_string(self, decoded: str, at: int) -> None:
        for marker in _MARKERS:
            if marker in decoded:
                self._dynamic("dynamic_marker", at)
        if _CALLABLE_RE.fullmatch(decoded.strip()) is not None:
            self._dynamic("callable_string", at)

    def _new_node(
        self,
        path: str,
        kind: str,
        depth: int,
        value=None,
        numeric_lexeme: str | None = None,
        value_span: dict | None = None,
    ) -> _Node:
        if depth > self.limits["max_depth"]:
            self._limit("max_depth", depth)
        nxt = self.node_count + 1
        if nxt > self.limits["max_nodes"]:
            self._limit("max_nodes", nxt)
        is_scalar = kind != "object" and kind != "array"
        if is_scalar:
            nscalars = self.scalar_count + 1
            if nscalars > self.limits["max_scalars"]:
                self._limit("max_scalars", nscalars)
            self.scalar_count = nscalars
        self.node_count = nxt
        if depth > self.max_depth_observed:
            self.max_depth_observed = depth
        node = _Node(path, kind, depth)
        node.value = value
        node.numeric_lexeme = numeric_lexeme
        node.value_span = value_span
        if kind == "object":
            node.members = {}
        elif kind == "array":
            node.elements = []
            node.state = "array"
        else:
            node.state = "scalar"
        return node

    def _add_decl(self, node: _Node, kind: str, span: dict) -> None:
        sig = (kind, span["byte_start"], span["byte_end"])
        if sig in node._decl_sigs:
            return
        nxt = self.decl_count + 1
        if nxt > self.limits["max_declarations"]:
            self._limit("max_declarations", nxt)
        node.declarations.append({"kind": kind, "span": span})
        node._decl_sigs.add(sig)
        self.decl_count = nxt

    def _charge_map_key(self, node: _Node) -> None:
        current = 0 if node.members is None else len(node.members)
        nxt = current + 1
        if nxt > self.limits["max_object_keys"]:
            self._limit("max_object_keys", nxt)

    def _note_map_keys(self, node: _Node) -> None:
        count = 0 if node.members is None else len(node.members)
        if count > self.max_object_keys_observed:
            self.max_object_keys_observed = count

    def _charge_array_item(self, node: _Node) -> None:
        current = 0 if node.elements is None else len(node.elements)
        nxt = current + 1
        if nxt > self.limits["max_array_items"]:
            self._limit("max_array_items", nxt)

    def _note_array_items(self, node: _Node) -> None:
        count = 0 if node.elements is None else len(node.elements)
        if count > self.max_array_items_observed:
            self.max_array_items_observed = count

    def _charge_key_bytes(self, name: str) -> None:
        size = len(name.encode("utf-8"))
        if size > self.limits["max_key_bytes"]:
            self._limit("max_key_bytes", size)

    def _charge_string(self, decoded: str) -> None:
        size = len(decoded)
        if size > self.limits["max_string_codepoints"]:
            self._limit("max_string_codepoints", size)

    def _close_tree(self, node: _Node) -> None:
        node.closed = True
        node.state = "closed"
        if node.members:
            for child in node.members.values():
                self._close_tree(child)
        if node.elements:
            for child in node.elements:
                self._close_tree(child)

    def _finalize_dotted(self) -> None:
        for node in self.dotted_current:
            if node.state == "dotted_current":
                node.state = "dotted_finalized"
        self.dotted_current = []

    def _apply_decls(self, node: _Node, decls: list[tuple[str, dict]]) -> None:
        for kind, span in decls:
            self._add_decl(node, kind, span)

    def _hex_digits(self, count: int) -> int:
        if self.i + count > self.n:
            self._syntax("malformed unicode escape")
        block = self.text[self.i : self.i + count]
        for char in block:
            if char not in "0123456789abcdefABCDEF":
                self._syntax("malformed unicode escape")
        self.i += count
        return int(block, 16)

    def _keyword_boundary(self, pos: int) -> bool:
        if pos >= self.n:
            return True
        char = self.text[pos]
        return not (
            ("A" <= char <= "Z")
            or ("a" <= char <= "z")
            or ("0" <= char <= "9")
            or char == "_"
        )

    def _number_from_lexeme(self, lexeme: str, start: int) -> tuple:
        raw_bytes = len(lexeme.encode("utf-8"))
        if raw_bytes > self.limits["max_numeric_lexeme_bytes"]:
            self._limit(
                "max_numeric_lexeme_bytes",
                raw_bytes,
                reason="numeric lexeme exceeds profile",
            )
        kind, sign, coeff, tuple_exp, explicit, ndigits = _analyze_number(lexeme)
        if ndigits > self.limits["max_numeric_coefficient_digits"]:
            self._limit(
                "max_numeric_coefficient_digits",
                ndigits,
                reason="numeric coefficient digit count exceeds profile",
            )
        cap = self.limits["max_numeric_abs_exponent"]
        if explicit is not None and abs(explicit) > cap:
            self._limit(
                "max_numeric_abs_exponent",
                abs(explicit),
                reason="numeric absolute exponent exceeds profile",
            )
        if abs(tuple_exp) > cap:
            self._limit(
                "max_numeric_abs_exponent",
                abs(tuple_exp),
                reason="exact Decimal tuple exponent exceeds profile",
            )
        if sign and coeff.strip("0") == "":
            self._number_invalid("negative zero is refused", start)
        canonical = _expand_fixed(sign, coeff, tuple_exp)
        canonical_bytes = len(canonical.encode("utf-8"))
        if canonical_bytes > self.limits["max_numeric_canonical_bytes"]:
            if (
                self.limits["max_numeric_canonical_bytes"]
                < CODE_CONFIG_PROFILE_LIMITS["max_numeric_canonical_bytes"]
            ):
                reason = "canonical decimal length exceeds supplied lowered profile"
            else:
                reason = "canonical decimal length exceeds profile"
            self._limit(
                "max_numeric_canonical_bytes",
                canonical_bytes,
                reason=reason,
            )
        return kind, canonical, sign, coeff, tuple_exp

    def _make_number_node(
        self,
        path: str,
        depth: int,
        decls: list[tuple[str, dict]],
        lexeme: str,
        start: int,
        end: int,
    ) -> _Node:
        kind, canonical, sign, coeff, tuple_exp = self._number_from_lexeme(
            lexeme, start
        )
        node = self._new_node(
            path,
            kind,
            depth,
            value=canonical,
            numeric_lexeme=lexeme,
            value_span=self._make_span(start, end),
        )
        node.sign = sign
        node.coeff = coeff
        node.tuple_exp = tuple_exp
        self._apply_decls(node, decls)
        return node

    def parse_json(self) -> _Node:
        self._skip_json_ws()
        if self._at_eof():
            self._empty("empty document")
        root = self._json_value("", 0, [])
        self._skip_json_ws()
        if not self._at_eof():
            self._syntax("trailing content outside JSON grammar")
        return root

    def _json_value(
        self, path: str, depth: int, decls: list[tuple[str, dict]]
    ) -> _Node:
        self._skip_json_ws()
        if self._at_eof():
            self._syntax("malformed JSON")
        char = self._peek()
        if char == "{":
            return self._json_object(path, depth, decls)
        if char == "[":
            return self._json_array(path, depth, decls)
        if char == '"':
            return self._json_string_value(path, depth, decls)
        if char == "+":
            self._syntax("plus sign outside JSON number grammar")
        if char == "-" or ("0" <= char <= "9"):
            return self._json_number_value(path, depth, decls)
        if char == "/":
            if self.text.startswith("//", self.i) or self.text.startswith(
                "/*", self.i
            ):
                self._syntax("comments outside JSON grammar")
            self._syntax("malformed JSON")
        return self._json_keyword_value(path, depth, decls)

    def _json_object(
        self, path: str, depth: int, decls: list[tuple[str, dict]]
    ) -> _Node:
        start = self.i
        self._advance()
        node = self._new_node(path, "object", depth)
        self._apply_decls(node, decls)
        self._skip_json_ws()
        if self._peek() == "}":
            self._advance()
            node.value_span = self._make_span(start, self.i)
            return node
        while True:
            self._skip_json_ws()
            if self._peek() != '"':
                if self._peek() == "}":
                    self._syntax("trailing comma outside JSON grammar")
                self._syntax("malformed JSON object")
            key_start = self.i
            key, key_span = self._json_string_token()
            self._charge_key_bytes(key)
            if _has_surrogate(key):
                self._syntax("unpaired surrogate", key_start)
            self._dynamic_key(key, key_start)
            if key in node.members:
                self._duplicate("decoded key collision", key_start)
            self._skip_json_ws()
            if self._peek() != ":":
                self._syntax("malformed JSON object")
            self._advance()
            self._charge_map_key(node)
            child = self._json_value(
                _child_path(path, key),
                depth + 1,
                [("json_key", key_span)],
            )
            node.members[key] = child
            self._note_map_keys(node)
            self._skip_json_ws()
            char = self._peek()
            if char == ",":
                self._advance()
                continue
            if char == "}":
                self._advance()
                break
            self._syntax("malformed JSON object")
        node.value_span = self._make_span(start, self.i)
        return node

    def _json_array(
        self, path: str, depth: int, decls: list[tuple[str, dict]]
    ) -> _Node:
        start = self.i
        self._advance()
        node = self._new_node(path, "array", depth)
        self._apply_decls(node, decls)
        self._skip_json_ws()
        if self._peek() == "]":
            self._advance()
            node.value_span = self._make_span(start, self.i)
            return node
        index = 0
        while True:
            self._skip_json_ws()
            if self._peek() == "]":
                self._syntax("trailing comma outside JSON grammar")
            self._charge_array_item(node)
            child = self._json_value(_index_path(path, index), depth + 1, [])
            node.elements.append(child)
            self._note_array_items(node)
            index += 1
            self._skip_json_ws()
            char = self._peek()
            if char == ",":
                self._advance()
                continue
            if char == "]":
                self._advance()
                break
            self._syntax("malformed JSON array")
        node.value_span = self._make_span(start, self.i)
        return node

    def _json_string_token(self) -> tuple[str, dict]:
        start = self.i
        if self._peek() != '"':
            self._syntax("malformed JSON string")
        self._advance()
        chars: list[str] = []
        while not self._at_eof():
            char = self._peek()
            if char == '"':
                self._advance()
                return "".join(chars), self._make_span(start, self.i)
            if char == "\\":
                self._advance()
                if self._at_eof():
                    self._syntax("malformed JSON string", start)
                esc = self._peek()
                if esc == "u":
                    self._advance()
                    code = self._hex_digits(4)
                    if 55296 <= code <= 56319:
                        if (
                            self._peek() == "\\"
                            and self.i + 1 < self.n
                            and self.text[self.i + 1] == "u"
                        ):
                            self._advance()
                            self._advance()
                            low = self._hex_digits(4)
                            if not (56320 <= low <= 57343):
                                self._syntax("unpaired surrogate", start)
                            scalar = (
                                0x10000
                                + ((code - 55296) << 10)
                                + (low - 56320)
                            )
                            chars.append(chr(scalar))
                        else:
                            self._syntax("unpaired surrogate", start)
                    elif 56320 <= code <= 57343:
                        self._syntax("unpaired surrogate", start)
                    else:
                        chars.append(chr(code))
                    continue
                if esc not in _JSON_ESC:
                    self._syntax("malformed JSON string escape", start)
                self._advance()
                chars.append(_JSON_ESC[esc])
                continue
            if ord(char) < 32:
                self._syntax("unescaped control in JSON string", start)
            self._advance()
            chars.append(char)
        self._syntax("unterminated JSON string", start)
        raise AssertionError("unreachable")

    def _json_string_value(
        self, path: str, depth: int, decls: list[tuple[str, dict]]
    ) -> _Node:
        start = self.i
        decoded, span = self._json_string_token()
        self._charge_string(decoded)
        if _has_surrogate(decoded):
            self._syntax("unpaired surrogate", start)
        self._dynamic_string(decoded, start)
        node = self._new_node(
            path, "string", depth, value=decoded, value_span=span
        )
        self._apply_decls(node, decls)
        return node

    def _json_number_value(
        self, path: str, depth: int, decls: list[tuple[str, dict]]
    ) -> _Node:
        start = self.i
        like = _JSON_NUMLIKE_RE.match(self.text, self.i)
        grammar = _JSON_NUM_RE.match(self.text, self.i)
        if (
            grammar is not None
            and like is not None
            and grammar.end() == like.end()
        ):
            lexeme = grammar.group(0)
            self.i = grammar.end()
            return self._make_number_node(
                path, depth, decls, lexeme, start, self.i
            )
        if like is None:
            self._syntax("malformed JSON number", start)
        lexeme = like.group(0)
        if "_" in lexeme:
            self._syntax("underscore outside JSON number grammar", start)
        if re.match(r"-?0[0-9]", lexeme) is not None:
            self._syntax("leading zero outside JSON number grammar", start)
        self._syntax("malformed JSON number", start)
        raise AssertionError("unreachable")

    def _json_keyword_value(
        self, path: str, depth: int, decls: list[tuple[str, dict]]
    ) -> _Node:
        start = self.i
        if self.text.startswith("true", self.i) and self._keyword_boundary(
            self.i + 4
        ):
            self.i += 4
            node = self._new_node(
                path,
                "boolean",
                depth,
                value=True,
                value_span=self._make_span(start, self.i),
            )
            self._apply_decls(node, decls)
            return node
        if self.text.startswith("false", self.i) and self._keyword_boundary(
            self.i + 5
        ):
            self.i += 5
            node = self._new_node(
                path,
                "boolean",
                depth,
                value=False,
                value_span=self._make_span(start, self.i),
            )
            self._apply_decls(node, decls)
            return node
        if self.text.startswith("null", self.i) and self._keyword_boundary(
            self.i + 4
        ):
            self.i += 4
            node = self._new_node(
                path,
                "null",
                depth,
                value=None,
                value_span=self._make_span(start, self.i),
            )
            self._apply_decls(node, decls)
            return node
        if self.text.startswith("NaN", self.i) and self._keyword_boundary(
            self.i + 3
        ):
            self._syntax("nonfinite constant outside JSON grammar", start)
        if self.text.startswith("Infinity", self.i) and self._keyword_boundary(
            self.i + 8
        ):
            self._syntax("nonfinite constant outside JSON grammar", start)
        if self.text.startswith("-Infinity", self.i) and self._keyword_boundary(
            self.i + 9
        ):
            self._syntax("nonfinite constant outside JSON grammar", start)
        self._syntax("malformed JSON", start)
        raise AssertionError("unreachable")

    def parse_toml(self) -> _Node:
        self.root = self._new_node("", "object", 0)
        self.root.state = "header"
        self.current = self.root
        self.dotted_current = []
        saw = False
        while True:
            self._skip_toml_trivia()
            if self._at_eof():
                break
            saw = True
            if self._peek() == "[":
                self._toml_header()
            else:
                self._toml_keyval(self.current)
            self._skip_toml_space()
            if not self._at_eof() and self._peek() == "#":
                self._skip_comment()
            self._skip_toml_space()
            if not self._at_eof() and not self._is_newline():
                self._syntax("expected newline after TOML statement")
        if not saw:
            self._empty("whitespace/comments-only document")
        return self.root

    def _toml_header(self) -> None:
        start = self.i
        self._advance()
        if self._peek() == "[":
            while not self._at_eof() and self._peek() != "]":
                if self._is_newline():
                    break
                self._advance()
            if self._peek() == "]":
                self._advance()
            if self._peek() == "]":
                self._advance()
            self._unsupported("array of tables outside subset", start)
        comps = self._key_components()
        self._skip_toml_space()
        if self._peek() != "]":
            self._syntax("malformed TOML table header")
        self._advance()
        header_span = self._make_span(start, self.i)
        self._finalize_dotted()
        node = self.root
        for index, (name, span, tok_i) in enumerate(comps):
            last = index == len(comps) - 1
            child = None if node.members is None else node.members.get(name)
            if child is None:
                self._charge_map_key(node)
                child = self._new_node(
                    _child_path(node.path, name),
                    "object",
                    node.depth + 1,
                )
                child.state = "header" if last else "implicit_header"
                node.members[name] = child
                self._note_map_keys(node)
            else:
                if child.closed or child.state in (
                    "inline",
                    "closed",
                    "scalar",
                    "array",
                ):
                    if child.closed or child.state in ("inline", "closed"):
                        self._duplicate(
                            "inline-table boundary cannot be extended", tok_i
                        )
                    self._duplicate("table or value redefinition", tok_i)
                if child.kind != "object":
                    self._duplicate("table or value redefinition", tok_i)
                if last:
                    if child.state == "implicit_header":
                        child.state = "header"
                    elif child.state == "header":
                        self._duplicate("repeated explicit table header", start)
                    else:
                        self._duplicate("table or value redefinition", tok_i)
            self._add_decl(child, "toml_key", span)
            node = child
        self._add_decl(node, "toml_table", header_span)
        self.current = node
        self.dotted_current = []

    def _toml_keyval(self, base: _Node) -> None:
        comps = self._key_components()
        self._skip_toml_space()
        if self._peek() != "=":
            self._syntax("malformed TOML key-value")
        self._advance()
        self._skip_toml_space()
        node = base
        for name, span, tok_i in comps[:-1]:
            child = None if node.members is None else node.members.get(name)
            if child is None:
                self._charge_map_key(node)
                child = self._new_node(
                    _child_path(node.path, name),
                    "object",
                    node.depth + 1,
                )
                child.state = "dotted_current"
                node.members[name] = child
                self._note_map_keys(node)
                self.dotted_current.append(child)
            else:
                if child.closed or child.state in (
                    "inline",
                    "closed",
                    "scalar",
                    "array",
                ):
                    if child.closed or child.state in ("inline", "closed"):
                        self._duplicate(
                            "inline-table boundary cannot be extended", tok_i
                        )
                    self._duplicate("table or value redefinition", tok_i)
                if child.kind != "object":
                    self._duplicate("table or value redefinition", tok_i)
                if child.state == "header":
                    self._duplicate("table or value redefinition", tok_i)
                if child.state == "dotted_finalized":
                    self._duplicate("table or value redefinition", tok_i)
                if child.state == "implicit_header":
                    child.state = "dotted_current"
                    self.dotted_current.append(child)
            self._add_decl(child, "toml_key", span)
            node = child
        tname, tspan, tok_i = comps[-1]
        if node.members is not None and tname in node.members:
            self._duplicate("decoded key collision", tok_i)
        self._charge_map_key(node)
        value = self._toml_value(
            _child_path(node.path, tname), node.depth + 1, []
        )
        self._add_decl(value, "toml_key", tspan)
        node.members[tname] = value
        self._note_map_keys(node)

    def _key_components(self) -> list[tuple[str, dict, int]]:
        parts: list[tuple[str, dict, int]] = []
        while True:
            self._skip_toml_space()
            if self._at_eof():
                self._syntax("malformed TOML key")
            char = self._peek()
            if char == '"' or char == "'":
                if self.text.startswith('"""', self.i) or self.text.startswith(
                    "'''", self.i
                ):
                    self._unsupported("multiline string outside subset", self.i)
                start = self.i
                decoded, span = self._toml_quoted_token()
                self._charge_key_bytes(decoded)
                if _has_surrogate(decoded):
                    self._syntax("unpaired surrogate", start)
                self._dynamic_key(decoded, start)
                parts.append((decoded, span, start))
            else:
                match = _BARE_KEY_RE.match(self.text, self.i)
                if match is None:
                    self._syntax("malformed TOML key")
                start = self.i
                decoded = match.group(0)
                self.i = match.end()
                span = self._make_span(start, self.i)
                self._charge_key_bytes(decoded)
                self._dynamic_key(decoded, start)
                parts.append((decoded, span, start))
            self._skip_toml_space()
            if self._peek() == ".":
                self._advance()
                continue
            break
        if not parts:
            self._syntax("malformed TOML key")
        return parts

    def _toml_value(
        self, path: str, depth: int, decls: list[tuple[str, dict]]
    ) -> _Node:
        if self._at_eof():
            self._syntax("malformed TOML value")
        char = self._peek()
        if char == '"':
            if self.text.startswith('"""', self.i):
                self._unsupported("multiline string outside subset", self.i)
            return self._toml_string_value(path, depth, decls, literal=False)
        if char == "'":
            if self.text.startswith("'''", self.i):
                self._unsupported("multiline string outside subset", self.i)
            return self._toml_string_value(path, depth, decls, literal=True)
        if char == "[":
            return self._toml_array(path, depth, decls)
        if char == "{":
            return self._toml_inline(path, depth, decls)
        if self.text.startswith("true", self.i) and self._keyword_boundary(
            self.i + 4
        ):
            start = self.i
            self.i += 4
            node = self._new_node(
                path,
                "boolean",
                depth,
                value=True,
                value_span=self._make_span(start, self.i),
            )
            self._apply_decls(node, decls)
            return node
        if self.text.startswith("false", self.i) and self._keyword_boundary(
            self.i + 5
        ):
            start = self.i
            self.i += 5
            node = self._new_node(
                path,
                "boolean",
                depth,
                value=False,
                value_span=self._make_span(start, self.i),
            )
            self._apply_decls(node, decls)
            return node
        return self._toml_number_value(path, depth, decls)

    def _toml_quoted_token(self) -> tuple[str, dict]:
        if self._peek() == "'":
            return self._toml_literal_token()
        return self._toml_basic_token()

    def _toml_literal_token(self) -> tuple[str, dict]:
        start = self.i
        self._advance()
        chars: list[str] = []
        while not self._at_eof():
            char = self._peek()
            if char == "'":
                self._advance()
                return "".join(chars), self._make_span(start, self.i)
            if self._is_newline():
                self._syntax("unterminated TOML string", start)
            self._advance()
            chars.append(char)
        self._syntax("unterminated TOML string", start)
        raise AssertionError("unreachable")

    def _toml_basic_token(self) -> tuple[str, dict]:
        start = self.i
        self._advance()
        chars: list[str] = []
        while not self._at_eof():
            char = self._peek()
            if char == '"':
                self._advance()
                return "".join(chars), self._make_span(start, self.i)
            if self._is_newline():
                self._syntax("unterminated TOML string", start)
            if char == "\\":
                slash_at = self.i
                self._advance()
                if self._at_eof():
                    self._syntax("malformed TOML string", start)
                if self._is_newline():
                    self._unsupported(
                        "line-joining backslash outside subset", slash_at
                    )
                esc = self._peek()
                if esc == "u":
                    self._advance()
                    code = self._hex_digits(4)
                    if 55296 <= code <= 57343:
                        self._syntax("unpaired surrogate", start)
                    chars.append(chr(code))
                    continue
                if esc == "U":
                    self._advance()
                    code = self._hex_digits(8)
                    if code > 0x10FFFF or 55296 <= code <= 57343:
                        self._syntax("malformed TOML unicode escape", start)
                    chars.append(chr(code))
                    continue
                if esc not in _TOML_ESC:
                    self._syntax("malformed TOML string escape", start)
                self._advance()
                chars.append(_TOML_ESC[esc])
                continue
            self._advance()
            chars.append(char)
        self._syntax("unterminated TOML string", start)
        raise AssertionError("unreachable")

    def _toml_string_value(
        self,
        path: str,
        depth: int,
        decls: list[tuple[str, dict]],
        *,
        literal: bool,
    ) -> _Node:
        start = self.i
        if literal:
            decoded, span = self._toml_literal_token()
        else:
            decoded, span = self._toml_basic_token()
        self._charge_string(decoded)
        if _has_surrogate(decoded):
            self._syntax("unpaired surrogate", start)
        self._dynamic_string(decoded, start)
        node = self._new_node(
            path, "string", depth, value=decoded, value_span=span
        )
        self._apply_decls(node, decls)
        return node

    def _toml_array(
        self, path: str, depth: int, decls: list[tuple[str, dict]]
    ) -> _Node:
        start = self.i
        self._advance()
        node = self._new_node(path, "array", depth)
        self._apply_decls(node, decls)
        self._skip_toml_space()
        if self._is_newline():
            self._unsupported(
                "physical newline inside array outside subset", start
            )
        if self._peek() == "]":
            self._advance()
            node.value_span = self._make_span(start, self.i)
            return node
        index = 0
        while True:
            self._skip_toml_space()
            if self._is_newline():
                self._unsupported(
                    "physical newline inside array outside subset", start
                )
            if self._peek() == "]":
                self._advance()
                break
            self._charge_array_item(node)
            child = self._toml_value(_index_path(path, index), depth + 1, [])
            node.elements.append(child)
            self._note_array_items(node)
            index += 1
            self._skip_toml_space()
            if self._is_newline():
                self._unsupported(
                    "physical newline inside array outside subset", start
                )
            if self._peek() == ",":
                self._advance()
                self._skip_toml_space()
                if self._is_newline():
                    self._unsupported(
                        "physical newline inside array outside subset", start
                    )
                if self._peek() == "]":
                    self._advance()
                    break
                continue
            if self._peek() == "]":
                self._advance()
                break
            self._syntax("malformed TOML array")
        node.value_span = self._make_span(start, self.i)
        return node

    def _toml_inline(
        self, path: str, depth: int, decls: list[tuple[str, dict]]
    ) -> _Node:
        start = self.i
        self._advance()
        node = self._new_node(path, "object", depth)
        node.state = "inline"
        self._apply_decls(node, decls)
        saved_current = self.current
        saved_dotted = self.dotted_current
        self.current = node
        self.dotted_current = []
        self._skip_toml_space()
        if self._is_newline():
            self._unsupported(
                "physical newline inside inline table outside subset", start
            )
        if self._peek() == "}":
            self._advance()
            node.value_span = self._make_span(start, self.i)
            self._close_tree(node)
            self.current = saved_current
            self.dotted_current = saved_dotted
            return node
        while True:
            self._skip_toml_space()
            if self._is_newline():
                self._unsupported(
                    "physical newline inside inline table outside subset", start
                )
            self._toml_keyval(node)
            self._skip_toml_space()
            if self._is_newline():
                self._unsupported(
                    "physical newline inside inline table outside subset", start
                )
            if self._peek() == ",":
                self._advance()
                self._skip_toml_space()
                if self._is_newline():
                    self._unsupported(
                        "physical newline inside inline table outside subset",
                        start,
                    )
                if self._peek() == "}":
                    self._syntax("trailing comma not allowed in inline table")
                continue
            if self._peek() == "}":
                break
            self._syntax("malformed TOML inline table")
        if self._peek() != "}":
            self._syntax("malformed TOML inline table")
        self._advance()
        node.value_span = self._make_span(start, self.i)
        self._close_tree(node)
        self.current = saved_current
        self.dotted_current = saved_dotted
        return node

    def _toml_number_value(
        self, path: str, depth: int, decls: list[tuple[str, dict]]
    ) -> _Node:
        start = self.i
        date = _TOML_DATE_RE.match(self.text, self.i)
        if date is not None:
            self._unsupported("date/time outside subset", start)
        if _TOML_TIME_RE.match(self.text, self.i) is not None:
            self._unsupported("date/time outside subset", start)
        if _TOML_BASE_RE.match(self.text, self.i) is not None:
            self._unsupported("base-prefixed integer outside subset", start)
        if _TOML_NONFINITE_RE.match(self.text, self.i) is not None:
            self._unsupported("nonfinite TOML value outside subset", start)
        flt = _TOML_FLOAT_RE.match(self.text, self.i)
        if flt is not None:
            lexeme = flt.group(0)
            self.i = flt.end()
            return self._make_number_node(
                path, depth, decls, lexeme, start, self.i
            )
        integer = _TOML_INT_RE.match(self.text, self.i)
        if integer is not None:
            lexeme = integer.group(0)
            self.i = integer.end()
            return self._make_number_node(
                path, depth, decls, lexeme, start, self.i
            )
        like = _TOML_NUMLIKE_RE.match(self.text, self.i)
        if like is not None:
            lexeme = like.group(0)
            if "_" in lexeme:
                self._syntax("invalid TOML digit separator placement", start)
            self._syntax("malformed TOML number", start)
        self._syntax("malformed TOML value", start)
        raise AssertionError("unreachable")

    def flatten(self, root: _Node) -> list[dict]:
        out: list[dict] = []

        def walk(node: _Node) -> None:
            out.append(self._emit(node))
            if node.kind == "object":
                keys = sorted(node.members, key=lambda item: item.encode("utf-8"))
                for key in keys:
                    walk(node.members[key])
            elif node.kind == "array":
                for child in node.elements:
                    walk(child)

        walk(root)
        return out

    def _emit(self, node: _Node) -> dict:
        if node.kind == "object":
            keys = sorted(node.members, key=lambda item: item.encode("utf-8"))
            children = [node.members[key].path for key in keys]
        elif node.kind == "array":
            children = [child.path for child in node.elements]
        else:
            children = []
        decls = sorted(
            node.declarations,
            key=lambda item: (
                item["span"]["byte_start"],
                item["span"]["byte_end"],
                item["kind"],
            ),
        )
        return {
            "path": node.path,
            "kind": node.kind,
            "value": node.value,
            "numeric_lexeme": node.numeric_lexeme,
            "children": children,
            "value_span": node.value_span,
            "declarations": decls,
        }

    def budget(self) -> dict:
        return {
            "node_count": self.node_count,
            "scalar_count": self.scalar_count,
            "max_depth_observed": self.max_depth_observed,
            "declaration_count": self.decl_count,
            "max_array_items_observed": self.max_array_items_observed,
            "max_object_keys_observed": self.max_object_keys_observed,
        }

    def cross_check(self, root: _Node) -> None:
        try:
            if self.fmt == "json":
                std = json.loads(
                    self.text,
                    parse_float=Decimal,
                    parse_constant=_reject_nonfinite,
                    object_pairs_hook=_object_pairs_hook,
                )
            else:
                std = tomllib.loads(self.text, parse_float=Decimal)
        except CodeConfigError:
            raise
        except Exception:
            self._mismatch(
                "standard library parser rejected a scanner-accepted document"
            )
        self._compare(root, std)

    def _compare(self, node: _Node, std: object) -> None:
        kind = node.kind
        if kind == "object":
            if type(std) is not dict:
                self._mismatch("object kind mismatch")
            for std_key in std:
                if type(std_key) is not str:
                    self._mismatch("object key type mismatch")
            ours = set(node.members)
            theirs = set(std)
            if ours != theirs:
                self._mismatch("object key set mismatch")
            for key, child in node.members.items():
                self._compare(child, std[key])
            return
        if kind == "array":
            if type(std) is not list:
                self._mismatch("array kind mismatch")
            if len(std) != len(node.elements):
                self._mismatch("array length mismatch")
            for index, child in enumerate(node.elements):
                self._compare(child, std[index])
            return
        if kind == "string":
            if type(std) is not str or std != node.value:
                self._mismatch("string value mismatch")
            return
        if kind == "boolean":
            if type(std) is not bool or std is not node.value:
                self._mismatch("boolean value mismatch")
            return
        if kind == "null":
            if std is not None:
                self._mismatch("null value mismatch")
            return
        if kind == "integer":
            if type(std) is not int:
                self._mismatch("integer kind mismatch")
            if std != int(node.value, 10):
                self._mismatch("integer value mismatch")
            return
        if kind == "decimal":
            if type(std) is not Decimal:
                self._mismatch("decimal kind mismatch")
            ours_dec = Decimal(
                (node.sign, tuple(int(digit) for digit in node.coeff), node.tuple_exp)
            )
            if ours_dec != std:
                self._mismatch("decimal value mismatch")
            return
        self._mismatch("unsupported stdlib type")


def parse_code_config_bytes(
    *,
    payload: bytes,
    config_format: str,
    limits: dict[str, int],
) -> dict:
    if type(payload) is not bytes:
        _raise(
            "CODE_CONFIG_INPUT_INVALID",
            reason="payload must be exact bytes",
            instance_pointer="/payload",
        )
    if type(config_format) is not str or (
        config_format != "json" and config_format != "toml"
    ):
        _raise(
            "CODE_CONFIG_INPUT_INVALID",
            reason="config_format must be exact json or toml",
            instance_pointer="/config_format",
        )
    snap = _snapshot_limits(limits)
    if len(payload) > snap["max_source_bytes"]:
        _raise(
            "CODE_CONFIG_LIMIT_EXCEEDED",
            instance_pointer="/payload",
            limit_name="max_source_bytes",
            limit=snap["max_source_bytes"],
            observed=len(payload),
        )
    try:
        text = _decode_source(payload)
        meta = _source_metadata(payload)
        coords = _build_coords(payload, text)
        parser = _Parser(
            payload, text, coords, snap, config_format, meta["line_count"]
        )
        if config_format == "json":
            root = parser.parse_json()
        else:
            root = parser.parse_toml()
        parser.cross_check(root)
        return {
            "config_format": config_format,
            "source": meta,
            "budget": parser.budget(),
            "nodes": parser.flatten(root),
        }
    except CodeConfigError:
        raise
    except (ValueError, RecursionError, ArithmeticError, MemoryError, OverflowError):
        _raise(
            "CODE_CONFIG_PARSER_MISMATCH",
            reason="standard library parser disagreed",
            instance_pointer="/payload",
        )
