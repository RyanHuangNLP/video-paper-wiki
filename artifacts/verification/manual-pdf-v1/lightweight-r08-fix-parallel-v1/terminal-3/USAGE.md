# run-quickstart.sh

Parameterized replay of `docs/lightweight-pdf-quickstart.md` as real shell statements.

```
/bin/bash --noprofile --norc run-quickstart.sh \
  --python /path/to/python --pdf /path/to.pdf \
  --workspace /path/to/.work/ws --output "/path/with space" \
  --helper protocol_from_export.py --mode installed --step walkthrough --log steps.log

/bin/zsh -f run-quickstart.sh ...   # same flags
```

Flags (also accepted as env): `--python --pdf --workspace --output --question --topic --requirements --title --source-src --mode installed|source --step help|walkthrough|export --log --helper`.

`--mode source` sets `PYTHONPATH` from `--source-src` and uses `CLI=("$PYTHON" -B -m video_paper_wiki_research)` (no `-I`). Does not extract a PDF.

`paste-help.sh` is the exact documented `CLI=(python -I -B -m video_paper_wiki_research)` plus `"${CLI[@]}" --help` (put the intended `python` on PATH).
