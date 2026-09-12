# Terminal 1 review addendum — subprocess interpreter portability

This addendum preserves `terminal-1-review-r1.md` unchanged.

The frozen R2 test file `tests/research/test_light_pdf_recovery.py` hardcodes:

```python
PYTHON = Path("/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python")
```

The process-level crash/recovery tests use that value to launch child processes. It works on the submitting macOS workstation but cannot select the locked matrix interpreter on Linux/CI or another checkout. The test must derive the active test runtime, such as `Path(sys.executable)`, and retain the process-level coverage without skipping it. This is a test portability blocker for the claimed cross-platform recovery evidence, separate from the production findings in the original review.

The current handoff's local test evidence remains valid for the stated macOS `.venv` command; it does not establish Linux/CI execution of the child process tests.

## Continuation-packet consistency check

At review time, `AGENT-1-CONTINUE.md` was not present in `architect-overall-r1`; therefore no T1 continuation instruction could be hash-checked. The available Agent 2, Agent 3, and Agent 4 continuation packets are consistent with the frozen 5/9/6 owned-path scopes in `TERMINAL-2.md`, `TERMINAL-3.md`, and `TERMINAL-4.md`. Agent 2 explicitly requires a new five-path R3; Agent 3 explicitly requires nine owned paths plus exact T1/T2 imports; Agent 4 explicitly identifies the missing seven T3 imports and does not claim integration. No scope expansion or acceptance contradiction was found in those three packets.
