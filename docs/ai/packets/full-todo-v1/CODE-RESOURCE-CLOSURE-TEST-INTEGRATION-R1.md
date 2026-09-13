# CODE resource closure-test integration

This bounded Architect integration amendment follows the first full local
regressions of resource snapshot
`324a37b10e3053ad3e47f1af2a622832bb3fd502f07582b5d56e9a1c7c6a0c3b`.
Both Python versions reached the same generic closure-test failure at
`$defs/request_target/if` in the new common schema. Preserve that candidate and
both interrupted regression records. Neither is a completed full-suite pass.

The schema uses 22 conditional property overlays inside three closed object
definitions: request_target (if/then), git_stopped_at (two allOf if/then pairs),
and status_payload (eight allOf if/then pairs). These overlay nodes constrain
properties of their enclosing object. Closing an individual overlay would
reject the enclosing object's other declared properties or change the condition.
The existing global test already treats the three projection-runtime overlays
separately for this reason.

Authorize one additional product-test path:
`tests/contract/test_additional_properties.py`, owned by Architect for this small
integration change, with independent review before final candidate acceptance.
The original 14 resource candidate paths remain byte-identical. No resource,
generator, profile, kernel or existing schema change is part of this amendment.

The change must recognize only the literal new common-schema filename and the
22 exact paths above. Each recognized node must have exactly properties and,
for an if node, required. Every condition's required list must equal its
selector property names. The enclosing named definition must remain an object
with additionalProperties false; each overlay property must belong to that
parent's declared properties. Assert the exact observed overlay set so missing,
moved or additional open nodes fail. Keep every existing closure assertion and
projection/envelope exception unchanged. Never skip the whole common schema,
all conditional nodes, or all nodes without an explicit object type.

Review this amendment and the concrete test diff independently. Run the new
integration check plus existing resource/schema tests, then both full suites
with the existing pinned uv 0.12.7 explicitly on PATH. The first test runner
omitted that PATH entry, independently causing 33 installed-test setup errors;
correcting the runner does not authorize a product workaround. Use a new attempt
namespace and preserve the original logs.

Freeze all 15 candidate paths after review. The 11 packaged resource bytes and
profile digest remain unchanged, so wheel evidence on the previous 14-path
snapshot may support resource-byte parity if its exact scope is retained and
the test-only successor is verified explicitly. Local commit, remote delivery,
public CODE implementation and human acceptance remain separate steps.
