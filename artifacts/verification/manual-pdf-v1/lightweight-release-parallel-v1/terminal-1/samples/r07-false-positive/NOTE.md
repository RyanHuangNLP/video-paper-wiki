# Preserved Architect r07 false-positive

Old `verify_r06.py` `_verify_links` extracts `papers/<64hex>/source.md#page-N`
and joins that tail onto `--workspace`. It never resolves the full href against
`output.parent`.

This sample keeps a real workspace `source.md` with `<a id="page-1"></a>`, and a
Markdown file whose only source-looking href is:

`../not-workspace/papers/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/source.md#page-1`

Independent disk fact: that relative path from `output/` does not exist. The
workspace file does exist. The old verifier returns empty `errors`; the new
checker must return `ok=false`.
