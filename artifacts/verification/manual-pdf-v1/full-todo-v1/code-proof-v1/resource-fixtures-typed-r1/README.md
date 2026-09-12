# Typed CODE proof fixtures R1

This is a post-CONFIG preparation generator for seven independently authored
success vectors in `config-r1/static-vectors-r4.json`:

`json-nested-lf`, `json-unicode-crlf-tabs`, `json-pointer-escaping`,
`toml-nested-lf`, `toml-unicode-crlf-inline`, `toml-dotted-promotion`, and
`toml-numeric-boundaries`.

Each vector is generated for both SHA-1 and SHA-256.  The generator constructs
a fresh regular configuration blob, one root tree, and one commit as Git loose
object bytes, then feeds exactly those three retained bodies to the accepted
Git verifier.  The parser result is produced by the exact CONFIG source
checkout named at invocation time and is compared with the frozen independent
vector before any saved typed evidence is written.  Every case contains the
six R4/R7 envelopes, request/observe/status/config/handoff success payloads,
the ordinary request and observe inputs, the actual commit/tree/blob bodies,
and logical `.work/<batch>/code-evidence-v1` references.  The host assertion is
explicitly synthetic; `officiality_claim`
is null and no repository officiality, source admission, license, capture,
publication, scientific claim, or human approval is asserted.

The generator does not import the CONFIG parser during module import.  A run
requires all of `--accepted-config-head`, `--accepted-config-tree`, and
`--accepted-config-acceptance-sha256`; it performs read-only Git checks that the
source checkout is exactly that accepted head/tree before importing the parser
or creating typed results.  It also verifies the frozen static-vector SHA-256.
The acceptance-record digest is recorded in `manifest.json` for later review.

The profile hash defaults to 64 lowercase zeroes.  After the installed profile
has been separately accepted, pass `--profile-sha256` with its exact 64-digit
SHA-256; the value is carried into request identities and all dependent
envelopes.  No string replacement or post-sealing patching is used.

Use a fresh output directory; an existing output path is refused before any
fixture is generated.  The generator writes only its requested artifact
directory, never a repository object database, provider, Vault, source file,
schema, test, or production resource.  It does not run a public command.

Example, after CONFIG acceptance (values below are placeholders and must be
replaced with the exact accepted evidence):

```console
python artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/resource-fixtures-typed-r1/generate_typed_fixtures.py \
  --source-root /path/to/accepted/checkout \
  --output-dir /private/tmp/typed-fixtures-r1-fresh \
  --accepted-config-head <40-lowercase-hex> \
  --accepted-config-tree <40-lowercase-hex> \
  --accepted-config-acceptance-sha256 <64-lowercase-hex> \
  --profile-sha256 <64-lowercase-hex>
```

The current source checkout is intentionally not imported or executed while
this preparation artifact is being drafted.  Generation, parser replay,
manifest audit, and dual-Python verification remain pending the exact CONFIG
acceptance and an independent review of this generator.
