# 终端 1：修复 R08 混合引用漏检

先读同目录 COMMON.md。在 NEW/terminal-1/ 的已准备副本开发 verify_links.py、test_verify_links.py、USAGE.md，旧目录和产品源码只读。初始版本 SHA 51d67390…，三个真实反例见 Architect r08/verifier-edges.json 与 check_verifier_edges.py。

保持 CLI `--workspace --output --report`、函数 verify_links、报告 ok/source_link_count/checked/errors 与非零拒绝行为。修复不能只让三个字符串特判通过：完整解析 URL path/query/fragment，识别来源链接之后校验实际 output.parent 下的目标、workspace 归属和锚点，不能把剩余来源引用当 ordinary 静默丢弃。

冻结的最小支持/拒绝语义：

- 保持产品正常输出可用：相对 Markdown 链接、尖括号内的空格/括号路径、百分号编码的 path/fragment、来源路径反引号、单/双引号 HTML href。
- 本地来源链接带非空 query 时，明确记入 checked/errors 并拒绝；不能把 query 当文件名后缀再忽略。
- 带 Markdown title 或未加引号 HTML href 的来源链接：可以正确提取并校验目标，也可以明确报 unsupported；不允许未提取/未检查却返回成功。在 USAGE 中准确声明采用哪种行为，不假称完整 Markdown 解析器。
- 对 http(s)/file 等外部来源 URL，保持本地来源检查的明确拒绝语义；普通非来源链接可以忽略。错误或不支持的来源链接与正常引用并存时，也必须拒绝整体。

用独立磁盘事实确认三种坏输入：query 链接指向不存在文件、带 title 的链接指向不存在文件、unquoted HTML 指向不存在 page-2；每份文档同时保留一条正常引用。旧普通错误相对路径、零引用拒绝、正常编码/空格/括号和所有原 15 项行为继续通过，不削弱断言。

实现侧可补本轮 smoke，但不等待或修改 T2 独立回归。先用自己新目录的 test_verify_links.py 验证，检查它实际加载本轮脚本而非 OLD 版本；只允许必要路径适配。旧样本/旧错误脚本保持只读。不要跑产品全量或重新四论文生成。

在 USAGE 写支持/拒绝矩阵、准确调用、唯一引用计数语义和输入只读保证。冻结脚本、测试、用法、结果 SHA；ready 的 files=[]，artifacts 列明本轮脚本/测试/说明，stopped_writing=true。写出后停止，供 T2 和 T4 按摘要读取。后续修订必须新 revision，不能覆盖 ready。
