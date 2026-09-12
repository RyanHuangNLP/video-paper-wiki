set -eu
unset PYTHONPATH
python -I -B -m video_paper_wiki_research --help

unset PYTHONPATH
python -I -B -c "import video_paper_wiki_research.light_index as m; print(m.__file__)"

CLI=(python -I -B -m video_paper_wiki_research)
# 自定义解释器（路径可含空格）时写成：
# CLI=("/absolute/path/to/python" -I -B -m video_paper_wiki_research)
# 源码树：先 export PYTHONPATH，再 CLI=(python -B -m video_paper_wiki_research)
PDF=/Users/huangzhanpeng/python_code/video-paper-wiki/inbox/arxiv-2204.03458.pdf
WS=/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r08-fix-parallel-v1/architect-r09/.work/zsh-workspace
OUT='/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-r08-fix-parallel-v1/architect-r09/zsh output notes'
QUESTION="What method does this paper propose?"   # 与 PDF 正文同一语言；中文问句不会跨语言命中英文 PDF
TOPIC="video diffusion models"
REQUIREMENTS="Two short paragraphs citing original PDF file pages"

CTX="$OUT/qa-context.json"          # qa export 的 stdout
ANS="$OUT/qa-answer.json"           # 当前会话根据 CTX 写出
QA_MD="$OUT/qa answer.md"           # qa import 的 Markdown
WCTX="$OUT/writing-context.json"
DRAFT="$OUT/writing-draft.json"
WMD="$OUT/writing draft.md"

mkdir -p "$WS" "$OUT"
"${CLI[@]}" pdf add --pdf "$PDF" --workspace "$WS" --title "可选标题"

"${CLI[@]}" index build --workspace "$WS"

"${CLI[@]}" qa export --question "$QUESTION" --workspace "$WS" > "$CTX"

python -I -B /Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-r08-fix-parallel-v1/terminal-3/protocol_from_export.py --context "$CTX" --answer "$ANS"
"${CLI[@]}" qa import --context "$CTX" --answer "$ANS" --output "$QA_MD" --workspace "$WS"

"${CLI[@]}" writing export --topic "$TOPIC" --requirements "$REQUIREMENTS" --workspace "$WS" > "$WCTX"

python -I -B /Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-r08-fix-parallel-v1/terminal-3/protocol_from_export.py --context "$WCTX" --draft "$DRAFT"
"${CLI[@]}" writing import --context "$WCTX" --draft "$DRAFT" --output "$WMD" --workspace "$WS"

"${CLI[@]}" index build --workspace "$WS"
