# 四终端轻量版收尾 — Architect r08

结论：**本轮交付材料暂不通过，需要修正验证器、快速入门命令及交接版本。** 已验收的 R07 产品源码和测试没有新增改动，不撤销原产品验收；本轮也没有发现需要重开索引修复的产品缺陷。

本轮实际检查范围绑定 18 文件快照 `b8b644b0fed9fd0d116a8a427625d468558e3c949fd73258a01d3783a3843569`：原 R07 的 17 文件加 quickstart。其中 README 为 `f8395276775c930cf87d0e5a427663083e7a25ae55b1eb577b6383091da6458b`，integration quickstart 为 `6c02145f0627020cf717048162f363a470d64d62fc41f2f71f0ce4b8d8569178`。这不是整个待交付 Git 清单，也不是新的 CI 验收。

## 需要修正的三项

### R08-1 · P2 · 引用验证器在好坏链接混合时仍可能误报成功

定位：[verify_links.py](/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-release-parallel-v1/terminal-1/verify_links.py:115)，以及该文件第 15、17、88–100 行的链接提取。

新版对普通错误相对路径已经能正确拒绝，但会漏掉其他来源链接。Architect 独立构建了一个正常引用，随后分别增加：

1. 指向不存在文件的 `source.md?x=1#page-1`；
2. 指向不存在文件、带 Markdown title 的 `[bad](../missing/papers/<sha>/source.md#page-1 "missing")`；
3. 使用未加引号 HTML href、指向不存在 `page-2` 锚点的来源链接。

三例都返回 exit 0、ok=true、source_link_count=1、errors=[]。磁盘上缺文件或缺锚点的事实均独立确认。第一例在 `_classify` 的无 scheme 分支把 query 混入文件名，随后当作 ordinary 跳过；后两例未被提取，已有正常引用又掩盖了零引用拒绝条件。这违反本轮“无法解析/不支持的来源引用必须明确报错”的要求。

修正应覆盖混合输入，采用完整 URL path/query/fragment 解析，对来源链接的未支持语法明确拒绝；不必增加第三方解析依赖或支持任意 Markdown。旧 R07 反例及本轮普通正反例继续保留。证据：[verifier-edges.json](verifier-edges.json)，可复跑脚本：[check_verifier_edges.py](check_verifier_edges.py)。

### R08-2 · P2 · 快速入门命令尚不能在用户终端直接运行

定位：[integration quickstart 第 72 行](/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration/docs/lightweight-pdf-quickstart.md:72)。当前 integration 文件使用 `$CLI pdf add`，前文只解释 CLI 的含义，没有 shell 赋值。在干净 Bash 和 zsh 中均不能执行。

终端 3 的当前 draft 已修订为 SHA `82d44948d71f821317047b91fc17e9c3c74281acd695d97697ec541661ca1b74`，在第 47 行加入标量 `CLI="python -I -B -m video_paper_wiki_research"`。该写法在 Bash 可用，但默认 zsh 不对 `$CLI` 做空格拆词，仍报 command not found，exit 127。单纯复制现有 draft 不能完全解决。

可用 shell 数组及 `"${CLI[@]}"` 调用，或用明确的 shell 函数/完整命令；源码入口也要相应修改。Architect 在现有新 wheel 上实际验证：旧 integration 写法两种 shell 均 exit 127；修订标量 Bash exit 0、zsh exit 127；数组写法两者 `--help` 均 exit 0。应按最终文档实际 shell 语句验收，不仅由 Python subprocess 参数列表替代执行。证据：[documentation-shell-check.json](documentation-shell-check.json)。

### R08-3 · P2 · 终端 3 与终端 4 的交接不是同一修订

