# 轻量 PDF → Markdown

使用项目现有 pypdf，不安装 Docling、PyTorch 或模型。知识文件保存 Markdown；
一个小 JSON 记录来源路径、文件摘要和页数，不复制 PDF，不输出页面图片。

```sh
.venv/bin/python tools/lightweight-pdf/extract.py --pdf '/absolute/path/paper.pdf' --output '/absolute/path/new-output-directory'
```

生成 `source.md` 和 `source.json`。引用使用 PDF 文件页码。
该路径适合可直接选中文字的 PDF；扫描页没有文字时会明确标记，整份无文字则拒绝生成空知识条目。
公式、多栏排版、图表仍需核对原 PDF。它不声称是 Docling 的结构化解析结果，
也不生成旧 Docling 流程的 profile、run 或发布凭证。

## 完整回归的环境准备

首次准备小型构建缓存（本机实测缓存约 1.9 MB，隔离构建工具约 1.6 MB）：

```sh
UV_CACHE_DIR="$PWD/.work/cache/uv-tests" /Users/huangzhanpeng/.hermes/bin/uv pip install --python .venv/bin/python --target .work/test-build-backend -r tools/lightweight-pdf/build-requirements.txt
```

随后全量测试固定使用这份可写缓存，不修改 `.venv`，也不下载模型：

```sh
.venv/bin/python tools/lightweight-pdf/test.py --source /Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration --evidence artifacts/verification/manual-pdf-v1/architect/new-run
```

每次选一个新的证据目录。测试预检检查 Unix socket，使用短临时路径，并关闭 pytest 插件自动加载。
若 Codex 沙箱禁止 socket，使用该命令的正常审批执行，或在本机终端执行；不要跳过相关测试。
