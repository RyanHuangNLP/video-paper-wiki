# 终端 1：索引实现

先读同目录 COMMON.md。工作目录和证据位置按共同约定。

仅修改 `src/video_paper_wiki_research/light_index.py`。独立实现旧工作区定位校验与恢复；不等终端 2 交测试，不修改任何测试、夹具、CLI、README 或其他实现。需要验证时在自己的 terminal-1/ 证据目录写一次性脚本。

先用共享 legacy-workspace 还原临时工作区，记录基线直接查询/重建仍错页的真实现象。修复后，未经再次编辑的相同旧工作区必须先报 INDEX_STALE，再经 build_index 恢复 quasar 第 1 页和 nebula 第 2 页。正文区间必须按当前页锚点确定，验证页号/完整页集合/所有偏移，而不只比较正文哈希。

同时验证稳定重建、合法导言和页内增删、缺失/重复/乱序锚点的拒绝、多论文验证失败不提前改写来源。跑现有六个 test_light_*.py；不要跑全量或修改断言让它们通过。共享夹具不原地修改。

完成后 terminal-1/ready.json 的 files 仅列 light_index.py，并给出其精确 SHA、基线/修复后证据和实际测试结果。停止实现写入。终端 2/3 会按该 SHA 复制实现验证，终端 4 最后集成。