定位：[terminal-4/ready.json 第 43 行](/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-release-parallel-v1/terminal-4/ready.json:43)。终端 4 接收的 T3 ready 摘要为 `3d53b6ec04ff3730514b0fb04b16eae6c10456d2f685f629779c6083cda506f7`，当前实际为 `99aca9687a8ad9e8bd9a1e7b044deb4a643cb6ac423f43a7f4e5ec911ffd3810`。当前 T3 draft quickstart 与 integration 文件亦不同，因此 T4 的一项 artifact 摘要校验失败。

此外，delivery-inventory.json 是文档复制前的 69 路径观察；最终 delivery-manifest.json 为 70 路径。较早观察可以保留，但应明确标为历史输入。ci-plan.md 的 “Current source / dependency hashes” 仍把含 README 的旧 17/413/857 映射标为 match，不能代表文档集成后的当前输入。

修正 R08-1/2 后，先冻结各自新产物，停止写入，再由终端 4 按新摘要接收、集成和生成新的最终清单/CI 输入/ready。保留原记录和失败证据，不把旧结果改标签充当新通过。证据：[input-check.json](input-check.json)、[input-check-after.json](input-check-after.json)、[delivery-check.json](delivery-check.json)。

## 已通过且可以保留的证据

- 产品/测试/构建输入相对基线除 README 外全部相同；新 quickstart 是获准新增路径。四份原 PDF、旧 R06/R07 保护证据未变。评审前后所有已观察输入摘要一致。
- Architect 独立运行 T1 现有测试：**15 passed in 0.13s**。这些测试未覆盖上述三个新反例，因此不能据此认定验证器已完整通过。见 [verifier-pytest.json](verifier-pytest.json)。
- 四论文共 **104 页**的现有工作区中，分页切片和摘要检查通过。使用新 wheel 的隔离 Python 对 **8 份实际 QA/writing export** 逐项重放，返回值与保存的上下文完整一致；工作区字节不变。15 条 claim 的来源切片、paper/page/chunk 身份核对通过。见 [trial-check.json](trial-check.json)。这证明来源对应性和可重放性，不是新的模型生成或人工事实审稿。
- 首次比较问题只命中 SANA、首次中文写作无词法结果、标注改写后获取两篇证据均可重现；失败尝试没有被掩盖。
- Architect 不依赖 T1 的提取器，对实际交付的 7 份 Markdown 逐一核对完整链接、所在输出目录、目标文件与页锚点，并与各自模型上下文/citations 比较。T2 共 **13 个**、T3 共 **5 个**唯一来源目标通过；同一文件中重复出现的同一目标未重复计数。见 [output-links.json](output-links.json)。
- 新 wheel SHA `9e1861d92a3b5fc63159a0d0e6e1aca63eb50e283fb6e008f579ef70fce13b21` 正确；**186 个包文件/资源**与当前源码及实际安装文件逐字节一致，隔离导入没有落到源码树。见 [wheel-check.json](wheel-check.json)。离线依赖来自已有环境的 overlay，这与从空环境重新解析依赖不同。
- Repo Steward 独立核对真实 Git worktree 范围：最终 manifest 的 **70/70 路径**与当前候选一致，10 个 tracked 修改、60 个 untracked 文件，无越界或受保护路径误纳入。此通过只针对当前清单和旧文档，不覆盖未来修订。

## 记录措辞与剩余交付

新 wheel 实际未包含 README/quickstart，METADATA 也未嵌入文档；T4 报告的 “documentation-bearing artifact” 应改为“本轮重建的程序包”，文档另按各自 SHA 验收。代码及包资源不变时，文档小修不必为了一个新的 wheel 摘要再次重建。

本机 Python 3.12 缺少测试依赖，按工作包如实记录未跑即可；没有用 Python 3.13 冒充。历史 2246 项全量不必为验证脚本和文档修正再跑一遍。后续仍需要当前真实提交的远程四项 CI。

本次仅写评审证据及小型输入快照，没有修改产品、文档或任何终端冻结产物，没有调用 Grok，没有 Git 写操作或远程动作。**完成上述三项并重新冻结交接后，才能发出 Repo Steward 提交/PR/CI 指令。**
