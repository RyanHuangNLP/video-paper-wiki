# T2 R7 Unicode backup reproduction

This independent review ran only the stopped T2 R7 accepted source (`light_backup.py` SHA-256 `d0142126b09f600dbe34dc98e67830f800bcaa33f3cc4c1240bf54eb127af540`; snapshot `a3d06ca1aeee2673d6057a7bd619562e4a32d9569dba9ee2f50dd41ea81d7f34`) in a synthetic temporary `.work` tree. It did not read real corpus data, inspect Git, start a Builder, or modify product source.

The blocker reproduces deterministically. A workspace containing `notes-α-中文.md` is accepted by `create_backup`, and the produced stdlib ZIP carries UTF-8 filename flag `0x800` on that member. R7's deterministic parser requires both central and local member flags to equal zero, so `verify_backup` returns `LIGHT_BACKUP_INVALID` with `ZIP64, encrypted, compressed, or data-descriptor members are refused`; `restore_backup` returns the same refusal and creates no destination.

The ASCII control (`notes-alpha.md`) creates, verifies and restores successfully with matching bytes. Independently mutated valid ASCII archives with encrypted flag `0x001` and unknown flag `0x020` are both refused, preserving the intended security controls.

This is a **product blocker** for Unicode user filenames. The minimum fix is to allow exactly `0x000` or the valid UTF-8 filename marker `0x800` consistently in local and central headers, while continuing to reject encryption, data descriptors, compression, ZIP64 and all other unknown flags. Add the Unicode roundtrip regression and retain the encrypted/unknown-flag refusals.

Evidence files: `checks.json`, `provenance.json`, `reproduction.json`, and this summary. No source fix or final acceptance is issued here.
