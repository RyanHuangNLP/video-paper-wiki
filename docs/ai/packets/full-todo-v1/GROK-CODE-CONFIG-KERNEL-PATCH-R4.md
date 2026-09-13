# Return one bounded CONFIG repair patch

You are Grok Build, the author of the existing configuration parser. Return one
complete fenced diff in apply_patch format: `*** Begin Patch`, two
`*** Update File:` headers with the exact paths below, context hunks using `@@`
without line counts, and `*** End Patch`. No tool calls, prose, placeholders,
test-execution claims or full-file output. The excerpts below are sufficient.

Allowed paths:

- /Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/code-proof-v1/terminal-1/source/src/video_paper_wiki/code_config_parser.py
- /Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/code-proof-v1/terminal-1/source/tests/unit/test_code_config_parser.py

Independent review reproduced a narrow defect in the complete stdlib-tree
cross-check. With json.loads returning `{Key("a"): True}`, where Key subclasses
str, parsing the valid source `{"a":true}` succeeds. A str subclass with armed
hash/equality traps instead invokes its custom equality method and leaks an
AssertionError. R1 requires unsupported stdlib types to become
CODE_CONFIG_PARSER_MISMATCH. Object keys need the same exact builtin type
discipline already applied to values.

Required production change: only in `_compare`'s object branch, after the exact
dict guard and before any set, membership, equality, lookup or formatting of its
keys, reject each non-exact-str stdlib key through the existing `_mismatch` with
a fixed non-source-echoing reason. Iterate the exact dict safely and inspect key
types without executing custom methods. Keep every later key-set, value, kind,
array-order and numeric check intact. Do not change parsing, limits, API, output
shapes or error codes; do not broadly catch callbacks as a substitute for avoiding
them.

Add focused unittest methods immediately before `test_hostile_decimal_context`:

1. Instrument both json.loads and tomllib.loads, at a root object and a nested
   object. Return an exact dict with (a) an ordinary str-subclass key and (b) a
   hostile str-subclass key. Construct dictionaries before arming traps; trap
   __hash__, __eq__, __str__ and __repr__ without invoking these methods during
   assertions or subtest naming. Require CodeConfigError, exit_code 2, code
   CODE_CONFIG_PARSER_MISMATCH, exact closed details keys {instance_pointer,
   reason}, pointer /payload and a nonempty fixed reason, and zero callbacks.
   Restore the stdlib patch and verify the equivalent ordinary source succeeds.
   Verify a plain non-string key is refused too. Existing wrong-value and
   missing/extra-key tests remain unchanged.
2. Add a separate error-content regression with independently selected sources
   and expected codes: JSON duplicate decoded key, JSON malformed syntax, JSON
   dynamic string and JSON negative-zero decimal. Use distinctive synthetic
   key/string sentinels and a multi-character numeric lexeme, avoiding trivial
   single digits that can coincide with position metadata. For each refusal,
   assert that the complete raw source, decoded sentinel key/value and selected
   original lexeme never appear in the message, str(error), or JSON-serialized
   details. Require the correct code, exit_code 2, /payload, exact scanner detail
   keys {instance_pointer,reason,byte_offset,codepoint_offset}, nonempty bounded
   reason and exact integer offsets. Expected syntax/code behavior comes from
   JSON grammar and the rules below, not from running the implementation. Do not
   weaken existing assertions, add skips/xfails, edit fixtures or rewrite tests.

The test module already imports `json`, `TestCase`, `patch`, CodeConfigError and
parse_code_config_bytes. Its class is TestCodeConfigParser. `_fresh_limits()`
returns a mutable copy of CODE_CONFIG_PROFILE_LIMITS. `self._parse(payload, fmt)`
calls parse_code_config_bytes with those limits. A local
`import video_paper_wiki.code_config_parser as mod` gives access to mod.json and
mod.tomllib for patch.object. `self.assertRaises`, `self.subTest` and other usual
TestCase assertions are available. Production `_mismatch` raises CodeConfigError
with exit_code=2, code CODE_CONFIG_PARSER_MISMATCH and details exactly
{instance_pointer:"/payload", reason:<fixed string>}. CodeConfigError has
`.code`, `.message`, `.details`, `.exit_code` and subclasses ValueError.

For error-content test expectations: repeated decoded JSON keys are
CODE_CONFIG_DUPLICATE_KEY; a trailing JSON object comma is
CODE_CONFIG_SYNTAX_INVALID; a decoded string containing `${` is
CODE_CONFIG_DYNAMIC_UNSUPPORTED; an otherwise valid JSON decimal spelling of
negative zero is CODE_CONFIG_NUMBER_INVALID. All these scanner errors have the
four context fields listed above. Default numeric caps are lexeme bytes 128,
coefficient digits 64, absolute exponent 128 and canonical bytes 256. Choose
short sources that stay below all caps. Reasons are fixed implementation strings;
only dynamic markers have an exact required reason token, `dynamic_marker`.

## Exact production edit context

```python
    def _compare(self, node: _Node, std: object) -> None:
        kind = node.kind
        if kind == "object":
            if type(std) is not dict:
                self._mismatch("object kind mismatch")
            ours = set(node.members)
            theirs = set(std)
            if ours != theirs:
                self._mismatch("object key set mismatch")
            for key, child in node.members.items():
                self._compare(child, std[key])
            return
        if kind == "array":
```

## Exact test insertion context

```python
    def test_hostile_decimal_context(self) -> None:
        before = getcontext().copy()
        payload = b"1e-4"
```

Insert the new methods before this method and preserve it unchanged. The other
fixture-oracle corrections are being handled separately and must not be included
in this patch. Return the complete bounded patch now.
