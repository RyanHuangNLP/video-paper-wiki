# 终端 2：真实四论文检索、问答和写作试用

先读同目录 COMMON.md。产品源码只读，本轮只写自身工作目录和本轮证据根 terminal-2/。四份现有研究 PDF 已在 baseline.json 的 pdf_inputs 列出绝对路径、大小和 SHA：主仓库 inbox 中三份 arxiv PDF，加 Downloads 中的 SANA。先核对摘要，直接读取原文件，不复制、不联网下载、不扩大到其他个人文件。

用共享源码的真实 CLI 在自己的新 `.work/.../terminal-2/workspace` 逐份 pdf add，再 index build。记录四份 paper_id、页数、warnings、文本元数据/索引字节；逐页核对 Unicode 切片、摘要与 PDF 文件页码。现有库里的原生文本足够才算该输入成功；若某份不可提取，记录真实失败，继续其他论文，不能用合成 PDF 替换成四篇成功。重复 add 不产生重复论文记录；多论文工作区不能只有 SANA。

在模型生成之前，写 `cases.json`，固定以下六个案例的问题/主题、预期证据/论文范围与通过条件：

1. 三个可回答的单篇问题，分别覆盖至少三篇不同论文（从实际论文中选择可核对事实）。
2. 一个需要至少两篇证据的比较问题；若当前一次检索没有给足来源，如实记录不足或收窄结论，不拼造上下文。可记录一次明确标注的查询改写，初次结果必须保留。
3. 一个固定、可复现的无关词法查询，验证空结果/INSUFFICIENT_EVIDENCE，不用脚本伪装模型拒答，也不要求系统对任何自然语言都必然检索为空。
4. 一个限定两篇 paper_id 的简短中文草稿，约 300–600 字；实际 writing export 的过滤必须生效，引用至少两篇才算多论文写作成功。若证据不足，保留未达标结果。

源码 CLI 的 qa export 和 writing export 输出为真实模型输入。由当前 Grok 会话阅读 evidence 后形成新的答案/草稿 JSON，再用真实 qa import / writing import 生成 Markdown；不调用新的模型服务，不用 `_model_from_evidence` 或固定引文拼接脚本代替这次生成。保存模型输入、实际会话生成的 JSON、命令与最终 Markdown 的对应关系。无法完成模型输出时记录 needs_input，不将协议夹具当内容试用。

每个回答/草稿拆出实际事实性 claim，生成 `claim-review.json`：claim、chunk_id、paper_id、PDF 页码、原文精确切片及 SHA、supported/unsupported/uncertain、理由。至少覆盖所有数字、模型/方法归属和比较结论。评价限于来源对应性和当前模型自检，不声称独立人工审稿或全面事实正确。不要预设必须全部通过；记录实际命中、漏检、 unsupported 和 uncertain 的数量。

输出目录放在 workspace 外且包含空格。先自行从 output.parent 检查完整来源链接和锚点并保存结果，不等待 T1；T4 后续会用冻结验证器再核验。保存 `outputs.json`，列每个实际 output 的绝对路径、workspace、文件 SHA，供 T4 重放检查。结果须保留在自己的本轮目录，不能在交接前删除引用目标。不要重复归档全文到 evidence，workspace 保留一份即可；原 PDF 摘要前后不变。

交付 `trial-report.md`、cases.json、claim-review.json、outputs.json 及输入/输出摘要。报告区分流程通过、检索表现、内容对应性和未覆盖项。产品问题以最小复现/needs_fix 交接，不直接修改源码或仓库测试。成功写 files=[] 的 ready；失败仍按 COMMON 冻结 handoff，不阻塞其他终端。
