# 事务式工作流与任务可观测性

`workflow/` 保存机器可读的全局工作流状态和追加式转换历史。研究合同仍在根 `RESEARCH.md`，但其顶部阶段、阶段一子状态、阶段状态和门禁结果是 `state.json` 的用户可读投影，不允许手工单独推进。

## 状态文件

`state.json` 使用 schema version 1，包含 `revision`、`current_phase`、`phase_one_substate`、`phase_status`、`gate_result`、`last_transition_id` 和 `updated_at`。初始模板 revision 为 0，尚无真实转换。

`transitions.jsonl` 每行是一个 JSON 对象，至少包含：

- `transition_id`、`revision` 和 `occurred_at`；
- `from_node`、`to_node`、`from_phase`、`to_phase`；
- `reason`、`decision_ids`、`authorization_ids`；
- `gate_result` 和严格校验摘要。

记录追加后不得原地修改。回退也创建新记录。

## 唯一转换入口

工作流转换只通过：

```bash
uv run python scripts/transition_workflow.py --to DIVERGE --reason "用户提供研究种子"
```

工具先核对 `state.json`、`RESEARCH.md` 投影和转换链，再按目标状态执行门禁。任何错误或警告都会拒绝推进，不写入半完成状态。写入时使用锁、事务日志、临时文件和原子替换；若上次进程在提交中断，下一次调用先恢复到一致状态。

`RESEARCH.md` 的研究合同正文仍由 Codex 维护；只有顶部机器状态和阶段切换表由事务工具更新。

## 阶段二与阶段三任务状态

阶段二实验和阶段三写作共用 `src/runtime/progress.py`。活动任务在 `workflow/tasks/<task-run-id>/` 保存：

- `status.json`：当前步骤、完成量、资源用量、阻塞和恢复条件；
- `events.jsonl`：追加式进度、检查点、警告和错误；
- `heartbeat.json`：最近心跳。

阶段二最终状态快照应复制到对应 `experiments/runs/<run-id>/`；阶段三最终状态、主张/引用检查与输出 manifest 应进入 `paper/sessions/<session-id>/`。活动任务默认是本地运行状态，不作为论文证据。

运行中的脚本至少每 30 秒更新心跳。Codex 应每 30–60 秒轮询并向用户报告实验/章节、seed 或写作步骤、完成量、资源消耗、最近心跳、已保存检查点和阻塞原因。百分比必须来自明确的完成数与总数，不能按生成字数猜测。

实时进度系统不得自动改写 `experiments/TODO.md` 或 `paper/TODO.md`。两个 TODO 文件继续按原有方式由 Codex 在任务规划、正式状态变化、阻塞处理和完成交接时维护；每次心跳、step、sample、epoch 或百分比变化只写上述实时状态文件。TODO 与实时状态关注不同层级，不要求逐事件逐字段相同。
