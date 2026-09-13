# CODE proof cap review disposition — R11

Architect disposition of the R10 review, with one explicit bundle error-pointer
binding. All earlier contracts/reviews remain immutable. No schema/resource
generation or public implementation is dispatched by this record.

R10-RAW-CAP-CONTEXT-001 is not a conflicting semantic choice: R9 already fixes
the four error keys, and R10's table fixes the limit values. For clarity, the two
raw admission errors are exactly CODE_PROOF_LIMIT_EXCEEDED, exit code 2, with:

```text
request: {instance_pointer: "/input", limit_name: "max_request_input_bytes",
          limit: 65536, observed: 65537}
observe: {instance_pointer: "/input", limit_name: "max_observe_input_bytes",
          limit: 1048576, observed: 1048577}
```

These are counts of bytes actually read before the bounded reader stops. The
message remains fixed and source-free. A replaced or uncheckable retained edge
still causes the higher-priority unsafe-path refusal. Equal-to-cap admission
and oversized malformed JSON behavior remain as specified in R10.

R10-BUNDLE-CAP-DOMAIN-002's domain question is already answered by R4's saved-byte
identity rules and R7: input `manifest.json` must be a canonical saved
code-git-bundle envelope, and generated `bundle.json` is its byte-identical copy.
The word "raw" in "raw Git bundle" distinguishes acquisition mode; it does not
permit a second noncanonical manifest serialization. The byte domain includes
the entire envelope and its one final LF. Whitespace padding, duplicate keys,
noncanonical escape/number spellings or an extra final LF are not normalized
into an accepted manifest.

The bundle limit error pointer is now explicitly `/bundle`; its code remains
CODE_PROOF_LIMIT_EXCEEDED and its details have exactly:

```text
{instance_pointer: "/bundle", limit_name: "max_bundle_bytes",
 limit: <applicable bundle byte cap>, observed: <bytes actually observed>}
```

The applicable cap is the hard profile cap during initial bounded retention,
then the materialized request cap after validated limits are available. A
complete retained canonical manifest is measured by its full byte length. If a
bounded read stops at cap+1, observed is that measured prefix count; it does not
claim to know the rest of an oversized file. A hard-cap failure does not require
parsing an oversized request or bundle to discover lower caps. Once limits are
available, the lower cap applies before installation and before interpretation
of any yet-unvalidated bundle metadata. All complete saved envelopes are checked
again using their exact serialized length during pure workflow preflight.

This is the same byte-count domain for input and output: the output copy cannot
shrink or change the input manifest. Object body limits and ordinary observe
input limits remain separate. Bundle cap-1/cap/cap+1 vectors should use a lowered
materialized cap around a valid canonical manifest's measured size, avoiding
invented padding fields in its closed schema. Raw hard-cap overflow may use an
oversized malformed file to prove refusal before decoding. Assert the bound
pointer/limit/count, no installation, and existing final-lineage priority.

The R10 review artifact's reviewer.agent field names cursor_cli_preflight in
error. Architect assigned and received that review from the Progress Monitor,
cursor_lanes34_controller. This corrects attribution only and preserves the
original report; Repo Steward authored the separate R9 review. The remaining
public freeze dependency is the exact generated schema/profile set and its
independent resource/wire checks, followed by implementation verification.
