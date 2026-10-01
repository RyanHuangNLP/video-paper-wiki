# P1-R2 flow scale, repository navigation, and experiment search_scope

Current producer behavior after this knife. Consumer limits are unchanged.

## Pairwise comparison is not always computed

`flow status` sizes the vault from `status_experiment_store()` before calling the full-vault matrix.

- Vault condition count ≤ 64: the matrix runs. `stages.compare.pairwise_state` is `computed`. `counts.pairwise` and `stages.compare.pairwise_count` are the judged pair count. `by_verdict` is the real summary.
- Vault condition count > 64: the matrix is skipped. `pairwise_state` is `not_computed_limit`. Both pair counts are `null`. `by_verdict` is `{}`. `missing_inputs` states the observed count and the 64 limit.
- Other D1/D2/S1 faces, selection, and recovery still run. Store damage, basis changes, and illegal associations still fail. Uncomputed pairs are never written as zero.

Legacy status documents without `pairwise_state` and with integer pair counts still validate. Documents that put `null` counts on `computed` (or omit the limit state) are rejected.

## Single-paper matrix and reading suggestions

On a vault above 64 conditions, `compare-matrix` and `survey-reading-build` bind one `--paper-id`.

Candidate scope, in order: explicit `paper_filter`, saved selection, otherwise known papers. Inside that scope the first paper in UTF-8 byte order with 1–64 conditions is used. Action id, reason, and argv name that same paper. Reason includes `单篇`.

If the scope has no such paper, those actions are omitted. `missing_inputs` names the blocked scope and says to bind `--paper-id` or `flow select` in a new batch. Formal conditions and saved selection are not rewritten.

Article prepare is omitted when selected papers together exceed the article context row limit (64). An explicit over-limit article prepare still receives the consumer's `ARTICLE_CONTEXT_LIMIT`. Experiment prepare for one eligible paper does not depend on matrix or article availability.

Vaults with ≤ 64 conditions keep the previous unfiltered matrix and reading commands.

## Repository links on reading pages

D1 stores `owner/repo`. Reading pages call `identity.repo_id` then `repo_page_slug`. Display text stays the stored repository. A relative link is emitted only when `wiki/code/<slug>.md` is already in the vault. A legal repository without that file shows `正式代码页尚未安装`. Illegal values stay escaped text.

## Experiment unknown `search_scope` paths

`search_scope.artifact_paths` accepts portable vault-relative paths and the existing `.raw/captured/...` and `.raw/derived/...` grammars from common. Other hidden roots, absolute paths, traversal, backslashes, control characters, and URLs remain rejected. Flow prepare still copies the real `source_digest.path` into unknown slots.
