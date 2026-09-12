# Discovery provider target notes R1

Design-only companion to DISCOVERY-EXPANSION-DESIGN-R2. Checked 2026-09-09.
These notes establish documented target syntax, not successful current API
execution. The R2 design's generic "references filter" should become the
documented cites filter for incoming citations at contract freeze.

## Fixed target profiles

- OpenAlex lookup: /works/W<digits> or /works/doi:<canonical DOI>.
- OpenAlex incoming citations: /works?filter=cites:W<digits>.
- OpenAlex outgoing or related IDs: first retain referenced_works/related_works
  from a singleton observation; then request a bounded explicit batch with
  /works?filter=openalex:W<digits>|W<digits>. Regenerate from canonical IDs; never
  follow a supplied cited_by_api_url, PDF location or arbitrary response link.
- Topic: /works?search=<encoded frozen query>.
- Project and arXiv-only lookup: platform Web query descriptions; there is no
  invented project endpoint or direct arXiv singleton capability in this profile.

All list targets use explicit per_page, fixed top-level select fields, and
sort=cited_by_count:desc for citation/ID lists or relevance_score:desc for
topic search. The installed validator checks exact regenerated encoding.
Cursor continuation is restricted to topic/citation lists. Batched explicit
IDs do not use a cursor; only another explicit bounded unseen ID slice can
continue references/related material. Every slice is charged as a new request.
An OpenAlex response to batch IDs may omit missing IDs; record requested IDs
and observed IDs distinctly rather than interpreting omission as not-found
or producing manufactured title metadata.

Proposed select string:
id,ids,title,publication_date,cited_by_count,authorships,locations,referenced_works,related_works
The normalized schema need not retain every field in these responses. It records
only supplied visible facts with exact observation provenance and unavailable
markers. No raw-byte hash, model quality score or complete-source claim follows
from a select projection.

## Primary sources

External ID singleton routes are documented in
[Get Singleton](https://help.openalex.org/api/get-single-entities/).

Filter combination and bounded OR are documented in
[Filter](https://help.openalex.org/api/filtering/).
Incoming citations and outgoing-reference filter semantics are documented in the
provider's [filter-works source](https://github.com/ourresearch/openalex-docs/blob/main/api-entities/works/filter-works.md);
its [citation recipe](https://github.com/ourresearch/docs/blob/main/guides/recipes.mdx)
also shows the OpenAlex-ID batch and cites forms. These were visible in indexed
primary-source results; no current backend response was available to validate
those two filters independently.

Use the current [:desc sort syntax](https://help.openalex.org/api/sorting/)
and [top-level select projection](https://help.openalex.org/api/selecting-fields/).
Do not silently copy the OpenAPI description's different "-field" convention;
the target profile fixes one documented syntax.

The [work attribute dictionary](https://help.openalex.org/data/works/attributes/)
describes identifiers and neighborhood arrays. DOI may denote the published
version; arXiv in a location is not automatically same-work evidence.
The [citations explanation](https://help.openalex.org/data/works/citations/)
makes indexed matches distinct from the full bibliography.

## Observed access limits in this session

The Web tool rejected two bounded api.openalex.org list-read URLs as
"not safe to open (non-retryable error)". No response status, headers, result
payload, key requirement or successful API read was observed. This is a host
tool result, not a claim that OpenAlex itself refused access. It is not an
auto-review denial and no permission question is pending.

Old docs.openalex.org Work URLs redirected to the new help homepage. One indexed
openalex-help content/api/works.md GitHub URL returned 404; its raw counterpart
returned cache miss. Do not use those missing pages as current complete filter
documentation or put fetched live payloads into test fixtures. The official
filter-works/recipe search results support the proposed syntax above.

After exact profile freeze, a separate held-out trial must use actually
available host tools and persist success or capability_unavailable honestly.
The Python implementation remains entirely offline either way.

