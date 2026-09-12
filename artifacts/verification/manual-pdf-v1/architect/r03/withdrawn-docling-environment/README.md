# 手动 PDF 本地环境

本目录固定当前 macOS / Python 3.13 的解析依赖和模型文件。独立环境位于
`.work/environments/manual-pdf`，模型位于 `.work/models/docling-2.117.0`，
uv 缓存在 `.work/cache/uv`。共享 `.venv` 不参与安装。

在项目根目录执行首次准备：

```sh
.venv/bin/python tools/manual-pdf-environment/run.py setup
.venv/bin/python tools/manual-pdf-environment/fetch_models.py
.venv/bin/python tools/manual-pdf-environment/run.py build --source /Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration
.venv/bin/python tools/manual-pdf-environment/run.py check
```

`setup` 会安装完整 hash lock，之后需要重新运行 `build` 安装项目 wheel。
构建从显式指定的候选目录复制必要文件到新的临时目录，不在候选源码中生成构建文件。
默认不安装或调用 `vpwiki-admin`。依赖与模型下载需要网络；正常解析设置离线环境。
模型下载只请求固定官方提交的五个文件，验证大小和上游校验值后才启用。
重复运行下载器会校验并复用已有文件。

完整测试：

```sh
.venv/bin/python tools/manual-pdf-environment/run.py test --source /Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration
```

测试使用 `/private/tmp/vp.test.*` 短目录，禁用第三方 pytest 插件自动加载，并固定 uv 路径及缓存。
测试预检会真实检查 Unix socket。如果 Codex 沙箱禁止创建 socket，使用同一命令的
正常审批执行，或在本机终端执行；不跳过 socket 用例，也不关闭相关断言。

安装后的产品入口：

```sh
.venv/bin/python tools/manual-pdf-environment/run.py research -- --help
.venv/bin/python tools/manual-pdf-environment/run.py parser -- --help
```

解析 profile/export 命令需传入上述模型目录的绝对路径。该配置使用 CPU 四线程，关闭 OCR，
启用版面分析和表格识别；适用于当前含文本 PDF 的测试范围。
PDF 页面预览使用独立环境中的 `pypdfium2`，避免依赖当前机器损坏的 Poppler Fontconfig 配置。
验收记录追加到统一目录 `artifacts/verification/manual-pdf-v1/architect.md`。

参考：[Docling 离线模型使用](https://docling-project.github.io/docling/usage/advanced_options/)。
