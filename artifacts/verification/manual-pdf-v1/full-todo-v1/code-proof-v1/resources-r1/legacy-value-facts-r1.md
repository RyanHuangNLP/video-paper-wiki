# CODE proof legacy value facts capsule R1

Status: read-only prerequisite capsule for the R1 resource-input freeze.
Reviewed at `2026-09-10T08:36:05.473Z` against accepted worktree
`.work/parallel/code-proof-v1/terminal-1/source`, HEAD
`4ab1830939cd41981983909763434d5612df6070`, tree
`22fc77a38704386eaad5ad9be8a9268f0a1a5392`. The worktree was clean when
read. This capsule only records the existing identity lexical rules and the
existing raw-source metadata helper. It does not authorize a source edit,
public API implementation, fixture repair, or public command behavior.

## Canonical paper IDs

`is_canonical_paper_id(value)` first does `raw = str(value)`. The public R7
boundary still has to enforce its exact-builtin-string and UTF-8-byte rules;
the coercion in this legacy helper does not authorize a wider public input
type.

The four canonical scheme checks use `fullmatch(raw)` with these exact source
patterns from `src/video_paper_wiki/identity.py`:

| scheme | source symbol | exact pattern | accepted canonical language |
| --- | --- | --- | --- |
| arXiv | `_ARXIV_CANON` | `^arxiv:(?:[0-9]{4}\.[0-9]{4,5}|[a-z-]+(?:\.[a-z]{2})?/[0-9]{7})$` | new numeric `arxiv:YYYY.NNNN[N]`, or lower-case old-style `arxiv:class[/subclass]/NNNNNNN`; no version suffix |
| DOI | `_DOI_CANON` | `^doi:10\.[0-9]{4,9}/[\x21-\x40\x5b-\x7e]+$` | lower-case `doi:10..../suffix` with no space and no ASCII `A-Z` in the suffix |
| OpenAlex | `_OPENALEX_CANON` | `^openalex:W[0-9]+$` | `openalex:W` followed by one or more decimal digits |
| PDF digest | `_SHA_CANON` | `^sha256:[0-9a-f]{64}$` | `sha256:` followed by exactly 64 lower-case hexadecimal digits |

The DOI suffix class is exactly `[\x21-\x40\x5b-\x7e]`: printable ASCII except space and `A-Z`. Canonical DOI acceptance has one additional fixed-point condition. After the sealed canonical check (`_DOI_CANON.fullmatch` plus ASCII/NFKC-casefold equality and no Unicode uppercase), the helper calls `normalize_doi(raw)` and accepts only when `normalized == raw`. `normalize_doi` strips the candidate, recognizes the seven case-insensitive DOI aliases (`https://doi.org/`, `http://doi.org/`, `https://dx.doi.org/`, `http://dx.doi.org/`, `doi.org/`, `dx.doi.org/`, `doi:`), applies NFKC then `casefold()` to the body, and rebuilds `doi:<body>`. Thus a canonical DOI is a fixed point of the normalizer and of NFKC/casefold; an upper-case suffix, non-ASCII spelling, or terminal newline fails the canonical check.

The source lines establishing these facts are `identity.py:29-43`,
`identity.py:122-145`, and `identity.py:256-269`. The current helper accepts
versioned and aliased arXiv/DOI inputs only through the separate normalizers;
those aliases are not canonical paper-ID values.

## Raw source text metadata

The existing `code_text_metadata(payload)` in
`src/video_paper_wiki/code_evidence_contracts.py:43-75` returns exactly four
keys, in insertion order:

```text
{
  "newline_style": str,
  "ends_with_newline": bool,
  "line_count": int,
  "normalized_sha256": str
}
```

`newline_style` is one of `none`, `lf`, `crlf`, or `mixed`. It is classified
from the raw bytes: `crlf = payload.count(b"\r\n")` and
`lf = payload.count(b"\n") - crlf`; both positive gives `mixed`, then CRLF-only
gives `crlf`, LF-only gives `lf`, and no LF gives `none`. The helper first
normalizes strict UTF-8 bytes by changing CRLF to LF. It rejects an initial
UTF-8 BOM, invalid UTF-8, forbidden controls (including U+2028/U+2029), and a
bare CR. Consequently `ends_with_newline` and `line_count` are properties of
the normalized LF bytes, while `newline_style` retains the raw newline-style
classification.

The line-count boundary is the exact implementation at
`code_evidence_contracts.py:59-62`:

```python
if not normalized:
    return 0
return normalized.count(b"\n") + (not normalized.endswith(b"\n"))
```

Therefore empty bytes have zero lines; non-empty bytes with no LF have one
line; normalized bytes ending in LF have one line per LF; and normalized bytes
without a final LF have one additional final line. CRLF is counted after its
conversion to LF. The helper's raw-byte gate is `_bounded_bytes` in
`capture_contracts.py:124-128`: it requires `isinstance(payload, bytes)` and
rejects lengths above `MAX_BYTES = 67108864` (64 MiB).

R7 names a five-key wire `TextMetadata`:

```text
{normalized_size_bytes, normalized_sha256, newline_style,
 ends_with_newline, line_count}
```

The legacy helper does **not** return `normalized_size_bytes`. R7 defines that
value as `len(normalized)` after CRLF-to-LF only. A future public layer must
derive and validate that extra field without changing the legacy helper or
silently treating the four-key helper result as the complete R7 wire object.
The existing cap is sufficient for the proposed 8 MiB raw profile cap
(`8,388,608 <= 67,108,864`), subject to the public layer's own byte-budget and
exact-type checks.

Dual locked-Python probes confirmed the same values on Python 3.12.14 and
3.13.13. Representative results are:

| raw bytes | style | ends | lines | normalized SHA-256 |
| --- | --- | ---: | ---: | --- |
| empty | none | false | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `a` | none | false | 1 | `ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb` |
| `a\n` | lf | true | 1 | `87428fc522803d31065e7bce3cf03fe475096631e5e07bbd7a0fde60c4cf25c7` |
| `a\n\n` | lf | true | 2 | `a7da489976d0047490617adb4f7a1f27f7af8b52a5176fd002ffe471863520ab` |
| `a\r\n` | crlf | true | 1 | `87428fc522803d31065e7bce3cf03fe475096631e5e07bbd7a0fde60c4cf25c7` |
| `a\r\nb\n` | mixed | true | 2 | `911169ddaaf146aff539f58c26c489af3b892dff0fe283c1c264c65ae5aa59a2` |
| `a\r\nb\r\n` | crlf | true | 2 | `911169ddaaf146aff539f58c26c489af3b892dff0fe283c1c264c65ae5aa59a2` |

## Bound source evidence

The JSON companion records byte sizes and SHA-256 values for the accepted
source, direct helper dependencies, R7, and the earlier interface-facts review.
No source, test, schema, profile, Git, provider, or runtime file was modified
for this capsule. Exact-string enforcement, public UTF-8 byte budgets,
`normalized_size_bytes` emission, and all semantic identity/replay checks remain
later public-layer obligations.
