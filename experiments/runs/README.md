# 实验运行结果

`experiments/runs/` 存放每次**实际执行**实验后生成的运行结果。每次运行都应拥有独立目录，作为该次结果的不可变证据；不要将不同运行的日志、配置或指标混在一起。

## 目录结构

推荐按运行 ID 创建目录：

```text
experiments/runs/
└── run-20260718-001-baseline/
    ├── command.txt            # 实际执行的完整命令
    ├── config_snapshot.json   # 本次使用的配置快照
    ├── script_path.txt        # 所用 experiments/scripts/ 脚本路径
    ├── environment.json       # Python、PyTorch、CUDA、GPU 等环境信息
    ├── metrics.json           # 机器可读的最终指标
    ├── run.log                # 标准输出与错误日志（已脱敏）
    ├── metadata.json          # 数据/模型版本、种子、Git 提交、状态等
    └── artifacts/             # 本次生成的图表、预测或小型检查点
```

文件并非必须全部存在，但每个成功运行至少应保留命令、配置快照、最终指标和元数据；失败运行也应保留日志与失败原因。

## API 与 GPU 资源记录

使用 API、GPU 或二者联合的实验，必须在 `metadata.json` 中分别记录两类资源是否启用、实际用途和可复现版本信息。未使用的资源也应保留 `enabled: false`，不要通过缺少字段表示。字段值在运行时动态采集，不要把示例中的占位值写死在模板或实验代码中。

```json
{
  "experiment_id": "exp-001",
  "status": "success",
  "resources": {
    "gpu": {
      "enabled": true,
      "device": "<runtime-detected GPU model>",
      "framework": "PyTorch",
      "purpose": "<purpose confirmed in RESEARCH.md>",
      "local_model": "<local model or checkpoint version>"
    },
    "api": {
      "enabled": true,
      "protocol": "openai-compatible",
      "model": "<non-secret model name configured by LLM_MODEL>",
      "purpose": "<purpose confirmed in RESEARCH.md>",
      "key_environment_variable": "LLM_API_KEY"
    },
    "data_flow": "<ordered API/GPU inputs, outputs, and interactions>"
  }
}
```

可以记录凭据所用的环境变量名称，但不得将真实值保存到任何运行文件。例如，下列内容严禁出现：

```json
{
  "api_key": "sk-xxxx"
}
```

`metrics.json` 应按实验实际使用的资源记录可用的消耗与性能指标，并明确数值单位和统计口径：

- API：请求总数、成功数、失败数、输入 token、输出 token、总耗时、估算费用及币种、限流次数和重试次数。
- GPU：GPU 型号、CUDA 版本、PyTorch 版本、峰值显存、GPU 运行时间、训练步数和吞吐量。

指标不适用或无法安全、可靠采集时，应显式标记为 `null` 或说明未记录原因，不得伪造数值。

## 写入规则

- 运行开始前创建新目录；不得复用或覆盖既有运行目录。
- 仅将本次运行产生的结果写入该目录。
- 指标应同时保存为机器可读格式（优先 JSON）和必要的可读摘要。
- 日志必须脱敏，禁止写入 API 密钥、令牌、密码、完整环境变量或敏感样本。
- 大型数据集、原始模型权重和可重新下载的依赖不应提交到此目录；在元数据中记录其来源、版本和校验信息即可。
- 运行结束后不要手动改写指标或配置快照。若需要重跑或修复，应创建新的运行目录。
- API 或 GPU 在预检、执行或收尾阶段失败时，保留已产生的脱敏日志和产物，将运行状态记为失败并写明原因；只完成部分流程不得标记为成功。

## 与其他目录的关系

- 实验实现脚本位于 `experiments/scripts/`。
- 通用源码和工具分别位于 `src/` 与 `scripts/`。
- 被确认用于分析或论文的结果可由脚本从本目录读取，或在 `paper/` 中引用；无论采用何种方式，都必须保留对本运行目录及实验 ID 的追溯。

只有具备足够运行证据的目录，才能支撑 `registry.yaml` 中的成功状态和论文中的实证性结论。
