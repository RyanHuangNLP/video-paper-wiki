# CODE proof state and install amendment — R5 candidate

Architect candidate addressing CPI-R4-MODE-ABSENCE-004, CPI-R4-REUSE-INITIAL-005
and the observed installer mismatch recorded in architect-public-layout-followup-r4.json.
R2/R3/R4 and their reviews remain immutable. The current Builder owns only the
three-file Git kernel. This amendment is not an implementation dispatch: the
public schemas, exact retained-session API, error mapping, resource freeze and
independent review are still required.

## State classification and reuse

The initial complete output snapshot records every fixed slot and family, including
absence, before classification. A saved request has no acquisition mode. Only a
valid retained intent supplies normalized_text or git_objects mode. Validate
request/intent identity and dependencies before interpreting the following table.
Forbidden means refuse even for an empty regular file or empty directory; status
does not delete or reinterpret forbidden entries as pending work.

| Retained state | Allowed fixed files | Allowed families | Classification |
| --- | --- | --- | --- |
| Namespace absent or empty | none | none | No prepared request; public response wording remains in the wire freeze |
| Request only | request | none | Prepared, awaiting acquisition |
| Normalized intent, no observation | request, intent | none | Pending normalized observation |
| Complete normalized observation | request, intent, observation | none | Complete normalized evidence |
| Raw intent, no stored bundle | request, intent | none | Pending; bundle is needed |
| Raw bundle, no observation | request, intent, bundle | objects absent, empty, or a valid installed prefix | Pending; report exact missing bodies and observation |
| Complete raw observation | request, intent, bundle, observation | exact objects; optional valid configs/handoffs | Complete raw evidence with separately derived optional artifacts |

File basenames above abbreviate the exact .json slots in R4. Every other
combination refuses. In particular, bundle, objects, configs and handoffs are
always forbidden in normalized mode, before and after completion. No derived
family exists without a complete raw observation. No objects family exists
before the saved raw bundle. Empty derived families are allowed only after a
complete raw observation because a derivation command may have created its
directory before interruption. A complete raw observation requires all exact
declared bodies; its missing body is corruption, not an interrupted acquisition.
The raw object inventory includes the commit and root tree, so a complete raw
objects family cannot be empty.

Pending raw bodies must be exactly a prefix of the bundle's OID-sorted inventory,
with each present body byte-exact, safe and correctly named. Empty objects after
bundle is the zero-length prefix. A non-prefix subset refuses rather than being
repaired as an ordinary interrupted sequential install. This fixes the intended
meaning of R3/R4's matching observed prefix; it does not permit unknown bodies.
When the bundle is absent, its reference in intent cannot supply an invented
inventory. An observation without any required earlier dependency is corrupt.

Every reuse condition in R4 means initial-snapshot reuse. The target must have
been present in the command's first complete snapshot, with retained descriptor,
named identity, exact type/mode/link count and exact bytes. Those properties must
still agree at every later reuse check. A target first appearing after captured
absence refuses as a lineage failure even if its bytes are identical. This rule
applies to request, intent, bundle, raw bodies, observation and every derived file.
A file created by this command is tracked as its own authorized installation;
it is not retroactively classified as an initially reusable file.

Read-only status never repairs or creates a family. Repeated observe repairs only
the valid missing suffix after revalidating the exact bound external input as R3
requires. Config and handoff commands use complete stored evidence and do not
reopen the original external bundle. Existing per-path format and content
immutability continues to apply to derivations.

## Selected publication primitive and logical peak charge

Inspection of the current staging._atomic_install established that it creates a
sibling temporary file, publishes by no-replace hard link, then unlinks the
temporary name. It does not perform a same-inode rename. R4's rename premise and
current+N budget formula therefore cannot be inherited from that helper.

Select a new private CODE installer using an explicit no-replace hard-link
publication followed by owned temporary-name removal. It is implemented in the
future CODE retained-I/O module, not by modifying or blindly calling the legacy
installer. Use retained directory descriptors and os.link with
follow_symlinks=False; do not substitute a replacing rename or a copy operation.
The source temporary descriptor stays open through publication and cleanup.

