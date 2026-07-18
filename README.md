# Codex 科研工作台

这是一个面向 Codex 的可复现科研项目模板。项目将研究任务、论文源码、实验实现、实际运行证据和论文写作分离保存，使工作可在对话中断后继续，并让论文结论可追溯到具体实现与运行结果。

## 快速开始

```bash
uv sync
```

如需访问外部服务，可复制 `.env.example` 为 `.env` 并填写本地值。`.env` 不应被读取、输出或提交；数据集、模型和运行产物的存放规则见对应目录的 README。

## 工作流程

1. 在 [RESEARCH.md](RESEARCH.md) 定义研究目标、问题、指标、预算和范围。
2. 在 `src/` 实现论文方法与可复用训练/评测代码。
3. 为每个实验在 `experiments/scripts/` 保存一个可直接运行的脚本。
4. 每次实际执行均在 `experiments/runs/` 创建独立目录，保存命令、配置快照、日志、元数据和指标。
5. 在 [paper/draft_zh.md](paper/draft_zh.md) 起草和修订论文；只有用户明确要求时才同步到 `paper/main.tex`。

数值、表格和实证性结论必须可追溯到相应实验 ID 与运行目录；不可核实的信息标记为 `TODO`。

## 目录说明

```text
README.md            # 项目入口与使用说明
AGENTS.md            # Codex 的长期工作规则
RESEARCH.md          # 全局唯一的研究任务合同
TODO.md              # 当前待办事项
datasets/            # 数据集与来源说明
models/              # 模型检查点与版本说明
baselines/           # 外部对比方法源码与版本登记
src/                 # 论文方法、训练和评测源码
scripts/             # 数据预处理等跨实验通用脚本
experiments/         # 实验脚本、运行记录与索引
paper/               # 草稿、正式论文、引用与图像
docs/                # 稳定、跨阶段的项目规范
```

进入某个目录前，优先阅读该目录的 `README.md`。在仓库根目录启动 Codex 时，它应遵循 [AGENTS.md](AGENTS.md)。

## 文档维护

每次变更仓库内容时，都应同步检查根目录 `README.md` 和 `AGENTS.md` 是否仍准确反映项目结构、使用方式、边界与维护约定。仅影响某个子目录的变更，应先更新该目录的说明文档；如果同时影响根目录使用方式或 Codex 工作流，再更新根目录文档。详细的 agent 侧约束以 `AGENTS.md` 的 `Documentation Update Policy` 为准。
