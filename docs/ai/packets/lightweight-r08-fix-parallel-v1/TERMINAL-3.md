# 终端 3：让 quickstart 在 Bash 和 zsh 中实际可执行

先读同目录 COMMON.md。只编辑本轮 `.work/parallel/lightweight-r08-fix-parallel-v1/terminal-3/draft/docs/lightweight-pdf-quickstart.md`。初稿为旧 T3 的 82d44948…修稿；它仍使用标量 CLI 和未加引号 `$CLI`。integration 的 quickstart 和 README 均不由你直接改。

修复全部命令调用。推荐 `CLI=(python -I -B -m video_paper_wiki_research)`，后续一律 `"${CLI[@]}" ...`；源码分支对应数组 `CLI=(python -B -m video_paper_wiki_research)` 并显式设置 PYTHONPATH。也可用 Bash/zsh 都可用的 shell 函数或完整命令，但不能要求用户打开非默认拆词选项，不使用 eval。需要自定义 Python 路径时保留引号，使路径含空格也不会拆坏。

删去“不要给 $CLI 加引号”的错误指导；让变量先定义、路径引用正确，保留实际模型 JSON 生成步骤和词法/空文本边界。不要改正文产品能力、不添加未实现功能，不改其他文档。

验收必须执行文档的**实际 shell 语句**：

- 在 `/bin/bash --noprofile --norc` 和 `/bin/zsh -f` 中运行最终文档的变量定义、数组/函数与核心命令。只替换本次真实路径、问题和协议输入，不把 `$CLI` 改写成 Python subprocess 的参数列表。
- 使用 baseline.wheel_python 指定的现有隔离安装，源码目录外、清空 PYTHONPATH，先 `--help` 与实际模块 SHA；在本终端工作目录下分别为 Bash/zsh 创建独立 `.work` 工作区，用 baseline.pdf_input 的原 PDF 完成 pdf add、index build、qa export/import、writing export/import，输出目录含空格。保留这些本轮文本工作区及输出到 Architect review 结束，不能在 T4 检查引用前删除目标。
- 模型输入步骤可以使用明确标注的协议示例，chunk_id 必须从该次 export 来，生成 JSON 与文档结构一致；这是 shell/协议验收，不是新的模型质量试用。
- 同一组 shell 调用在源码分支也验证 `--help` 与只读 export，保证数组选项/解释器模式/PYTHONPATH 没有混用；不为源码模式再提取两套 PDF。

保存可复跑 `.sh` 脚本，标注每段对应文档片段与仅替换的变量。Python、PDF、workspace、output 等路径通过参数或环境变量传入，不能把 T3 写入路径写死，供 T4 指向它自己的工作目录。记录 Bash/zsh 名称/版本、命令、exit、模块 SHA、输入输出结果以及最终 doc SHA。不能只保存两次 help 就声称完整文档流程通过。输出链接可以按完整 href 独立核验，供 T4 再用新验证器检查；新的 outputs.json 只列实际保留的本轮结果和 workspace。

ready 的 files 只含 docs/lightweight-pdf-quickstart.md，注明 draft_root 和 SHA；artifacts 列 shell 脚本、报告及 outputs.json。确认命令日志对应最终文档后，原子写 handoff/ready 并停止所有本版本写入，T4 才获得复制权限。需要再改时建立新 revision 并重新交接，不再发生旧 ready 原地变更。
