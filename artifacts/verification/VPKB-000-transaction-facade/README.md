# Transaction facade verification evidence

This directory first records the **pre-implementation compatibility investigation**
used to freeze transaction-facade-v1 revision 1, SHA-256
`a800f6aff5e1af839c112b1c4da1591c3081601da866b36af83755af8597ef67`.
The package baseline is `9d87dc67b949fc0cef5ac64b91a2d15aea8ec0fe`.
These observations are not local-suite, wheel, candidate-CI or Architect
acceptance of the new implementation; those must be recorded separately.

`failed-attempt1-results.json` separately records the first complete Python
3.12/3.13 suites: each had 1162 passes, two failures, no errors/skips, exit 1.
The two legacy security guards mistook the required `address_requests` field
for a network-client import because they scanned substrings. The snapshot was
272 source files, SHA-256
`493b88c84413045c8fec1a3dd073d30914cc8dc021d160567be8a8723d659fef`,
preserved in `failed-attempt1-source.json`. Both normalized failure logs remain
alongside their raw digests. A guard correction requires a new source snapshot
and complete retest; these failures are not relabelled as later successes.

`local-results.json` records the subsequent corrected working-tree acceptance:
Python 3.12.14 passed all 1239 tests in 76.20 seconds, and Python 3.13.13 passed
all 1239 in 72.81 seconds. Both processes exited 0, with zero failures/errors/
skips. This includes 144 independent facade probes, three portable upstream
fixtures and 75 source-policy regressions; both formerly failing checks remain
present and pass. Each run's complete before/after file map equals the 274-file
`source-files.json` snapshot
`437fb3bb0cc0c8baa26e93cb374b1814519771c3e0cd3df161e6ab24a466fa8e`.
Only that explicit inventory is fixed, not every task-status or evidence file.

The isolated wheel build, offline install and smoke each exited 0. The wheel
SHA-256 is `728e33caeb0dda83d4da6a43689a19aa312d1e0d3b82d6363b14d71815c7b52a`.
It loads 16 schemas and passes the new facade binding/byte/refusal/copy checks,
the earlier hash/locator vectors, 1365 text cases and 8116 line ranges. Doctor
correctly refuses a non-checkout directory and passes in an isolated minimal
checkout. The smoke uses synthetic supplied transaction evidence, not actual
upstream execution. `wheel-smoke.normalized.py.txt` preserves its source with
path placeholders; its distinct normalized digest and original executed-script
digest are recorded. Substitute paths and prepare an isolated wheel environment
before attempting a replay; the normalized file itself was not executed.

The bounded source-policy correction replaces substring checks with static AST
import checks; it does not hide the `address_requests` field or change production
contracts. The helper explicitly does not claim arbitrary Python data-flow or
OS sandbox coverage. Runtime/Vault boundary tests remain intact. New-candidate
remote CI and exact-commit Architect acceptance still need separate evidence;
local success is not merge authorization.

`behavior-results.json` preserves Builder's r4 and Steward's fresh steward1
replay. Both used runner SHA-256
`194ea887de43206cf5af9ccd993e1f9252d36e139308694f9d6bb13fa44d14ed`
against detached upstream pin `9f8c1199047eac2c3828496279fbb7ba9540b90b`,
version 2.1.1. The record contains the source-file digests, identical complete
upstream source-inventory digest, project source inputs and per-run raw artifact
digests. Source inventories were unchanged before/after; Steward also checked
that the pinned submodule remained clean.

Each run recorded 25 public CLI/script subprocesses: 23 exit 0 and two expected
exit 2 refusals (direct managed-metadata writes and incorrect canonical source
identity). Positive publication, expansion counterexamples and wrong-source-ID
tracks passed. Strict lint returned exit 0; chunk/BM25 retrieval found the fixed
fixture page. Result hashes/modes, ordered writes, head-last journal ordering,
canonical receipt/head bytes and repeat-render bytes were checked.

The two `*-commands.normalized.log` files retain command/environment/exit records
and stdout/stderr. Literal absolute checkout/run/investigation prefixes are
replaced with documented placeholders. These two logs and the two failed-attempt
logs also remove per-line trailing ASCII spaces/tabs and excess blank EOF lines;
internal whitespace/content remain intact. These are normalized copies, not original
logs: every original file has its raw SHA-256 and byte length in the JSON record,
and each normalized log has a separate digest. The historical runner itself was
a temporary investigation script; its portable successor belongs in
`tests/upstream`, with the permanent test source reviewed and hashed separately.

Limits remain explicit: the investigation used a fixture-only head and incomplete
Paper metadata/projection, synthetic provenance and upstream string locators,
and separately prepared navigation. It did not validate the complete project
record/structured-locator mapping, prospective ledger runtime, historical audit,
race/rollback, real Vault operations, human gates or OS-level network confinement.
No aggregate runner exit is inferred where only the per-command ledger and final
summary were retained. No merge or auto-merge is authorized by this evidence.
