# R09 delivery and exact-head acceptance

**ACCEPTED_MANUAL_PDF_LIGHTWEIGHT_WORKFLOW_AT_EXACT_HEAD**

R08 三项修复及本地 R09 review 通过，精确 70 路径候选已提交并推送：

- Commit: `0fcae592acb977c6b422e7de3b2c3e0cf79df5a0`
- Tree: `d2d592f25d2361d5cbcc3bf58ca441a2824c256b`
- Draft PR: [#95](https://github.com/RyanHuangNLP/video-paper-wiki/pull/95) → `integration`
- Live base: `08709894adfb20ec07e976783f0ba436d975b74f`
- Fresh [Tests run 34046551184](https://github.com/RyanHuangNLP/video-paper-wiki/actions/runs/34046551184), attempt 1
- Actual CI checkout: `6931e1a8f57ec4b0f22d004b92e9842e3bf48908`, parents exactly the base and delivered head; its tree equals the candidate tree.

| CI job | Result |
|---|---|
| macOS 15 / Python 3.12 | 2246 passed |
| macOS 15 / Python 3.13 | 2246 passed |
| Ubuntu 24.04 / Python 3.12 | 2246 passed |
| Ubuntu 24.04 / Python 3.13 | 2246 passed |

Architect independently retrieved the final PR/run/job/merge metadata and all four raw logs, checked the checkout ref/SHA and test counts, and rechecked candidate bytes and preserved evidence. The integration worktree and index are clean. The 70-path new commit remains distinct from the PR's inherited full base comparison.

The first push was blocked by automatic approval review because target trust had not been established. Read-only GitHub metadata then confirmed the configured repository is private, the authenticated account matches its owner, and has ADMIN permission. Following the user's trust confirmation, a standard reviewed retry succeeded. No alternate push channel or force operation was used.

PR #95 remains OPEN and DRAFT. It was not merged, marked ready, approved, or set to auto-merge. Prior local/failed evidence remains intact. Human gates and formal Vault publication remain separate.

下一步：审阅 PR #95，并按最终 quickstart 用自己选定的一份 PDF 试用和检查页码引用。无需再拆四个终端。若要进入 integration 合并阶段，需要在试用和审阅后另行明确合并指令。
