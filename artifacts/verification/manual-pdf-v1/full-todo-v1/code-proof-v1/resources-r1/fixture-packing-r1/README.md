# CODE resource fixture packing R1

This package contains a stdlib-only packer for the deterministic positive
fixture transport required by `CODE-PROOF-RESOURCE-GENERATION-PLAN-R1.md`.
It reads the accepted R3 base fixture directory and corrected typed R2 fixture
directory, validates each manifest-listed file's exact size and SHA-256, and
checks that the complete `saved/`, `success-data/`, and `inputs/` data sets are
covered.  Raw Git object bodies are pin-checked for complete input coverage,
but are never parsed as instances or included in the output.

The output is the closed object `{schema, profile_sha256, cases}` with schema
`video-paper-wiki.code-proof-resource-fixtures.v1`.  Each case is exactly
`{name, title, instance}`.  Names use `base/<relative-path>` or
`typed/<relative-path>` so their origin remains traceable; cases are unique,
ASCII, and sorted by name.  Saved envelopes use their own `schema` as title,
ordinary request/observe inputs use their two input schema titles, and every
success payload uses `video-paper-wiki.code-proof-command-result.v1`.

The packer validates both manifest pins and requires the same expected profile
SHA-256 in both manifests and every saved request envelope.  Ordinary request
inputs must omit `profile_sha256`.  It preserves parsed instance values and
does not replace profile strings, re-seal ce1 identities, normalize source
text, import product code, call Git/provider services, or write product tests
or schemas.  The output path must be fresh; an existing file is refused.

The current accepted placeholder run uses the all-zero profile and these
manifest pins:

```text
base R3:   f53f4f6ef768732dc423da0ebf478716fab500cc716856a07fee21f7abb12136
typed R2:  ba6f2f628f16b78c467bea7907cfcd2039616e0a852ace7abb79d6d40a56e00a
```

Expected positive JSON cases are 82 from base and 182 from typed, for 264
total.  Raw-body entries remain checked for pin completeness but are not read
or included.  The separate common/profile validation case belongs in the
resource test suite and is intentionally not an instance case here.

Example invocation:

```console
python pack_resource_fixtures.py \
  --base-dir ../resource-fixtures-r3 \
  --typed-dir ../resource-fixtures-typed-r2 \
  --profile-sha256 0000000000000000000000000000000000000000000000000000000000000000 \
  --base-manifest-sha256 f53f4f6ef768732dc423da0ebf478716fab500cc716856a07fee21f7abb12136 \
  --typed-manifest-sha256 ba6f2f628f16b78c467bea7907cfcd2039616e0a852ace7abb79d6d40a56e00a \
  --output-file packed-zero-r1.json
```

The generated zero-profile bundle and its run record are kept beside this
script.  A second invocation with the same output path must fail before
replacement; a changed profile or manifest pin must fail before output.
