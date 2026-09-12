# Terminal 3 — 可恢复研究工作流与自然语言 Skill

先读 COMMON、CONTRACT、freeze.json。cwd 为 ROOT/.work/parallel/lightweight-workflow-v2/terminal-3/source；Grok 4.6 / xhigh。预计约 3–5 小时。目标是让用户说“读这篇 PDF / 用这些论文回答 / 写一段相关工作”后，由当前会话自动办理中间 JSON、保存上下文、完成有引用的 Markdown，并可在重启后继续。

## 精确自有源码范围

- `src/video_paper_wiki_research/light_workflow.py`（新增）
- `tests/research/test_light_workflow.py`（新增）
- `tests/research/test_light_workflow_recovery.py`（新增）
- `tests/research/test_light_skill_routing.py`（新增）
- `.agents/skills/video-paper-read/SKILL.md`（新增）
- `.agents/skills/video-paper-read/agents/openai.yaml`（新增）
- `.agents/skills/video-paper-read/references/workflow.md`（新增）
- `.agents/skills/video-paper-ingest/SKILL.md`
- `.agents/skills/video-paper-query/SKILL.md`

只读本机 skill-creator guide：`/Users/huangzhanpeng/.codex/skills/.system/skill-creator/SKILL.md`。可以依照它校验自己的 Skill；不创建额外文件、安装 Skill 或修改全局配置。CLI/README 属于 T4。T1/T2 冻结文件可按 COMMON 导入自己的 source，保持 byte-identical，不能改生产者代码。

## 连续里程碑

1. 不等后端：实现合同 C 的 request/session/manifest 存储、canonical identity、只读 status、状态判定、advisory lock、意图/receipt 与中断恢复，测试用小型协议适配 stub 明确标成协议测试。写 Skill 路由与案例，避免把 canonical Vault 路径误当普通阅读默认。
2. T1/T2 backend ready 后校验 hash、复制已冻结文件，接上 prepare_workflow / workflow_status / complete_workflow。prepare 执行有明确路径的 PDF add、必要 index build、export/live revalidation，再冻结上下文；不在 status 自动修复。重复 request+snapshot 重用 session，改源产生新 session 并保留旧记录。
3. 覆盖进程间重启：prepare 后退出，重新打开 status/read context，再 complete；完成后相同 document/output 幂等。注入 intent 前后、输出创建前后、receipt 前后的异常，验证精确 intent/output 允许恢复，用户修改/无 intent 目标永不覆盖。坏引用不得先写 intent。并发 complete 至多一个拥有写权限，不能留下虚假 complete。
4. 写完整自然语言 Skill：默认轻量阅读、明确 paper selection、无结果、英文原文/中文提问检索词调整、扫描 PDF 无原生文字、source 编辑导致 stale、用户已有 draft 的保护、显式 canonical 请求路由。读取实际 CLI help 的最终验证由 T4 做；你先做真实后端的 synthetic workflow 回归和 Skill 文件规范验证，冻结 final。

## 必须证明的行为

session ID 不包含时钟随机因素；同 request+context bytes 两次 prepare 相同、源变化不同。manifest/request/context 任一坏 hash、目录名不符、symlink、unknown entry、恶意 session path 都不能返回 awaiting_model/complete。所有状态查看只读；缺 workspace 不创建。completed output 后源变更显示 stale 并保留旧输出；输出被用户编辑/删除显示 needs_attention，不能重跑覆盖。context No-results 时不建假 session，Skill 不请求模型编造答案。

自然语言体验不是把提示词写在文档就等于完成：至少在真实后端上记录一次“prepare→读 context→模型 document fixture→complete→重启 status”的工程链路。fixture 只能叫结构试验，实际当前模型试用由 T4 在最后真实 CLI 上完成。若环境允许在当前 Grok 会话直接产生有证据的答案，可另留真实标注，但不替代 T4 集成试用。

## 验证与交接

跑三个自有 test 文件；接收 final T1/T2 后重跑受影响项并记录 inputs。Skill 规范检查不要只硬编码字符串是否出现；验证元数据可解析、引用文档存在，以及被写出的示例协议与 backend 实际返回一致。任何尚未接收的 final 或新 CLI 验证必须列为未跑，不标全产品 ready。T3 final 只代表本 lane 目标已实现且真实后端定向测试通过。
