# verify_links.py

只读检查产品生成的本地 `papers/<64hex>/source.md#page-N` 引用。标准库，无网络，不改 Markdown / 来源 / 索引。不是完整 Markdown 解析器。

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
  /Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-r08-fix-parallel-v1/terminal-1/verify_links.py \
  --workspace /abs/workspace \
  --output /abs/answer.md \
  --report /abs/report.json
```

缺少任一参数、或路径不是绝对路径：非零退出（参数缺失为 argparse 退出码 2）。不要从输出里截 `papers/...` 再拼 workspace。

## 返回值

| 字段 | 含义 |
| --- | --- |
| `ok` | 全部来源引用合法且文件、页锚点存在；任一坏的/不支持的来源引用会使整体失败 |
| `source_link_count` | 识别到的来源引用数（按首次出现的完整 href 去重） |
| `checked` | 每项含完整 `href`、`resolved_path`、`anchor`、`exists` |
| `errors` | 字符串列表；空表示通过 |

`resolved_path` 以 **output 文件的 parent** 解析 URL **path**（含 `..`），query 不并入文件名。`exists` 表示该解析路径上是否有普通文件。`anchor` 是 URL 解码后的 fragment。

CLI：`ok=true` 退出 0；`ok=false` 退出 1。报告总会写入 `--report`（先写临时文件再替换）。

## 支持 / 拒绝矩阵

**提取并校验（通过条件：path 后缀为 `papers/<64hex>/source.md`，无 query，fragment 为 `page-<digits>`，解析目标正好是声明 workspace 下该文件且含 `<a id="page-N"></a>`）：**

| 形式 | 行为 |
| --- | --- |
| 相对 Markdown `[text](path#page-N)` | 提取并校验 |
| 尖括号路径 `[text](<path with spaces or (parens)#page-N>)` | 提取并校验 |
| 百分号编码的 path/fragment | URL 解码后提取并校验 |
| 反引号 `` `path#page-N` `` | 提取并校验 |
| 单/双引号 HTML `href="..."` / `href='...'` | 提取并校验 |
| 带 Markdown title 的来源链接 `[text](path#page-N "title")` | **提取并校验目标**（不是 unsupported 占位） |
| 未加引号 HTML `href=path#page-N` | **提取并校验目标**（不是 unsupported 占位） |

**明确拒绝（记入 `checked`/`errors`，整体 `ok=false`）：**

| 形式 | 行为 |
| --- | --- |
| 本地来源链接带非空 query，如 `source.md?x=1#page-1` | 拒绝；query 不是文件名后缀，不会被忽略 |
| `http(s)` / `file://` 等外部来源 URL | 拒绝，不访问网络 |
| 非法 hash、缺 fragment、错误相对层级、缺文件、缺锚点 | 拒绝 |
| 好坏来源引用并存 | 仍拒绝整体；正常引用不能掩盖坏引用 |

**可忽略：** 普通非来源链接（网站、其它笔记）。零来源引用 → `ok=false`。

输入只读：只读 Markdown 与 `source.md`；只写 `--report`。
