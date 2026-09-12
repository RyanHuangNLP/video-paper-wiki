set -eu
export PYTHONPATH=/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/src
export PYTHONDONTWRITEBYTECODE=1
python -B -c "import video_paper_wiki_research.light_index as m; print(m.__file__)"
python -B -m video_paper_wiki_research --help

CLI=(python -B -m video_paper_wiki_research)
# 自定义解释器（路径可含空格）时写成：
# CLI=("/absolute/path/to/python" -I -B -m video_paper_wiki_research)
# 源码树：先 export PYTHONPATH，再 CLI=(python -B -m video_paper_wiki_research)
PDF=/Users/huangzhanpeng/python_code/video-paper-wiki/inbox/arxiv-2204.03458.pdf
WS=/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r08-fix-parallel-v1/architect-r09/.work/bash-workspace
OUT='/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r08-fix-parallel-v1/architect-r09/bash output notes'
QUESTION="What method does this paper propose?"   # 与 PDF 正文同一语言；中文问句不会跨语言命中英文 PDF
TOPIC="video diffusion models"
REQUIREMENTS="Two short paragraphs citing original PDF file pages"

CTX="$OUT/qa-context.json"          # qa export 的 stdout
ANS="$OUT/qa-answer.json"           # 当前会话根据 CTX 写出
QA_MD="$OUT/qa answer.md"           # qa import 的 Markdown
WCTX="$OUT/writing-context.json"
DRAFT="$OUT/writing-draft.json"
WMD="$OUT/writing draft.md"

CTX="$OUT/source-qa-context.json"
"${CLI[@]}" qa export --question "$QUESTION" --workspace "$WS" > "$CTX"
