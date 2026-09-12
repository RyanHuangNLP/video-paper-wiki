# T3 R4：最后发布步骤的实时校验顺序

本修复由 Astra 在原合同 C、原九路径内批准。R3 handoff/ready SHA d6424b577f3d375adc12e4aab16781fd9cff25a9bf60943c260720627b4a3087 及所有旧证据保持原样。

R3 原八个探针已经通过，但新 publication_edge_probe.py 复现剩余发布顺序缺口：_publish_session 在创建 inner session 目录、搬运三份文件、调用 before-publish hook 之前检查 live context。因此实际最后一个 staged 文件移动或 before-publish hook 时编辑 source.md，依然返回 OK/state=stale 并留下一个新 session。control 正常 awaiting_model。

源模块 SHA 73bc3982273189f739481473d786fea8499c626be9bf380c9b9178326cd729d0，具体证据为同目录 publication-edge-results.json。不是重新打开已关闭的旧错误，而是同一“完成 staging 后、实际安装前核验”约束仍有操作窗口。

只修复 light_workflow.py 及原自有测试中的相关回归。保持所有 staging 组装/文件移动/测试 hook 完成后，在实际发布 rename 前核验 live context。此时源失效须返回 ok=false/INDEX_STALE、session_id=null，不产生新 session；保留所有已有 session、源文件和未知材料，只清理本次能够证明归属的临时文件。成功、重复请求复用和既有中断恢复语义不变。不要更改接口、T1/T2 输入、其他人的代码或 Skill。

增加覆盖最后实际文件搬运和 before-publish hook 两个窗口的有效回归，断言新 session 数为零并保持旧/未知数据。重新跑三项自有测试、受影响的真实后端组合及原八探针；复制 probe 后运行，不能覆盖 Architect 原观察。不要重复全产品、wheel 或真实 PDF。

在全新 r4 中冻结全部九个自有文件，十个 T1 r3/T2 r4 导入文件保持原 SHA，绑定新测试日志和本任务 SHA，发布实际完整的 handoff/ready 并停写。允许就本缺口自行修复自测失败，不扩大范围，不执行 Git/PR。测试通过只表明候选 ready，由 Astra 验收。
