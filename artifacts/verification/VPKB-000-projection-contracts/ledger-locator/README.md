# Ledger locator revision 1: local evidence

This is the bounded codec slice, not acceptance of complete projection inputs,
assessment history, SQLite, generation, VPKB-000 or a human gate. The baseline is
`208c206801214bb8f6e2f58f995ad7755ce87332`. These observations describe a
working-tree candidate before its next commit; new candidate CI is pending.
Historical runtime CI in the parent directory cannot be inherited by this slice.

[Local results](local-results.json) bind the frozen revision 1 contract
`493fc3d135141512c7956f3729726ae72febbb1a34cc8cd5669add96af16e191`
to 288 source inputs, snapshot
`b689ce10e8325ee430b9a893bf5da54a9f6a2f69b59d2e4dedbb76dca7e30fed`.
Both Python 3.12.14 and 3.13.13 passed 1464 tests with zero failures/errors/skips
and exit 0; before/after source snapshots match. These are two-point observations,
not continuous monitoring. Fresh offline wheel build/install and isolated `-I`
smoke passed: 18 schemas and the independent locator vectors. The wheel digest
is recorded; the wheel binary is deliberately not copied here.

[Independent review](independent/vpl-steward-review-final.json) records 54 checks
and a separate 130-test codec/identity run. Ten positive and 21 negative vectors
were generated before reviewing Builder output, using stdlib serialization over
fixed ASCII keys and IEEE-754 bit decomposition for rational expectations, not
the implementation under test. Checks include complete 65536-byte UTF-8 wires,
65537-byte refusal, canonical spellings, exact ratios, strict types, phase/error
pointers, aliases and a warmed-registry no-I/O probe. Immutable packaged schema
loading is an allowed cold-registry exception. These are bounded checks, not an
exhaustive proof over all possible objects.

[Builder evidence](builder/vpl-candidate.json) records the four implementation
files and a 242-test targeted run. [Public CLI commands](public-cli/commands.json)
contain nine operations at upstream pin `9f8c1199047eac2c3828496279fbb7ba9540b90b`:
eight exit 0; the deliberately unsupported upstream `uncertain` relation exits 2.
The valid `context` wire is byte-preserved in the canonical claim ledger and
round-trips to project `uncertain`. Steward audited these existing artifacts;
no second CLI replay is claimed. The before/after inventories contain the same
201 upstream files. Coordinates and the derived-artifact fixture are synthetic:
this does not prove extraction, a complete artifact inventory, record/receipt/head
closure, scientific correctness, a real Vault operation or human authorization.

The specification notes are historical **draft** reviews. The Steward note's
`e0afd75...` draft SHA is preserved, not relabelled as the frozen `493fc3d...`
contract. Final implementation review and local results bind the frozen SHA.

[Archive manifest](archive-manifest.json) distinguishes each original byte hash
from its archived hash. `<REPO>`, `<USER_HOME>` and `<TMP>` replace local paths.
Plain logs additionally remove trailing spaces/tabs and excess blank EOF; JSON
numbers and wire contents are unchanged. Embedded log/source/runner SHA fields
still refer to the originals. [JUnit summaries](junit-summary.json) retain raw
XML hashes and counts only; XML including hostnames is deliberately omitted.
Original logs, XML, scripts and artifacts remain under the original temporary
paths. Neither archive manifests nor test-source snapshots claim a future commit
hash or include their own checksum.

The archived suite/wheel/probe scripts retain the original algorithm but use
path tokens, so they are reviewable command records, not ready-to-run scripts.
To replay them, make a temporary copy, bind `<REPO>` to the checkout and `<TMP>`
to a fresh short real temporary root, prepare the locked interpreters and tooling,
and supply the referenced source manifests/vector files at the recorded paths.
Do not blindly overwrite original evidence directories. Routine regression is
available directly from the repository with its README environment recipe:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_ledger_locator.py tests/test_ledger_locator_upstream.py tests/unit/test_identity.py tests/contract/test_identity.py --basetemp=/private/tmp/locator-replay-new
```

The public test requires the already prepared pinned submodule; pytest does not
download it. AF_UNIX tests in the full suite require normal local socket access.
Network setup, fixture approval tokens, and passed tests confer no merge or real
Vault authorization.
