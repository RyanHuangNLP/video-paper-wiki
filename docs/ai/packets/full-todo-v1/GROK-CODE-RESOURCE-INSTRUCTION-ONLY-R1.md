请直接完成下面这项 Python 修复，返回可使用的代码。不要只给建议。
本次只提供这段任务说明，不提供项目文件、代码包或测试资料。不要读取任何
本地文件，不要调用工具、shell、网络搜索或子代理，也不要声称已经运行测试。

任务是修复一个 JSON Schema 生成器及其 pytest 契约测试。协调者会在本地把
你返回的代码放入现有文件，审查后再运行；你不用操作文件。

生成器的四个问题：

1. 仓库标识是 owner/name。两个组件各为 1–100 个 ASCII 字母、数字、点、
   下划线或连字符；允许首尾标点，禁止组件恰好是 . 或 ..，仓库名还禁止
   不区分大小写的 .git 后缀。普通输入允许大小写，保存后仅允许小写。
   同一段正则还会被嵌入 commit/blob/raw URL，后面紧接斜杠，因此排除条件
   必须针对组件结束位置，不能只看整个字符串结尾，也不能跨斜杠检查后缀。
   请给出替换用的四个 Python 原始字符串常量赋值：_OWNER_INPUT、_NAME_INPUT、
   _OWNER_SAVED、_NAME_SAVED。现有代码会把 owner 和 name 用 / 拼接并加上
   整体开头/结尾锚点，再生成三种 URL；不要重写其他路径语法。
2. JSON Pointer 最长应为 16416 个字符：32 层，每层一个 256 字节的全斜杠
   键被转义为 512 个字符，再加一个路径分隔符。原转义语法保持不变。
3. 源文件最多 262144 字节，单行末尾标量的一基、右开 column_end 可达
   262145。只修正 column_end 上界，不扩大其他字节或坐标上界。
4. 输入目录是 .work/ 开头的相对路径，至少一个非空组件，总长最多 4096。
   最短 .work/a 合法。目录组件允许 Unicode、空格、点、下划线、连字符、
   .git，以及超过 128 字符的名称；不得套用输出 batch-id 的语法。
   禁止组件恰好为 . 或 ..、空组件、重复/末尾斜杠、反斜杠、C0/C1、DEL、
   U+2028/U+2029。给出 _CHECKOUT_REL 的替换赋值，不加整体锚点，现有包装器
   会加锚点。NFC、真实文件身份和字节大小由后续语义检查负责。

请在第一块 Python 代码中给出上述五个常量赋值，并明确列出三个数值替换点：
json_pointer 的 max_length=16416，span.column_end 的 maximum=262145，
bundle_directory 的 min_length=7。这些是不同的指定位置，不能全局替换数字。

测试模块已有 copy、pytest、Any、Iterator，以及以下工具和 fixtures；不需要
读取它的源文件。这些接口说明足以写出替换函数和新增测试：

- fixture_bundle 是 {schema, profile_sha256, cases}，每个 case 为
  {name, title, instance}。实际用例覆盖所有正常分支，但不能依赖顺序或名字。
- validators_by_title 是 title 到严格 JSON Schema validator 的字典。
- registry 是只含十个 schema、拒绝外部解析的 registry。
- _validate(validators_by_title, title, instance) 成功返回 None，失败抛异常。
- _is_valid(validators_by_title, title, instance) 返回布尔值。
- _validate_def(registry, def_name, instance)、_def_is_valid(registry, def_name,
  instance) 对 common schema 中的指定定义做同样检查。
- _walk(instance) 产生 (JSON-Pointer 字符串, 节点)，根路径为空；
  _resolve_pointer(instance, '#'+pointer) 返回该容器。
- _set_path(instance, tuple_path, new_value) 按字典键和列表下标修改值。
- _load_json(_fixture_path()) 返回 (原始字节, fixture_bundle 字典)。
- IntSubclass 是已有的 int 子类，用来确认严格整数检查拒绝 int 子类。

请返回第二块完整 Python 代码，包含：

