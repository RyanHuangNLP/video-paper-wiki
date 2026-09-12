# T2 — paper maintenance and lightweight backup

Own production:
- src/video_paper_wiki_research/light_library.py (new)
- src/video_paper_wiki_research/light_backup.py (new)
- src/video_paper_wiki_research/light_library_state.py (new optional shared helper)
- src/video_paper_wiki_research/light_pdf.py (only necessary maintenance/backup integration, public API compatible)
- src/video_paper_wiki_research/light_index.py (only necessary maintenance/backup integration, old behavior preserved)
- src/video_paper_wiki_research/light_workspace.py (only diagnostics integration)

Own tests:
- tests/research/test_light_library.py (new)
- tests/research/test_light_library_recovery.py (new)
- tests/research/test_light_backup.py (new)

Implement CONTRACT T2/common fully: list/edit, reversible archive/restore, native-text PDF replacement with clear old-note preservation, journals and explicit recovery; deterministic lightweight manifest/ZIP create/verify/fresh-root restore with all path/hash/type/size validation and transparent exclusions.

No core Vault backup reuse, original PDF copy, defaults/model changes, external output following or silently skipped user content. No writes to T1 light_context or T3 CLI/Skill. Existing workflow lock helpers are available read-only. Do not create an unreviewed new global generation counter or rewrite old completed sessions.

Tests cover exact title/tags no-op/change, note/source preservation, source and session staleness, active lock refusal, archive/restore slot conflicts, replacement duplicate/conflict and old-note attribution, interruption before/after moves and exact recovery, malformed/foreign journal preservation; all backup exclusions, explicit extra-output mapping, source-race detection, binary/PDF/symlink/hardlink/path/collision/oversize/ZIP tamper refusal, safe create-only publication and byte-exact fresh restore. Historical old workflow documents remain exact bytes and require reprepare in a new root.

Publish stopped r1 snapshot/handoff per COMMON. No CLI edits, no Git or real-Vault actions.
