# 阶段一调研证据

`research/` 保存阶段一形成研究目标与研究合同所需的**结构化、可追溯、非敏感证据**。它回答“检索过什么、采用了哪些来源、哪些最小事实主张得到何种支持，以及研究决策为什么形成”；当前有效合同与全局状态仍只写入根目录 `RESEARCH.md`。

本目录不是资料下载区、网页镜像、论文全文库、聊天记录或临时笔记目录。`RESEARCH.md` 只引用这里的稳定 ID 和必要摘要，不复制搜索流水账或完整证据内容。

## 目录结构

```text
research/
├── README.md
├── search_log.jsonl   # 每行一次实际检索，使用 QRY-<nnn>
├── sources.yaml       # 正式来源元数据，使用 SRC-<nnn>
├── claims.yaml        # 最小事实主张与证据关系，使用 CLM-<nnn>
├── decisions.yaml     # 研究决策与支撑链，使用 DEC-<nnn>
└── summaries/         # 按研究问题生成的精简、可回查摘要
```

模板可以保留空集合；有第一条真实对象时才新增真实条目，不得添加虚构示例。所有 ID 在本项目内唯一，删除或合并对象时不得复用旧 ID。

所有结构化证据都禁止出现 `api_key`、`token`、`password`、`secret`、`cookie`、`credential`、`authorization` 等凭据字段及其常见后缀变体；即使值是占位符也不允许。`full_text`、`raw_content`、`raw_sample`、`personal_data`、`prompt_content`、`response_content` 等全文或敏感载荷字段同样禁止。授权事实只通过 `RESEARCH.md` 的 `AUTH-<nnn>` 摘要与非敏感决策关系表达，不把认证头或访问令牌写入证据层。

验证器对查询、标题、主张、决策、用户输入来源和备注设置保守的文本长度上限，并检查常见邮箱、手机号和身份证号模式，以约束最小披露。这些启发式规则既不能证明内容真实，也不能发现全部个人信息；Codex 在写入前仍需人工语义检查，不得通过拆分字段规避限制。

## `search_log.jsonl`

文件使用 UTF-8 JSON Lines；每个非空行必须是一个完整 JSON 对象，不允许跨行、注释或尾随逗号。一次实际查询对应一行，查询 ID 使用 `QRY-<nnn>`。记录完成后按追加式证据处理；需要修正时追加新的查询记录，并通过可选的 `supersedes_query_id` 指向旧记录，不原地美化历史查询。

必需字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `query_id` | string | 唯一 `QRY-<nnn>` |
| `research_question_ids` | string[] | 对应的 `RQ-<nnn>`；方向探索阶段可为空数组 |
| `query` | string | 实际执行且已脱敏的查询式 |
| `language` | string | 查询语言或语言标签 |
| `platform` | string | 搜索引擎、数据库、站点或工具名称 |
| `searched_at` | string | 带时区的 ISO 8601 检索时间 |
| `filters` | object | 时间、域名及其他实际使用的过滤条件；未使用时保存空对象 |
| `result_count` | integer | 工具返回或人工可见的结果数；不可可靠获得时为 `null` |
| `included_source_ids` | string[] | 本次纳入的 `SRC-<nnn>` |
| `exclusions` | object[] | 被排除结果的非敏感引用及排除原因；没有时为空数组 |
| `counterevidence_search` | boolean | 是否以反证、失败、负面结果或相似工作为目标 |

可选字段：`supersedes_query_id`、`notes`。查询式不得包含个人信息、受限样本、凭据、未获授权的内部标识或可还原敏感内容的长文本。

## `sources.yaml`

文件采用受限、可验证的 YAML 子集：顶层包含 `schema_version: 1` 和 `sources` 列表；列表项为扁平键值，数组使用 JSON 兼容的行内数组。每个正式纳入调研的来源使用 `SRC-<nnn>`。

每个来源必须记录：

- `source_id`：唯一来源 ID。
- `title`：标题。
- `creators`：作者或机构数组。
- `url`：公开、非敏感 URL；没有时为 `null`。
- `doi_or_identifier`：DOI、标准号、报告号或其他稳定标识；没有时为 `null`。
- `published_at`、`accessed_at`：发布日期与访问日期；未知发布日期为 `null`。
- `source_type`：论文、标准、官方数据、技术文档、报告、网页等。
- `provenance_level`：`原始来源` 或 `二手来源`。
- `data_classification`：`公开`、`内部`、`受限`、`个人信息` 或 `混合`。
- `version`、`license`：版本与许可证；未知时明确写 `unknown`，不得猜测。
- `contains_restricted_content`：是否包含受限内容。
- `external_transfer_allowed`：是否允许发送到外部服务；未确认时必须为 `false`。
- `accessibility_status`：`可访问`、`部分可访问`、`不可访问` 或 `待复查`。
- `update_retraction_conflict_status`：`无已知问题`、`存在更新`、`已撤回`、`存在冲突` 或 `待复查`。
- `notes`：必要的精简说明；没有时为 `null`。

至少提供 `url` 或 `doi_or_identifier` 之一。转载和镜像仍需单独登记，但必须在 `notes` 中指向可识别的原始来源，不得作为独立交叉证据重复计数。

## `claims.yaml`