A. fixture_bundle 的替换定义，保留 @pytest.fixture(scope='session')，接收
   validators_by_title，在返回 bundle 前先验证所有正例。单独运行一个负例
   测试时也必须先验证其正例来源。
B. test_unknown_and_missing_fields(fixture_bundle, validators_by_title) 的
   替换定义：对所有字典节点测试未知字段和删除必填字段，不用仅按 title/
   pointer 去重而漏掉不同分支。唯一允许删除后仍合法的字段是 title 为
   video-paper-wiki.code-proof-request-input.v1 的根 limits。
C. 一个保留真实字典键/列表下标类型的遍历 helper，以及
   test_strict_integers_in_instances(fixture_bundle, validators_by_title) 的
   替换定义。将每个 type(value) is int 的值分别改为 bool、浮点和 IntSubclass
   并确认不合法。加入 {'0': [1]} 这种数字字典键的 helper 回归测试；该对象
   只是 helper 的测试，不是公共 wire 文档。
D. 上面四项修复的正负边界测试，用 _validate_def/_def_is_valid。
   common 定义名为 repository_input、repository_saved、github_commit_url、
   github_blob_url、github_raw_url、json_pointer、span、bundle_directory。
   URL 分别是 https://github.com/owner/repo/commit/<40位小写hex>、
   https://github.com/owner/repo/blob/<同oid>/config.json、
   https://raw.githubusercontent.com/owner/repo/<同oid>/config.json。
   保留合法首尾标点和大小写规则，覆盖嵌入 URL 后的 .、..、.git 排除。
   span 是闭合对象，字段为 byte_start、byte_end、codepoint_start、
   codepoint_end、line_start、column_start、line_end、column_end、raw_sha256、
   snippet_sha256；两个 hash 为64位小写hex。验证合法最大 column_end 后，
   仅将它改为262146。Pointer 验证16416与16417。目录边界包含上述字符规则。
E. 定向的一字段畸形测试，每次从已验证的正例开始：
   - 保存文档 title 为 video-paper-wiki.code-config-evidence.v1；instance.data
     的 format=json/toml 时 result 是字典、source_only_reason 为 null。
     仅把 result 改为 null 必须拒绝；另一次仅把 reason 改为
     explicit_source_only 也必须拒绝，不要在一个负例同时改两个字段。
   - CONFIG result.nodes 的每个节点含 declarations 数组，声明只有 kind 和
     span，kind 为 json_key/toml_key/toml_table。覆盖声明 kind 和 span 畸形；
     没有 declaration.path 字段，不要假定其存在。
   - 原始观察 title 为 video-paper-wiki.code-proof-observation.v1，data.mode
     为 git_objects，data.git_proof.targets 是 Git kernel 目标列表。
     目标含 path、outcome、reason、walk、stopped_at、blob。
     permitted_regular_blob 分支 reason=null、blob 为对象；missing 分支
     reason=absent_entry、blob=null；unsafe 分支 blob=null，reason 可为
     symlink。walk 元素字段为 tree_oid、name_hex、mode、oid，mode 使用
     40000/100644/100755/120000/160000。覆盖 outcome、reason 和 walk 字段。
     fixture 没有 unsafe 目标，可从合法目标构造 schema-only unsafe 正例，
     先用 common 的 git_target 定义验证，再逐字段变坏；不声称语义来源有效。
   - 保存文档根 id 形如 ce1:<kind>:<64位小写hex>，引用对象含 id、sha256。
     覆盖非hex和长度错误，保留语法正确但语义哈希错误仍可通过 schema 的区别。

说明一个额外的局部删除点：现有 test_impossible_nulls 在 typed result=None
后又设置 source_only_reason='explicit_source_only'，协调者应删除第二个赋值，
保留其他已有检查。不要要求替换整个旧函数。

请只输出这两块完整代码、三个数值替换点和这个局部删除说明。最后简短说明
“未运行测试”。不需要哈希清单、传输清单、审批文档、项目探索或进一步提问。
