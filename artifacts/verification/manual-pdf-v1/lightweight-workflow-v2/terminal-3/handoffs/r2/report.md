# Terminal 3 final (r2)

## 做了什么

在 `codex/lightweight-workflow-v2-t3` 完成合同 C 的 Architect 返修，并停止写入。

- 拒绝 `.light-workflow` / `sessions` / `staging` / `locks` 符号链接状态路径；prepare/status/complete 在读写前检查完整状态链。四个 symlink 探针均返回 `LIGHT_SESSION_INVALID`，外部目录无泄漏文件。
- intent/receipt 改用带 ownership marker 的唯一 staging 目录。固定名 `.<session>.completion-intent.json.tmp` 若已是未知普通文件则保留原字节，不再覆盖后移走。
- `_publish_session` 在写完 staged JSON 之后、安装 session 目录之前再次 `validate_live_context`。源在 staging 后被改则返回 `ok=false/INDEX_STALE`、`session_id=null`，不安装新 session，保留已有历史，只清理可证明归属的临时文件。
- `_validate_loaded_session` 校验 request 恰好为合同 C 字段集合、类型、非空 query、合法 kind、normalized selection，并核对其与 context 的 kind/query/requirements/selection。仅摘要自洽不够。损坏 session 的 status 为 `needs_attention`；complete 返回 `LIGHT_SESSION_INVALID` 且不写 intent/output/receipt。
- 覆盖 prepared 发布中断、intent/receipt 临时写入中断：重试只恢复绑定的自有产物，未知项保持原字节。
- 按 hash 导入 T1 r3 与 T2 r3 final 五文件，接通真实后端。导入文件保持生产者 SHA。

## 测试结果

- 自有三项 + 导入 T1/T2 定向/兼容：**137 passed**，exit 0。日志：`E/terminal-3/logs/r2-final-pytest.log`。
- Architect `probe_workflow.py` 复制到 `/private/tmp/lw3-replay/` 后重放，未覆盖 Architect 历史记录。全部缺口闭合。重放结果：`E/terminal-3/logs/r2-probe-replay.json`。
- 模块 `__file__` 均落在 terminal-3/source。

## Official r1 事实

`E/terminal-3/handoffs/r1/` 只有 `report.md` 和 5 个 Skill 副本，没有 `handoff.json` / `ready.json`。未伪造历史交接，也未迁移或删除这些旧文件。本 revision 是 r2。

## 预计未完成

无本路实现剩余项。T4 CLI/文档/当前会话模型试用、Architect 审查、Steward 提交不在本 lane。

## 需要谁处理什么

- Architect 审查本 lane r2 final。
- T4 按 hash 接收本 handoff；不得把结构 fixture 标成真实模型试用。
- T1/T2 文件仍由原作者维护。

## 没有运行的验证

全量 2246、Python 3.12、installed-wheel、T4 CLI help / 当前会话模型试用、OCR/Docling、真实 Vault、网络、Git 写。

## 运行设置

- execution_host=cursor
- requested_model=grok-4.6
- requested_effort=xhigh
- observed_model=grok-4.6
- observed_effort=null（界面档位不可读，不虚构 xhigh）
- 无 Grok CLI session_id

## 供 Architect 审查的绝对路径

- 源码根：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-3/source`
- handoff.json：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-3/handoffs/r2/handoff.json`
- ready.json：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-3/handoffs/r2/ready.json`
