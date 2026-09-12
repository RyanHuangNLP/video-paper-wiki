# Terminal 4 — CLI 集成、文档和端到端验收候选

先读 COMMON、CONTRACT、freeze.json。cwd 为 ROOT/.work/parallel/lightweight-workflow-v2/terminal-4/source；Grok 4.6 / xhigh。预计约 4–5 小时，先独立开发 CLI 与验收用例，最后组合 T1/T2/T3 完成连续体验。

## 精确自有源码范围

- `src/video_paper_wiki_research/cli.py`
- `tests/research/test_light_cli.py`
- `tests/research/test_light_workflow_cli.py`（新增）
- `tests/research/test_light_workflow_installed.py`（新增）
- `README.md`
- `docs/lightweight-pdf-quickstart.md`

T1/T2/T3 的精确自有文件可按 COMMON 复制到自己的 source，保持 byte-identical，列入 imported_files/integrated_files；你无权更改这些文件。不能修改 shared conftest/依赖/锁/CI/主仓库/integration/其他终端/旧 artifacts。完整集成只发生在自己的 linked worktree。

## 连续里程碑

1. 先独立实现合同 D 的 argparse 命令与 JSON/exit/dispatch 行为：workspace inspect、workflow prepare/status/complete、QA repeatable paper-id、旧 import/export 接 T2 API。用明确的接口 stub 检查参数映射、help、混合 flag 拒绝和旧 canonical 分流，标注为协议测试。构造后端齐备后可立即跑的 CLI 端到端回归，不等输入空转。
2. 更新 README/quickstart 的自然语言 Skill 第一入口、最小 CLI fallback、选论文、查看状态与重启继续、人工改 source 后 re-prepare、保留用户输出。保持已验收 Bash/zsh 可复制性，命令不使用仅 Bash 数组或 zsh 不拆词的标量命令。Skill 部分由 T3 维护，发现矛盾向其交新 findings。
3. 接收各路 final：核对 baseline/contract/freeze/ready/file hashes；依赖 milestone 如曾被使用必须比对 final。精确复制，生成完整候选 map。真实执行 CLI 案例：新 workspace→PDF→prepare→document→complete→status；重复 add 保留 notes；选定论文问答/写作；无结果；坏引用；context 篡改；源编辑前后 index stale；损坏 session；完成中断恢复；已编辑 output 拒绝覆盖；旧 CLI/legacy dispatch 兼容。
4. 固定全部源码后跑一次全量 tests（锁定共享 Python 3.13，短临时目录），构建一次离线新 wheel，用单独安装目录验证两个入口、模块来源/新文件 SHA、26 schemas 以及新 CLI workflow。实际依赖只能来自现有 offline cache；缺项如实记录，不下载或改锁。不能复用旧 wheel 冒称新实现通过。
5. 最后用 baseline 指定的一篇已有真实 PDF 直接读做当前 Grok 会话试用：生成一个 QA answer 和一小段有引用的 draft，记录输入上下文/模型文档/输出与实际命令。至少一个 Markdown 输出位于带空格/括号的 workspace 外 sibling 目录。逐个检查实际 href 相对 output.parent 的目标、页 anchor、引用 slice/hash 与当前 context/source 联合一致，混入坏引用负例须被拒绝。运行 README/quickstart 中的真实 Bash 与 zsh 命令，记录实际 substitutions，不用虚构结果。

## 集成接受条件

完整行为依赖真实导入模块，不凭 mock 报告成功。T2 已复现三漏洞在新 CLI 中均失败且没有新输出；有效 control 成功。T1/T3 恢复后状态真实且 preserves notes。旧 2246 测试只是基线计数，记录本轮实测数量及失败/未跑，不强行改测试来维持数字。所有生产者 final 与本地导入的 bytes 相同，测试前后源码不变。

installed check 从 source 之外运行并清空 PYTHONPATH（推荐 isolated `-I -B`），新 wheel 只安装一次；脚本记录 actual module __file__、wheel SHA、入口 help/smoke。已有固定 vendor 可作为只读参数输入。Python 3.12 和远程四矩阵由后续 Steward/CI；本轮不联网触发。

## 最终交接

自有 files 与 imported_files 分列，integrated_files 覆盖全部新增/修改交付候选；不得混入三个生产者报告、真实 PDF、测试 workspace、模型文档或旧历史证据到源码交付集。交付报告包含功能表、具体测试/试用、接口缺项、旧用户内容保护结果、wheel SHA、所有来源 handoff SHA，以及一个建议 PR 标题/正文草案（本地文件）。所有当前模型内容标注为试用，不声称人工事实验收或 canonical Vault 发布。完成后 freeze final 并停止写入，等 Architect 审查；不自行 Git 提交/推送或改 PR95。
