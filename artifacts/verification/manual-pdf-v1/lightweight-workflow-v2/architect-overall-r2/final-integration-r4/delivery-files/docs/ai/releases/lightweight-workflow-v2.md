# Recoverable lightweight PDF workflow

This candidate extends baseline `0fcae592acb977c6b422e7de3b2c3e0cf79df5a0` with a recoverable local PDF reading and drafting workflow. Repeated PDF addition preserves edited notes. Users can inspect workspace readiness, select papers, prepare a model task, resume its session, and save cited Markdown through either research CLI entrypoint or the reading Skill.

PDF and session publication is atomic. Context and index validation compares current source bytes before publication; stale or forged evidence is refused. Completion records an intent before creating output, so retries can recover their own output while preserving unrelated files. Publication-edge regressions verify that a source edit before the final rename produces `INDEX_STALE` without publishing a session.

The product implementation combines accepted T1 r3, T2 r4 and T3 r4 with T4 r3 CLI, documentation and tests. Architect made one final local integration correction to `test_light_workflow_installed.py`: remove copied/relocated virtual-environment evidence and preserve observations from the original installation. Independent Luna review confirmed the test assertions were unchanged. No production bytes changed in that correction.

Local acceptance evidence covers 2,382 passing tests on locked Python 3.13.13, with zero failures, errors or skips. The offline wheel has SHA-256 `3b3f08e1e903b1abdfd21a9b141b557ffa237753670739b0e70877044aa08522`; every packaged Python source module (109) and every schema (53) matches the candidate. The changed test is not packaged, so the same current wheel was reused. A new native virtual environment verified installed module origins and equivalent module/console workflow results outside the source checkout.

The unchanged real-PDF trial contains a completed Q&A and short draft, each with four valid source links and eight verified evidence rows. Invalid citations were refused without output. The documented Bash and zsh flows passed. These are engineering and model-trial results; factual and visual review remain human work.

The catalog and overlays remain at 67 entries. Canonical Vault/operator behavior, dependencies and schema bytes are unchanged. This release does not add OCR, network/model clients, automatic Vault publication, or a merge decision.

Delivery is a draft PR targeting `integration`. Fresh Linux/macOS × Python 3.12/3.13 CI and a separate Architect decision must bind the exact delivered head, base and tested merge revision. Historical CI does not certify this candidate. Detailed historical work packages, raw model logs and real-PDF artifacts remain local protected evidence; the release record identifies their hashes without claiming to carry all of them in Git.
