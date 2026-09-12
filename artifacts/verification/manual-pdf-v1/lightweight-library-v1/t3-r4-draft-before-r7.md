# T3 revision 4 — final nested-note integration and full acceptance replay

Dispatch only after `t3-r4-freeze.json` binds the stopped R3 handoff, exact
Architect-accepted T1 R4 and T2 R6 inputs, this packet and its prompt. Preserve
all prior source bundles and test results. Original contract/baseline and
eleven T3 owner paths remain unchanged. R3's substantive integration, parser,
Skill, documentation and installed-wheel requirements remain in force.

## Exact owner successor

T2 R6 corrects one integration gap: the shared live-paper classifier now permits
regular nested notes/code and empty directories while preserving unsafe-path
refusal. Archive's existing text/code limits and complete inventories remain;
native/replacement owned staging remains exact. T1 R4 is unchanged.

Verify all fifteen current imported files against R3's T1 R4/T2 R5 input bytes
before changing them. Replace only the three successor T2 paths named by the
new freeze using its accepted R6 bundle bytes; verify all fifteen resulting
imports against accepted T1 R4/T2 R6 manifests. Imported source/test files remain
read-only afterward. This is the explicit handoff for those three imports;
permission-bit changes needed to copy them do not grant backend authorship.
Never reimplement or modify any imported owner bytes.

Extend the existing synthetic actual-CLI pipeline, within T3-owned tests, so a
paper containing nested Markdown/code notes and an empty directory remains
visible and can be archived/restored with exact bytes/directories, and nested
old notes survive replacement in the old archive. Reuse the current backend
commands and preserve original source attribution. No main CLI feature rewrite
is expected. Correct only a demonstrated T3-owned integration issue; backend
issues must return to Architect. Keep malformed-JSON checks, actual library
commands, knowledge state transitions and compare/backup roundtrips active.

## Correct offline build environment

R3's first full-suite attempts produced 2539 passed and 33 fixture setup errors
on each Python version because the uv build resolver did not use the intended
cached backend. Keep those results as failures of their original attempts.
The dedicated installed helper understands `LW2_UV_CACHE`; the closure fixtures
inherit `UV_CACHE_DIR` directly. Root independently built the stopped delivery
baseline successfully, offline, with the following explicit existing cache.
No install/download or default environment change is needed.

For every final source/full/installed command, explicitly set:

```
PATH=/Users/huangzhanpeng/.hermes/bin:$PATH
UV_CACHE_DIR=/Users/huangzhanpeng/.cache/uv
LW2_UV_CACHE=/Users/huangzhanpeng/.cache/uv
UV_OFFLINE=1
UV_PYTHON_DOWNLOADS=never
PYTHONDONTWRITEBYTECODE=1
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
GIT_OPTIONAL_LOCKS=0
PYTHONPATH=<exact T3 source>/src
```

Use the existing locked Python 3.13.13 and 3.12.14 interpreters from COMMON,
short real `/private/tmp` basetemps/cache and uv 0.12.7. Do not use an old wheel,
skip failing fixture groups, alter baseline tests, or describe research/unit
subsets as a full suite. Run the complete repository `tests` suite on each
Python version against the final candidate. Preserve command exits and complete
counts, module provenance and the specific environment used.

Build a fresh final wheel and run actual console/module library operations in a
new isolated environment, verifying site-packages provenance and exact backend
bytes. The existing owned installed test may provide that evidence when run on
the final source with fresh temporary output. Keep defaults/dependencies unchanged.
Validate the updated Skill, and check docs against the final actual behavior.

## Handoff

Freeze new `terminal-3/r4` files/checks/report/handoff/ready. Include every
changed T3 owner file relative to original baseline, plus separate original
owner manifests and all fifteen accepted import hashes. Bind R3 input, R4
freeze, original contract, full suites and fresh wheel evidence. Use truthful
ready flags; set `architect_accepted=false`, `stopped_writing=true`, and stop.
Normal evidence write denial permits a complete source-local R4 bundle/location
report only; do not retry a denied write through another method.

Architect will independently check this exact stopped source, then run the
separate local three-real-PDF/current-model trial. Do not read its raw corpus,
authored documents or trial outputs. No Git/PR/CI, merge, new workers, external
messages, model/default changes, schema/catalog/Vault changes or human approval.
