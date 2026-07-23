# 实验目录

`experiments/` 存放与实验设计、执行和追溯直接相关的文件。它的目标是让每一项实验都能定位到对应的实现、配置、运行记录与结果，而不依赖聊天历史或临时终端命令。

启动任何实质性实验前，必须通过 [三阶段工作流门禁](../docs/WORKFLOW_GATES.md) 的阶段二进入检查。实验因资源、凭据、付费/外发授权、数据、隐私、许可证或指标错误停止时，保留失败证据，在根目录 `RESEARCH.md` 记录全局停止状态，并在本目录 `TODO.md` 记录受影响任务。

## 目录结构

```text
experiments/
├── README.md          # 本目录说明
├── TODO.md            # 阶段二实验与分析任务
├── registry.yaml      # 实验与运行的索引（如启用）
├── evidence_handoff.yaml # 阶段二完成时生成的证据交接（如启用）
├── scripts/           # 每次实验对应的可执行实现脚本
└── runs/              # 每次实际运行生成的独立记录
```

## 职责边界

- `TODO.md` 只保存实验级的当前任务、下一步、阻塞项和精简完成摘要，不保存命令输出、指标明细、调试流水账或实时心跳。它继续由 Codex 按原有任务管理节点维护，进度工具不得自动改写。每个真实实验任务必须引用 `RESEARCH.md` 中已确认的 `RQ-<nnn>` 与 `SC-<nnn>`，使阶段二执行可以回溯到研究问题和成功标准。
- `scripts/` 保存实验实现。每次运行必须使用或明确引用一个可直接执行的脚本；详见 `scripts/README.md`。
- `runs/` 保存实际运行产物，例如命令、配置快照、日志、指标、检查点位置和失败原因；详见 `runs/README.md`。
- `registry.yaml` 在首次确认具体实验时由 Codex 创建；没有实际实验时不创建空登记表或虚假示例。每个条目至少记录 `experiment_id`、`status`、`script`、`runs`、`research_question_ids`、`success_criterion_ids` 和 `decision_ids`；这些引用必须指向当前已确认研究合同，不要将原始日志、密钥或大型模型文件放入其中。
- `evidence_handoff.yaml` 只在阶段二准备完成时创建，使用 `schema_version: 1`、`handoffs:` 和唯一 `HANDOFF-<nnn>` 条目。条目必须使用 JSON 标量/数组并记录 `research_question_ids`、`success_criterion_ids`、`experiment_ids`、`run_ids`、`supported_claims`、`unsupported_claims`、`negative_results`、`limitations`、`local_evidence_verified`、`registry_reconciled` 与 `completed_at`。它是阶段三入口材料，不得用不存在的远端目录或聊天中的数值代替本地运行证据。

`registry.yaml` 与 `runs/` 必须双向一致：登记的 run ID 必须存在且属于相同实验，本地存在的每个运行也必须被登记；`planned` 条目不得已有运行，`completed` 条目至少包含一个本地 `success` 运行。状态变化时更新索引，不回写历史运行目录。

不属于本目录的内容包括：全局研究目标、阶段状态和阶段一任务应写在根目录 `RESEARCH.md`，论文写作任务应写在 `paper/TODO.md`，通用可复用代码应放在 `src/`，通用辅助脚本应放在 `scripts/`，论文正文与产物应放在 `paper/`。

## 最低可追溯信息

每次实验至少应能回答以下问题：使用了哪个实验 ID、回答哪个研究问题、验证哪个成功标准、依据哪个研究决策、使用哪个脚本和配置、什么数据与模型版本、哪个随机种子、如何运行、产出了哪些指标，以及结果是否成功。任何无法回答这些问题的运行都不应作为论文结论的依据。研究范围变化时先回退阶段一并更新相应 `RQ` 与 `DEC`，不得让 registry 静默指向已失效合同。

## 可见进度

每个下载、生成、训练或评测长任务在执行前使用 `scripts/manage_task_progress.py` 创建 `../workflow/tasks/<task-run-id>/`。实验脚本按实际 sample、epoch、step 或 seed 更新完成数、资源消耗和检查点，并至少每 30 秒刷新心跳；Codex 通过 `list --stage stage_two` 轮询并每 30–60 秒向用户报告。任务结束后将三个进度文件归档到对应不可变 run 目录。

这些实时写入不投影到 `TODO.md`。只有任务规划改变、任务形成持久状态、出现需要记录的阻塞或任务完成交接时，Codex 才按原有格式维护 `TODO.md`。

阶段二外部模型 API token 使用任务状态中的 `api_input_tokens`、`api_output_tokens` 和 `api_total_tokens`，并在成功运行的 `metrics.json.api` 中保存对应输入、输出和合计值。通用的 `input_tokens`/`output_tokens` 属于 Codex 任务会话计量，不得当作实验 API 消耗。
