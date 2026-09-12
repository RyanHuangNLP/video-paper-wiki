# CODE public-wire fixture set R1

This directory contains the smallest synthetic shape examples for the R4/R7/R9/R11/R12 public wire. It is fixture evidence only. It does not contain installed CODE schemas or a profile, does not bind a real `profile_sha256`, and does not claim public workflow acceptance.

`generate_resource_fixtures.py` imports the accepted pure JCS and `verify_code_git_objects` APIs from `.work/parallel/code-proof-v1/terminal-1/source`. Each raw case uses exactly three real synthetic fixture objects: the fixture commit, its root tree, and the `config.json` blob. The verifier consumes all three objects and proves the one regular configuration target for both SHA-1 and SHA-256. No network, Git command, source checkout, Vault, public CLI, or configuration parser is used.

The generated `saved/` tree contains all six saved envelope kinds: request, Git bundle, acquisition intent, observation, configuration evidence, and source handoff. The configuration envelope uses `format: "source-only"`, `result: null`, and `source_only_reason: "explicit_source_only"`. The `normalized/` case supplies a separate normalized-text request/intent/observation branch and deliberately has no raw bundle, configuration artifact, or handoff.

`inputs/` demonstrates the two ordinary input shapes (`request-input` and `observe-input`), with raw and normalized observe instances. `success-data/` contains the five success payload shapes: request, observe, status, config, and handoff. JSON/TOML parser results are intentionally absent.

The default profile hash is an explicit 64-zero placeholder. Rebuild with `--profile-sha256 <64 lowercase hex>` after the installed profile is frozen; the generator then rebuilds all dependent IDs, references, and saved bytes. The current manifest remains `synthetic_only: true`, `no_installed_resources: true`, `public_command_execution: false`, and `configuration_parser_invoked: false`.

The script mirrors the accepted `code_text_metadata` rules locally because that legacy module imports `jsonschema`, which is not present in the locked minimal fixture environment. It preserves strict UTF-8, BOM/control rejection, CRLF-to-LF normalization, newline style, terminal-newline state, line count, normalized size, and normalized SHA-256.
