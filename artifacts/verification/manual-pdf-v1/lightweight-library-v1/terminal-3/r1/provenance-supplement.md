# Provenance supplement to independent review

This supplement corrects the provenance wording in `independent-review.md`; it does not replace or overwrite that review.

No T1 or T2 candidate in this run has Architect acceptance. The phrase “accepted T1/T2 files” in the earlier review means the immutable R1 handoff snapshots used as reproduction inputs, not Architect-accepted candidates. T1 R1 was explicitly rejected; T1 R2 and T2 R2 were later stopped with `ready_for_architect` handoffs, and remain unaccepted. The active run's `CURRENT.json` records the phase as `t1-r2-and-t2-r2-running-t3-r1-dependency-pending`.

## Exact modules used by the original reproduction

The original end-to-end reproduction used this namespace path order:

```text
.../terminal-1/r1/files/src/video_paper_wiki_research
.../terminal-2/r1/files/src/video_paper_wiki_research
.../terminal-3/source/src/video_paper_wiki_research
```

The loaded module `__file__` paths and SHA-256 values were:

| module | exact `__file__` | SHA-256 |
| --- | --- | --- |
| `light_compare` | `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-library-v1/terminal-1/r1/files/src/video_paper_wiki_research/light_compare.py` | `9e333f86b0bf42377704c3a587c3da5d470e1337f637a37e90d72613ec0d207d` |
| `light_context` | `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-library-v1/terminal-1/r1/files/src/video_paper_wiki_research/light_context.py` | `d889b26d1daba9c4f8df778c6fb54b6ecf37c610fa29f4e57d6fd6b591e5cf6e` |
| `light_knowledge` | `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-library-v1/terminal-1/r1/files/src/video_paper_wiki_research/light_knowledge.py` | `dfad2c978737e729d2d21c6d6e481ec13801078311ed7da1459fffedfb79f402` |
| `light_index` | `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-library-v1/terminal-2/r1/files/src/video_paper_wiki_research/light_index.py` | `ceac321f97c4820a2ddb0c5ec48231e7cfdf4e4d9f1e3f1ff46555d24011d9ef` |
| `contracts` | `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-library-v1/terminal-3/source/src/video_paper_wiki_research/contracts.py` | `22409784bca848ae7969d57f882fe8e9119d59bd3e29303f15ae75697a2d7658` |
| `light_qa` | `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-library-v1/terminal-3/source/src/video_paper_wiki_research/light_qa.py` | `d0ccf305d0dfd24128c45b22cb1f5ccbde8baf89b8d40ee95fdec798bc17d23b` |
| `light_workflow` | `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-library-v1/terminal-3/source/src/video_paper_wiki_research/light_workflow.py` | `e4f7f8880ab41d388ede82f4672e4b969f6ee147e794d02d59359bfa8ee57595` |
| `light_writing` | `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-library-v1/terminal-3/source/src/video_paper_wiki_research/light_writing.py` | `b5ee32cbae4242afd641b8f2e491a9ff38480411d9b76c872d53dc0b274115c9` |

The original review therefore applies directly to immutable T1 R1/T2 R1 plus the stopped T3 R1 source. It does not claim that those inputs were Architect accepted. Root's later R2 replay independently confirms that `[A,A,B]` silent deduplication and comparison-table double escaping remain in the R2 candidate; that is separate evidence from the R1 reproduction above.

## R2 distinction

T1 R2 is stopped and has handoff source hash `light_compare.py = f8f12e9e46104ba3e07c28bf08ea001f2564ac8fdd7a917acc4faf70a011aa03`; its source is under `/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-library-v1/terminal-1/source/`. T2 R2 was actively writing at the time of this correction and was not reviewed; no Architect-accepted T2 R2 handoff exists. No R2 file was substituted into the original R1 review, and the active T2 R2 code was not read or executed for this preflight.

The public `[A,A]` case is already closed by the minimum-size check; the remaining selection blocker is `[A,A,B]`, which silently becomes a two-paper selection.

## Validator command and environment

The successful validator invocation was exactly:

```text
PYTHONPATH=/Users/huangzhanpeng/.cache/uv/archive-v0/o4l3z62xfUQgdlPd .venv/bin/python /Users/huangzhanpeng/.codex/skills/.system/skill-creator/scripts/quick_validate.py .work/parallel/lightweight-library-v1/terminal-3/source/.agents/skills/video-paper-read
```

It returned `Skill is valid!`. The `.venv` interpreter was Python 3.13.13. The `PYTHONPATH` directory is the cached PyYAML 6.0.3 runtime containing `yaml/__init__.py` and `pyyaml-6.0.3.dist-info`; no dependency installation was performed.
