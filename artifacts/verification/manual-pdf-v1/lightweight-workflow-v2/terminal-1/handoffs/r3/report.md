# Terminal 1 R3 brief

## 返修

按 Architect 指令修复五项，不改 T2 helper、合同或旧交接。

1. 畸形 UTF-8：`classify_paper_dir` 先解码再 `_load_paper`，`UnicodeDecodeError` 变为 `SOURCE_INVALID`；extract 拒绝并保留原字节；inspect 完成只读诊断、`needs_attention`。
2. 恢复前校验：`_recover_owned` 在 rename 前用 digest 校验 UTF-8/JSON/身份/anchors；坏 staging 不发布 final pair。普通中断恢复测试仍通过。
3. 事务 symlink：`.light-transactions` / staging / lock 逐级拒绝 symlink 与非普通 lock，使用 `O_NOFOLLOW`；外部目录保持原字节。inspect 只读报告。
4. 空 workspace + 合法零论文 index：`index_state=current` 且 `state=empty`。
5. 恢复子进程改用 `sys.executable`，导入当前候选。

## 测试

- 运行前/后源码 SHA 相同，绑定本日志。
- 三文件定向：35 passed（`focused-pytest-r3.log`）
- 六文件定向+兼容：54 passed（`compat-six-pytest-r3.log`）
- scratch 探针复放：UTF-8 extract `SOURCE_INVALID` 且保留；inspect `needs_attention`；坏 staging `invalid_final_pair_published=false`；事务 symlink `WORKSPACE_INVALID` 且 `outside_files=[]`；空 index `state=empty,index_state=current`。
- Architect 原 `probe-pdf-results.json` SHA `6842683fa3e45b1d3d5878d3e1cf6cfc47a0eceebcd118e136a86567deda82b3` 未改。

## Finding 对应回归

- UTF-8：`test_malformed_utf8_is_refused_and_preserved`，`test_malformed_utf8_is_diagnosed_without_aborting_inspect`
- 恢复前校验：`test_invalid_owned_staging_is_refused_before_publish`；原进程中断恢复仍在
- symlink：`test_transaction_symlink_is_refused_without_outside_writes`，`test_transaction_symlink_is_reported_read_only`
- 空 index：`test_empty_workspace_valid_index_is_current`
- 可移植解释器：`test_light_pdf_recovery.py` 使用 `sys.executable`

## 未跑

Python 3.12 / Linux / full suite / wheel / 远程 CI / Git。

## 路径

- 源码：`/Users/huangzhanpeng/python_code/video-paper-wiki/.work/parallel/lightweight-workflow-v2/terminal-1/source`
- 指令：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/architect-overall-r1/AGENT-1-CONTINUE.md` SHA `ee1b5d224dd8fe419effd216f55f9650d6031b53928da2f180d8954ac66a65fa`
- 交接：`/Users/huangzhanpeng/python_code/video-paper-wiki/artifacts/verification/manual-pdf-v1/lightweight-workflow-v2/terminal-1/handoffs/r3`
