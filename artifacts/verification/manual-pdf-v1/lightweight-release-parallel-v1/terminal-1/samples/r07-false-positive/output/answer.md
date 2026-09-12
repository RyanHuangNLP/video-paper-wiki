# r07-style false positive

The only source-looking href is the Markdown link. It keeps the papers/SHA/source.md
tail so the old substring verifier joins that tail onto the real workspace.
Resolved from this file's parent, the relative path does not exist.

[bad relative](../not-workspace/papers/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/source.md#page-1)