The 134217728-byte cap counts logical file bytes under the one output
code-evidence-v1 namespace, including any live owned temporary name. It does not
count unrelated .work siblings, input bundle files, installed resources, process
memory or filesystem blocks. Those inputs retain their own independent caps.
Count two simultaneous names for the same inode twice: this is a conservative
logical-path budget, not physical storage accounting.

Let C be the sum of the current retained installed output file sizes, with no
active temporary name, and let N be the complete new serialized/raw payload size
for an initially absent final slot. Require C + 2*N <= max_output_peak_bytes
before creating the temporary file. The actual phases are:

| Phase | Additional logical bytes | Expected owned inode links |
| --- | ---: | ---: |
| Before temporary creation | 0 | 0 |
| Temporary payload complete | N | 1 |
| Temporary and final names both exist | 2*N | 2 |
| Temporary name removed, final installed | N | 1 |

An initially retained identical final file is reused with no new temporary name
and no additional charge. Every observed regular file's actual stat size is
charged before reading, including a pending/orphan entry that will subsequently
be refused. Unsafe types and unknown/per-file oversized names are refused before
reading their contents. No accepted result may omit their observed charge to
manufacture a budget pass. The final public error schema must preserve the
distinction between a budget refusal and a lineage failure.

Only the currently owned installation inode may temporarily have link count two,
and only while its recorded temporary and final names both reference that inode.
This narrowly specified live phase amends R4's general single-link rule; every
retained input, initially observed output and completed output must be single-link.
No pre-existing hardlinked file is made valid by this exception. One temporary
file exists at a time. A later command encountering a leftover temporary name or
hardlinked output refuses it; status never adopts or removes that entry.

## Required retained installer behavior before its API freeze

1. Revalidate all retained directory lineages, resource/input identities and
   scoped complete sets. Verify target absence again and apply the C+2*N cap.
2. Exclusively create one bounded private sibling name with no-follow flags and
   mode 0600. Record its returned descriptor identity immediately. Retain that
   descriptor; verify the named edge and exact single-link regular type/mode.
3. Write at most N bytes, handle short writes, and refuse zero-progress writes.
   Verify exact final size and bytes through the retained descriptor, fsync, and
   revalidate the temporary named edge plus all retained inputs before publishing.
4. Publish by one no-replace hard link from the checked temporary name to the
   initially absent final name in the same retained directory. EEXIST is a
   lineage refusal even when the new final has identical bytes. Never overwrite
   or adopt it. Verify both names and the retained descriptor have the recorded
   inode, exact bytes/mode and link count two before cleanup.
5. Remove only the command-owned temporary name after checking its recorded
   identity. Verify its absence and the final's retained identity/bytes/mode and
   single-link state, fsync the containing directory, then update the allowed
   complete-set snapshot. Perform all-exits retained-lineage validation.

The detailed implementation must surface cleanup failures; it cannot use the
legacy _unlink_at helper that silently swallows OSError. If a temporary name is
observed missing, replaced or unsafe, do not unlink the observed replacement or
claim successful cleanup. Preserve the failure evidence and refuse. After a
successful link, a subsequent exception may leave a verified single-link final
file as the allowed installed prefix once owned-temp cleanup succeeds; do not
roll back by unconditionally unlinking a possibly replaced final slot.

The forthcoming retained-session API must specify concrete observation checkpoints
for cleanup and all error paths. Retained descriptors and named revalidation do
not lock out unrelated filesystem writers; do not claim atomic compare-and-unlink
from a stat/unlink pair. A persistent changed named edge at an applicable final
check overrides a preceding semantic or write error. This amendment does not
declare an unimplemented all-exits path proven safe.

Before public implementation freeze, independent review must exercise target
appearance before link, temporary-name replacement, link-count change, short and
zero writes, fsync/link/unlink failures, directory replacement, unknown sibling
insertion, initial parse/size failures and cleanup failures. Check the exact
C+2*N boundary and each transient link phase. Bind those tests to the concrete
retained session and installer, with unchanged legacy helpers. The six closed
envelope schemas and their actual installed resource hashes remain separate
required inputs to that freeze.
