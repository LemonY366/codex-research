# 通用脚本

`scripts/` 存放跨多个实验可复用的辅助脚本，尤其是数据预处理、数据下载、格式转换、数据检查、环境检查、指标汇总和结果导出等确定性操作。

## 适合放在这里的脚本

- 数据集下载、解压、清洗、切分、去重与格式转换。
- 数据质量检查、统计汇总、校验和生成和许可证信息收集。
- 通用特征构建、缓存生成和预处理结果验证。
- 运行环境、GPU、CUDA 和依赖版本检查。
- 跨实验复用的指标解析、结果汇总、表格导出和复现检查。

例如：

```text
scripts/
├── prepare_dataset.py
├── validate_dataset.py
├── build_splits.py
├── check_environment.py
├── transition_workflow.py
├── manage_task_progress.py
└── export_results.py
```

## 不应放在这里的内容

- 某次具体实验的模型、训练或评测实现：放在 `experiments/scripts/`，并按实验 ID 持久化。
- 某次实际运行的日志、配置快照和指标：放在 `experiments/runs/`。
- 论文数据图生成脚本：放在 `paper/images/scripts/`，并与图像一起保存。
- 可复用的业务/模型源码：放在 `src/`。

## 脚本规范

- 提供 `--help`，并使用显式的输入、输出和配置路径；不要依赖未记录的当前目录或本地状态。
- 尽量做到可重复执行；同样输入应产生相同结果，或明确记录随机种子。
- 输出数据时记录来源、版本、处理参数和校验信息。
- 不要覆盖原始数据；默认将处理结果写入明确的派生数据目录或用户指定的输出路径。
- 缺少输入、配置无效或环境不满足时，清晰报错并返回非零状态码。
- 不得读取 `.env`、打印完整环境变量、输出密钥或在脚本中硬编码凭据。

典型调用方式：

```bash
uv run python scripts/prepare_dataset.py --input datasets/raw --output datasets/processed
```

## 工作区边界验证

`validate_workspace.py` 是模板预置的只读检查工具，用于交叉检查机器状态、转换账本和 `RESEARCH.md` 投影，并检查渐进式需求获取、Codex 主导头脑风暴与用户结束发散、候选方向数量与唯一最终方向、合同字段确认依据、数据证据成熟度、恢复摘要、稳定 ID、研究问题一致性关系、阶段二任务回指，以及 `research/` 证据。阶段一没有固定资源配额或研究周期。工具还检查阶段 TODO、registry 与本地运行对账、运行可复现字段、阶段二/三任务进度与心跳、证据交接和论文实验 ID 追溯；它不启动 Codex、不读取 `.env`、不创建或修复文件，也不替代来源真实性和科研有效性判断。

```bash
uv run python scripts/validate_workspace.py
uv run python scripts/validate_workspace.py --strict
python3 -m unittest discover -s tests -v
```

常规模式在发现错误时返回非零状态；`--strict` 也将警告视为失败。`tests/` 使用 Python 标准库 `unittest` 覆盖阶段一合同、头脑风暴、连续切换、门禁、搜索覆盖、来源质量、引用与冲突、资源计量、安全、迁移及临时工作区端到端演练；合成证据不会写入正式 `research/`。质量预警、个人信息模式和凭据检查是启发式检查，不能代替科研合理性评审、来源事实核验、人工隐私审查或专用密钥扫描器。运行证据的覆盖检查可识别 Git 已跟踪文件的改写；默认忽略、未建立外部校验基线的本地运行无法仅凭当前文件状态证明从未被修改。

## 工作流与进度工具

`transition_workflow.py` 是阶段和阶段一子状态的唯一写入入口。它先运行当前及目标状态门禁，再用锁、事务日志和原子替换同步机器状态、转换账本及 `RESEARCH.md` 投影；校验失败时不改变状态。

`manage_task_progress.py` 创建、更新、查看和归档阶段二/三任务的结构化进度。实验任务写入 `workflow/tasks/`，写作会话写入 `paper/sessions/`；`list --stage stage_two|stage_three` 供 Codex 周期轮询。该工具不读取或改写两个阶段的 `TODO.md`，TODO 继续按原有任务管理方式维护。两个工具均只使用 Python 标准库。

进度更新的 `--input-tokens`、`--output-tokens`、`--total-tokens` 用于 Codex 任务/阶段三写作会话，`--api-input-tokens`、`--api-output-tokens`、`--api-total-tokens` 专用于阶段二实验外部 API。输入和输出均存在时工具自动计算并核对 total；不可获得时用 `--token-unavailable FIELD:REASON` 记录原因。

`manage_task_progress.py token-summary --stage phase_one|stage_two|stage_three|all` 汇总 token：阶段一读取当前资源快照，阶段二只累计 `api_*`，阶段三只累计写作会话字段。输出同时列出缺失计数的任务 ID，避免把部分合计误报为完整总量。
