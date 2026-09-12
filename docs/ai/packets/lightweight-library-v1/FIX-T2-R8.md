# T2 revision 8 — round-trip the writer's UTF-8 member names

Dispatch only with the exact R8 freeze and Architect instruction. Preserve R7
and every earlier snapshot/review. The original contract and nine T2 owner paths
are unchanged. Only these two paths may change relative to stopped R7:

- `src/video_paper_wiki_research/light_backup.py`
- `tests/research/test_light_backup.py`

T3's installed integration exposed a supported-content gap: the stdlib ZIP
writer sets the UTF-8 language-encoding bit (0x0800) for non-ASCII member names,
but the raw deterministic-container parser currently requires zero flags in
both headers. A backup containing a Chinese or Greek note name can therefore
be created but refused by its own verifier/restorer. Changing fixtures to ASCII
does not resolve the user-visible defect. The contract permits safe UTF-8 names
and forbids encryption, compression, data descriptors and unsupported metadata;
the filename encoding bit is not encryption or a data descriptor.

Accept exactly the existing writer's filename encoding convention: flag zero
for ASCII names and exactly 0x0800 for UTF-8 names containing a non-ASCII
character. Validate decoded UTF-8 names and bind each local header to its central
entry, including the encoding flags. Reject every other bit, mismatched flags,
non-ASCII bytes without the required encoding bit, malformed UTF-8, and
noncanonical ASCII headers with the encoding bit. Keep all existing fixed
versions, timestamps, regular private attributes, size/CRC, contiguous-layout,
member order, duplicate/casefold, traversal and manifest complete-set checks.
Do not change the writer, generated ASCII archives, archive schema, filenames,
text policy or size limits; do not sanitize/rename/omit Unicode user files.
Do not broadly replace the raw parser with a permissive zipfile-only check.

Add synthetic public create -> verify -> restore roundtrips with nested Chinese
Markdown, Greek code-note names and an explicitly included outside-workspace
Chinese Markdown report. Verify exact member names and bytes, deterministic
same-snapshot reuse, and unchanged ASCII behavior. Add mutations of local-only,
central-only and both headers for encryption, data-descriptor and unknown bits;
invalid/missing UTF-8 flags; mismatched flags; malformed UTF-8 names. Verification
must be read-only and restore refusal must leave the destination absent and all
existing input bytes untouched. Preserve every existing negative assertion.

Run all three owned suites and the related native/index/workspace/workflow
regressions with the existing locked Python, exact source PYTHONPATH, offline
flags and short real temporary roots. Publish fresh terminal-2/r8 evidence with
all nine owner files, R7 input, R8 freeze/contract, actual command exits and
byte-identical handoff/ready. Only the two allowed files may differ from R7.
Stop afterward with architect_accepted=false. No T3/Git/PR/CI/Vault/merge,
dependencies/models or extra agents. If the normal evidence write is denied,
report a complete source-local bundle without retrying the denied copy.