文件顶层包含 `schema_version: 1` 和 `claims` 列表。一个条目只表达一个可以独立核验的最小事实主张，使用 `CLM-<nnn>`。

每个主张必须记录：

- `claim_id`：唯一主张 ID。
- `claim`：最小事实主张，不混合事实、推论与建议。
- `research_question_ids`：相关 `RQ-<nnn>` 数组。
- `source_ids`：支持或反驳该主张的 `SRC-<nnn>` 数组。
- `evidence_locations`：按来源给出页码、章节、表格、行号或锚点；只保存定位信息和最小必要说明。
- `support_level`：`直接支持`、`部分支持`、`间接推论`、`不支持` 或 `来源冲突`。
- `source_independence`：`独立`、`部分独立`、`同源` 或 `待核验`。
- `temporal_status`：`当前有效`、`可能过期`、`已过期` 或 `待核验`。
- `conflict_status`：`无已知冲突`、`存在冲突` 或 `待核验`。
- `verification_status`：`已核验`、`部分核验`、`待核验` 或 `无法核验`。
- `eligible_for_research_contract`：是否允许作为 `RESEARCH.md` 当前合同判断的证据。

只有来源可识别、证据位置可回查且核验状态满足当前研究要求的主张，才可以将 `eligible_for_research_contract` 设为 `true`。模型自报置信度不能替代该字段。

支撑研究合同的关键主张应尽量具有直接来源；只有部分支持或间接推论时必须保留质量警告和局限。`conflict_status: 存在冲突` 的合同主张阻止阶段一门禁，不能通过多数投票或删除不利来源消除。

## `decisions.yaml`

文件顶层包含 `schema_version: 1` 和 `decisions` 列表。只记录会改变研究目标、候选方向选择、范围、数据、baseline、指标、预算、授权或阶段状态的持久决策，使用 `DEC-<nnn>`；措辞调整和普通对话不登记。选定最终方向的决策必须把其他 `DIR-<nnn>` 候选及其否决原因分别写入 `alternatives` 和 `rejection_reasons`，不能只记录获选方案。

每个决策必须记录：

- `decision_id`：唯一决策 ID。
- `decision`：当前决策内容。
- `user_input_source`：用户确认所在的非敏感日期、轮次或摘要引用；不复制完整聊天。
- `supporting_claim_ids`：支撑该决策的 `CLM-<nnn>` 数组；纯偏好或授权决策可为空。
- `alternatives`：实际比较过的替代方案数组。
- `rejection_reasons`：与替代方案对应的精简否决原因数组。
- `user_confirmation_status`：`已确认`、`暂定`、`待确认`、`存在冲突` 或 `不适用`。
- `affected_contract_fields`：受影响的 `RESEARCH.md` 合同字段数组。
- `triggers_phase_rollback`：是否触发阶段回退。
- `decided_at`：决策日期或带时区时间；未确认时为 `null`。

已确认决策不得通过重写历史来改变含义。方向改变时新增决策，并在新条目的可选 `supersedes_decision_id` 中引用被替代决策。

## 允许提交的内容

满足以下全部条件时，可以提交：

- 脱敏后的查询式与过滤条件。
- 公开来源的书目信息、公开 URL、DOI、版本和许可元数据。
- 最小事实主张、证据定位、支持关系与核验状态。
- 不包含受限信息的决策摘要和用户确认引用。
- 基于允许使用来源撰写的精简、原创摘要。

提交前必须检查来源许可、隐私、保密、体积和外部传输边界。结构化元数据可提交不代表相应来源全文可以提交。

## 禁止提交或默认不保存的内容

- API key、令牌、密码、Cookie、完整环境变量或受限下载地址。
- 个人信息、敏感样本、内部查询词、未公开项目代号或可重识别组合。
- 付费墙内容、受版权保护的网页或论文全文、大段逐字摘录、网页镜像和批量下载文件。
- 未经许可的内部报告、受限数据、模型权重、截图、附件或 OCR 全文。
- 完整聊天记录、模型隐藏推理、工具原始响应和命令输出。

确有必要保留的受限材料由用户在本地授权位置管理，不写入本目录；结构化文件只记录不泄露内容的来源 ID、访问状态和限制说明。`.gitignore` 默认排除 `research/private/`、`research/raw/` 与 `research/source_files/`，但忽略规则不是保存授权，Codex 不得自行创建或读取这些目录中的受限内容。

## 阶段完成后的压缩

阶段一结束时执行以下整理：

1. `RESEARCH.md` 只保留当前有效合同、关键决策和 `SRC`/`CLM`/`DEC` 引用。
2. `search_log.jsonl` 保留可复现查询记录，不把返回页面正文复制进来，也不倒改已执行查询。
3. `sources.yaml`、`claims.yaml` 和 `decisions.yaml` 保留所有仍被合同、阶段二任务或后续写作引用的条目；被替代对象标明状态或替代关系，不复用 ID。
4. `summaries/` 只保留按研究问题组织的精简结论、反证、冲突和未决项；删除重复、临时和可由结构化登记重建的摘要。
5. 压缩前检查所有 ID 引用仍可解析；压缩后运行 `uv run python scripts/validate_workspace.py --strict`。

压缩是减少重复叙述，不是删除不利证据、来源冲突、未解决问题或改变已确认决策。
