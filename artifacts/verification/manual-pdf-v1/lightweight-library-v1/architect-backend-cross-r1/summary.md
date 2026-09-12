# Architect backend cross-feature R1

This is a backend-only acceptance overlay assembled from accepted T1 R4 and T2 R5 bytes. It is not a final product acceptance or T3 integration.

The exact handoff manifests and every copied production file verified before execution. The overlay contains 120 non-cache source files, with T1 R4 as the baseline and the six T2 R5 production files overlaid. No T3 source or Git metadata was copied.

## Result

`architect_crossfeature_checks_r2.py` ran with the root `.venv` Python 3.13.13 and `PYTHONPATH` set only to the overlay `src/`: **7 passed, 1 failed, exit 1**.

The failing case is `test_archive_restore_preserves_complete_paper_and_retry` at line 149. After the fixture adds `nested/example.py` beneath a valid paper, `archive_paper` returns `LIGHT_LIBRARY_INVALID` with `unexpected dir nested`. The backend therefore rejects a nested directory before the archive/restore complete-paper roundtrip can run.

The seven passing cases cover knowledge citation/reuse, metadata staleness and preservation, workspace locking, native-add preconditions, cross-paper comparison refusal, and backup roundtrip/tamper behavior.

Evidence: `checks.json`, `provenance.json`, and `junit.xml` in this directory. This result is a bounded integration finding; it does not authorize source edits, T3 import, merge, or product acceptance.
