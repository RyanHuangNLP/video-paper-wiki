# Git kernel R8: four test expectation corrections

Architect owns this small integration fix under the existing team agreement.
Grok Build remains the main implementation author. Its R7 response and normalized
source are preserved in the kernel verification directory. The normalized R7
candidate produced 40 passes and six parametrized failures on Python 3.13.

Only `tests/unit/test_code_git_objects.py` in the CODE worktree may change.
The exact preimage is 44,950 bytes, SHA-256
`60fc5308d14eed52ccc5387b68fd9fdc79d779ea23feffd4e73e4c406803575d`.

Change exactly four test expectation lines: use `limit` and `observed` as the
existing structured error detail keys, and use `invalid_oid_key` for both new
body-map key rejection assertions. These names follow `_limit_exceeded` and
`_validate_bodies_map` in the frozen production module. Preserve every check,
fixture construction, limit value, counter, production byte and static fixture.

Freeze the resulting three-file candidate. Repo Steward must independently
review the raw-to-normalized patch, these four corrections, scope, focused tests
and the prepared adversarial harness. Architect will replay both locked Python
focused suites, generated Git graphs and strict inputs before local acceptance.
No public push, real Vault operation, merge or human acceptance is included.
