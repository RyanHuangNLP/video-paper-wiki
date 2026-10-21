# Bounded dependency source and license observations

The [original observation](source-license-observation.json) is a byte-exact copy.
Scope is only `docling==2.117.0`, `docling-slim==2.117.0`,
`docling-core==2.92.0` and the existing pinned `claude-obsidian` vendor. The two-pin
upstream manifest remains `pinned`; no lock, dependency or upstream source was
changed, and no Docling package was installed, imported or executed.

The exact lock URLs, sizes and SHA-256 values were checked before archive reads.
The `docling` wheel is metadata-only and depends on `docling-slim[standard]` of
the same version; the implementation is in slim, whose core version is separately
resolved by this lock. All three METADATA files declare MIT. Slim/core contain
separate LICENSE members. Neither the verified docling wheel nor its verified
sdist contains a LICENSE file: its evidence is the METADATA/PKG-INFO declaration,
not an invented license hash. The pinned vendor was detached and clean, with its
LICENSE byte hash recorded. These observations do not resolve PyPI artifacts to
an exact upstream Git commit, audit transitive packages/models, or provide a legal
compliance or redistribution conclusion.

[METADATA/PKG-INFO/LICENSE files](metadata/) and [vendor LICENSE](vendor-LICENSE)
are byte-exact evidence. [Archive manifest](archive-manifest.json) distinguishes
original and archived script hashes. No wheel, sdist or third-party Python source
is copied into this repository. The original observation's nine
`extracted_read_only_core_sources` entries and their `saved` relative paths refer
only to `<TMP>/vpkb-dependency-source-review/source/` from the original inquiry.
They do not denote files shipped here. Source inspection did not run a parser or
Pydantic validation. Distribution 2.92.0 and document-format 1.10.0 are separate
version identifiers; inspecting ref/text/provenance model definitions cannot
prove real text, coordinates or artifact closure.

`collect.py` is the normalized historical collector and contains path tokens;
it is retained for source review, not claimed as directly replayed after editing.
The separate [replay-artifacts.py](replay-artifacts.py) is an explicit, standalone
retrieval script: it requires this exact lock hash, downloads only the four
recorded lock artifacts from files.pythonhosted.org, checks hash and size, and
reads only metadata/license archive members. It refuses an existing output
directory and never installs/imports packages, fetches models, or extracts source.
It was syntax-checked; no second network replay is claimed. Run only with explicit
network authorization, outside pytest, using Python 3.11 or later:

```sh
python replay-artifacts.py --repo /path/to/checkout --out /private/tmp/dependency-review-new
```

All original temporary files remain intact. This evidence records observations,
not a change from the repository's pinned dependency status.
