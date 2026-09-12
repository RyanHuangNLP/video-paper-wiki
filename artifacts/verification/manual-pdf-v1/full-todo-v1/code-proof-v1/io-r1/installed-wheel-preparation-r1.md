# Installed-wheel preparation for the retained I/O candidate

This is a preparation checklist for the future I/O candidate. It adapts the
accepted `foundation_wheel_probe_r1.py` flow; it is not a run record and does
not authorize a build, install, source change, or acceptance.

## Pins that the future run must receive explicitly

The run must require command-line (or an equivalent immutable input record)
values for all of these items and refuse to infer a missing value:

- the I/O candidate path, byte size, SHA-256, product snapshot SHA-256,
  source root, baseline head/tree, and the exact
  `CODE-PROOF-IO-freeze-r1.json` path, size, and SHA-256;
- the wheel path, byte size, and SHA-256, plus its `RECORD` digest/contents;
- the accepted foundation `code_proof_resources.py` source byte pin and the
  eleven frozen resource pins.

The current I/O freeze supplies the preparation baseline only: source root
`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/code-proof-v1/terminal-1/source`,
head `d440c7aaebb4dcc2c52cab719b0d73347a41493f`, tree
`3dcff27982242ac4edbf0473e4271a91535d1b0f`, and freeze SHA-256
`267cd82f8dccb673eb07bdaabddcb4de0c4a38ba6fcd8055474c11e5dca9ad07`
(571899 bytes). These values must be rechecked against the future candidate;
they are not a substitute for candidate or wheel pins. The historical
foundation wheel SHA-256 `51ed433d7cccbe9c4d93c103c9d3b7cfa1bbc37f8af1440f017f98c617b62629`
must not be reused as the I/O wheel pin.

The candidate must identify exactly the two frozen product paths:
`src/video_paper_wiki/code_proof_io.py` and
`tests/unit/test_code_proof_io.py`. Before any installation, verify their
source bytes against the candidate rows and verify that the source checkout
has the pinned head/tree and no other product changes.

## Two isolated runtime runs

Run the same acceptance body independently with both locked interpreters:

- `/private/tmp/l4r5.s54ypl35/locked-312/bin/python`;
- `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python`.

For each runtime, create a new temporary install target and an unrelated empty
working directory. Install the explicitly pinned wheel with the locked uv
`/Users/huangzhanpeng/.hermes/bin/uv`, offline and without dependencies, into
that target. Invoke the interpreter as `-I -B -` from the empty directory.
Remove source checkout, `src`, build-copy, wheel, and editable-install paths
from the child `sys.path`; then assert every imported package/module origin is
inside the fresh install target. A missing install, an editable/source import,
or an origin outside that target is a refusal, never a fallback.

## Installed bytes and origin checks

Before importing, inspect the wheel `RECORD` and the installed tree. Assert:

1. `video_paper_wiki/code_proof_io.py` is byte-identical to the two-file
   candidate's `src/video_paper_wiki/code_proof_io.py`.
2. `video_paper_wiki/code_proof_resources.py` is byte-identical to the
   accepted foundation module pin; the I/O candidate may not silently replace
   that foundation.
3. All eleven frozen resources are byte-identical, with their exact size and
   SHA-256: the ten named `schemas/*.json` pins and
   `src/video_paper_wiki/profiles/code-proof-v1.json`. In the wheel these must
   occur at `video_paper_wiki/schemas/*.json` and
   `video_paper_wiki/profiles/code-proof-v1.json`, respectively, with no
   missing or substituted member.

The candidate's `tests/unit/test_code_proof_io.py` is source/test evidence for
the later full suites. It is not a required wheel member; do not manufacture a
wheel packaging requirement for tests.

Import the installed `video_paper_wiki.code_proof_resources` in this genuine
installed layout and call its origin-plan surface. Require `layout ==
"installed"` and require the package, schemas, and profiles directories and
all eleven records to resolve under the install target. Do not patch
`code_proof_resources.__file__` (or any other foundation origin input) for
this check. The result must come from the actual wheel layout, not from a
source-layout fixture or a patched module path.

## Scratch checkout and session seam

Keep session checks in a fresh short-lived directory under the approved
temporary boundary. The synthetic checkout must contain a retained `.git`
marker and a single-link regular `pyproject.toml` whose parsed project name is
exactly `video-paper-wiki`; it must not search upward or consult `PWD`. Keep
the fixture separate from the real checkout and real Vault, and record its
path only in the run evidence.

For the installed I/O module, exercise one fresh session setup and the
documented reuse path against that scratch checkout. Patch only the module's
`code_proof_io._getcwd` seam to return the scratch checkout spelling, retaining
and restoring the original seam around each case. Do not patch
`os.getcwd`, global filesystem/network/process functions,
`code_proof_resources.__file__`, or any other global/runtime authority. The
session must obtain the installed resource plan and retained eleven bytes
itself, validate the markers through its retained descriptors, and preserve its
fresh/reuse and cleanup semantics. Any source fallback, path-parent search,
global CWD patch, or resource-origin patch fails the check.

## Evidence boundary

Write separate evidence for each runtime containing the exact candidate/wheel
pins, install argv and target, empty CWD, package/module origins, all eleven
resource comparisons, marker/session outcomes, and cleanup status. Keep local
results distinct from remote CI and human review. A prepared checklist or a
passing foundation probe does not establish an I/O wheel result; acceptance
requires a future exact candidate and wheel, two fresh installed runs, and
the corresponding independent review.
