# SOURCE-CATALOG R2 — cache and generation acquisition boundaries

Read with immutable R1 SHA-256
cf7767abc88bb2b3122daca13709df95aa80b4d4ea9a9c172c615e4f8ad6fe46.
This clarifies its existing IO and digest rules without adding owned paths.
catalog/source-catalog-v1.json is already an explicit R1 allowed production
resource. profile_sha256 is ordinary SHA-256 of that exact resource's UTF-8
file bytes, including its actual whitespace. The profile contains no self-hash,
no expected catalog digest and no build timestamp. Its format is closed and its
exact expected content is frozen alongside R1/R2; implementation cannot silently
change limits or tokenization by loading an arbitrary self-consistent profile.
The exact initial resource bytes are SOURCE-CATALOG-PROFILE-R1.json, SHA-256
3263bdc02f570d5d6fbd06aa3c8c7e0a6d796ecf80cf76f673e84aea0d3b83f8
(4376 bytes); implementation copies them byte-for-byte to the already owned
catalog/source-catalog-v1.json path. Missing optional legacy PDF charspan produces
UNSUPPORTED_LEGACY_RESOLUTION with reason legacy_charspan_unavailable; a present
invalid/out-of-bounds span or mismatching excerpt hash remains an evidence error.

## Cache state machine

States at the first observation are missing-parent, missing-leaf and present.
Read-only commands keep every successfully acquired ancestor descriptor and
record the first missing edge as (retained parent descriptor, exact child name).
They do not create any .work/batch/cache directory. On every exit the successfully
acquired edges must retain their identities and the missing edge must still be
absent. A subsequent foreign file or directory, even an empty directory or a
byte-identical catalog, is WORK_PATH_UNSAFE. No descendant of a missing parent
is claimed to have been inspected.

Build may use the existing retained batch-session creation for .work/<batch>.
It then acquires the dedicated source-catalog directory and fixed catalog.json
slot before projection. If source-catalog was observed missing, use exclusive
mkdir; EEXIST is a foreign collision. Retain the newly acquired directory and
verify its named identity immediately and at finalization. If catalog.json was
observed absent, only an exclusive no-clobber install may satisfy that state;
foreign post-observation appearance always refuses, including identical bytes.
An owned installation uses the descriptor/identity returned by the established
atomic installer, verifies its named inode/mode, and binds the final stamp/bytes
after the installer's temporary hardlink has been removed. Never replace the
original observed file identity with a later stat to excuse a replacement.

For present files require the usual regular-file, one-link, portable path and
private mode checks, retain full bytes and named edges, and compare against the
reconstructed canonical artifact. The dedicated source-catalog directory may
contain only catalog.json after a successful build, or be empty before one;
foreign siblings are WORK_PATH_UNSAFE. Retain/recheck its complete set on every
exit. The surrounding .work and batch sibling namespaces remain independent;
only their named edges are retained, not an ownership claim over other batches.
Temporary install files are private in-flight material removed by the installer;
they cannot become persistent allowed cache siblings.

## Generation acquisition

Capture the complete .py file-name sets in the installed video_paper_wiki
package and the complete schema-resource registry set, plus every traversed
directory identity. Retain package/resource named ancestors and each source or
resource file's identity/bytes through reconstruction and final verification.
On finalization enumerate the same scoped sets again: newly added or removed
.py/schema siblings, ancestor replacement and file-byte/identity changes refuse
WORK_PATH_UNSAFE. Normal __pycache__/.pyc activity is outside the declared .py
generation set and is not included in the digest. Non-Python package resources
are included only through the separate complete schema list and the fixed
taxonomy/profile resources. No CWD resource fallback and no live path reread may
escape the retained generation session.

Acquisition failure must still verify every reached directory/set/file or missing
edge before returning the original typed error. It does not claim to have captured
unread bytes. Final safety verification continues across all retained groups so
one ordinary parser/limit failure cannot skip a later named-edge check. The same
rule applies to retained Vault, generation and cache groups together.
