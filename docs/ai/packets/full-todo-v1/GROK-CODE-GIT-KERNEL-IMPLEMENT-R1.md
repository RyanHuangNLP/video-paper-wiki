# Grok Build: implement frozen CODE Git kernel R1

You are the main implementation Builder selected by the user: Grok Build CLI,
exactly grok-4.6 with xhigh reasoning. Architect has now frozen this bounded
implementation. Implement it, run its scoped tests, report the actual result,
then stop writing until another explicit Architect packet. This is not a
readiness-only review. Do not change models or spawn subagents.

Your source working directory is exactly:
`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/code-proof-v1/terminal-1/source`

Read these Architect-owned files at the absolute root (read-only):

- `/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/packets/full-todo-v1/CODE-GIT-KERNEL-freeze-r1.json`
- `/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/packets/full-todo-v1/CODE-GIT-KERNEL-R1.md`
- `/Users/huangzhanpeng/python_code/video-paper-wiki/docs/ai/packets/full-todo-v1/CODE-GIT-KERNEL-CLARIFICATIONS-R2.md`

The frozen source baseline is 8728aafc9aa7af5caf90d60bfa6ab2ba89419f75,
tree cefcd1be9797d1f4202153d7b9dc4ee1d8423f14. Steward and Architect already
verified the clean worktree and absent three allowed paths. Do not use the older
root checkout as your production baseline. Historical root coordination sections
do not supersede this new exact ownership/freeze.

You may create only these three files relative to your source directory:

1. `src/video_paper_wiki/code_git_objects.py`
2. `tests/unit/test_code_git_objects.py`
3. `tests/fixtures/code-git-objects-v1.json`

Copy the third file byte-for-byte from:
`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/kernel-r1/independent-git-fixture-v1.json`
Its SHA-256 is b8936db0a65d58d533016840e3d7cfbc686f819b240c812207e73638165955f0
and size is 52532 bytes. It contains independently generated synthetic Git SHA-1
and SHA-256 objects. Do not modify those bytes or invoke Git to regenerate it.
Each format has all_objects and cases. Map the fixture fields type/size to the
contract record fields object_type/body_size_bytes, select required_object_oids
per case, and decode body_hex to raw bodies for tests. all_objects includes
parent commits and unused objects: valid cases deliberately exclude them.

Implement all API, strict primitive validation, budget ordering, Git framing,
commit/tree parsing, deterministic path walks, complete consumed-set equality,
ten closed error codes and exact output shapes in the two frozen contract files.
Keep the module pure and standard-library-only. Important points already settled
by Architect: no raw bytes in the returned proof dict; no caller-framing parser;
missing stopped_at.name_hex retains the attempted ASCII component; only its mode
and oid are null. CODE_GIT_PROFILE_LIMITS is the specified MappingProxyType.
Every declared tree is syntax checked once even if later rejected as unused.
Do not fabricate a hash-valid self-referential Git graph with mocked hashes.

Read your source README testing recipe and pyproject.toml as needed. Existing
locked runtimes are `/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python`
and `/private/tmp/l4r5.s54ypl35/locked-312/bin/python`; verify each executable and
version before reporting.
Do not install dependencies. Set PYTHONPATH to your source `src` directory so
testing imports this new worktree. Use PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 and a
short real /private/tmp directory for --basetemp and cache_dir. Run the new
focused test file on both available locked Python runtimes. Full repository
suites and the installed-wheel acceptance belong to complete CODE integration,
not this three-file slice. Test subprocesses may run pytest only; production and
tests must not invoke Git, network, resource loaders or filesystem operations
inside a kernel call. Normal fixture reads before guarded pure calls are allowed.

Write one development brief here:
`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/full-todo-v1/code-proof-v1/kernel-r1/builder-development-brief-r1.json`

The brief must bind exact contract/freeze/prompt SHA-256 values, session ID,
changed file paths/sizes/SHA-256, executed test commands and observed outcomes,
test counts and runtime versions, unresolved issues and known unrun integration
lanes. Include stopped_writing=true only after all writes are done. Also print a
concise final development brief to stdout. Never claim Architect acceptance or
Git/CI delivery. A turn limit or test failure is not successful completion.

No writes outside the three paths, named brief and disposable temporary test
files. No Git mutations, network/provider fetch, web search, Cursor runtime,
dependency/model downloads, real Vault/admin operations or agents. If a concrete
contract gap blocks work, report it and pause only the affected portion without
silently changing the frozen semantics. Normal permission mode stays enabled.
