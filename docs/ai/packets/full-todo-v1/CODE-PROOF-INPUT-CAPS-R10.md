# CODE proof input and saved request caps — R10

Architect semantic supplement closing R9-INPUT-CAP-NAMES-008. R7's eight-field
`limits.public` map remains unchanged. R2–R9 and their reviews stay immutable.
This supplement does not dispatch public implementation or claim resource freeze.

The two ordinary metadata input caps are fixed parser admission constants:

| Ordinary command input | Fixed cap | Error limit_name | Error pointer |
| --- | ---: | --- | --- |
| request input file | 65536 bytes | max_request_input_bytes | /input |
| observe input file | 1048576 bytes | max_observe_input_bytes | /input |

These names are intentionally not materialized request-limit keys. They are the
two explicit exceptions to R9's phrase "corresponding materialized key". Neither
can be overridden by request data. Cap the raw bytes before JSON decoding and
before reading any embedded limits. Retained ordinary input reading is bounded
to cap+1 bytes; on excess, `observed` is that actual cap+1-byte prefix count. It
does not claim the unbounded file's total length. Do not read the remainder just
to make an error count larger. Refusal still passes through retained final
lineage verification, with the existing unsafe-path priority.

`limits.public.max_request_bytes` applies only to the complete sealed request
envelope, including canonical JSON encoding and the final LF. Its default and
hard maximum are 65536; it may be lowered, with no change to the fixed raw-input
cap. After successful ordinary input validation and full limit materialization,
seal the request and measure the saved bytes before any output installation.
An excess uses CODE_PROOF_LIMIT_EXCEEDED with exactly:

```text
{instance_pointer: "/request", limit_name: "max_request_bytes",
 limit: <materialized request cap>, observed: <complete serialized byte count>}
```

Input whitespace counts toward raw admission but is not retained in canonical
request bytes. Envelope metadata and materialized limits count toward the saved
cap even when absent from the ordinary input. Consequently a raw file that fits
its fixed cap can still fail its lowered saved cap. Passing either cap never
implies passing the other. Equal-to-cap fits; cap+1 refuses. Malformed input that
exceeds its fixed raw cap receives the raw cap error before a decoder error.

The same distinction holds for observe: max_observe_input_bytes is the fixed raw
metadata input cap; max_intent_bytes and max_observation_bytes apply to their
respective complete saved envelopes, in that order. max_bundle_bytes applies to
the separately retained raw Git bundle manifest, not to the ordinary observe
file or any individual Git object body. The five Git limits continue to govern
those bodies. Other public limits and the whole-install peak simulation from R9
are unchanged.

Resource generation must encode the exact eight lowerable public keys and the
two fixed input error labels without introducing two new request-limit keys.
Document the fixed constants in the new profile's frozen description; the final
resource packet still must bind the entire actual profile shape and bytes.
Required boundary vectors cover fixed request/observe raw cap-1/cap/cap+1,
oversized malformed JSON priority, whitespace-heavy ordinary input, and a valid
request under the raw cap whose complete envelope fails a lowered saved cap.
For each refusal assert no output installation and the exact bounded error
context; all original input and output retained-lineage checks still apply.
