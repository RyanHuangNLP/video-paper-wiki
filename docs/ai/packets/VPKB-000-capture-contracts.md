# VPKB-000-capture-contracts

- Parent：VPKB-000。
- 阶段：local_acceptance_complete_ci_pending；契约：frozen revision 2；实现：complete。
- 冻结规范：`docs/ai/contracts/capture-contracts-v1.md`。
- 契约SHA-256：`d54e1c36608ca0d57c0ea467f208a9645259ff2c879f23958a58c2280ed9e23d`。
- Architect：Codex / `gpt-5.6-sol` / `ultra`。
- Builder、Repo Steward：两个Codex子agent，各`gpt-5.6-sol` / `medium`。
- Packet baseline：`65c279f3dac280f1046c08536f59887b0dc613c7`，接续PR94 draft → integration。
- 验证产物：`artifacts/verification/VPKB-000-capture-contracts/`；本地验收通过，新候选CI待运行。

Architect已完成下述设计待办并经Builder、Steward独立审查，按上述摘要放行实现。
精确字段/API/错误优先级以冻结规范为准；本文件保留设计清单和范围便于追踪。
前一包的667项测试和绿色CI不能当作本包验收。工程契约由Architect设计、复核并冻结，
不需要为每个字段决定单独向用户申请；若涉及产品变更或人工gate则仍由用户决定。

## 目标与依赖

补齐capture inspection和code evidence manifest的纯数据契约，使后续适配器只有一套
字段、身份/哈希绑定及UTF-8行定位规则可消费。依据现有开发计划§4.4、§5.2、VPKB-000，
保持既有canonical身份、JCS、CLI错误envelope、依赖pin及67条目录不变。

本包只在内存校验对象和字节，不读取Vault，不枚举文件，不调用上游，不写staging或source ledger。
真实capture/code-map命令、inspect/apply、无跟随读取、writer lock、并发及运行时source-ID验证留到VPKB-001。
纯validator只能证明输入声明内部一致，不能证明sibling枚举完整、权限隔离或真实文件未改变。

## Architect在下发实现前完成

产出`docs/ai/contracts/capture-contracts-v1.md`，明确以下内容及正反例。
只有内容完成且记录版本/摘要后，才将`contract_status`改为`frozen`并给Builder下发任务。

1. proposal与inspected的字段集合、类型、必填/禁止项及升级关系；所有object关闭未知字段。
2. inspection、manifest、operation、上游plan/bundle之间的hash依赖图和精确JCS材料，排除自引用或循环。
3. no-sibling create与single-matching-sibling reuse分别的目标、`would_change`、operation和plan字段；不伪造执行结果。
4. route、完整sibling snapshot的path/hash/mode语义、文件类型、排序去重、大小边界和拒绝码。
5. UTF-8的BOM、LF/CRLF/裸CR/混合换行、末尾换行、空文件、NUL/控制字符策略，及行范围/snippet hash精确定义。
6. 多logical origin如何保留repo/full commit/path，大小写归一、排序去重和数量上限；不得对代码套用claim的NFKC/空白折叠。
7. source-ID声明与VPKB-001受控上游导入验证的界面：本包不重写上游算法，也不把声明当作已验证来源。

Architect记录的设计决定要与现有common/locator定义一致。若需兼容性变更，单列迁移及fixture影响，
不能由Builder在编码中顺手改变现有接口。

## Builder的实现范围

本次正式允许文件如下，冻结规范进一步限制具体语义：

- 新增`schemas/video-paper-wiki.capture-inspection.v1.schema.json`。
- 新增`schemas/video-paper-wiki.code-evidence-manifest.v1.schema.json`。
- 新增`src/video_paper_wiki/capture_contracts.py`、`code_evidence_contracts.py`，仅纯校验/字节规范化。
- 修改`src/video_paper_wiki/contracts.py`注册及分派；此文件由Builder单写，Architect通过评审修改语义。
- 不改`schemas/video-paper-wiki.common.v1.schema.json`；在新API中做兼容的严格边界校验。
- 新增对应valid/invalid fixtures和专属contract/unit tests，更新schema数量与注册覆盖测试。
- Steward独立测试单写`tests/contract/test_capture_independent.py`；Builder不改此文件。
- Steward记录本包验证结果，不覆盖前一包证据。

Builder不修改CLI实际capture/code-map入口，不添加HTTP/admin调用，不更改目录、retrieval schema、
依赖版本、任务完成判定或人工gate。遇到规范缺口，把问题和最小失败用例交给Architect；先做其他已冻结部分。

## 验收清单

| 条件 | 预期证据 | 当前 |
| --- | --- | --- |
| 两份schema及嵌套对象拒绝未知字段，注册与wheel资源可读 | contract测试、独立wheel验证 | passed-locally；14 schemas |
| PDF无sibling固定`.pdf`，code无sibling固定`.bin`；唯一matching legacy复用 | 纯对象正反fixtures | passed-locally |
| 多/错/symlink/special声明、非法路径、重复snapshot拒绝 | 明确拒绝码和路径定位测试 | passed-locally |
| 每项审批材料变动导致绑定失效，无hash循环 | hash性质及变异测试 | passed-locally |
| raw相同的多origin不会丢失repo/commit/path身份 | 多origin成功与冲突测试 | passed-locally |
| 行规范逐字节可重放，越界/错误snippet hash拒绝 | Unicode/换行/范围边界fixtures | passed-locally；额外1365文本/8116范围复核 |
| 667项既有回归保持，新增用例在3.12/3.13与Linux/macOS通过 | 准确命令、本地与CI结果 | macOS双版本各899 passed；新候选CI pending |
| 不宣称真实no-follow/锁/并发/上游执行或human gate通过 | 独立范围审查 | passed；仍未执行这些运行时验证 |

Architect总审修复了非字符串根对象键和循环hash材料的异常泄漏；由Builder实现、
Steward独立复核。最终本地全量与wheel构建前后257个验证输入文件摘要一致，
snapshot为`4fb11baa15eb303b9fc223b4b49ff93a05d93b53b080ce4f825d5b874eb18752`。
本地结果属于稳定working-tree源码；后续提交需核对同一源码摘要并绑定新的远程CI。

Steward在候选提交稳定后记录packet base、head、PR base、实际tested checkout SHA和CI run/attempt/job。
Architect在同一候选提交上总体审查和验收；新head不能继承旧head的通过结论。
该包通过只关闭capture/code-evidence纯契约子包，不关闭VPKB-000。

## 后续和回滚

后续是统一非持久transaction facade、projection/SQLite契约，以及固定上游源码/fixture验收。
它们不能提前消费仍在设计中的字段。文件和依赖明确独立时可并行准备资料/用例，最终由Architect协调集成。

回滚仅针对本包明确提交和文件，不reset/clean用户工作区，不删除既有inbox、tools或未跟踪计划。
