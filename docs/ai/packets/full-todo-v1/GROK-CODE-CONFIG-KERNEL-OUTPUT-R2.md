# Grok Build: implement the frozen CODE configuration kernel

Implement this bounded project task using Grok Build grok-4.6 / xhigh. This is
the direct-output invocation amendment to GROK-CODE-CONFIG-KERNEL-IMPLEMENT-R1.
It retains all semantic and test requirements. The accepted Git kernel is already
locally delivered at b46e106e48438f18cbbcf0c3fbee8f0a7524f071, tree
3819b8d91ef3eb0b6649793d1b16a3d7806b87a1. Architect's separate exact freeze and
dispatch authorize this run. You author the complete implementation and tests;
Architect installs your returned contents mechanically and runs the tests.

Use only read_file to read these exact files relative to the supplied working
directory. They are hash-checked copies prepared for this call:

1. CODE-CONFIG-KERNEL-R1.md — complete pure parser API, limits, output, errors,
   coordinate and acceptance contract; read all of it.
2. CODE-CONFIG-CLARIFICATIONS-R2.md — authoritative dynamic refusal positions
   and explicit TOML table state transitions; read all of it.
3. CODE-PROOF-CLOSURE-R3.md — exact numeric grammar, coefficient, explicit and
   tuple exponent, canonical numeric and source-coordinate rules; read all of it.
   Its public transport discussion is future work, outside this parser slice.
4. CODE-CONFIG-TOML-MATRIX-R2.json — all 26 normative transition examples.
5. CODE-CONFIG-DYNAMIC-VECTORS-R2.json — normative token-offset examples.
6. static-vectors-r2.json — accepted independent fixture. Inspect its complete
   structure and all success/refusal and supplementary groups. It is copied
   unchanged into tests/fixtures/code-config-vectors-v1.json by Architect.
7. legacy-helper-interface.md — existing helper imports, exact implementation
   excerpts and fixture-use notes for test parity; no legacy edits are allowed.
8. invocation-inputs.json — accepted baseline and original/copy fingerprints.

Read in bounded chunks where necessary; do not assume a truncated tool result
contains the entire file. The working directory is a prepared input directory,
not the production checkout. Do not inspect its ancestors, unrelated files,
credentials, home settings, memory or other repositories. File paths in fixture
provenance are explanatory, not instructions to read those original locations.
Do not request shell, editing, writing, grep/list tools, web, MCP or subagents.
Normal permission mode remains default. No installation, command execution,
Git mutation, model download, real Vault/admin operation or network acquisition.

Return exactly two complete UTF-8 Python file bodies, each inside one fenced
Python block, in the order below. Place its exact marker on the immediately
preceding line. Use LF newlines and one terminal LF per file. Do not output a
diff, JSON-escaped source, omitted sections, placeholders or an encoded archive.

BEGIN_FILE src/video_paper_wiki/code_config_parser.py
```python
<the entire production module>
```
END_FILE src/video_paper_wiki/code_config_parser.py

BEGIN_FILE tests/unit/test_code_config_parser.py
```python
<the entire focused test module>
```
END_FILE tests/unit/test_code_config_parser.py

After the second file, return a short development brief describing the design,
covered cases and any unresolved contract question. Explicitly say that no files
were written and no tests were run in this invocation. Do not invent hashes,
test counts, acceptance or delivery. Then stop; no further tools or edits.
If a necessary contract is inconsistent, explain the exact blocker without
silently changing it or presenting incomplete file bodies as a candidate.

Required implementation reminders (the complete contracts remain normative):

- Export CodeConfigError(ValueError), CODE_CONFIG_PROFILE_LIMITS and keyword-only
  parse_code_config_bytes(payload, config_format, limits). Accept only exact
  builtin primitive types. For limits, check exact dict and constant-time count,
  then every key's exact str type before set/membership/lookup/equality/formatting
  can invoke custom callbacks. Snapshot validated primitives. All 13 limits can
  be lowered; reject bool as int, subclasses and malformed keys without callback.
- Implement the bounded scanner before the mandatory independent whole-tree
  json.loads/tomllib.loads check. Do not pass hostile nesting to stdlib first or
  locate tokens by regex searches after semantic parsing. Charge limits before
  insertion/conversion/descent. Track TOML implicit/header/dotted section/closed
  inline states exactly as the R2 clarification specifies.
- Numeric values are canonical magnitude strings with integer/decimal kinds and
  original lexemes. No floats, context-sensitive Decimal arithmetic, global
  Decimal-context changes or integer-conversion-limit changes. Enforce negative
  zero and all four numeric caps, plus lexical/coefficient/exponent rules.
- Preserve original Unicode and byte/codepoint/line/column spans. Handle CRLF,
  escaped surrogate pairs and key identity. Return complete ordered fresh nodes,
  declarations, children, source metadata and budget; no raw source in errors.
- Production calls are standard-library-only and pure, with no file/resource/
  network/subprocess/environment/clock/randomness/dynamic evaluation or imports
  of supplied source. No legacy source, schema, metadata or dependency edits.

Required tests include all independently authored fixture success records with
exact source and expected_nodes equality, budget derived separately from those
records, every refusal and both supplementary_groups. Fixtures' extra notes are
not output fields. Test every limit at boundaries and lowered settings, callback
traps, complete stdlib type/key/value/array corruption, no-alias determinism and
key order, exact spans and legacy helper parity, tiny hostile Decimal contexts,
dynamic token start positions, Unicode/CRLF/source validation, all TOML state
transitions and closed inline boundaries. Guard file/resource/network/subprocess
operations after import during both successful and refused calls. Construct
test fixtures before arming hash/decoder guards. Use no skip, xfail, unconditional
assertions or expected-value changes made to accommodate an implementation bug.

Architect and independent Repo Steward will inspect both complete returned
modules, mechanically copy the immutable fixture, then run the focused tests
and independent generated/adversarial cases with the existing locked Python
3.12/3.13 environments in short real temporary paths. Do not run those checks
yourself in this read-only invocation. Full repository and installed-wheel
acceptance belongs to complete CODE integration later; this parser alone does
not prove program usage, official repository relationships or scientific claims.
