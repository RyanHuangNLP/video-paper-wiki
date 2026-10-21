# Assessment history revision 1: local evidence

This slice checks supplied complete assessment graphs and derives their heads.
It does not establish complete Vault enumeration, primary ownership, retained
artifact bytes, human identity/authorization, receipt or rollback integrity, or
core replacement transaction co-publication. Complete inventory, SQLite,
generation and VPKB-000 remain open. No merge or human-gate action is authorized.

[Local results](local-results.json) describe a working-tree candidate based on
`3e2bebb1d50928a7af95e07b4868bdbe8113cd0b`, under frozen revision 1 SHA
`ff7e7830d9931c52c447a2a95818dca091cb6d5bc97184d1be1103072ecf44cb`.
The 292-file [source snapshot](local/source-files.json), SHA
`3564cd9e769825c6190fc4c03d93655bd2deed2b022ef752762c51244b7f41ae`,
matched before/after both full suites and fresh offline installed-wheel checks.
Python 3.12.14 and 3.13.13 each passed **1596 tests**, zero failures/errors/skips,
exit 0. The new 18-schema wheel passed inherited capture/facade/runtime/locator
smoke plus 29 positive and 38 negative independent history vectors. Its SHA is
`23d40bf7676eeb631e1b8cb0fe4e7fc8c268ccfba529a2e625a2618f43d8fa15`;
the binary is not included here. [Architect local review](local/architect-review.json)
is separate from the future exact-commit CI decision. Prior locator acceptance
in the adjacent directory is historical and cannot be inherited by a new head.

[Independent preparation](independent/vph-steward-preparation.json) fixed all
expected claim/event IDs, raw-text hashes, evidence fingerprints and head maps
before reading/importing Builder's implementation. The generator uses explicit
identity formulas and stdlib JSON over ASCII keys; existing identity/schema were
only secondary controls. Coverage includes every permitted human state edge,
old/current/returned fingerprints, raw text versus normalized identity, display
exclusions, duplicate evidence, Gregorian UTC spelling, exact UTF-8 limits and
an 801-event chain. The unchanged vectors, Python-only adversaries, graph,
alias, safe diagnostic and warmed no-I/O controls total **85 passed**; a separate
history/identity/prospective run passed **184 tests**. See the
[final independent review](independent/vph-steward-review-final.json).

[Builder candidate](builder/vph-candidate.json) identifies exactly three new
implementation/test/fixture files and **290 passed** targeted tests. Its stdlib
[golden generator](builder/vph-builder-generate.py) is retained for review.
The source freeze leaves existing identity, JCS, schemas, prospective, runtime,
locator, dependency and CLI behavior unchanged. Old per-event schemas may still
accept human no-ops; this newly frozen whole-history profile rejects them.

The two specification reviews retain the original draft SHA `00e928ec...`.
The [freeze record](spec-review/vph-freeze.json) documents the header-only change
to frozen `ff7e7830...`; old review observations are not relabelled. Synthetic
cyclic graphs are tested separately from hash identity: the end-to-end malformed
cycle has invalid IDs and fails identity; the real graph routine's structural
control uses explicitly synthetic IDs, not a claimed hash fixed point.

[Archive manifest](archive-manifest.json) distinguishes original and archived
byte hashes. `<REPO>`, `<USER_HOME>` and `<TMP>` replace local paths. Plain logs
also strip per-line trailing spaces/tabs and excess blank EOF; internal content,
JSON numbers and original digest fields remain unchanged. JUnit XML is omitted
to avoid publishing hostnames; [JUnit summaries](junit-summary.json) retain
original XML hash, size, time and counts. Original temporary files remain intact.
Two snapshots establish before/after equality, not continuous monitoring.

Archived scripts retain historical algorithms with path tokens and are not
claimed as directly runnable or executed after normalization. To replay them,
make temporary copies, bind tokens to a checkout and fresh short real temporary
root, restore required manifests/vectors, and prepare the locked interpreters and
tooling. [External input references](external-inputs.json) name and hash the
previous locator smoke and real runtime fixture bytes inherited by wheel smoke;
old directories are not copied again. Do not overwrite original evidence.
Routine repository regression uses its existing README setup recipe:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_assessment_history.py tests/contract/test_prospective_validation.py tests/contract/test_identity.py tests/unit/test_identity.py --basetemp=/private/tmp/history-replay-new
```

Immutable packaged schema loading is the only permitted cold-registry I/O
exception. Full tests may need normal local AF_UNIX access. No network download,
upstream script, parser/model or real Vault action is part of this pure API.
