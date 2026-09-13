# Paper analysis task (manual PDF staged extraction)

You are given a staged, unpublished PDF extraction context. The source is
provisional: it is not captured, not receipt-backed, and not published.

Do not invent a captured source ID, approval, license, or accepted claim.
Do not describe prospective `.raw/captured/...` paths as existing Vault records.
Do not ask the parser to invent claims.

Return one JSON object with exactly these fields:

- `context`: the supplied context reference `{id, sha256}`
- `generator`: `{model, runtime}` where each is `{value, identity_source, reason}`
  with `identity_source` one of `platform_reported`, `self_reported`, `unknown`
- `generated_at`: UTC `YYYY-MM-DDTHH:MM:SSZ`
- `prompt_sha256`: SHA-256 of this exact task prompt (prompt bytes + LF +
  canonical context data excluding `prompt_sha256`)
- `transport_draft`: object whose fields mirror `video-paper-wiki.paper-analysis-draft.v1`
  except `schema` is `video-paper-wiki-research.paper-analysis-transport.v1` and
  every `claims[].locators[]` entry is a canonical `vpwiki-locator-v1:` wire
  string copied unchanged from the supplied context blocks

Requirements:

- `paper_id` equals the context `paper_id`
- at least one claim, and every claim has at least one locator
- every claim `assessment` is `provisional`
- `claim_id` values are the canonical `clm-` identities for the paper subject
  and claim text
- locators are drawn exactly from the supplied blocks; do not add, alter, or
  invent source, path, or ref values
- keep all source fields prospective until later admission
