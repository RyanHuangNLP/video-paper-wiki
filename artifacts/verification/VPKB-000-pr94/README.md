# VPKB-000-pr94 验证记录

日期：2026-09-01。接续 [PR #94](https://github.com/RyanHuangNLP/video-paper-wiki/pull/94)
的 `be2599759db7ea80aff60baae0e7859824307527`；维持 draft → `integration`，目录冻结 67。
本记录只关闭当前输入安全修复与交接子包，不代表整个 VPKB-000、engine-mvp 或 corpus-v1 完成。

## 修复与覆盖

- 原 #94 的 plan 对象/数组 schema 拒绝及 lstat→open 替换错误分类仍由全量测试覆盖。
- 将 schema 类型检查放到共享 validator：prepare 的异常输入也返回 `SCHEMA_INVALID` / exit 2。
- JSON 只接受 RFC 8259 的空格、Tab、CR、LF；合法前后空白通过，非 JSON Unicode 空白拒绝。
- 在解码前限制最多 64 层容器，忽略字符串中的括号和转义；避免 decoder、schema 与 JCS 递归异常。
- 拒绝键和值中的孤立 Unicode surrogate，避免错误输出发生 `UnicodeEncodeError`；合法 surrogate pair 保留。
- 新增 54 个回归用例；plan request、prepare plan、approval-ref 两个命令族均验证单行 JSON、exit 2、零额外写入与 fixture 网络拦截。

## 实际结果

| 环境 | 命令 | 结果 |
| --- | --- | --- |
| macOS arm64 / Python 3.13.13 / uv 0.12.7 | `.venv/bin/python -m pytest -q --basetemp=<短真实临时路径>` | 667 passed，0 failed / error / skipped；61.78s |
| macOS arm64 / Python 3.12.14 / uv 0.12.7 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 <独立3.12环境>/bin/python -m pytest -q --basetemp=<短真实临时路径>` | 667 passed，0 failed / error / skipped；66.88s |
| 独立已安装 wheel / Python 3.13.13 | 仓库外运行真实 `vpwiki` 子进程 | 12 个打包 schema 可读；带空白的 plan 成功；非法 Unicode prepare 单条 JSON 拒绝；未写 Vault |
| 配置与复核 | YAML 解析、所有 CI run 段 `bash -n`、链接检查、`git diff --check`、独立代码复核 | 通过 |

初次沙箱内运行原套件为 608 passed / 5 failed：五项均在创建本地 Unix socket 时被沙箱以 `EPERM` 拒绝。
最终两次全量运行允许创建这些本地 socket；未 skip、删除或弱化相关安全测试。
首次 standalone wheel 离线安装无法查询未缓存的包索引；改为用 `uv sync --locked --offline`
准备锁定依赖，再以 `uv pip install --no-deps --reinstall --offline <wheel>` 替换 editable 主包，完成了独立 wheel 验证。

精确 source 文件 SHA-256、JUnit 结果计数和依赖 pin 见 [results.json](results.json)。
GitHub CI 配置覆盖 Linux/macOS × Python 3.12/3.13；其执行结果以 PR 对应提交的 Actions 为准，不能从本地结果推断。

## 重放与边界

按根目录 [README](../../../README.md) 的锁定安装和短临时目录测试命令重放。
需要测试源代码 checkout、Python 3.12/3.13、pytest 和本地 Unix socket 创建权限；不需要真实论文、Vault、模型或 admin。
工具链和依赖首次安装可能联网；测试使用本地 fixture，`network_attempts` 仅覆盖使用该 fixture 的测试，
`uv --offline --no-sync` 只约束 uv，不是系统级 egress 封锁。

未安装 operator 包或 Docling extra，未下载解析模型，未修改 67 条目录或原有用户文件，未发布 Vault 或审批人工 gate。
后续 VPKB-000 仍需补 capture/code-evidence 契约、transaction facade、projection/SQLite 契约及上游 digest/fixture 验证，
见 [任务索引](../../../docs/ai/task-index.yaml)。
