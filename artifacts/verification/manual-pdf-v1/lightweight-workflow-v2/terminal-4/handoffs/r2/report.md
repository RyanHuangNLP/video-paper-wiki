# T4 r2 needs_input — T3 r3 imported, official full/wheel gated

Builder checkpoint only. Not Architect acceptance. Not an official full-suite or new-wheel result.

## Done since r1

- Received official T3 r3 from immutable `files/` (handoff==ready SHA-256 `d6424b577f3d375adc12e4aab16781fd9cff25a9bf60943c260720627b4a3087`). Nine allowlisted files copied; T1 r3 and T2 r4 bytes unchanged.
- Live workflow CLI: four former `importorskip` tests now run. After two T4-only assertion fixes (`LIGHT_SESSION_CONFLICT` needs a valid different QA document; `markdown_path` is workspace-relative), `test_light_cli.py` + `test_light_workflow_cli.py` + T3 three files: **75 passed, 0 skipped**. This is not a full suite and must not be relabelled as one.
- Current-session model trial on `inbox/arxiv-2204.03458.pdf` (not copied). QA session `2f75a9ebc6014e6e41e211d39b71483d9a1e0cf5c4fc94e03de3912ad6bd0b32` and writing session `0f61bd8877073e6818966a860c0eaf2585b25e6c6aa5c805b533f4f5a7ea60f7` completed into a spaced/parenthesis sibling directory. Joint href/page-anchor/slice/hash checks passed against live context/source. Bad complete: `INVALID_CITATION`, no output file.
- Real Bash and zsh README/quickstart substitutions now include live `workflow prepare`/`complete` (both shells exit 0).
- Real CLI refuse/output-protection: bad citation, session conflict (valid second QA document), edited output, source-edit `INDEX_STALE` + status `stale`, tampered import, repeat-add notes, `NO_RESULTS`. Existing user bytes preserved on every refuse.

## Owned source this revision

Only `tests/research/test_light_workflow_cli.py` changed versus r1 (two live assertion fixes). Other five owned paths unchanged. Imported files were not edited.

## Upstream finding (do not patch in T4)

T3 r3 `light_workflow.py` SHA-256 `73bc3982273189f739481473d786fea8499c626be9bf380c9b9178326cd729d0` still has the publication-order window already recorded by Architect (`lane3-final-r3/architect-rejection.json`). T4 replay of the same synthetic probe: control `ok=true/awaiting_model`; `last_staged_file_move` and `before_publish_hook` return `ok=true/status=OK/state=stale` and publish a new session. Expected per Architect repair note: `ok=false/INDEX_STALE`, `session_id=null`, no new session. T4 did not change T3 files.

## Not run / not claimed

- Official locked Python 3.13 full suite
- New offline isolated wheel (dual entry / new-module SHA / 26 schemas)
- `lane3-r3-acceptance.json` is absent. Historical 102/4, 117/4, and any prior wheel numbers are not current-byte results.

## Remaining

Official full 3.13 suite and one new offline wheel after `lane3-r3-acceptance.json` exists, or after a corrected T3 final if Architect withholds acceptance for the publication-order window. Then write a new revision with byte-identical ready/handoff and stop writing.
