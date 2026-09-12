# CODE public-wire fixture set R3

R3 is an additive synthetic fixture set built from the accepted R2 generator
and the frozen R5/R7 wire contracts. It preserves the two verified raw Git
formats and the normalized-present sample, then adds minimal positive examples
for the public status state machine, normalized host outcomes, and an
incomplete raw target set.

The generated cases cover `empty`, `requested`, `pending_normalized`,
`pending_raw_bundle`, both `pending_raw_bodies` situations (a missing suffix
body and all bodies present before observation), and complete `observed`
normalized/raw snapshots. Raw cases use the accepted Git verifier and exactly
three synthetic objects: the commit, root tree, and `config.json` blob. The
mixed raw case requests `config.json` and `missing.py`; its configuration target
is retained as explicit `source-only` evidence while the missing target makes
the target set ineligible for source handoff. Its raw target reason is copied
from the verifier's `absent_entry` result, as required by R7.

Every saved ce1 envelope and reference is generated afresh for its R3 batch.
Wire paths use canonical hypothetical checkout-relative locations such as
`.work/<batch>/code-evidence-v1/...`; physical fixture files are kept under
`saved/`, `success-data/`, and `inputs/` in this directory. The generator never
invokes a public command, network/provider, Git process, configuration parser,
or installed resource loader.

The profile hash defaults to the explicit 64-zero placeholder. Pass
`--profile-sha256 <64 lowercase hex>` to rebind all request-dependent IDs and
references after a real installed profile is separately frozen. R12's ten
schemas and profile are intentionally not fabricated by this preparation
package; `manifest.json` records that no installed resources are claimed.

Rerunning requires a fresh output directory because the generator refuses to
overwrite any existing fixture file.
