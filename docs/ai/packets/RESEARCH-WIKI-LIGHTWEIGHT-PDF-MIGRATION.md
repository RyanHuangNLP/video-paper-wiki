# 手动 PDF 轻量入口迁移

当前分工已更新为用户手动启动的四终端并行任务，执行 [共同约定与分工](lightweight-parallel-v1/COMMON.md) 及该目录的 TERMINAL-1..4.md。下文保留此前单终端迁移范围供追溯。

2026-09-06。用户在本轮明确要求限制知识库体积，只保留 Markdown、代码等轻量内容；
Architect 明确提出停止并清理模型下载，改用已有 pypdf 后，用户回复「那这样可以的」「继续吧」。
这项指示替代本阶段必须使用本地 Docling 模型的方案，不重启已取消的八小时调度。
Grok 仍由用户在自己的终端手动运行。

## 已有结果

轻量提取工具：`tools/lightweight-pdf/extract.py`，位于主仓库。
真实 SANA PDF 31/31 页提取成功。输出包含分页原文、来源记录、阅读笔记、问答及草稿，
总计 117,768 字节。路径：主仓库 `artifacts/verification/manual-pdf-v1/sana-lightweight/`。
模型、独立 Docling 环境与本轮大型缓存均已删除。当前集成产品代码未被此轮修改。

## 终端 4 的实现范围

工作目录继续使用 `/Users/huangzhanpeng/.grok/worktrees/python-code-video-paper-wiki/integration`。
先核对现有修改，再把轻量提取纳入 `vpwiki-research` 的正常手动 PDF 入口，贯通本地 Markdown
阅读工作区、文本检索、当前模型回答和可编辑草稿。可以复用上述已经实测的提取逻辑。

要求：

1. 默认使用已有 pypdf 的原生文本提取，不安装 Docling、PyTorch、OCR 或其他模型。
2. 持久知识文件只含 Markdown、代码和必要的小型来源记录；可重建检索缓存保持轻量。
   不复制原 PDF 到知识库，不生成页面图片、视频或模型权重。原 PDF 保留在用户指定路径。
3. 明确标记 `pypdf-native-text`、版本、原始 PDF SHA-256、文件页码和原文切片。
   不把这些输出伪装成 Docling 的 document/profile/run，不复用虚假的 bbox。
4. 扫描页和图表信息缺失要说明；整份没有原生文本时明确返回当前路径不支持，不能悄悄下载 OCR。
5. QA 必须返回实际原文与页码，回答和草稿中的引用必须能回到同一来源。保持模型生成接口复用当前模型，
   不引入额外 LLM/embedding 服务。旧流程的 receipt/published/human-gate 状态不从新阅读输出自动继承。
6. 修复实际入口依赖的环境问题；使用轻量测试缓存和短临时路径完成所需测试。不要改动历史验收证据。

允许修改 research 包、其 CLI/资源/测试、轻量工具及必要 README；若修改共享核心接口，先在
开发简报中说明具体必要性。保留 67 条原有目录与 overlay，不改用户真实 Vault，不调用
`vpwiki-admin`，不做 Git 提交、推送、合并或自主调用其他工作者。

## 验证交付

- 用用户提供的原始 SANA PDF 跑正常产品入口，31 页文本与实际页码可以检查。
- 在本次生成的 Markdown 内容上执行真正的查询，导出的上下文包含实际文本；完成一次带引用回答和草稿。
- 检查知识输出目录没有 PDF、图片、视频、模型文件；报告实际总字节数。
- 保留本次环境运行与产品集成测试的区别。旧 Docling 合成测试通过不等于轻量入口已经贯通。
- 把新增结果追加到主仓库绝对路径
  `/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/terminal-4.md`。
  返回变更文件和验证结果后停止写入，交 Architect 复核。无需重新创建大型架构审查周期。
