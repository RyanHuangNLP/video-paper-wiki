# arXiv 摘要预览

在仓库根目录使用 `vpwiki-research paper`，或在已有 Python 环境中使用
`python -m video_paper_wiki_research paper`。传入 arXiv ID 或官方 HTTPS 摘要 URL：

```sh
vpwiki-research paper request --arxiv 2408.06072v2 --session screening
```

命令生成规范 URL 和请求文件。命中 24 小时内的有效缓存会返回原始元数据与观察引用；
`--refresh` 要求重新观察。显式 v2 与不带版本的请求分别缓存。命令自身不访问网络。

由当前会话的 Web 工具对生成的 URL 执行一次 open。请求之间至少间隔三秒；不要自动
重试、搜索替代版本或下载 PDF。保存连接器返回的完整规范化文本，保留命名段落、
版本引用和提交历史。`L<number>:` 行号及连接器引用装饰可以保留。旧 CAP 摘录缺少
作者、摘要和若干行，不能作为成功元数据使用。

观察输入是未封装的 JSON 对象，字段如下。`request` 使用请求输出中的 exact reference；
`payload.sha256` 是 `text` 原始 UTF-8 字节的 SHA-256：

```json
{
  "request": {"id": "rw1:request:<content-sha256>", "sha256": "<exact-file-sha256>"},
  "observed_at": "2026-09-09T01:00:00Z",
  "executor": {"value": "unknown", "identity_source": "unknown", "reason": "连接器未提供运行时身份"},
  "source_url": "https://arxiv.org/abs/2408.06072v2",
  "capability_profile": "normalized-content",
  "reported_content_type": "text/html",
  "transport": {
    "final_url": {"value": null, "unavailable_reason": "未观察到源站最终 URL"},
    "redirect_chain": {"value": null, "unavailable_reason": "连接器未暴露完整跳转链"},
    "headers": {"value": null, "unavailable_reason": "连接器未暴露源站响应头"},
    "content_type": {"value": null, "unavailable_reason": "源站响应头不可用"},
    "dns_ips": {"value": null, "unavailable_reason": "连接器未暴露 DNS 或 IP"},
    "raw_response_sha256": {"value": null, "unavailable_reason": "没有原始 HTTP 字节"},
    "wire_bytes": {"value": null, "unavailable_reason": "没有传输字节计数"},
    "timeout_enforced": {"value": null, "unavailable_reason": "工具没有取消超时参数"},
    "redirect_policy_verified": {"value": null, "unavailable_reason": "跳转策略未验证"}
  },
  "outcome": {"status": "ok", "retry_after_seconds": null},
  "payload": {"format": "arxiv-abs-normalized-text-v1", "text": "<连接器实际返回的完整文本>", "sha256": "<text-utf8-sha256>"}
}
```

这是带占位符的格式说明，不能直接当作观察证据。时间须改成实际观察时间；不能把
示例身份和来源声明当作连接器证明。超时、限流、未找到或失败可以记录为相应 status，
payload 可为 null。失败观察保留，但不会产生元数据。`byte-exact` 分支没有执行器，
返回 `CONNECTOR_CAPABILITY_UNAVAILABLE`，不读取所谓原始响应文件。

```sh
vpwiki-research paper observe --session screening --request REQUEST.json --observation INPUT.json
vpwiki-research paper preview context --session screening --metadata METADATA.json
vpwiki-research paper preview validate --session screening --metadata METADATA.json --proposal PROPOSAL.json
vpwiki-research paper preview render --session screening --preview PREVIEW.json
```

将 context 的原样 task_prompt 交给当前模型。proposal 恰好包含 generator、generated_at、
prompt_sha256、sections；context 返回结构示例。六项中文内容要标注 extracted、inferred、
ambiguous 或 unknown。模型和运行环境身份分别记录，未知是有效状态，自述不等于平台验证。
task_prompt 哈希只标识这个任务输入，不代表平台隐藏提示词。程序验证结构及绑定关系；
语言质量、语义支持程度仍需阅读判断。

预览只依据摘要，显示明确版本、观察时间和 latest_at_observation / older_at_observation /
latest_unknown。只有完整可见历史才能据此判断是否为观察时最新版本；不能把未知解释为 v1。

收到用户明确选择后记录：

```sh
vpwiki-research paper decide --session screening --preview PREVIEW.json --action ingest --selected-version 2 --event-id choice-1 --user-text '用户实际的选择原文' --source user_message
vpwiki-research paper list --session screening
```

skip/later 不带 selected-version。事件 ID 在会话中唯一；相同事件重放复用原记录，改动
原事件内容返回冲突。新选择追加到完整序列，列表按序列取最后一项，不按时间戳覆盖历史。
ingest 仅返回 decision、preview、metadata、observation 的精确引用和选定版本，供后续
SOURCE-VERSION 验证；没有执行收录、生成批准引用或签发回执。

离线合成样例可这样完整重放，所有选择都显式标为 fixture：

```sh
python -m pytest -q tests/research/test_paper_preview.py::test_public_cli_complete_flow
python -m pytest -q tests/security/test_paper_preview_boundary.py
```

样例在临时 checkout 中生成请求、完整合成页面、摘要预览和 fixture 决策，验证 CLI
七个入口，不需要 Web、模型调用或真实 Vault。真实页面观察与用户真实选择另行记录。
存储仅位于 `.work/research/<session>/preview-v1/{requests,observations,metadata,proposals,decisions}`，
每个对象至多 1 MiB、JSON 深度至多 32、每个目录至多 256 个文件。对象为不可覆盖的
JCS+LF 文件；任何引用损坏会拒绝缓存与列表。没有自动清理，现有轻量库备份不包含这些预览。
