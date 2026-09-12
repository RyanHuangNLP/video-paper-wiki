#!/bin/sh
# Exact documented installed array + --help (quickstart sections 2 and 1).
# Requires: `python` on PATH is the intended interpreter; PYTHONPATH empty.
unset PYTHONPATH
CLI=(python -I -B -m video_paper_wiki_research)
"${CLI[@]}" --help
