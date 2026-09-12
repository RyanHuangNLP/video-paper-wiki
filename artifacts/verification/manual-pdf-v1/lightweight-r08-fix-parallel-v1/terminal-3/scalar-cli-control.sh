#!/bin/sh
# R08-2 control: scalar CLI plus unquoted $CLI (the bug the draft must not reintroduce).
unset PYTHONPATH
CLI="python -I -B -m video_paper_wiki_research"
$CLI --help
