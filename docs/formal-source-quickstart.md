# 轻量 Markdown 的正式来源登记

`vpwiki-research formal-source` 把已有轻量工作区的 `source.md` 原样交给正式来源流程。
它不复制原 PDF，不调用模型或网络，也不执行 Vault 写入。轻量论文仍可独立阅读和查询。

先用轻量库中已有的 SHA-256 论文 ID 生成计划：

```bash
vpwiki-research formal-source plan \
  --workspace-root /absolute/checkout/.work/my-library \
  --paper-id sha256:YOUR_64_CHARACTER_DIGEST \
  --batch-id source-capture-001
```

计划绑定 `source.md`、`source.json` 的准确字节及全部页码锚点。过期元数据需要先刷新。
可用 `--canonical-paper-id arxiv:2501.12345` 明确选择已有论文实体，用
`--version-label '作者提供的 v2'` 记录版本声明；该声明不代表已核实的 arXiv 版本。
省略版本时记录为未知。

计划返回 `awaiting_external_approval`。外部提供的
`video-paper-wiki.markdown-capture-approval-ref.v1` 必须绑定计划的 canonical JSON
哈希、batch ID、paper ID 和 Markdown 哈希。程序不会生成批准记录；匹配的引用也不是
密码学签名或执行授权。不要把测试夹具用作真实批准。

```bash
vpwiki-research formal-source prepare \
  --plan /absolute/checkout/.work/source-capture-001/markdown-source/plan.json \
  --approval-ref /absolute/external-approval.json

vpwiki-research formal-source inspect \
  --prepared /absolute/checkout/.work/source-capture-001/markdown-source/request.json \
  --operation-id source-capture-001 \
  --upstream-root /absolute/pinned/claude-obsidian \
  --vault-root /absolute/vault
```

所有命令输出单个 JSON envelope。`inspect` 的 `data.authority` 是后续使用的 authority
对象；保存这个对象时不要包入外层 envelope。新捕获返回 `awaiting_operator_capture`。
相同 Markdown 已存在于精确 `.raw/captured/<hash>.md` 路径时返回 `capture_reused`，
且不创建子事务。其他扩展名的同哈希文件、多个同哈希文件或不安全文件会被拒绝。

操作者在独立流程中执行获批的 capture 后，可把实际执行结果与执行前后的
`{path: null | {sha256, mode}}` 文件描述绑定到 create authority：

```bash
vpwiki-research formal-source bind-result \
  --authority /absolute/capture-authority.json \
  --result /absolute/actual-capture-result.json \
  --before /absolute/actual-before.json \
  --after /absolute/actual-after.json
```

输出的 `data` 是 `operation-result-authority.v1`。这一步只检查提供的材料是否一致，
不会执行 capture，也不把调用方的描述当成独立执行证明。

在已有有效 genesis/receipt 链的 Vault 中准备来源登记：

```bash
vpwiki-research formal-source admit \
  --authority /absolute/capture-authority.json \
  --capture-result /absolute/bound-capture-result.json \
  --batch-id source-register-001 --operation-id source-register-001 \
  --vault-root /absolute/vault \
  --upstream-root /absolute/pinned/claude-obsidian \
  --ingested-at 2026-09-09T00:00:00Z
```

登记使用新的 batch 和 operation ID。首次登记必须有精确内容的外部 capture result；
手工放入的 raw 文件不能代替它。复用内容可引用此前的实际捕获结果。已经精确登记、
且 raw 路径已被有效登记回执声明的来源会返回 `source_already_registered`。

新的登记返回 `source_registration_prepared`、publication request 和 inspection authority，
并保持 `published=false`、`receipt_backed=false`。操作者实际发布成功后，来源才正式登记。
没有 genesis 时返回 `RECEIPT_BOOTSTRAP_REQUIRED`，需要先完成独立初始化流程。

此步骤只登记来源，不生成论文页、已接受的论断、版本显示选择或知识发布。
