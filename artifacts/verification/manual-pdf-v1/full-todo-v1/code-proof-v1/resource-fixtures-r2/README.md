# CODE public-wire fixture set R2

R2 is an additive correction to `resource-fixtures-r1`; every R1 byte remains preserved. It fixes only three shape issues identified by the independent R1 review:

* ordinary request inputs omit `profile_sha256`; saved request envelopes retain it because the installed profile supplies that field;
* raw intent bundle directories use canonical checkout-relative `.work/<batch>/raw-input` paths;
* raw body references, config/handoff stored paths, and handoff source-body paths use complete logical checkout-relative `.work/<batch>/code-evidence-v1/...` paths.

The physical fixture files remain under this directory's `saved/` and `success-data/` folders. Those locations are artifact storage only; the `.work/...` values are hypothetical logical paths in the public wire and do not claim that a public command installed files there.

The generator imports the accepted CODE worktree to use its JCS and Git verifier APIs. It makes no checkout changes, runs no public command, uses no network or Git process, and does not invoke a configuration parser. It refuses to overwrite any existing generated file, so rerunning it requires a fresh output directory.

Both raw cases use exactly three synthetic fixture objects (commit, root tree, and `config.json` blob) and pass `verify_code_git_objects` for SHA-1 and SHA-256. Configuration remains explicit `source-only`; no typed JSON/TOML result is claimed. The normalized branch contains only request, intent, and observation examples.

The profile hash defaults to an explicit 64-zero placeholder. Pass `--profile-sha256 <64 lowercase hex>` after the installed profile is frozen to rebuild all dependent IDs and references. The manifest records the actual `code_text_metadata` comparison for the 53-byte fixture under the project `.venv`.
