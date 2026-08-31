# Video Paper Wiki

面向视频生成论文的本地知识库工程，目前处于 **VPKB-000 工程基础阶段**。接续基线为 [PR #94](https://github.com/RyanHuangNLP/video-paper-wiki/pull/94) 的 `be25997`，交付路径为 draft PR → `integration`。

[种子目录](docs/seed/engine-mvp.json)及其 overlays 保持 **67 篇冻结**。文件名中的 `engine-mvp` 不代表该里程碑已经完成；共享契约仍有缺口，尚未完成 VPKB-000、engine-mvp 或 corpus-v1。当前任务、依赖和待验证项见[任务索引](docs/ai/task-index.yaml)，交接工作使用[工作包模板](docs/ai/work-packet-template.md)。

## 本地环境

在仓库根目录运行，需要 Python 3.12 或 3.13，以及 [uv](https://docs.astral.sh/uv/getting-started/installation/)（CI 固定为 0.12.7）。

```bash
uv sync --locked
uv run --offline --no-sync vpwiki doctor
```

`uv sync --locked` 按锁文件安装主包与默认 `dev` 依赖；首次安装可能下载 Python、构建工具和依赖，不能视为零网络。默认环境不安装 `operator/`、Docling extra 或解析模型。`doctor` 只报告本地环境，不验证完整知识库或里程碑。

## 已可用的命令

以下命令通过 `uv run --offline --no-sync vpwiki …` 调用，具体参数可查看对应命令的 `--help`。

| 命令 | 当前行为 |
| --- | --- |
| `doctor` | 返回本地 Python、主包及 admin 入口是否在 PATH 上的信息。 |
| `ingest plan --request <文件>` | 校验请求，在 `.work/<batch>/plan/` 暂存计划及其绑定哈希，不下载来源。 |
| `ingest prepare --plan <文件> --approval-ref <文件>` | 校验已有计划、外部审批引用和本地 blob，在 `.work/<batch>/prepared/` 暂存字节。 |
| `draft export --sha256 <摘要> --batch-id <批次>` | 读取已有本地 PDF blob，生成 `preview_only` 草稿；当前不产生可发布的 claims。 |
| `draft validate --path <文件>` | 校验草稿契约。 |
| `review export --draft <文件> --batch-id <批次>` | 在 `.work/<batch>/review/` 生成 Markdown 审阅副本。 |

本地 blob 默认从 `.work/blobs/<sha256>` 读取，也可由 `VPWIKI_BLOB_ROOT` 指定已有目录；缺失时返回错误，不联网补齐。`prepare` 所需的 `approval_ref` 必须由外部授权流程提供，Agent 不得自行生成或把测试 fixture 当成真实审批。

其余 CLI 入口仍有占位实现；例如 `review inspect`、`ingest inspect`、查询和 audit 当前返回 `NOT_IMPLEMENTED`，不能据此运行完整入库链路。

## 安全边界与验证

已开放的 Agent CLI 只读取本地输入，并将生成物暂存于 `.work/`；不提供 fetch、apply 或 index build。不要在此开发环境安装或执行 `vpwiki-admin`，也不要直接改写真实 Vault 的 `.raw/`、`wiki/`、账本或人工 gate 状态。

在 Linux/macOS 上，安装依赖后用独立、较短的真实临时目录运行测试，避免 Unix socket 路径长度限制及临时路径中的符号链接干扰安全检查：

```bash
(
  set -eu
  VPKB_TEST_TMP="$(mktemp -d /tmp/vp.XXXXXX)"
  VPKB_TEST_TMP="$(uv run --offline --no-sync python -c 'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve())' "$VPKB_TEST_TMP")"
  trap 'rm -rf "$VPKB_TEST_TMP"' EXIT
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --offline --no-sync python -m pytest -q --basetemp "$VPKB_TEST_TMP/p"
)
```

[CI 配置](.github/workflows/tests.yml)覆盖 Linux/macOS × Python 3.12/3.13，针对进入 `integration`/`main` 的 PR、`integration` 的 push 以及手动触发执行。Actions 固定 commit SHA，依赖安装与测试分开；具体是否通过须查看对应提交的 Actions 记录。

`--offline --no-sync` 禁止 uv 在测试时下载或同步环境，并不构成所有测试进程的系统级网络封锁。部分安全测试使用 `network_attempts` fixture 拦截 Python 网络与子进程入口；当前 CI 不证明操作系统层面的零 egress、真实 Docling 模型解析或生产 Vault 事务已经验收。
