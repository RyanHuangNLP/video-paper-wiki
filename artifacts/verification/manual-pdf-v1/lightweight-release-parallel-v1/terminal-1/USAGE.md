# verify_links.py

只读检查产品生成的本地 `papers/<64hex>/source.md#page-N` 引用。标准库，无网络，不改 Markdown / 来源 / 索引。

## 入口

函数：

```python
from pathlib import Path
from verify_links import verify_links

result = verify_links(Path("/abs/workspace"), Path("/abs/answer.md"), Path("/abs/report.json"))
```

`report` 可省略；省略时只返回 dict，不写文件。CLI 必须给三个绝对路径。

CLI：

```sh
/Users/huangzhanpeng/python_code/video-paper-wiki/.venv/bin/python \
  /Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-release-parallel-v1/terminal-1/verify_links.py \
  --workspace /abs/workspace \
  --output /abs/answer.md \
  --report /abs/report.json
```

缺少任一参数、或路径不是绝对路径：非零退出（参数缺失为 argparse 退出码 2）。不要从输出里截 `papers/...` 再拼 workspace。

## 返回值

JSON / dict 字段：

| 字段 | 含义 |
| --- | --- |
| `ok` | 全部来源引用合法且文件、页锚点存在 |
| `source_link_count` | 识别到的来源引用数（按首次出现的完整 href 去重） |
| `checked` | 每项含完整 `href`、`resolved_path`、`anchor`、`exists` |
| `errors` | 字符串列表；空表示通过 |

`resolved_path` 是以 **output 文件的 parent** 解析完整 href（含 `..`）后的路径，不是 `workspace / papers/...`。`exists` 表示该解析路径上是否有普通文件。`anchor` 是 URL 解码后的 fragment。

CLI：`ok=true` 退出 0；`ok=false` 退出 1。报告总会写入 `--report`（先写临时文件再替换）。

## 支持的来源链接语法

从 Markdown 读取**完整** href，再 URL 解码 path 与 fragment：

- 产品 CLI 重写后的 Markdown：`[text](relative/papers/<64hex>/source.md#page-N)`
- 含空格或括号时的尖括号形式：`[text](<relative with spaces/papers/<64hex>/source.md#page-N>)`
- 参考文献反引号：`` `relative/papers/<64hex>/source.md#page-N` ``
- HTML：`href="..."` / `href='...'`
- 百分号编码（例如父目录空格写成 `%20`）
- 相对路径中的 `..`（输出在 workspace 外时的正常情况）

路径后缀必须是 `papers/<64hex>/source.md`，fragment 必须是 `page-<digits>`。解析目标必须正好是声明 workspace 下的该文件，且含 `<a id="page-N"></a>`。

普通非来源链接（网站、其它笔记）忽略。

## 失败语义

下列任一情况 `ok=false`，CLI 非零：

- 输出文件或 workspace 目录不存在
- 没有任何来源引用
- 缺 `source.md`、缺页锚点、解析到错误论文目录或错误相对层级
- 前缀错误：完整 href 解析不到 workspace 内同名来源（即使 workspace 里该论文文件存在）
- 无法解析的预期来源引用，或不支持的语法（`http(s)`、`file://`、非法 hash、缺 fragment 等）——报错，不静默全绿
- 不访问网络；网络形式的来源 href 记为非法语法

本工具不是模型质量验收，也不修复旧 `verify_r06.py`。
