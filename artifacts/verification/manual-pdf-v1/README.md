# Terminal 统一报告目录

以后所有终端都将 Markdown 报告写入同一个绝对目录：

```text
/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/
```

固定文件名：

- 终端 1：[terminal-1.md](terminal-1.md)
- 终端 2：[terminal-2.md](terminal-2.md)
- 终端 3：[terminal-3.md](terminal-3.md)
- 终端 4：`terminal-4.md`（由终端 4 首次交付时创建）

每个终端只写自己的文件。以后新任务或新进展继续在该文件追加一个带日期和任务名的段落，写明完成内容、测试结果和未完成事项。不要另找目录，也不要在自己的 worktree 下创建同名投递目录；使用上面的绝对路径。

这条平铺文件规则替代之前的 `terminal-N/rNN/report.md` 投递规则。旧归档和原始报告保留，不需要终端维护。已有三份报告已复制到上述固定文件。

Architect 的本轮审阅见 [review.md](architect/r01/review.md)。报告目录只用于交接，不启动开发、测试或 Git 操作。
