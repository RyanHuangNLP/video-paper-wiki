# Public CODE acceptance preparation

This is the acceptance plan for the public command implementation after the
resource prerequisite. It is not a source allowlist, interface freeze or Builder
handoff. Bind the eventual implementation packet to the exact accepted resource
head and profile bytes. The source inventory is `public-code-integration-map-r1`
with its separate Architect corrections; neither document accepts public CODE.

## Observable command outcomes

Validate the five command leaves through the existing CLI result envelope and
the exact R7 success-data shapes. The resource test increment already owns its
ten schemas, profile, prepared fixture bundle and schema-count assertion; a
public increment must not silently take ownership of those paths or either
accepted kernel.

| Leaf | Required observable result |
| --- | --- |
| request | Validate ordinary input, materialize exact installed profile/limits, seal one request and return deterministic acquisition targets. |
| observe | Admit and validate complete acquisition inputs before new intent installation; retain raw evidence or explicitly weaker normalized evidence and return the complete observation/status payload. |
| status | Report the actual validated state, dependency list, retained references and next action without creating files. |
| config | Re-derive one selected target from complete retained raw evidence and store its exact JSON/TOML or explicit source-only evidence. |
| handoff | Re-derive every eligible target, reuse a validated path-ordered prefix and create only its missing JSON-record suffix. |

The output layout has four fixed files (`request.json`, `intent.json`,
`bundle.json`, `observation.json`) and three bounded directories (`objects`,
`configs`, `handoffs`). Raw observation copies the exact input bundle bytes.
Config and handoff filenames use SHA-256 of the logical ASCII target path.
Handoff creates no body copy: `source_body_path` identifies an existing retained
object body. Configs may be an arbitrary individually valid subset; handoffs
must be a path-ordered prefix; pending raw objects follow their separate OID
prefix rule.

## Independent acceptance groups

1. **Resource loading.** Use an explicit ten-schema registry and installed
   profile bytes, reject changed inventory/bytes or undeclared references, and
   prove source-checkout and installed-wheel behavior. Check exact builtin
   primitive types before identity or derivation. Preserve original source
   Unicode exceptions while enforcing metadata spelling rules.
2. **Ordinary input admission.** Exercise exact input caps before decoding,
   duplicate keys, floats/nonfinite values, invalid UTF-8/BOM/surrogates,
   trailing input and closed shapes. Omitted request limits materialize from
   the profile. Request input never gains a caller-supplied profile hash.
3. **Identity and binding.** Reject noncanonical saved bytes, wrong ce1 IDs,
   wrong kind/hash references and valid-looking resealed forgeries. Recompute
   all derived values from the retained source, never trust schema validity or
   an unchanged record hash alone. Cover both Git OID widths and wrong selected
   format with otherwise valid lexical OIDs.
4. **State replay.** Cover all six states, including both pending-raw-body
   situations; valid initial interrupted prefixes; missing dependencies;
   orphan derived records; forbidden slots/families; corrupt/non-prefix object
   or handoff sets; and empty/subset/complete config sets. Only valid prefixes
   can resume. Status remains read-only in every state and failure case.
5. **Retained paths.** Validate original input spelling before Path conversion.
   Apply the R2 resource clarification to input bundle components, keeping the
   output batch grammar separate. Test alias/symlink/type/mode/link refusals,
   input/output ancestor and descriptor identity conflicts, ancestor/marker
   replacement, and unchanged sibling authority. Do not chmod caller paths.
6. **All exits and race windows.** Exercise first and repeated scans, absent
   fixed slots, directory creation failures, conflicts and late appearances.
   Named ancestor/resource/input/output checks must survive both successful
   and exceptional exits with R6/R8 lineage precedence. Use persistent distinct
   replacement identities; never rely on inode reuse behavior for a test.
7. **Install budgets and order.** Prove each actual serialized file cap before
   first installation and preflight the whole missing-file sequence with
   `C + 2*N`; recheck at each temporary creation. Include validated prefixes,
   existing config/handoff files and live temporaries. Validate intent before
   observation caps; keep fixed input-cap precedence. No dropped evidence.
8. **Evidence strength.** Exercise normalized present/missing/inaccessible/
   unavailable branches and explicit limits on their eligibility. Raw mixed
   targets may leave a separately valid selected configuration. Whole-set
   handoff eligibility and required hosting assertions remain strict.
9. **CLI and zero egress.** Exercise the real installed entry point and existing
   envelope/error conventions. Public `vpwiki` does not acquire remote data,
   invoke Git, call a host tool, run subprocesses, import an operator/admin
   workflow, or write outside the approved `.work` boundary.

Use valid fixtures before one-field adversarial mutations; distinguish schema
shape checks from actual byte/identity/filesystem replay. Keep local fixtures,
real supplied host observations, remote CI and human acceptance separate.

## Delivery boundary

After Builder stops, freeze the exact public candidate, independently review
its ownership and behavior, run the affected tests and both locked full suites,
and verify installed-wheel operation. Record local acceptance against the exact
commit. New head or base changes require the corresponding renewed checks.
Remote publication, draft PR/CI, merging and real-data/human gates retain their
existing explicit authorization boundaries. This plan does not close the
pending source-publication permission question or the overall TODO ledger.
