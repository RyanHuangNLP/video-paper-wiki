# SOURCE-PUBLICATION R5 — command-tree fixture completion

Read with unchanged R2, R3 and R4. This amendment adds only
`tests/fixtures/contracts/agent-safe-command-tree.v1.json` to the root-owned
implementation allowlist. The original 26-path allowlist omitted this existing
complete CLI leaf inventory. `tests/contract/test_agent_command_tree.py` requires
an exact match with the parser, so the three already-authorized source-publication
prepare/inspect/audit leaves must be added to the fixture. Preserve all prior
leaves, the exact-set test and forbidden-command checks. No production interface,
schema count, permission, authorizer, base-catalog table, or human gate changes.

The successor allowlist has 27 paths. R4 freeze and original review evidence
remain unchanged history. Root is explicitly authorized to make this fixture-only
addition under the existing local implementation ownership; Repo Steward checks
its exact scope before candidate delivery. All other R2/R3/R4 requirements stand.
